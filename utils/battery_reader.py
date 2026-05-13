# utils/battery_reader.py
import os


class BatteryReader:
    """
    변환된 CSV 파일에서 마지막 행의 4번째 열(인덱스 3)에서 배터리 값을 읽는다.
    - 변환본 구조: timestamp, deviceId, STX, battery, ...
    - 변환할 때만 읽으면 됨 (변환 후 배터리 갱신)
    """

    def __init__(self, logger=None):
        self.logger = logger

    def read_last_battery(self, csv_path: str):
        """
        변환된 CSV 파일의 마지막 행에서 4번째 열(인덱스 3)의 배터리 값을 읽는다.
        """
        if not csv_path or not os.path.exists(csv_path):
            if self.logger:
                self.logger.log(f"[BatteryReader] 파일 없음: {csv_path}", level="DEBUG")
            return None

        try:
            # 파일 끝에서부터 역순으로 읽어서 마지막 행 찾기
            with open(csv_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                buf = b""

                # 최대 10KB만 역순으로 읽기 (성능 최적화)
                max_read = min(pos, 10240)
                start_pos = max(0, pos - max_read)

                while pos > start_pos:
                    pos -= 1
                    f.seek(pos)
                    b = f.read(1)

                    if b == b"\n":
                        if not buf:
                            continue

                        # 역순으로 읽었으므로 뒤집기
                        line = buf[::-1].decode("utf-8", errors="ignore").strip()
                        buf = b""

                        if not line or line.lower().startswith("timestamp,"):
                            continue

                        # CSV 파싱: 4번째 열(인덱스 3) 읽기
                        # 쉼표로 분리하되, 따옴표 안의 쉼표는 무시
                        parts = []
                        current = ""
                        in_quotes = False
                        
                        for char in line:
                            if char == '"':
                                in_quotes = not in_quotes
                            elif char == ',' and not in_quotes:
                                parts.append(current)
                                current = ""
                            else:
                                current += char
                        parts.append(current)  # 마지막 부분
                        
                        if len(parts) >= 4:
                            raw = parts[3].strip().strip('"')
                            if raw:
                                try:
                                    battery_value = float(raw)
                                    if self.logger:
                                        self.logger.log(
                                            f"[BatteryReader] 배터리 읽기 성공: {csv_path} → {battery_value}%",
                                            level="DEBUG"
                                        )
                                    return battery_value
                                except (ValueError, TypeError) as e:
                                    if self.logger:
                                        self.logger.log(
                                            f"[BatteryReader] 배터리 값 변환 실패: {csv_path}, 값: '{raw}', 오류: {e}",
                                            level="DEBUG"
                                        )

                    else:
                        buf += b

                # 파일이 '\n' 없이 끝난 경우
                if buf:
                    line = buf[::-1].decode("utf-8", errors="ignore").strip()
                    if line and not line.lower().startswith("timestamp,"):
                        # CSV 파싱 (위와 동일)
                        parts = []
                        current = ""
                        in_quotes = False
                        
                        for char in line:
                            if char == '"':
                                in_quotes = not in_quotes
                            elif char == ',' and not in_quotes:
                                parts.append(current)
                                current = ""
                            else:
                                current += char
                        parts.append(current)
                        
                        if len(parts) >= 4:
                            try:
                                raw = parts[3].strip().strip('"')
                                if raw:
                                    battery_value = float(raw)
                                    if self.logger:
                                        self.logger.log(
                                            f"[BatteryReader] 배터리 읽기 성공 (마지막 행): {csv_path} → {battery_value}%",
                                            level="DEBUG"
                                        )
                                    return battery_value
                            except (ValueError, TypeError):
                                pass

        except Exception as e:
            if self.logger:
                self.logger.log(
                    f"[BatteryReader] 배터리 읽기 오류: {csv_path}, 오류: {e}",
                    level="ERROR"
                )

        if self.logger:
            self.logger.log(f"[BatteryReader] 배터리 읽기 실패: {csv_path}", level="DEBUG")
        return None
