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

        # 분 단위 중복 실행 방지
        self.last_convert_minute = None              # 자동 변환용
        self.last_interval_minute = {}               # gen_interval용

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
        매 20분마다 자동 변환 실행
        - 실행 시간: 1분, 21분, 41분
        - 같은 분 중복 실행 방지
        """
        RUN_MINUTES = {1, 21, 41}

        # 이미 이 분에 실행했으면 패스
        if self.last_convert_minute == now.minute:
            return

        # 설정된 분이면 실행
        if now.minute in RUN_MINUTES:
            _safe_log(self.logger, f"[Scheduler] 자동 변환 트리거 → convert_now() at {now.strftime('%H:%M')}")
            self.controller.convert_now()
            self.last_convert_minute = now.minute

    # ============================================================
    # __gen_interval__ 처리
    # ============================================================
    def _handle_gen_interval(self, now: datetime.datetime):
        cfg_data = self.controller.config.data

        for company, folders in cfg_data.items():
            if company.startswith("__") or not isinstance(folders, dict):
                continue

            for folder, folder_dict in folders.items():
                if folder.startswith("__") or not isinstance(folder_dict, dict):
                    continue

                abs_path = folder_dict.get("__absolute_path__", "")
                if not abs_path:
                    continue

                for filename, file_cfg in folder_dict.items():
                    if filename.startswith("__") or not isinstance(file_cfg, dict):
                        continue

                    interval = int(file_cfg.get("__gen_interval__", 0) or 0)
                    if interval <= 0:
                        continue

                    if now.minute % interval != 0:
                        continue

                    key = f"{company}/{folder}/{filename}"

                    if self.last_interval_minute.get(key) == now.minute:
                        continue

                    csv_path = os.path.join(abs_path, filename)
                    self._append_interval_row(csv_path)

                    _safe_log(
                        self.logger,
                        f"[Scheduler] gen_interval row 생성: {key} ({interval}분)"
                    )

                    self.last_interval_minute[key] = now.minute

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

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        new_row = {col: 0 for col in df.columns}
        if "timestamp" in df.columns:
            new_row["timestamp"] = now_str

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

        try:
            df.to_csv(csv_path, index=False)
        except Exception as e:
            _safe_log(self.logger, f"[Scheduler] CSV 저장 실패 → {e}", "ERROR")
