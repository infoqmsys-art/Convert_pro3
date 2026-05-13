import threading
import time
import datetime
import os
import pandas as pd


def _safe_log(logger, msg, level="INFO"):
    if logger:
        logger.log(msg, level=level)
    else:
        print(f"[{level}] {msg}")


class SchedulerManager:
    """
    Convert Pro 3 Scheduler Manager

    역할:
    - 주기적으로 변환 트리거(convert_now)
    - __gen_interval__ 설정이 있는 파일에 대해
      주기적 0값 row 생성 (임시 구조)

    주의:
    - second == 0 같은 정확한 초 조건 ❌
    - 분 단위 중복 방지 방식으로 안정성 확보
    """

    def __init__(self, controller, logger=None):
        self.controller = controller      # ConvertPro3App
        self.logger = logger
        self.thread = None
        self.running = False

        # 중복 실행 방지 (hour+minute 튜플 — minute만 저장 시 매시 5분마다 스킵되는 버그 방지)
        self.last_convert_minute = None              # 자동 변환용
        self.last_interval_time = {}                 # gen_interval용 (시간+분 저장)

    # ============================================================
    # 스케줄러 시작 / 종료
    # ============================================================
    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        _safe_log(self.logger, "[Scheduler] 스케줄러 시작됨")

    def stop(self):
        self.running = False
        _safe_log(self.logger, "[Scheduler] 스케줄러 종료됨")

    # ============================================================
    # 메인 루프
    # ============================================================
    def _run(self):
        while self.running:
            try:
                now = datetime.datetime.now()

                # ① __gen_interval__ 처리
                self._handle_gen_interval(now)

                # ② 자동 변환 트리거 (예: 매 15분)
                self._handle_auto_convert(now)

            except Exception as e:
                _safe_log(self.logger, f"[Scheduler] 루프 오류: {e}", "ERROR")

            time.sleep(1)

    # ============================================================
    # 자동 변환 처리 (안정형)
    # ============================================================
    def _handle_auto_convert(self, now: datetime.datetime):
        """
        config.json __scheduler__.auto_convert_minutes 분에 맞춰 자동 변환.
        기본 [5,25,45]. 빈 목록이면 자동 변환 없음. 같은 시+분 중복 실행 방지.
        """
        try:
            mins = self.controller.config.get_auto_convert_minutes()
        except Exception:
            mins = [5, 25, 45]
        run_minutes = set(mins)
        if not run_minutes:
            return

        # 이미 이 시각(시+분)에 실행했으면 패스
        current_hm = (now.hour, now.minute)
        if self.last_convert_minute == current_hm:
            return

        # 설정된 분이면 실행
        if now.minute in run_minutes:
            _safe_log(self.logger, f"[Scheduler] 자동 변환 트리거 → convert_now() at {now.strftime('%H:%M')}")
            self.controller.convert_now()
            self.last_convert_minute = current_hm

    # ============================================================
    # __gen_interval__ 처리
    # ============================================================
    def _handle_gen_interval(self, now: datetime.datetime):
        """gen_interval 처리 (Site 레벨 포함)"""
        cfg_data = self.controller.config.data

        for company, sites in cfg_data.items():
            if company.startswith("__") or not isinstance(sites, dict):
                continue

            for site_name, site_data in sites.items():
                if site_name.startswith("__") or not isinstance(site_data, dict):
                    continue

                for folder, folder_dict in site_data.items():
                    if folder.startswith("__") or not isinstance(folder_dict, dict):
                        continue

                    abs_path = folder_dict.get("__absolute_path__", "")
                    if not abs_path:
                        continue

                    for filename, file_cfg in folder_dict.items():
                        # 파일명은 .csv로 끝나고, file_cfg는 dict여야 함
                        if filename.startswith("__") or not filename.lower().endswith(".csv"):
                            continue
                        
                        if not isinstance(file_cfg, dict):
                            continue

                        interval = int(file_cfg.get("__gen_interval__", 0) or 0)
                        if interval <= 0:
                            continue

                        if now.minute % interval != 0:
                            continue

                        key = f"{company}/{site_name}/{folder}/{filename}"

                        # 시간+분 조합으로 중복 체크 (60분 주기 문제 해결)
                        time_key = (now.hour, now.minute)
                        if self.last_interval_time.get(key) == time_key:
                            continue

                        csv_path = os.path.join(abs_path, filename)
                        self._append_interval_row(csv_path)

                        _safe_log(
                            self.logger,
                            f"[Scheduler] gen_interval row 생성: {key} ({interval}분)"
                        )

                        self.last_interval_time[key] = time_key

    # ============================================================
    # 0값 row append (임시 구조)
    # ============================================================
    def _append_interval_row(self, csv_path: str):
        """
        - CSV 파일을 직접 읽고
        - 현재 시각 timestamp + 나머지 0값 row 추가
        ⚠️ 추후 FileProcessor로 통합 예정
        """

        if not os.path.exists(csv_path):
            _safe_log(self.logger, f"[Scheduler] CSV 없음 → {csv_path}", "WARNING")
            return

        try:
            df = pd.read_csv(csv_path, sep=None, engine="python", on_bad_lines="skip")
        except Exception as e:
            _safe_log(self.logger, f"[Scheduler] CSV 읽기 실패 → {e}", "ERROR")
            return

        if df.empty:
            return

        # 경로에서 폴더명(B열)과 파일명 확장자 제외(F열) 추출
        folder_name = os.path.basename(os.path.dirname(csv_path))
        file_stem   = os.path.splitext(os.path.basename(csv_path))[0]

        # B열(index 1), F열(index 5) 컬럼명
        b_col = df.columns[1] if len(df.columns) > 1 else None
        f_col = df.columns[5] if len(df.columns) > 5 else None

        # 시간은 분 단위로 반올림(초 제거)하여 timestamp 칼럼에 채움
        now_min = datetime.datetime.now().replace(second=0, microsecond=0)
        now_str = now_min.strftime("%Y-%m-%d %H:%M")

        # 모든 비시간 컬럼은 0으로 채우고, 시간 컬럼만 현재 시각으로 설정
        new_row = {}
        # timestamp 컬럼 찾기 (없으면 첫 번째 컬럼 사용)
        time_col = None
        if "timestamp" in df.columns:
            time_col = "timestamp"
        elif len(df.columns) > 0:
            time_col = df.columns[0]

        # BG라는 헤더가 있으면 그 칼럼 위치까지(포함) 0으로 채우고,
        # 없으면 기존 동작(모든 칼럼을 0)과 동일하게 마지막 칼럼까지 0으로 채움.
        # BG는 엑셀식 열 문자('A'..'Z', 'AA'..)로 해석하여 위치 계산
        def _excel_col_to_index(col_label: str) -> int:
            if not isinstance(col_label, str) or col_label == "":
                return 0
            col_label = col_label.upper().strip()
            idx = 0
            for ch in col_label:
                if 'A' <= ch <= 'Z':
                    idx = idx * 26 + (ord(ch) - ord('A') + 1)
                else:
                    # 비정상 문자면 중단
                    break
            return max(0, idx - 1)

        # 사용자가 의도한 엑셀 열(여기서는 'BG')까지 0으로 채움
        target_excel_label = "BG"
        try:
            excel_idx = _excel_col_to_index(target_excel_label)
            bg_index = min(excel_idx, len(df.columns) - 1)
        except Exception:
            bg_index = len(df.columns) - 1

        for i, col in enumerate(df.columns):
            if time_col and col == time_col:
                new_row[col] = now_str
            elif b_col and col == b_col:
                new_row[col] = folder_name   # B열: 업체 폴더명
            elif f_col and col == f_col:
                new_row[col] = file_stem     # F열: 파일명(확장자 제외)
            else:
                if i <= bg_index:
                    new_row[col] = 0
                else:
                    # BG 이후 칼럼은 변경하지 않음(빈값으로 남김)
                    new_row[col] = ""

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

        try:
            df.to_csv(csv_path, index=False)
        except Exception as e:
            _safe_log(self.logger, f"[Scheduler] CSV 저장 실패 → {e}", "ERROR")
