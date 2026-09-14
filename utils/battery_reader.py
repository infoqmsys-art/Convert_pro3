# utils/battery_reader.py
"""변환본 CSV에서 마지막 행의 battery(인덱스 3) 읽기."""
from __future__ import annotations

import os

from utils.battery import OUT_BATTERY_COL, parse_battery_cell


class BatteryReader:
    """
    변환된 CSV 파일에서 마지막 데이터 행의 battery(4번째 열)를 읽는다.
    - 성공: float (0.0 포함 — 파일에 진짜 0이 있을 때)
    - 파일 없음·열 없음·파싱 실패: None  (UI는 "—" 로 표시)
    """

    def __init__(self, logger=None):
        self.logger = logger

    def read_last_battery(self, csv_path: str) -> float | None:
        if not csv_path or not os.path.exists(csv_path):
            if self.logger:
                self.logger.log(f"[BatteryReader] 파일 없음: {csv_path}", level="DEBUG")
            return None

        try:
            with open(csv_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                if pos <= 0:
                    return None

                buf = b""
                max_read = min(pos, 10240)
                start_pos = max(0, pos - max_read)

                while pos > start_pos:
                    pos -= 1
                    f.seek(pos)
                    b = f.read(1)

                    if b == b"\n":
                        if not buf:
                            continue
                        line = buf[::-1].decode("utf-8", errors="ignore").strip()
                        buf = b""
                        val = self._battery_from_line(line, csv_path)
                        if val is not None or self._is_header_line(line):
                            if self._is_header_line(line):
                                continue
                            return val
                    else:
                        buf += b

                if buf:
                    line = buf[::-1].decode("utf-8", errors="ignore").strip()
                    if line and not self._is_header_line(line):
                        return self._battery_from_line(line, csv_path)

        except Exception as e:
            if self.logger:
                self.logger.log(
                    f"[BatteryReader] 오류: {csv_path}, {e}",
                    level="ERROR",
                )
            return None

        if self.logger:
            self.logger.log(f"[BatteryReader] 데이터 행 없음: {csv_path}", level="DEBUG")
        return None

    @staticmethod
    def _is_header_line(line: str) -> bool:
        low = line.lower()
        return low.startswith("timestamp,") or low.startswith("timestamp;")

    def _battery_from_line(self, line: str, csv_path: str) -> float | None:
        if not line:
            return None
        parts = self._split_csv_line(line)
        if len(parts) <= OUT_BATTERY_COL:
            if self.logger:
                self.logger.log(
                    f"[BatteryReader] 열 부족 ({len(parts)}): {csv_path}",
                    level="DEBUG",
                )
            return None
        val = parse_battery_cell(parts[OUT_BATTERY_COL])
        if val is None:
            if self.logger:
                self.logger.log(
                    f"[BatteryReader] 배터리 칸 비어있음/비숫자: {csv_path}",
                    level="DEBUG",
                )
            return None
        if self.logger:
            self.logger.log(
                f"[BatteryReader] OK: {csv_path} → {val}%",
                level="DEBUG",
            )
        return val

    @staticmethod
    def _split_csv_line(line: str) -> list[str]:
        parts: list[str] = []
        current = ""
        in_quotes = False
        for char in line:
            if char == '"':
                in_quotes = not in_quotes
            elif char == "," and not in_quotes:
                parts.append(current)
                current = ""
            else:
                current += char
        parts.append(current)
        return parts
