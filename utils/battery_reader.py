# utils/battery_reader.py
import os


class BatteryReader:
    """
    Convert CSV(24컬럼)에서 마지막 유효 라인의 battery(3열)를 읽는다.
    - 읽기 전용
    - 마지막 줄 기준 (정렬/중복/누락 보정 없음)
    - 실패 시 None
    """

    def __init__(self, logger=None):
        self.logger = logger

    def read_last_battery(self, csv_path: str):
        if not csv_path or not os.path.exists(csv_path):
            return None

        try:
            with open(csv_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                buf = b""

                while pos > 0:
                    pos -= 1
                    f.seek(pos)
                    b = f.read(1)

                    if b == b"\n":
                        if not buf:
                            continue

                        line = buf[::-1].decode("utf-8", errors="ignore").strip()
                        buf = b""

                        if not line:
                            continue

                        # 헤더 라인 스킵
                        # (utf-8-sig BOM이 있을 수 있어 strip 처리)
                        if line.lower().startswith("timestamp,"):
                            continue

                        parts = line.split(",")
                        if len(parts) < 4:
                            continue

                        raw = parts[3].strip()
                        if raw == "":
                            return None

                        try:
                            return float(raw)
                        except Exception:
                            # battery가 숫자로 파싱 불가하면 None
                            return None

                    else:
                        buf += b

                # 파일이 '\n' 없이 끝난 경우 마지막 buf 처리
                if buf:
                    line = buf[::-1].decode("utf-8", errors="ignore").strip()
                    if line and (not line.lower().startswith("timestamp,")):
                        parts = line.split(",")
                        if len(parts) >= 4:
                            try:
                                return float(parts[3].strip())
                            except Exception:
                                return None

        except Exception as e:
            if self.logger:
                self.logger.log(f"[BatteryReader] 읽기 실패 → {csv_path} → {e}", level="WARN")

        return None
