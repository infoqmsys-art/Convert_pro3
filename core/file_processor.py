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
- 원본의 batLevel(56열)을 읽어 Length 위치(3열)에 battery 값으로 덮어쓴다.
- Length 컬럼은 변환본에서 더 이상 의미를 가지지 않는다.
- 24열 이후의 모든 원본 컬럼은 변환 과정에서 제거한다.
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

    def convert_file(self, company, site, folder, filename):
        """
        파일 단위 변환 (Site 레벨 포함, 재시도 로직 포함)
        
        Returns:
            str: "converted", "fill", "skipped", "error"
        """
        max_retries = 3
        retry_delay = 1  # 초
        
        for attempt in range(max_retries):
            try:
                return self._convert_file_internal(company, site, folder, filename)
            
            except PermissionError as e:
                if attempt < max_retries - 1:
                    self.logger.log(
                        f"파일 점유 중... 재시도 {attempt + 1}/{max_retries} "
                        f"({company}/{site}/{folder}/{filename})",
                        level="WARN"
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 지수 백오프
                else:
                    self.logger.log(
                        f"파일 변환 실패 (점유됨): {company}/{site}/{folder}/{filename}",
                        level="ERROR"
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
        src_path = os.path.join(folder_cfg["__absolute_path__"], filename)

        if not os.path.exists(src_path):
            self.logger.log(f"원본 없음 → 스킵: {company}/{site}/{folder}/{filename}", level="DEBUG")
            return "skipped"

        # ⚙ 변환본 경로 규칙:
        #   C:\data\Convertfile\{company}\{folder}\{filename}
        #   - 폴더명(로거 식별자)으로 매핑, 현장은 트리용 논리 레벨
        out_dir = os.path.join(self.convert_root, company, folder)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, filename)
        
        self.logger.log(f"📂 변환본 경로: {out_path}", level="INFO")
        self.logger.log(f"📂 변환본 존재 여부: {os.path.exists(out_path)}", level="INFO")

        # 1단계: 마지막 변환 시점 확인 + 마지막 행 데이터 추출
        base_time, last_row = self._get_last_converted_data(out_path)

        # 2단계: 변환 대상 행 수집 (base_time 이후 데이터)
        lines = self._collect_target_lines(src_path, base_time)

        self.logger.log(f"⏰ 기준 변환 시간: {base_time}", level="INFO")
        self.logger.log(f"📊 변환 대상 행 수: {len(lines)}", level="INFO")

        file_cfg = self.config.data.get(company, {}).get(site, {}).get(folder, {}).get(filename, {})
        interval = file_cfg.get("__fill_interval__", 0)
        interval_int = int(interval) if interval else 0

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
                                    f"원본 마지막({last_ts}) < base_time({base_time}) → 원본에 새 데이터 없음. "
                                    f"원본 파일이 최신인지 확인하세요.",
                                    level="WARN"
                                )
                            else:
                                self.logger.log(
                                    f"원본 마지막({last_ts}) >= base_time인데 0행 수집됨. "
                                    f"원본 구분자/형식 문제 가능성.",
                                    level="WARN"
                                )
            except Exception:
                pass
            # 누락보충 설정이 있고 변환본 마지막 행이 있으면 → base_time ~ 현재 구간 채움
            if interval_int > 0 and last_row and base_time is not None:
                try:
                    _now = datetime.now()
                    # base_time 이후 채울 구간이 있는지 확인
                    slot_end = pd.Timestamp(base_time) + timedelta(minutes=interval_int)
                    if slot_end <= pd.Timestamp(_now):
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
                            self.logger.log(
                                f"🔧 원본 0행 누락보충: base_time({base_time}) ~ 현재 {len(tail_df)}행 채움",
                                level="INFO"
                            )
                            return "fill"
                except Exception as e:
                    self.logger.log(f"⚠️ 원본 0행 누락보충 실패: {e}", level="WARN")

            self.logger.log(f"변환 대상 없음 → 스킵: {company}/{site}/{folder}/{filename}", level="INFO")
            return "skipped"

        self.logger.log(f"🔍 last_row 타입: {type(last_row)}, 값: {last_row}", level="INFO")
        if last_row:
            self.logger.log(f"✅ 변환본 마지막 값 읽음: {last_row}", level="INFO")
        else:
            self.logger.log(f"⚠️ 변환본 마지막 값 없음 (최초 변환 또는 읽기 실패)", level="INFO")

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
            self.logger.log("DataFrame 비어있음 → 스킵", level="INFO")
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
                    self.logger.log(f"⚠️ timestamp 파싱 실패 행 제거: {dropped}행", level="INFO")
            if df.empty:
                self.logger.log("유효 timestamp 행 없음 → 스킵", level="WARN")
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
                            f"⚠️ base_time 이전 데이터 {dropped_past}행 제거 후 계속 진행 (base_time={bt})",
                            level="WARN",
                        )
                    df = df.loc[keep_mask].copy().reset_index(drop=True)
                    parsed_times = pd.to_datetime(df.iloc[:, 0], errors="coerce", format="mixed")
                    valid_times = parsed_times[parsed_times.notna()]
                    if len(valid_times) == 0:
                        self.logger.log("⚠️ base_time 이후 유효 timestamp 행 없음 → 스킵", level="WARN")
                        return "skipped"

                min_time = valid_times.min()
                max_time = valid_times.max()
                time_range_str = f"{min_time.strftime('%Y-%m-%d %H:%M')} ~ {max_time.strftime('%Y-%m-%d %H:%M')}"
                self.logger.log(f"📅 변환 대상 시간 범위: {time_range_str} (총 {len(df)}행)", level="INFO")
                # 콘솔 인코딩(cp949) 환경에서 이모지 출력 시 크래시 방지: Logger로만 출력
            else:
                self.logger.log(f"⚠️ 유효한 시간 데이터 없음 → 스킵", level="WARN")
                return "skipped"
        except Exception as e:
            self.logger.log(f"⚠️ 시간 범위 확인 실패: {e} → 스킵", level="WARN")
            return "skipped"

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
        self.logger.log(f"✅ 센서 처리 완료", level="INFO")
        
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
                        f"🔧 슬롯 매핑({interval_int}분): {before_map}행 → {len(df)}행 (중복 {removed}행 제거)",
                        level="INFO"
                    )

                # ② 경계 연결: 변환본 마지막 행 prepend (간격 7일 초과 시 스킵)
                if last_row and base_time is not None and len(df) > 0:
                    try:
                        first_ts = pd.to_datetime(df.iloc[0, 0], errors="coerce", format="mixed")
                        if pd.notna(first_ts) and base_time < first_ts:
                            gap_min = (pd.Timestamp(first_ts) - pd.Timestamp(base_time)).total_seconds() / 60
                            if gap_min > 60 * 24 * 7:
                                self.logger.log(
                                    f"🔧 경계 연결 스킵: base~첫행 간격 {gap_min/60/24:.0f}일 > 7일",
                                    level="INFO"
                                )
                            else:
                                row_vals = [last_row.get(h, 0.0 if h != "timestamp" else str(base_time)) for h in STANDARD_HEADER]
                                last_df = pd.DataFrame([row_vals], columns=range(len(STANDARD_HEADER)))
                                if last_df.shape[1] == df.shape[1]:
                                    df = pd.concat([last_df, df], ignore_index=True)
                                    self.logger.log(f"🔧 경계 연결: last_row prepend", level="INFO")
                    except Exception as e:
                        self.logger.log(f"⚠️ 경계 연결 prepend 스킵: {e}", level="WARN")

                # ③ 빈 슬롯 채움: 이전 행 복사, __filled__ 플래그 부여
                self.logger.log(f"🔧 누락 보충({interval_int}분): 빈 슬롯 채움", level="INFO")
                df = self.fill_interval.fill_gaps(df, interval_int).copy()
                added = getattr(self.fill_interval, "last_added", 0)

                # ④ 마지막 실측 ~ 현재 구간 채움
                if len(df) > 0 and base_time is not None:
                    try:
                        last_ts = pd.to_datetime(df.iloc[-1, 0], errors="coerce", format="mixed")
                        if pd.notna(last_ts):
                            slot_end = last_ts + timedelta(minutes=interval_int)
                            if slot_end <= pd.Timestamp(_now):
                                _max_fill = max(24, int(60 / interval_int * 24 * 7)) if interval_int > 0 else 24
                                tail_df = self.fill_interval.fill_from_last_to_now(
                                    df.iloc[[-1]].copy(), last_ts, interval_int,
                                    current_time_limit=_now, max_rows=_max_fill
                                )
                                if not tail_df.empty:
                                    df = pd.concat([df, tail_df], ignore_index=True)
                                    added += len(tail_df)
                                    self.logger.log(f"🔧 누락 보충: 마지막~현재 {len(tail_df)}행 추가", level="INFO")
                    except Exception as e:
                        self.logger.log(f"⚠️ 마지막~현재 구간 채움 스킵: {e}", level="WARN")

                fill_applied = True
                self.logger.log(f"✅ 누락 보충 완료 (추가 {added}행)", level="INFO")
            except Exception as e:
                self.logger.log(f"⚠️ 누락 보충 실패 (무시하고 계속): {e}", level="WARN")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 💾 저장
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if "__filled__" in df.columns:
            df = df.drop(columns=["__filled__"])
        self.logger.log(f"💾 저장: {len(df)}행 저장", level="INFO")
        self._save_append(df, out_path, interval_min=0)

        # 모니터링 캐시 업데이트 (변환 완료 직후, 실패해도 변환에 영향 없음)
        try:
            from monitoring.data_cache import update_file_cache
            update_file_cache(company, folder, filename, df)
        except Exception:
            pass

        self.logger.log(f"파일 변환 완료: {company}/{site}/{folder}/{filename}", level="DEBUG")

        return "fill" if fill_applied else "converted"

    def _get_last_converted_data(self, out_path):
        """
        변환본에서 **시간순으로 마지막**인 행의 timestamp와 데이터 추출.
        (파일 끝이 아니라 timestamp 최대값 기준 — 순서 꼬임/중복 시에도 올바른 base_time)
        Returns: (timestamp, last_row_data_dict) 또는 (None, None)
        """
        if not os.path.exists(out_path):
            self.logger.log(f"[INFO] 변환본 파일 없음 (최초 변환)", level="INFO")
            return None, None

        self.logger.log(f"[INFO] 변환본 마지막 행 읽기 시작...", level="INFO")
        
        try:
            # usecols=list(range(24)): STANDARD_HEADER 범위(24열)만 로드 — 초과 열 불필요
            df_all = pd.read_csv(out_path, header=None, sep=',', engine='python',
                                 on_bad_lines='skip', encoding='utf-8',
                                 usecols=list(range(24)))
            if df_all.empty or len(df_all) < 2:
                if len(df_all) == 1:
                    self.logger.log(f"[WARNING] 변환본에 데이터 행 없음", level="WARN")
                return None, None

            if df_all.iloc[0].astype(str).str.contains('timestamp', case=False, na=False).any():
                df_data = df_all.iloc[1:].copy()
            else:
                df_data = df_all.copy()

            if df_data.empty:
                return None, None

            try:
                ts_col = pd.to_datetime(df_data.iloc[:, 0], errors='coerce', format='mixed')
            except TypeError:
                ts_col = pd.to_datetime(df_data.iloc[:, 0], errors='coerce')
            valid = ts_col.notna()
            if not valid.any():
                self.logger.log(f"[WARNING] 변환본에서 유효한 timestamp 없음", level="WARN")
                return None, None

            idx_max = ts_col.idxmax()
            last_row_series = df_data.loc[idx_max]
            ts = ts_col.loc[idx_max]

            last_row_data = {}
            STRING_COLS = ("timestamp", "deviceId", "STX")
            for i, col_name in enumerate(STANDARD_HEADER):
                if i < len(last_row_series):
                    try:
                        if col_name in STRING_COLS:
                            last_row_data[col_name] = str(last_row_series.iloc[i]).strip() if pd.notna(last_row_series.iloc[i]) else ("2026-01-01 00:00" if col_name == "timestamp" else "")
                        else:
                            val = pd.to_numeric(last_row_series.iloc[i], errors="coerce")
                            last_row_data[col_name] = float(val) if pd.notna(val) else 0.0
                    except Exception:
                        last_row_data[col_name] = 0.0 if col_name not in STRING_COLS else ("" if col_name != "timestamp" else "2026-01-01 00:00")
                else:
                    last_row_data[col_name] = 0.0 if col_name not in STRING_COLS else ("" if col_name != "timestamp" else "2026-01-01 00:00")

            self.logger.log(f"[OK] 마지막 행 읽기 성공 (시간순 마지막: {ts})", level="INFO")
            self.logger.log(
                f"   AmountCH0={last_row_data.get('AmountCH0')}, AmountCH1={last_row_data.get('AmountCH1')}, AmountCH2={last_row_data.get('AmountCH2')}",
                level="INFO"
            )
            return ts, last_row_data

        except Exception as e:
            self.logger.log(f"[ERROR] 변환본 읽기 실패: {e}", level="ERROR")
            import traceback
            self.logger.log(f"   상세: {traceback.format_exc()}", level="ERROR")
        return None, None

    def _collect_target_lines(self, src_path, base_time):
        """
        원본 파일에서 base_time 이후 행만 수집
        
        시간 필터링 규칙:
        - 최소 연도: 2000년
        - 최대 연도: 현재 연도 + 1년
        - 파싱 불가능한 시간: 제외
        """
        from datetime import datetime
        
        lines = []
        skipped_count = 0
        skipped_old = 0  # 2000년 이전
        skipped_future = 0  # 미래 연도
        skipped_parse_error = 0  # 파싱 실패
        
        current_year = datetime.now().year
        max_year = current_year + 1  # 현재 + 1년까지 허용

        def _extract_first_field(raw_line: str) -> str:
            """
            원본 라인에서 timestamp 후보(첫 필드)를 최대한 안전하게 추출.
            - 다른 PC/로거에서 구분자가 ','가 아닐 수 있음(예: ';', 탭)
            - BOM/따옴표/공백 등 전처리
            """
            if raw_line is None:
                return ""
            s = str(raw_line).strip()
            if not s:
                return ""
            # BOM 제거
            s = s.lstrip("\ufeff")

            # 우선순위: 콤마 / 세미콜론 / 탭
            for sep in (",", ";", "\t"):
                if sep in s:
                    return s.split(sep, 1)[0].strip().strip('"').strip("'")

            # 구분자 탐지 실패: 공백으로만 구분된 경우도 있으니 첫 토큰만
            return s.split()[0].strip().strip('"').strip("'")

        # 자주 등장하는 포맷 순서 — strptime은 pandas보다 훨씬 빠름
        _FAST_FMTS = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
        )

        def _fast_parse(s: str):
            """strptime으로 빠르게 파싱, 실패 시 pd.to_datetime 폴백"""
            for fmt in _FAST_FMTS:
                try:
                    return pd.Timestamp(datetime.strptime(s, fmt))
                except ValueError:
                    continue
            # 폴백: 비표준 포맷 처리
            try:
                return pd.to_datetime(s, errors="coerce", format="mixed")
            except TypeError:
                return pd.to_datetime(s, errors="coerce")

        with open(src_path, "rb") as f:
            for raw in f:
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                first = _extract_first_field(line)
                if not first:
                    skipped_count += 1
                    skipped_parse_error += 1
                    continue

                ts = _fast_parse(first)

                # 시간 필터링
                if pd.isna(ts):
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

                # base_time 기준: 같은 시간대(슬롯) 포함 — 원본에 동일 시각이 없어도 비슷한 시간(같은 구간) 수집
                if base_time is None:
                    lines.append(line)
                else:
                    # base_time 이상 수집 (같은 시각·같은 구간 포함 → 매핑 단계에서 슬롯당 가장 가까운 행 사용)
                    if ts >= base_time:
                        lines.append(line)

        # 필터링 통계 로그
        if skipped_count > 0:
            self.logger.log(
                f"⚠️ 비정상 시간 데이터 제외: 총 {skipped_count}개 "
                f"(2000년 이전: {skipped_old}, {max_year}년 초과: {skipped_future}, 파싱 실패: {skipped_parse_error})",
                level="INFO"
            )

        return lines

    def _move_battery(self, df):
        """배터리 이동: 56열(batLevel) → 3열(battery)"""
        df = df.copy()

        # 원본 CSV의 컬럼 수 확인
        num_cols = df.shape[1]
        
        if num_cols < 57:
            # 56열(인덱스 56)이 없으면 0.0으로 채움
            self.logger.log(
                f"[배터리 이동] 컬럼 수 부족: {num_cols}개 (56열 필요). 배터리를 0.0으로 설정합니다.",
                level="WARN"
            )
            battery = pd.Series([0.0] * len(df), dtype="float64")
        else:
            # 56열에서 배터리 읽기
            try:
                battery = pd.to_numeric(df.iloc[:, 56], errors="coerce").fillna(0.0)
                self.logger.log(
                    f"[배터리 이동] 56열에서 배터리 읽기 성공. 평균값: {battery.mean():.2f}",
                    level="DEBUG"
                )
            except Exception as e:
                self.logger.log(
                    f"[배터리 이동] 56열 읽기 실패: {e}. 배터리를 0.0으로 설정합니다.",
                    level="WARN"
                )
                battery = pd.Series([0.0] * len(df), dtype="float64")

        # 3열에 배터리 값 할당 (dtype 호환성 보장)
        # 컬럼 이름을 사용하여 안전하게 할당 (FutureWarning 방지)
        col_name = df.columns[3]
        df[col_name] = battery.astype("float64")
        
        # 24개 컬럼만 남기기
        df = df.iloc[:, :24].copy()
        
        return df


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
                f"[INFO] 💾 저장 확인({context}): size={st.st_size} bytes, "
                f"mtime={datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')} - {out_path}",
                level="INFO",
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
                            f"[INFO] 📈 저장 결과({context}): rows={len(df)}, "
                            f"time_range={valid.min().strftime('%Y-%m-%d %H:%M')} ~ {valid.max().strftime('%Y-%m-%d %H:%M')}",
                            level="INFO",
                        )
                    else:
                        self.logger.log(
                            f"[WARN] 📈 저장 결과({context}): timestamp 유효행 0 - {out_path}",
                            level="WARN",
                        )
                except Exception:
                    pass
        except Exception:
            pass

    def apply_decimal(self, df, file_cfg):
        """채널별 소수점 설정 적용"""
        df = df.copy()

        for ch in range(8):
            col = 16 + ch
            ch_cfg = file_cfg.get(f"CH{ch}", {})
            dec = ch_cfg.get("decimal", "")

            if dec in ("", None):
                continue

            try:
                d = int(dec)
            except:
                continue

            df.iloc[:, col] = pd.to_numeric(df.iloc[:, col], errors="coerce").round(d)

        return df
    
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