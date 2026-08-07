import threading
import time
import datetime
import os


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
      FileProcessor.append_gen_interval_source_row() 로 원본 행 추가

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
            _safe_log(
                self.logger,
                f"[Scheduler] 자동 변환 트리거 → convert_now() at {now.strftime('%H:%M')}",
                "DEBUG",
            )
            self.controller.convert_now()
            self.last_convert_minute = current_hm

    # ============================================================
    # __gen_interval__ 처리
    # ============================================================
    def _handle_gen_interval(self, now: datetime.datetime):
        """gen_interval 처리 (Site 레벨 포함) — FileProcessor에 위임"""
        cfg_data = self.controller.config.data
        fp = getattr(self.controller, "file_processor", None)
        if fp is None:
            return

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

                        time_key = (now.hour, now.minute)
                        if self.last_interval_time.get(key) == time_key:
                            continue

                        csv_path = os.path.join(abs_path, filename)
                        if fp.append_gen_interval_source_row(csv_path):
                            _safe_log(
                                self.logger,
                                f"[Scheduler] gen_interval row 생성: {key} ({interval}분)",
                                "DEBUG",
                            )

                        self.last_interval_time[key] = time_key
