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
import pandas as pd
from datetime import datetime
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
        """전체 파일 변환 (UI/Scheduler 호출)"""
        self.logger.log("전체 파일 변환 시작", level="DEBUG")

        for company, folders in self.config.data.items():
            if company.startswith("__"):
                continue

            for folder, folder_cfg in folders.items():
                if folder.startswith("__"):
                    continue

                for filename in folder_cfg:
                    if filename.lower().endswith(".csv"):
                        self.convert_file(company, folder, filename)

        self.logger.log("전체 파일 변환 종료", level="DEBUG")

    def convert_file(self, company, folder, filename):
        """파일 단위 변환"""
        self.logger.log(f"파일 변환 시작: {company}/{folder}/{filename}", level="DEBUG")

        folder_cfg = self.config.data[company][folder]
        src_path = os.path.join(folder_cfg["__absolute_path__"], filename)

        if not os.path.exists(src_path):
            self.logger.log(f"원본 없음 → 스킵: {company}/{folder}/{filename}", level="DEBUG")
            return

        out_path = os.path.join(self.convert_root, company, folder, filename)

        # 1단계: 마지막 변환 시점 확인
        base_time = self._get_last_converted_time(out_path)

        # 2단계: 변환 대상 행 수집 (base_time 이후 데이터)
        lines = self._collect_target_lines(src_path, base_time)

        self.logger.log(f"기준 변환 시간: {base_time}", level="DEBUG")
        self.logger.log(f"변환 대상 행 수: {len(lines)}", level="DEBUG")

        # 3단계: DataFrame 생성
        if lines:
            df = pd.read_csv(
                StringIO("\n".join(lines)),
                header=None,
                engine="python",
                on_bad_lines="skip"
            )

            if df.empty:
                self.logger.log("DataFrame 비어있음 → 스킵", level="DEBUG")
                return
        else:
            self.logger.log(f"변환 대상 없음 → 스킵: {company}/{folder}/{filename}", level="DEBUG")
            return

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 📌 변환 파이프라인 (Core Transform)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # 4단계: 배터리 이동 (56열 → 3열)
        df = self._move_battery(df)

        # 5단계: 센서 처리 (보정값 적용)
        file_cfg = self.config.data.get(company, {}).get(folder, {}).get(filename, {})
        df = self.sensor.process(df, file_cfg)
        
        # 6단계: 소수점 처리
        df = self.apply_decimal(df, file_cfg)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔧 선택적 기능 (Optional Features)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # Fill Interval: 시간 간격 기반 누락 보충
        interval = file_cfg.get("__fill_interval__", 0)
        if interval > 0:
            df = self.fill_interval.process(df, interval)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 💾 저장
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        self._save_append(df, out_path)
        self.logger.log(f"파일 변환 완료: {company}/{folder}/{filename}", level="DEBUG")

    def _get_last_converted_time(self, out_path):
        """변환본 마지막 행의 timestamp 추출"""
        if not os.path.exists(out_path):
            return None

        try:
            with open(out_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                buf = b""
                pos = f.tell()

                while pos > 0:
                    pos -= 1
                    f.seek(pos)
                    b = f.read(1)

                    if b == b"\n":
                        if buf:
                            line = buf[::-1].decode("utf-8", errors="ignore")
                            ts = pd.to_datetime(line.split(",")[0], errors="coerce")
                            if pd.notna(ts):
                                return ts
                            buf = b""
                    else:
                        buf += b
        except Exception as e:
            self.logger.log(f"[FP] 기준 시간 읽기 실패 → {e}", level="WARN")

        return None

    def _collect_target_lines(self, src_path, base_time):
        """원본 파일에서 base_time 이후 행만 수집"""
        lines = []

        with open(src_path, "rb") as f:
            for raw in f:
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                parts = line.split(",")
                if not parts:
                    continue

                ts = pd.to_datetime(parts[0], errors="coerce")

                if pd.isna(ts) or ts.year < 2000:
                    continue

                if base_time is None:
                    lines.append(line)
                else:
                    if ts > base_time:
                        lines.append(line)

        return lines

    def _move_battery(self, df):
        """배터리 이동: 56열(batLevel) → 3열(battery)"""
        df = df.copy()

        try:
            battery = pd.to_numeric(df.iloc[:, 56], errors="coerce").fillna(0).to_numpy(dtype="float64")
        except Exception:
            battery = 0.0

        df.iloc[:, 3] = battery
        df = df.iloc[:, :24].copy()

        return df

    def _save_append(self, df, out_path):
        """변환본 저장 (최초: 생성, 이후: append)"""
        out_dir = os.path.dirname(out_path)
        os.makedirs(out_dir, exist_ok=True)

        df.columns = STANDARD_HEADER

        if not os.path.exists(out_path):
            df.to_csv(out_path, index=False, header=True, encoding="utf-8-sig")
            return

        with open(out_path, "a", encoding="utf-8-sig", newline="") as f:
            df.to_csv(f, index=False, header=False)

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
