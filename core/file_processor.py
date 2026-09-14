# core/file_processor.py
"""
============================================================
Convert Pro 3 – FileProcessor Core Principles (LOCKED)
============================================================

[원칙 1] 변환의 정의
- 변환이란 "원본 데이터를 가공하여 Convert 파일을 생성/추가하는 행위"이다.
- 시간 중복, 정렬, 누락 보정, 데이터 이상 여부는 변환의 본질이 아니다.
- 원본에 존재하는 유효한 모든 행은 기본적으로 변환 대상이다.

[원칙 2] 증분 변환 방식
- 최초 변환 시: 원본의 모든 유효 행을 변환하여 파일을 생성한다.
- 이후 변환 시: 변환본의 마지막 timestamp 이후 행만 변환하여
  기존 변환본 뒤에 그대로 append 한다.
- 기존 변환본의 중간 행이 삭제되었더라도,
  마지막 timestamp 기준만을 신뢰한다.

[원칙 3] 헤더 및 컬럼 정책
- 원본 CSV의 헤더 유무는 신경 쓰지 않는다 (header=None).
- timestamp는 항상 0열이며, 파싱 불가/연도 < 2000 데이터는 무시한다.
- 변환본 컬럼 구조는 항상 24개 컬럼으로 고정한다.
- 최초 생성 시에만 STANDARD_HEADER를 기록하고,
  이후 append 시에는 헤더를 절대 다시 쓰지 않는다.

[원칙 4] Battery 처리 규칙
- 원본 batLevel을 찾아 변환본 3열(battery)에 넣는다.
  후보: 컬럼명 / 0행 헤더명 / 고정 인덱스 56. 숫자(0~105%) 품질로 고른다 (utils.battery).
- 실패(열 없음·파싱 불가)와 실제 0%는 구분한다 (추출은 NaN, UI는 "—").
- 24열 이후 원본 컬럼은 변환 과정에서 제거한다.
- Battery는 UI 및 변환본 확인을 위한 핵심 값이다.

[원칙 5] 안정성 우선
- 변환 파이프라인은 “멈추지 않는 것”이 최우선이다.
- 일부 행에 문자열/JSON/이상값이 있어도 전체 변환은 계속되어야 한다.
- 예외 처리는 ‘스킵’이지 ‘중단’이 아니다.
- 고급 기능(fill_interval, 중복제거, 정렬 등)은 이후 단계에서 추가한다.

※ 이 원칙은 리팩터링·기능 추가 시에도 절대 변경하지 않는다.
============================================================
"""

import os
import time
import pandas as pd
from datetime import datetime, timedelta
from io import StringIO

STANDARD_HEADER = [
    "timestamp",
    "deviceId",
    "STX",
    "battery",
    "ProtocolVersion",
    "lineNumber",
    "intervalTimeSet",
    "amplifierX",
    "amplifierY",
    "amplifierZ",
    "frequencyX",
    "frequencyY",
    "frequencyZ",
    "degreeXAmount",
    "degreeYAmount",
    "degreeZAmount",
    "AmountCH0",
    "AmountCH1",
    "AmountCH2",
    "AmountCH3",
    "AmountCH4",
    "AmountCH5",
    "AmountCH6",
    "AmountCH7",
]

class FileProcessor:
    """
    Convert Pro 3 - 증분 변환 파이프라인
    - 최초 변환: 원본 전체 변환
    - 이후 변환: 마지막 timestamp 이후 행만 append
    """
    
    def __init__(self, config, tree, sensor, fill_interval, logger, convert_root=None):
        self.config = config
        self.tree = tree
        self.sensor = sensor
        self.fill_interval = fill_interval
        self.logger = logger
        self.convert_root = convert_root or r"C:\data\Convertfile"

    def convert_all(self):
        """전체 파일 변환 (UI/Scheduler 호출) - Site 레벨 포함"""
        self.logger.log("전체 파일 변환 시작", level="DEBUG")

        for company, sites in self.config.data.items():
            if company.startswith("__"):
                continue

            for site_name, site_data in sites.items():
                if site_name.startswith("__") or not isinstance(site_data, dict):
                    continue

                for folder, folder_cfg in site_data.items():
                    if folder.startswith("__") or not isinstance(folder_cfg, dict):
                        continue
                    for filename in folder_cfg:
                        if not filename.startswith("__") and filename.lower().endswith(".csv"):
                            self.convert_file(company, site_name, folder, filename)

        self.logger.log("전체 파일 변환 종료", level="DEBUG")

    def convert_file(self, company, site, folder, filename, stop_check=None):
        """
        파일 단위 변환 (Site 레벨 포함, 재시도 로직 포함)
        
        Returns:
            str: "converted", "fill", "skipped", "error"
        """
        max_retries = 3
        retry_delay = 1  # 초
        
        for attempt in range(max_retries):
            if stop_check and stop_check():
                return "skipped"
            try:
                return self._convert_file_internal(company, site, folder, filename)
            
            except PermissionError as e:
                if stop_check and stop_check():
                    return "skipped"
                if attempt < max_retries - 1:
                    self.logger.log(
                        f"파일 점유 중... 재시도 {attempt + 1}/{max_retries} "
                        f"({company}/{site}/{folder}/{filename})",
                        level="DEBUG"
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 지수 백오프
                else:
                    self.logger.log(
                        f"건너뜀(파일 점유): {company}/{site}/{folder}/{filename}",
                        level="WARN"
                    )
                    return "error"
            
            except Exception as e:
                self.logger.log(
                    f"변환 오류: {company}/{site}/{folder}/{filename} - {e}",
                    level="ERROR"
                )
                return "error"
        
        return "error"
    
    def _convert_file_internal(self, company, site, folder, filename):
        """파일 변환 내부 로직"""
        self.logger.log(f"파일 변환 시작: {company}/{site}/{folder}/{filename}", level="DEBUG")

        folder_cfg = self.config.data[company][site][folder]
        file_cfg = self.config.data.get(company, {}).get(site, {}).get(folder, {}).get(filename, {})

        if file_cfg.get("__nb_mode__"):
            return self._convert_neo_blast_file(company, site, folder, filename, folder_cfg, file_cfg)

        src_path = os.path.join(folder_cfg["__absolute_path__"], filename)

        if not os.path.exists(src_path):
            self.logger.log(f"원본 없음 → 스킵: {company}/{site}/{folder}/{filename}", level="DEBUG")
            return "skipped"

        # ⚙ 변환본 경로: {convert_root}/{company}/{folder}/{filename} (로거 폴더)
        from utils.convert_paths import prepare_convert_out_path

        out_path = prepare_convert_out_path(
            self.convert_root, company, site, folder, filename, logger=self.logger
        )

        self.logger.log(f"📂 변환본 경로: {out_path}", level="DEBUG")

        interval = file_cfg.get("__fill_interval__", 0)
        interval_int = int(interval) if interval else 0
        extend_to_now = bool(file_cfg.get("__fill_extend_to_now__", False))
        align_60 = bool(file_cfg.get("__align_60__", False))

        out_exists = os.path.exists(out_path)
        try:
            mtime_unchanged = (
                out_exists
                and os.path.getmtime(src_path) <= os.path.getmtime(out_path)
            )
        except OSError:
            mtime_unchanged = False

        # ── Fast path A: 채움 없음 + 원본 mtime 미변경 → 즉시 스킵 ──
        # (__align_60__: 10분 변환본은 그대로 두고 _60.csv만 동기화할 수 있음)
        if mtime_unchanged and not interval_int and not extend_to_now:
            if align_60 and out_exists:
                if self._sync_align60_from_main(
                    company, site, folder, filename, out_path
                ):
                    return "converted"
            self.logger.log(
                f"원본 미변경 → 스킵: {company}/{site}/{folder}/{filename}",
                level="DEBUG",
            )
            return "skipped"

        # ── Fast path B: 누락보충 ON + mtime 미변경 ──
        # 원본 전체 scan / 센서 파이프라인 생략. peek로 내용만 확인 후
        # 필요하면 슬롯 채움만 수행.
        if mtime_unchanged and interval_int > 0:
            from utils.csv_last_row import peek_last_timestamp
            from core.fill_interval_processor import _slot_ts

            base_time, last_row = self._get_last_converted_data(out_path)
            src_last = peek_last_timestamp(src_path)

            # peek상 원본이 base_time 보다 새면 mtime 오판 → 전체 경로로 진행
            need_full = (
                src_last is not None
                and base_time is not None
                and pd.notna(src_last)
                and src_last > pd.Timestamp(base_time)
            )
            if not need_full and last_row and base_time is not None:
                _now = datetime.now()
                bt_slot = _slot_ts(base_time, interval_int)
                now_slot = _slot_ts(_now, interval_int)
                if bt_slot is not None and now_slot is not None and bt_slot >= now_slot:
                    self.logger.log(
                        f"누락보충: 현재 슬롯까지 이미 있음 → 스킵 "
                        f"({company}/{site}/{folder}/{filename})",
                        level="DEBUG",
                    )
                    return "skipped"
                try:
                    row_vals = [
                        last_row.get(h, 0.0 if h != "timestamp" else str(base_time))
                        for h in STANDARD_HEADER
                    ]
                    last_df = pd.DataFrame([row_vals], columns=range(len(STANDARD_HEADER)))
                    _max_fill = max(24, int(60 / interval_int * 24 * 7))
                    tail_df = self.fill_interval.fill_from_last_to_now(
                        last_df, base_time, interval_int,
                        current_time_limit=_now, max_rows=_max_fill,
                    )
                    if not tail_df.empty:
                        if "__filled__" in tail_df.columns:
                            tail_df = tail_df.drop(columns=["__filled__"])
                        tail_df.columns = range(tail_df.shape[1])
                        self._save_append(tail_df, out_path, interval_min=0)
                        if align_60:
                            self._sync_align60_from_main(
                                company, site, folder, filename, out_path, force=True
                            )
                        self.logger.log(
                            f"누락보충: {company}/{site}/{folder}/{filename} "
                            f"(+{len(tail_df)}행)",
                            level="INFO",
                        )
                        return "fill"
                    return "skipped"
                except Exception as e:
                    self.logger.log(
                        f"⚠️ 고속 누락보충 실패 → 전체 경로: {e}", level="WARN"
                    )
            # need_full 이거나 last_row 없음 → 아래 전체 경로

        # 1단계: 마지막 변환 시점 확인 + 마지막 행 데이터 추출
        base_time, last_row = self._get_last_converted_data(out_path)

        # 2단계: 변환 대상 행 수집 (base_time 이후 데이터)
        lines = self._collect_target_lines(src_path, base_time)

        self.logger.log(f"기준 변환 시간: {base_time}", level="DEBUG")
        self.logger.log(f"변환 대상 행 수: {len(lines)}", level="DEBUG")

        # 구간: 변환본 마지막 행 시각(base_time) ~ 변환 시각(현재).
        # 원본 없음(0행) → 이 구간을 주기 채움(누락 처리). 원본 있음 → 아래에서 원본만 매핑·누락보충.
        if not lines:
            # 진단: base_time이 원본 마지막보다 크면 새 데이터가 없음. 원본의 마지막 시각 확인
            try:
                with open(src_path, "rb") as f:
                    last_line = None
                    for raw in f:
                        line = raw.decode("utf-8", errors="ignore").strip()
                        first = line.split(",", 1)[0].split(";", 1)[0].split("\t", 1)[0].strip().strip('"').strip("'")
                        if line and first.lower() != "timestamp":
                            last_line = line
                    if last_line:
                        first = last_line.split(",", 1)[0].split(";", 1)[0].split("\t", 1)[0].strip().strip('"')
                        last_ts = pd.to_datetime(first, errors="coerce")
                        if pd.notna(last_ts) and base_time is not None:
                            if last_ts < base_time:
                                self.logger.log(
                                    f"원본 마지막({last_ts}) < base_time({base_time}) "
                                    f"→ 새 데이터 없음",
                                    level="DEBUG",
                                )
                            else:
                                self.logger.log(
                                    f"건너뜀(형식 의심): {company}/{site}/{folder}/{filename} "
                                    f"— 원본 끝({last_ts}) >= base_time인데 수집 0행",
                                    level="WARN",
                                )
            except Exception:
                pass
            # 원본 0행이어도 누락보충(interval) ON 이면 변환본 마지막 ~ 현재 슬롯까지 채움.
            if interval_int > 0 and last_row and base_time is not None:
                try:
                    _now = datetime.now()
                    row_vals = [last_row.get(h, 0.0 if h != "timestamp" else str(base_time)) for h in STANDARD_HEADER]
                    last_df = pd.DataFrame([row_vals], columns=range(len(STANDARD_HEADER)))
                    _max_fill = max(24, int(60 / interval_int * 24 * 7))
                    tail_df = self.fill_interval.fill_from_last_to_now(
                        last_df, base_time, interval_int,
                        current_time_limit=_now, max_rows=_max_fill
                    )
                    if not tail_df.empty:
                        if "__filled__" in tail_df.columns:
                            tail_df = tail_df.drop(columns=["__filled__"])
                        tail_df.columns = range(tail_df.shape[1])
                        self._save_append(tail_df, out_path, interval_min=0)
                        if align_60:
                            self._sync_align60_from_main(
                                company, site, folder, filename, out_path, force=True
                            )
                        self.logger.log(
                            f"누락보충: {company}/{site}/{folder}/{filename} "
                            f"(+{len(tail_df)}행)",
                            level="INFO",
                        )
                        return "fill"
                except Exception as e:
                    self.logger.log(f"⚠️ 원본 0행 누락보충 실패: {e}", level="WARN")

            self.logger.log(
                f"변환 대상 없음 → 스킵: {company}/{site}/{folder}/{filename}",
                level="DEBUG",
            )
            if align_60 and os.path.exists(out_path):
                if self._sync_align60_from_main(
                    company, site, folder, filename, out_path
                ):
                    return "converted"
            return "skipped"

        self.logger.log(f"🔍 last_row 타입: {type(last_row)}", level="DEBUG")
        if last_row:
            self.logger.log(f"✅ 변환본 마지막 값 읽음", level="DEBUG")
        else:
            self.logger.log(f"⚠️ 변환본 마지막 값 없음 (최초 변환 또는 읽기 실패)", level="DEBUG")

        # 3단계: DataFrame 생성
        df = pd.read_csv(
            StringIO("\n".join(lines)),
            header=None,
            # 원본이 ',' 뿐 아니라 '\t', ';' 등일 수 있어 자동 감지
            sep=None,
            engine="python",
            on_bad_lines="skip"
        )

        if df.empty:
            self.logger.log(
                f"건너뜀(빈 데이터): {company}/{site}/{folder}/{filename}",
                level="WARN",
            )
            return "skipped"

        # timestamp 파싱 불가(NaT) 행은 이후 파이프라인(정렬/배터리 이동 등)을 망치므로 제거
        # format='mixed': 원본에 '2026-01-22 15:00' vs '2026-01-22 16:00:00' 혼재 시 모두 파싱 (pandas 2.0+)
        try:
            ts_parsed = pd.to_datetime(df.iloc[:, 0], errors="coerce", format="mixed")
        except TypeError:
            ts_parsed = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        try:
            valid_mask = ts_parsed.notna()
            if not valid_mask.all():
                dropped = int((~valid_mask).sum())
                df = df.loc[valid_mask].copy().reset_index(drop=True)
                if dropped > 0:
                    self.logger.log(
                        f"timestamp 파싱 실패 행 제거: {dropped}행",
                        level="DEBUG",
                    )
            if df.empty:
                self.logger.log(
                    f"건너뜀(시간 파싱 실패): {company}/{site}/{folder}/{filename}",
                    level="WARN",
                )
                return "skipped"
        except Exception:
            # 안전: 파싱 실패해도 기존 흐름 유지 (아래 시간 범위 체크에서 걸러짐)
            pass
        
        # DataFrame 생성 후 시간 범위 확인 및 로그 출력 (무한 반복 방지)
        try:
            time_col = df.iloc[:, 0]
            parsed_times = pd.to_datetime(time_col, errors='coerce', format='mixed')
            valid_times = parsed_times[parsed_times.notna()]
            if len(valid_times) > 0:
                # base_time 이전 데이터가 섞여 있어도 파일 전체를 스킵하지 않고,
                # 해당 행만 제거 후 계속 진행 (원본 파싱/구분자 이슈로 timestamp 열이 흔들릴 수 있음)
                if base_time is not None:
                    try:
                        bt = base_time.to_pydatetime() if hasattr(base_time, "to_pydatetime") else base_time
                    except Exception:
                        bt = base_time

                    parsed_times = pd.to_datetime(df.iloc[:, 0], errors="coerce", format="mixed")
                    keep_mask = parsed_times.notna() & (parsed_times >= bt)
                    dropped_past = int((parsed_times.notna() & (parsed_times < bt)).sum())
                    if dropped_past > 0:
                        self.logger.log(
                            f"base_time 이전 데이터 {dropped_past}행 제거 (base_time={bt})",
                            level="DEBUG",
                        )
                    df = df.loc[keep_mask].copy().reset_index(drop=True)
                    parsed_times = pd.to_datetime(df.iloc[:, 0], errors="coerce", format="mixed")
                    valid_times = parsed_times[parsed_times.notna()]
                    if len(valid_times) == 0:
                        self.logger.log(
                            f"건너뜀(유효 시간 없음): {company}/{site}/{folder}/{filename}",
                            level="WARN",
                        )
                        return "skipped"

                min_time = valid_times.min()
                max_time = valid_times.max()
                time_range_str = f"{min_time.strftime('%Y-%m-%d %H:%M')} ~ {max_time.strftime('%Y-%m-%d %H:%M')}"
                self.logger.log(
                    f"변환 대상 시간 범위: {time_range_str} (총 {len(df)}행)",
                    level="DEBUG",
                )
            else:
                self.logger.log(
                    f"건너뜀(유효 시간 없음): {company}/{site}/{folder}/{filename}",
                    level="WARN",
                )
                return "skipped"
        except Exception as e:
            self.logger.log(
                f"건너뜀(시간 확인 실패): {company}/{site}/{folder}/{filename} — {e}",
                level="WARN",
            )
            return "skipped"

        # 현장 옵션: 변환 실행 시점 기준 미래(timestamp) 행 제외
        try:
            df = self._drop_rows_timestamp_after_now_if_site_blocked(df, company, site)
            if df.empty:
                self.logger.log(
                    f"건너뜀(시간차단): {company}/{site}/{folder}/{filename}",
                    level="DEBUG",
                )
                return "skipped"
        except Exception as e:
            self.logger.log(f"⚠️ 현장 시간차단 필터 실패 (무시): {e}", level="WARN")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 📌 변환 파이프라인 (Core Transform)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        file_cfg = self.config.data.get(company, {}).get(site, {}).get(folder, {}).get(filename, {})
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔧 STEP 1: 시간 필터링 및 정렬 (중복 제거) - 새 데이터만 처리
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        interval = file_cfg.get("__fill_interval__", 0)
        interval_int = int(interval) if interval else 0
        initial_row_count = len(df)

        # 슬롯 기반(시간당 1행) 처리 비활성화: 항상 원본 시간 그대로 정렬만 수행
        if len(df) > 1:
            try:
                time_series = pd.to_datetime(df.iloc[:, 0], errors='coerce', format='mixed')
                df = df.iloc[time_series.argsort()].reset_index(drop=True)
            except Exception:
                pass

        # 진동계(VIBROMETER): 원본 init 9열(0-based 24~32)은 24열 자르기 전에 보관
        file_cfg = dict(file_cfg)
        if df.shape[1] >= 33:
            file_cfg["__vib_init__"] = df.iloc[:, 24:33].copy()
        else:
            file_cfg["__vib_init__"] = None
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔧 STEP 2: 배터리 이동 (56열 → 3열) - 새 데이터만 처리
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        df = self._move_battery(df)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔧 STEP 3: 센서 처리 (보정값 적용) - 새 데이터만 처리
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # FM 센서를 위한 마지막 변환본 값 추가
        # 원본 config를 직접 수정하지 않고 복사본 생성
        file_cfg = dict(file_cfg)  # 무조건 복사
        
        if last_row is not None and last_row:  # None도 아니고 빈 딕셔너리도 아님
            file_cfg["__last_converted_row__"] = last_row
        
        df = self.sensor.process(df, file_cfg)
        self.logger.log("센서 처리 완료", level="DEBUG")
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔧 STEP 4: 소수점 처리 - 새 데이터만 처리
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        df = self.apply_decimal(df, file_cfg)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔧 STEP 5: [누락처리] 슬롯 매핑 → 경계 연결 → 빈 슬롯 채움 → 마지막~현재
        #
        # 누락보충 정책: 원본참조/원본미참조 구분 없이
        #   fill된 행 = 이전 행 값 그대로 유지 ("측정 없음 = 변화 없음")
        #
        # ① map_slots           슬롯당 1행 정리 (겹침 방지)
        # ② prepend last_row    이전 변환본 마지막 행으로 경계 연결
        # ③ fill_gaps           빈 슬롯 → 이전 행 복사 (__filled__ 플래그)
        # ④ fill_from_last_to_now  마지막 실측 ~ 현재 구간 채움
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        fill_applied = False
        _now = datetime.now()
        if interval_int > 0:
            try:
                # ① 슬롯 매핑: 고빈도 데이터 → 슬롯당 1행으로 정리
                before_map = len(df)
                df = self.fill_interval.map_slots(df, interval_int)
                removed = before_map - len(df)
                if removed > 0:
                    self.logger.log(
                        f"슬롯 매핑({interval_int}분): {before_map}행 → {len(df)}행",
                        level="DEBUG",
                    )

                # ② 경계 연결: 변환본 마지막 행 prepend (간격 7일 초과 시 스킵)
                if last_row and base_time is not None and len(df) > 0:
                    try:
                        first_ts = pd.to_datetime(df.iloc[0, 0], errors="coerce", format="mixed")
                        if pd.notna(first_ts) and base_time < first_ts:
                            gap_min = (pd.Timestamp(first_ts) - pd.Timestamp(base_time)).total_seconds() / 60
                            if gap_min > 60 * 24 * 7:
                                self.logger.log(
                                    f"경계 연결 스킵: base~첫행 간격 {gap_min/60/24:.0f}일 > 7일",
                                    level="DEBUG",
                                )
                            else:
                                row_vals = [last_row.get(h, 0.0 if h != "timestamp" else str(base_time)) for h in STANDARD_HEADER]
                                last_df = pd.DataFrame([row_vals], columns=range(len(STANDARD_HEADER)))
                                if last_df.shape[1] == df.shape[1]:
                                    df = pd.concat([last_df, df], ignore_index=True)
                                    self.logger.log("경계 연결: last_row prepend", level="DEBUG")
                    except Exception as e:
                        self.logger.log(f"⚠️ 경계 연결 prepend 스킵: {e}", level="WARN")

                # ③ 빈 슬롯 채움: 이전 행 복사, __filled__ 플래그 부여
                self.logger.log(f"누락 보충({interval_int}분): 빈 슬롯 채움", level="DEBUG")
                df = self.fill_interval.fill_gaps(df, interval_int).copy()
                added = getattr(self.fill_interval, "last_added", 0)

                # ④ 마지막 실측 슬롯 다음 ~ 현재 슬롯까지 채움
                #    (실측+N분 게이트 금지 — 08:50 / now 09:30 이면 09:00 슬롯이 막힘)
                if len(df) > 0:
                    try:
                        last_ts = pd.to_datetime(df.iloc[-1, 0], errors="coerce", format="mixed")
                        if pd.notna(last_ts):
                            _max_fill = max(24, int(60 / interval_int * 24 * 7))
                            tail_df = self.fill_interval.fill_from_last_to_now(
                                df.iloc[[-1]].copy(), last_ts, interval_int,
                                current_time_limit=_now, max_rows=_max_fill
                            )
                            if not tail_df.empty:
                                df = pd.concat([df, tail_df], ignore_index=True)
                                added += len(tail_df)
                                self.logger.log(
                                    f"누락 보충: 마지막~현재 {len(tail_df)}행 추가",
                                    level="DEBUG",
                                )
                    except Exception as e:
                        self.logger.log(f"⚠️ 마지막~현재 구간 채움 스킵: {e}", level="WARN")

                fill_applied = True
                self.logger.log(f"누락 보충 완료 (추가 {added}행)", level="DEBUG")
            except Exception as e:
                self.logger.log(f"⚠️ 누락 보충 실패 (무시하고 계속): {e}", level="WARN")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 💾 저장
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if "__filled__" in df.columns:
            df = df.drop(columns=["__filled__"])
        self._save_append(df, out_path, interval_min=0)

        if align_60:
            self._sync_align60_from_main(
                company, site, folder, filename, out_path, force=True
            )

        # 모니터링 캐시 업데이트
        try:
            from monitoring.data_cache import update_file_cache
            update_file_cache(company, site, folder, filename, df)
        except Exception:
            pass

        tag = "누락보충" if fill_applied else "변환"
        self.logger.log(
            f"{tag}: {company}/{site}/{folder}/{filename} (+{len(df)}행)",
            level="INFO",
        )

        return "fill" if fill_applied else "converted"

    def _drop_rows_timestamp_after_now_if_site_blocked(
        self,
        df: pd.DataFrame,
        company: str,
        site: str,
    ) -> pd.DataFrame:
        """
        현장 설정 `__time_block_future__`(UI: 시간차단)일 때만:
        첫 열(timestamp)을 파싱해 **변환 실행 시점(now)보다 늦은** 행을 제거한다.
        """
        if df is None or df.empty:
            return df
        try:
            if not self.tree.get_site_time_block_future(company, site):
                return df
        except Exception:
            return df

        try:
            now_ts = pd.Timestamp(datetime.now())
        except Exception:
            return df

        try:
            try:
                ts_series = pd.to_datetime(df.iloc[:, 0], errors="coerce", format="mixed")
            except TypeError:
                ts_series = pd.to_datetime(df.iloc[:, 0], errors="coerce")

            try:
                skew_min = 180
                site_cfg = self.config.data.get(company, {}).get(site, {})
                if isinstance(site_cfg, dict):
                    v = site_cfg.get("__time_block_future_skew_min__", None)
                    if v is not None and str(v).strip() != "":
                        skew_min = int(float(v))
                skew_min = max(0, skew_min)
            except Exception:
                skew_min = 180

            cutoff_ts = now_ts + pd.Timedelta(minutes=skew_min)
            fut = ts_series.notna() & (ts_series > cutoff_ts)
            n_drop = int(fut.sum())
            if n_drop <= 0:
                return df
            keep = ~(fut)
            out = df.loc[keep].copy().reset_index(drop=True)
            self.logger.log(
                f"현장 시간차단: 미래 timestamp {n_drop}행 제외 → {len(out)}행 유지",
                level="DEBUG",
            )
            return out
        except Exception as e:
            self.logger.log(f"⚠️ 시간차단 필터 처리 오류: {e}", level="WARN")
            return df

    def _get_last_converted_data(self, out_path):
        """
        변환본에서 **시간순으로 마지막**인 행의 timestamp와 데이터 추출.
        (파일 끝이 아니라 timestamp 최대값 기준 — 순서 꼬임/중복 시에도 올바른 base_time)
        Returns: (timestamp, last_row_data_dict) 또는 (None, None)
        """
        from utils.csv_last_row import read_max_timestamp_row

        if not os.path.exists(out_path):
            self.logger.log("[INFO] 변환본 파일 없음 (최초 변환)", level="DEBUG")
            return None, None

        self.logger.log("[INFO] 변환본 마지막 행 읽기 시작...", level="DEBUG")

        try:
            ts, last_row_data = read_max_timestamp_row(out_path, STANDARD_HEADER)
            if ts is None or last_row_data is None:
                self.logger.log("[WARNING] 변환본에 유효한 데이터 행 없음", level="WARN")
                return None, None

            self.logger.log(f"[OK] 마지막 행 읽기 성공 (시간순 마지막: {ts})", level="DEBUG")
            return ts, last_row_data

        except Exception as e:
            self.logger.log(f"[ERROR] 변환본 읽기 실패: {e}", level="ERROR")
            import traceback
            self.logger.log(f"   상세: {traceback.format_exc()}", level="ERROR")
        return None, None

    def _collect_target_lines(self, src_path, base_time):
        """
        원본에서 base_time 이상 행만 수집.

        최적화 (증분 변환):
        - peek로 원본 끝이 base_time 이전이면 즉시 []
        - 파일 끝에서 창을 키워 읽다, 창 안 최소 timestamp < base_time 이면 중단
          (로거 append-only 가정 — 새 데이터는 끝에 있음)
        - 창이 과대해지거나 비정상이면 전체 scan 폴백
        """
        from datetime import datetime
        from utils.csv_last_row import peek_last_timestamp

        if not os.path.exists(src_path):
            return []

        current_year = datetime.now().year
        max_year = current_year + 1
        base_ts = pd.Timestamp(base_time) if base_time is not None else None

        if base_ts is not None:
            last = peek_last_timestamp(src_path)
            if last is not None and pd.notna(last) and last < base_ts:
                self.logger.log(
                    f"원본 끝({last}) < base_time({base_ts}) → 수집 0행 (전체 scan 생략)",
                    level="DEBUG",
                )
                return []

            try:
                lines = self._collect_target_lines_tail_window(
                    src_path, base_ts, max_year
                )
                if lines is not None:
                    return lines
                self.logger.log(
                    "원본 tail 수집 폴백 → 전체 scan",
                    level="DEBUG",
                )
            except Exception as e:
                self.logger.log(
                    f"원본 tail 수집 실패 → 전체 scan: {e}",
                    level="DEBUG",
                )

        return self._collect_target_lines_full(src_path, base_ts, max_year)

    def _collect_target_lines_tail_window(self, src_path, base_ts, max_year):
        """
        파일 끝 창을 256KB→… 로 키우며 base_time 이상 행 수집.
        창 내 최소 timestamp < base_time 이면 충분(그 앞은 더 오래됨).
        Returns: list[str] 또는 None(폴백)
        """
        file_size = os.path.getsize(src_path)
        if file_size <= 0:
            return []

        max_window = min(file_size, 32 * 1024 * 1024)  # 32MB 초과 시 폴백
        window = min(256 * 1024, file_size)

        while True:
            lines_raw, truncated = self._read_file_tail_lines(src_path, window)
            pairs = []
            min_ts = None
            for line in lines_raw:
                ts = self._parse_source_line_ts(line)
                if ts is None:
                    continue
                if ts.year < 2000 or ts.year > max_year:
                    continue
                if min_ts is None or ts < min_ts:
                    min_ts = ts
                if ts >= base_ts:
                    pairs.append((ts, line))

            # 창이 파일 전체이거나, 창이 base_time 이전까지 덮음 → 완료
            if (not truncated) or (min_ts is not None and min_ts < base_ts):
                pairs.sort(key=lambda x: x[0])
                return [ln for _, ln in pairs]

            if window >= max_window:
                return None  # 너무 큼 → 전체 scan

            window = min(window * 4, max_window, file_size)

    def _read_file_tail_lines(self, path, max_bytes):
        """파일 끝 max_bytes → (lines in order, truncated_at_start)."""
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            if pos == 0:
                return [], False
            read_size = min(pos, max_bytes)
            start = pos - read_size
            f.seek(start)
            chunk = f.read(read_size)

        truncated = start > 0
        text = chunk.decode("utf-8", errors="ignore")
        lines = text.splitlines()
        if truncated and lines:
            lines = lines[1:]
        return [ln.strip() for ln in lines if ln.strip()], truncated

    @staticmethod
    def _parse_source_line_ts(line):
        """원본 한 줄에서 timestamp 파싱. 실패 시 None."""
        from datetime import datetime as _dt

        if not line or line.lower().startswith("timestamp"):
            return None
        s = str(line).strip().lstrip("\ufeff")
        first = s
        for sep in (",", ";", "\t"):
            if sep in s:
                first = s.split(sep, 1)[0].strip().strip('"').strip("'")
                break
        else:
            parts = s.split()
            first = parts[0].strip().strip('"').strip("'") if parts else ""
        if not first:
            return None
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
        ):
            try:
                return pd.Timestamp(_dt.strptime(first, fmt))
            except ValueError:
                continue
        try:
            ts = pd.to_datetime(first, errors="coerce", format="mixed")
        except TypeError:
            ts = pd.to_datetime(first, errors="coerce")
        return ts if pd.notna(ts) else None

    def _collect_target_lines_full(self, src_path, base_ts, max_year=None):
        """원본 전체 1-pass 수집 (최초 변환·tail 폴백)."""
        from datetime import datetime

        lines = []
        skipped_count = 0
        skipped_old = 0
        skipped_future = 0
        skipped_parse_error = 0

        if max_year is None:
            max_year = datetime.now().year + 1

        with open(src_path, "rb") as f:
            for raw in f:
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                ts = self._parse_source_line_ts(line)
                if ts is None:
                    skipped_count += 1
                    skipped_parse_error += 1
                    continue
                if ts.year < 2000:
                    skipped_count += 1
                    skipped_old += 1
                    continue
                if ts.year > max_year:
                    skipped_count += 1
                    skipped_future += 1
                    continue
                if base_ts is None or ts >= base_ts:
                    lines.append(line)

        if skipped_count > 0:
            self.logger.log(
                f"⚠️ 비정상 시간 데이터 제외: 총 {skipped_count}개 "
                f"(2000년 이전: {skipped_old}, {max_year}년 초과: {skipped_future}, "
                f"파싱 실패: {skipped_parse_error})",
                level="DEBUG",
            )
        return lines

    def _convert_neo_blast_file(self, company, site, folder, filename, folder_cfg, file_cfg):
        """Neo Blast (.blast/.txt) 폴더 → 마스터 CSV 동기화."""
        from core.neo_blast_processor import sync_neo_blast_folder

        source_dir = (file_cfg.get("__nb_source_dir__") or folder_cfg.get("__absolute_path__") or "").strip()
        if not source_dir or not os.path.isdir(source_dir):
            self.logger.log(
                f"[NB] 원본 폴더 없음 → 스킵: {company}/{site}/{folder}/{filename}",
                level="WARN",
            )
            return "skipped"

        from utils.convert_paths import prepare_convert_out_path

        out_path = prepare_convert_out_path(
            self.convert_root, company, site, folder, filename, logger=self.logger
        )

        stats = sync_neo_blast_folder(
            source_dir,
            out_path,
            logger=self.logger,
            pvs_limit=file_cfg.get("__nb_pvs_limit__"),
            kine_limit=file_cfg.get("__nb_kine_limit__"),
        )
        if stats["appended"] > 0:
            return "converted"
        if stats["parsed"] > 0 and stats["skipped_dup"] > 0:
            return "skipped"
        if stats["failed"] > 0 and stats["appended"] == 0:
            return "error"
        return "skipped"

    def append_gen_interval_source_row(self, csv_path: str) -> bool:
        """
        __gen_interval__ 스케줄용: 원본 CSV에 현재 시각 + 0값 행 1줄 추가.
        (변환 파이프라인과 분리 — 원본에 행 추가 후 다음 convert_file 에서 반영)
        """
        import datetime

        if not csv_path or not os.path.exists(csv_path):
            self.logger.log(f"[gen_interval] CSV 없음 → {csv_path}", level="WARN")
            return False

        try:
            df = pd.read_csv(csv_path, sep=None, engine="python", on_bad_lines="skip")
        except Exception as e:
            self.logger.log(f"[gen_interval] CSV 읽기 실패 → {e}", level="ERROR")
            return False

        if df.empty:
            return False

        folder_name = os.path.basename(os.path.dirname(csv_path))
        file_stem = os.path.splitext(os.path.basename(csv_path))[0]
        b_col = df.columns[1] if len(df.columns) > 1 else None
        f_col = df.columns[5] if len(df.columns) > 5 else None

        now_str = datetime.datetime.now().replace(second=0, microsecond=0).strftime(
            "%Y-%m-%d %H:%M"
        )

        time_col = "timestamp" if "timestamp" in df.columns else df.columns[0]

        def _excel_col_to_index(col_label: str) -> int:
            if not isinstance(col_label, str) or col_label == "":
                return 0
            col_label = col_label.upper().strip()
            idx = 0
            for ch in col_label:
                if "A" <= ch <= "Z":
                    idx = idx * 26 + (ord(ch) - ord("A") + 1)
                else:
                    break
            return max(0, idx - 1)

        try:
            bg_index = min(_excel_col_to_index("BG"), len(df.columns) - 1)
        except Exception:
            bg_index = len(df.columns) - 1

        new_row = {}
        for i, col in enumerate(df.columns):
            if col == time_col:
                new_row[col] = now_str
            elif b_col and col == b_col:
                new_row[col] = folder_name
            elif f_col and col == f_col:
                new_row[col] = file_stem
            elif i <= bg_index:
                new_row[col] = 0
            else:
                new_row[col] = ""

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        try:
            df.to_csv(csv_path, index=False)
            self.logger.log(f"[gen_interval] 원본 행 추가: {csv_path}", level="DEBUG")
            return True
        except Exception as e:
            self.logger.log(f"[gen_interval] CSV 저장 실패 → {e}", level="ERROR")
            return False

    def _move_battery(self, df):
        """배터리 추출 후 3열 기록 + 24열 트림 (utils.battery)."""
        from utils.battery import move_battery_and_trim

        return move_battery_and_trim(df, logger=self.logger)
    @staticmethod
    def _align60_needs_sync(main_path: str, align60_path: str) -> bool:
        """10분 변환본 대비 _60.csv 생성·갱신 필요 여부."""
        if not os.path.exists(main_path):
            return False
        if not os.path.exists(align60_path):
            return True
        try:
            return os.path.getmtime(main_path) > os.path.getmtime(align60_path)
        except OSError:
            return True

    def _sync_align60_from_main(
        self,
        company,
        site,
        folder,
        filename,
        main_path,
        *,
        force: bool = False,
    ) -> bool:
        """
        10분 변환본(main_path)을 읽어 60분 슬롯당 1행만 남긴 _60.csv 생성.
        센서·누락보충은 10분 파일에만 적용 — _60은 그 결과를 정렬한 사본.
        """
        try:
            from utils.convert_paths import prepare_align60_out_path

            out_path_60 = prepare_align60_out_path(
                self.convert_root, company, site, folder, filename, logger=self.logger
            )
            if not os.path.exists(main_path):
                return False
            if not force and not self._align60_needs_sync(main_path, out_path_60):
                return False
            if self._rebuild_align60_from_main(main_path, out_path_60):
                self.logger.log(
                    f"60분 정렬: {os.path.basename(main_path)} → "
                    f"{os.path.basename(out_path_60)} (10분 변환본과 동일 값)",
                    level="INFO",
                )
                return True
        except Exception as e:
            self.logger.log(f"⚠️ 60분 정렬 실패: {e}", level="WARN")
        return False

    def _read_converted_dataframe(self, out_path: str) -> pd.DataFrame:
        """변환본 CSV 전체를 STANDARD_HEADER DataFrame으로 읽는다."""
        if not os.path.exists(out_path):
            return pd.DataFrame(columns=STANDARD_HEADER)
        try:
            raw = pd.read_csv(
                out_path, header=None, encoding="utf-8-sig", on_bad_lines="skip"
            )
            if raw.empty:
                return pd.DataFrame(columns=STANDARD_HEADER)
            if raw.iloc[0].astype(str).str.contains("timestamp", case=False, na=False).any():
                raw = raw.iloc[1:]
            if raw.empty:
                return pd.DataFrame(columns=STANDARD_HEADER)
            ncol = min(raw.shape[1], len(STANDARD_HEADER))
            df = raw.iloc[:, :ncol].copy()
            df.columns = list(STANDARD_HEADER[:ncol])
            for j in range(ncol, len(STANDARD_HEADER)):
                df[STANDARD_HEADER[j]] = 0.0
            return df[STANDARD_HEADER]
        except Exception as e:
            self.logger.log(f"[WARN] 변환본 전체 읽기 실패: {out_path} — {e}", level="WARN")
            return pd.DataFrame(columns=STANDARD_HEADER)

    def _rebuild_align60_from_main(self, main_path: str, align60_path: str) -> bool:
        """10분 변환본 전체 → map_slots(60). CH 값은 10분본과 동일, 행만 시간당 1개."""
        df = self._read_converted_dataframe(main_path)
        if df.empty:
            return False
        aligned = self.fill_interval.map_slots(df, 60)
        if aligned.empty:
            return False
        os.makedirs(os.path.dirname(align60_path), exist_ok=True)
        aligned.to_csv(align60_path, index=False, header=True, encoding="utf-8-sig")
        self._log_saved_file_state(align60_path, context="align60-rebuild", df=aligned)
        return True

    def _save_append(self, df, out_path, interval_min=0):
        """변환본 저장 (최초: 생성, 이후: 기존+신규 병합 → 시간순 정렬 → 슬롯 중복 제거 후 저장)"""
        out_dir = os.path.dirname(out_path)
        os.makedirs(out_dir, exist_ok=True)

        df = df.copy()
        df.columns = STANDARD_HEADER

        if not os.path.exists(out_path):
            try:
                df.to_csv(out_path, index=False, header=True, encoding="utf-8-sig")
            except PermissionError as e:
                self.logger.log(f"[ERROR] 변환본 저장 실패(권한/점유): {out_path} - {e}", level="ERROR")
                raise
            except Exception as e:
                self.logger.log(f"[ERROR] 변환본 저장 실패: {out_path} - {e}", level="ERROR")
                raise
            self._log_saved_file_state(out_path, context="create", df=df)
            return

        # 기존 파일 + 신규 병합 → 시간순 정렬 → 동일 시각(분 단위) 중복 제거 후 저장
        try:
            existing = pd.read_csv(out_path, header=None, encoding="utf-8-sig", on_bad_lines="skip")
            if existing.iloc[0].astype(str).str.contains("timestamp", case=False, na=False).any():
                existing = existing.iloc[1:]
            ncol = min(existing.shape[1], len(STANDARD_HEADER))
            existing = existing.iloc[:, :ncol].copy()
            existing.columns = list(STANDARD_HEADER[:ncol])
            for j in range(ncol, len(STANDARD_HEADER)):
                existing[STANDARD_HEADER[j]] = 0.0
            existing = existing[STANDARD_HEADER]
            merged = pd.concat([existing, df], ignore_index=True)
            # timestamp 파싱이 환경/데이터에 따라 흔들려도(초 포함/공백/이상값),
            # 저장 단계에서 새 데이터가 통째로 날아가지 않도록:
            # - 정렬은 to_datetime(coerce)로 하되, 실패(NaT)는 끝으로 보냄
            # - 중복 제거는 "분 단위 문자열 키"를 직접 만들어 keep='last'
            try:
                ts = pd.to_datetime(merged["timestamp"], errors="coerce", format="mixed")
            except TypeError:
                ts = pd.to_datetime(merged["timestamp"], errors="coerce")
            try:
                # NaT를 가장 뒤로 보내기 위해 큰 값으로 대체
                sort_key = ts.fillna(pd.Timestamp.max)
                merged = merged.iloc[sort_key.argsort(kind="mergesort")].reset_index(drop=True)
            except Exception:
                pass

            ts_key = merged["timestamp"].astype(str).str.strip().str.replace("\ufeff", "", regex=False).str.slice(0, 16)
            merged = merged.loc[~ts_key.duplicated(keep="last")].reset_index(drop=True)
            try:
                merged.to_csv(out_path, index=False, header=True, encoding="utf-8-sig")
            except PermissionError as e:
                self.logger.log(f"[ERROR] 변환본 저장 실패(권한/점유): {out_path} - {e}", level="ERROR")
                raise
            self._log_saved_file_state(out_path, context="merge", df=merged)
        except Exception as e:
            self.logger.log(f"[WARN] 병합 저장 실패, 단순 append 시도: {e}", level="WARN")
            try:
                with open(out_path, "a", encoding="utf-8-sig", newline="") as f:
                    df.to_csv(f, index=False, header=False)
            except PermissionError as e2:
                self.logger.log(f"[ERROR] 변환본 append 실패(권한/점유): {out_path} - {e2}", level="ERROR")
                raise
            except Exception as e2:
                self.logger.log(f"[ERROR] 변환본 append 실패: {out_path} - {e2}", level="ERROR")
                raise
            self._log_saved_file_state(out_path, context="append", df=df)

    def _log_saved_file_state(self, out_path: str, context: str = "", df: "pd.DataFrame | None" = None):
        """저장 직후 파일 상태를 로그로 남겨 '저장했는데 안 보임'을 진단하기 쉽게 한다.

        df가 전달되면 이미 메모리에 있는 데이터로 통계를 뽑아 파일 재읽기를 하지 않는다.
        df가 None이면 os.stat으로 크기/수정시간만 기록한다 (fallback).
        """
        try:
            st = os.stat(out_path)
            self.logger.log(
                f"저장 확인({context}): size={st.st_size} bytes, "
                f"mtime={datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')} - {out_path}",
                level="DEBUG",
            )

            # 이미 메모리에 있는 df로 통계 계산 (재읽기 없음)
            if df is not None and not df.empty:
                try:
                    ts_col = df["timestamp"] if "timestamp" in df.columns else df.iloc[:, 0]
                    try:
                        ts = pd.to_datetime(ts_col, errors="coerce", format="mixed")
                    except TypeError:
                        ts = pd.to_datetime(ts_col, errors="coerce")
                    valid = ts.dropna()
                    if len(valid) > 0:
                        self.logger.log(
                            f"저장 결과({context}): rows={len(df)}, "
                            f"time_range={valid.min().strftime('%Y-%m-%d %H:%M')} ~ "
                            f"{valid.max().strftime('%Y-%m-%d %H:%M')}",
                            level="DEBUG",
                        )
                    else:
                        self.logger.log(
                            f"저장 결과({context}): timestamp 유효행 0 - {out_path}",
                            level="DEBUG",
                        )
                except Exception:
                    pass
        except Exception:
            pass

    def apply_decimal(self, df, file_cfg):
        """슬롯별 소수점 설정 적용 (degreeX/Y + CH0~7)."""
        from core.sensor_processor import SENSOR_SLOTS

        df = df.copy()

        for slot_key, col in SENSOR_SLOTS:
            ch_cfg = file_cfg.get(slot_key, {})
            if not isinstance(ch_cfg, dict):
                continue
            dec = ch_cfg.get("decimal", "")

            if dec in ("", None):
                continue

            try:
                d = int(dec)
            except Exception:
                continue

            if col >= df.shape[1]:
                continue
            df.iloc[:, col] = pd.to_numeric(df.iloc[:, col], errors="coerce").round(d)

        return df
    
    def trim_source_before_time(self, src_path: str, cutoff_datetime) -> tuple[bool, int]:
        """
        원본 CSV에서 cutoff 미만 행만 삭제. 헤더(첫 행이 시간이 아니면)는 유지.
        Returns: (성공, 삭제 행 수)
        """
        if not src_path or not os.path.exists(src_path):
            return False, 0
        cutoff = pd.Timestamp(cutoff_datetime)
        try:
            with open(src_path, "r", encoding="utf-8-sig", newline="") as f:
                raw_lines = f.readlines()
            if not raw_lines:
                return True, 0

            kept: list[str] = []
            start = 0
            if FileProcessor._parse_source_line_ts(raw_lines[0]) is None:
                kept.append(raw_lines[0])
                start = 1

            deleted = 0
            for line in raw_lines[start:]:
                if not line.strip():
                    kept.append(line)
                    continue
                ts = FileProcessor._parse_source_line_ts(line)
                if ts is None or ts >= cutoff:
                    kept.append(line)
                else:
                    deleted += 1

            with open(src_path, "w", encoding="utf-8-sig", newline="") as f:
                f.writelines(kept)

            self.logger.log(
                f"원본 정리: {src_path} ({deleted}행 삭제, cutoff={cutoff})",
                level="INFO",
            )
            return True, deleted
        except Exception as e:
            self.logger.log(f"원본 정리 실패: {src_path} - {e}", level="ERROR")
            return False, 0

    def trim_converted_from_time(self, out_path: str, cutoff_datetime) -> tuple[bool, int]:
        """
        변환본에서 지정 시간 이상(>=)인 행을 삭제.

        Args:
            out_path: 변환본 CSV 경로
            cutoff_datetime: datetime 객체. 이 시간 이상(>=) 행 삭제

        Returns:
            (성공 여부, 삭제된 행 수)
        """
        if not os.path.exists(out_path):
            return False, 0

        import csv
        try:
            all_rows = []
            ts_col_idx = 0

            with open(out_path, 'r', encoding='utf-8-sig', newline='') as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if not row:
                        continue
                    if i == 0:
                        for j, c in enumerate(row):
                            if str(c).strip().lstrip('\ufeff').lower() == 'timestamp':
                                ts_col_idx = j
                                break
                        all_rows.append(row)
                        continue
                    all_rows.append(row)

            kept_rows = [all_rows[0]]
            for row in all_rows[1:]:
                if ts_col_idx >= len(row):
                    kept_rows.append(row)
                    continue
                try:
                    parsed = pd.to_datetime(row[ts_col_idx], errors="coerce")
                except Exception:
                    parsed = pd.NaT
                if pd.isna(parsed):
                    kept_rows.append(row)
                    continue
                if parsed >= cutoff_datetime:
                    continue
                kept_rows.append(row)

            deleted_count = len(all_rows) - len(kept_rows)

            with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                for row in kept_rows:
                    writer.writerow(row)

            self.logger.log(
                f"변환본 시간 이후 삭제 완료: {out_path} ({deleted_count}행 삭제됨)",
                level="INFO"
            )
            return True, deleted_count
        except Exception as e:
            self.logger.log(f"변환본 시간 이후 삭제 실패: {e}", level="ERROR")
            return False, 0

    def upload_folder(self, folder_path, recursive=False):
        """
        폴더 업로드 기능 (스텁 - 아직 구현되지 않음)
        
        Args:
            folder_path: 업로드할 폴더 경로
            recursive: 하위 폴더 포함 여부
        
        Note:
            이 기능은 아직 구현되지 않았습니다.
            필요하시면 서버 업로드, FTP, 클라우드 스토리지 등의 백엔드를 추가할 수 있습니다.
        """
        self.logger.log(
            f"[FileProcessor] 업로드 기능 호출됨 (구현되지 않음): {folder_path}, recursive={recursive}",
            level="WARN"
        )
        raise NotImplementedError(
            "폴더 업로드 기능이 아직 구현되지 않았습니다.\n"
            "필요하시면 서버 업로드, FTP, 클라우드 스토리지 등의 백엔드를 추가할 수 있습니다."
        )
