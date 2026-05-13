"""
===========================================================
[Convert_pro3] ManagementManager Module
-----------------------------------------------------------
📌 설계 의도

config.json (변환 전용) 과 분리된 관리 데이터를 management.json에 저장.

관리 데이터 (변환과 무관):
  - QM 관리자 목록
  - 업체별 담당자 목록
  - 현장별 메타 (주소, 프로그램, 점검주기, 보고설정 등)
  - 카테고리 (대분류 station_groups, 소분류 stations)
  - 로거-소분류 배정 (assignments: folder/filename → station_id)

management.json 구조:
{
    "__version__": 1,
    "qm_managers": [...],
    "companies": {
        "업체명": {
            "managers": [...],
            "sites": {
                "현장명": {
                    "address": "",
                    "program": "",
                    "memo": "",
                    "check_interval": 0,
                    "report_enabled": false,
                    "report_cycle": "",
                    "assigned_manager_id": "",
                    "assigned_qm_manager_id": "",
                    "station_groups": [...],
                    "stations": [...],
                    "assignments": { "폴더명/파일명.csv": "station_id" }
                }
            }
        }
    }
}

마이그레이션:
  - config.json 안의 관리 데이터를 management.json으로 이전
  - config.json에서 관리 필드 제거
  - 실행 전 config.json 자동 백업
  - management.json이 이미 존재하면 마이그레이션 스킵 (멱등성)
===========================================================
"""

import json
import os
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime


MGMT_VERSION = 1

# config.json 에서 추출할 현장 레벨 필드 → management.json 키 매핑
_SITE_FIELD_MAP = {
    "__site_address__":           "address",
    "__site_program__":           "program",
    "__site_memo__":              "memo",
    "__check_interval__":         "check_interval",
    "__report_enabled__":         "report_enabled",
    "__report_cycle__":           "report_cycle",
    "__assigned_manager_id__":    "assigned_manager_id",
    "__assigned_qm_manager_id__": "assigned_qm_manager_id",
    "__station_groups__":         "station_groups",
    "__stations__":               "stations",
}

# config.json 에서 제거할 최상위 레벨 필드
_ROOT_MGMT_FIELDS = {"__qm_managers__"}

# config.json 에서 제거할 업체 레벨 필드
_COMPANY_MGMT_FIELDS = {"__managers__"}

# config.json 파일 레벨에서 추출할 필드
_FILE_MGMT_FIELDS = {"__station_id__"}

# management.json 기본 구조
_DEFAULT_MGMT = {
    "__version__": MGMT_VERSION,
    "qm_managers": [],
    "companies": {}
}


def _empty_site_mgmt() -> dict:
    return {
        "address": "",
        "program": "",
        "memo": "",
        "check_interval": 0,
        "report_enabled": False,
        "report_cycle": "",
        "assigned_manager_id": "",
        "assigned_qm_manager_id": "",
        "station_groups": [],
        "stations": [],
        "assignments": {}
    }


class ManagementManager:
    """
    management.json 의 로드/저장/마이그레이션을 담당.

    사용 예 (Convert_pro3.py):
        self.mgmt = ManagementManager(base_dir, logger=self.logger)
        self.mgmt.migrate_from_config(config_path)   # 최초 1회

    사용 예 (server.py):
        _mgmt = ManagementManager(app_root)
        with _mgmt.edit() as m:
            m["companies"]["A"]["sites"]["B"]["stations"].append(...)
    """

    def __init__(self, base_dir: str, logger=None):
        self.path = os.path.join(base_dir, "management.json")
        self.logger = logger
        self._lock = threading.Lock()
        self.data: dict = {}
        self._load()

    # --------------------------------------------------
    # 로깅
    # --------------------------------------------------
    def _log(self, msg: str, level: str = "INFO"):
        if self.logger:
            self.logger.log(msg, level=level)
        else:
            print(f"[{level}] {msg}")

    # --------------------------------------------------
    # 로드 / 저장
    # --------------------------------------------------
    def _load(self):
        if not os.path.exists(self.path):
            self.data = {k: v for k, v in _DEFAULT_MGMT.items()}
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            self._log("management.json 로드 완료.")
        except Exception as e:
            self._log(f"management.json 로드 실패: {e}", level="ERROR")
            self.data = {k: v for k, v in _DEFAULT_MGMT.items()}

    def _save_raw(self, data: dict):
        """원자적 저장 (lock 내부에서 호출)."""
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
            raise

    def save(self):
        """management.json 원자적 저장 (Thread-safe)."""
        with self._lock:
            try:
                self._save_raw(self.data)
                self._log("management.json 저장 완료.")
            except Exception as e:
                self._log(f"management.json 저장 실패: {e}", level="ERROR")

    def reload(self):
        """파일에서 다시 로드 (외부에서 파일이 변경된 경우)."""
        with self._lock:
            self._load()

    @contextmanager
    def edit(self):
        """read-modify-write 전 구간을 락으로 직렬화하는 컨텍스트 매니저.
        예외 발생 시 저장하지 않는다.

        with mgmt.edit() as m:
            m["companies"]["A"]["sites"]["B"]["memo"] = "..."
        """
        with self._lock:
            self._load()          # 항상 최신 데이터로 시작
            try:
                yield self.data
            except Exception:
                raise
            else:
                self._save_raw(self.data)

    # --------------------------------------------------
    # 접근 헬퍼
    # --------------------------------------------------
    def get_site(self, company: str, site: str) -> dict | None:
        """현장 관리 데이터 반환. 없으면 None."""
        return (
            self.data.get("companies", {})
                     .get(company, {})
                     .get("sites", {})
                     .get(site)
        )

    def ensure_site(self, data: dict, company: str, site: str) -> dict:
        """data(edit() 안 dict) 에서 현장 노드를 보장하며 반환."""
        companies = data.setdefault("companies", {})
        comp = companies.setdefault(company, {"managers": [], "sites": {}})
        sites = comp.setdefault("sites", {})
        if site not in sites:
            sites[site] = _empty_site_mgmt()
        return sites[site]

    def ensure_company(self, data: dict, company: str) -> dict:
        companies = data.setdefault("companies", {})
        return companies.setdefault(company, {"managers": [], "sites": {}})

    def get_assignment(self, company: str, site: str, folder: str, filename: str) -> str:
        """파일의 station_id 반환. 없으면 ''."""
        site_m = self.get_site(company, site)
        if not site_m:
            return ""
        key = f"{folder}/{filename}"
        return site_m.get("assignments", {}).get(key, "")

    # --------------------------------------------------
    # 마이그레이션 (config.json → management.json)
    # --------------------------------------------------
    def migrate_from_config(self, config_path: str) -> bool:
        """
        config.json 안의 관리 데이터를 management.json으로 이전하고
        config.json에서 해당 필드를 제거한다.

        management.json이 이미 존재하면 스킵 (멱등성 보장).
        실패 시 config.json 백업을 복원한다.

        Returns:
            True  → 마이그레이션 실행됨
            False → 스킵(이미 존재) 또는 실패
        """
        if os.path.exists(self.path):
            self._log("management.json 이미 존재 → 마이그레이션 스킵.", level="INFO")
            return False

        if not os.path.exists(config_path):
            self._log("config.json 없음 → 마이그레이션 생략.", level="WARN")
            self.save()
            return False

        # ── 1. config.json 백업 ──────────────────────────────
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = config_path + f".backup_pre_mgmt_{ts}"
        try:
            shutil.copy2(config_path, backup_path)
            self._log(f"[Migration] config.json 백업 완료: {backup_path}")
        except Exception as e:
            self._log(f"[Migration] 백업 실패: {e}", level="ERROR")
            return False

        # ── 2. config.json 로드 ──────────────────────────────
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            self._log(f"[Migration] config.json 읽기 실패: {e}", level="ERROR")
            return False

        # ── 3. 관리 데이터 추출 → management.json 구성 ────────
        mgmt = {
            "__version__": MGMT_VERSION,
            "qm_managers": cfg.get("__qm_managers__", []),
            "companies": {}
        }

        for company, company_val in cfg.items():
            if company.startswith("__") or not isinstance(company_val, dict):
                continue

            comp_mgmt = {
                "managers": company_val.get("__managers__", []),
                "sites": {}
            }

            for site, site_val in company_val.items():
                if site.startswith("__") or not isinstance(site_val, dict):
                    continue

                site_mgmt = _empty_site_mgmt()

                # 현장 메타 필드 이전
                for cfg_key, mgmt_key in _SITE_FIELD_MAP.items():
                    if cfg_key in site_val:
                        site_mgmt[mgmt_key] = site_val[cfg_key]

                # 파일별 station_id → assignments 이전
                for folder, folder_val in site_val.items():
                    if folder.startswith("__") or not isinstance(folder_val, dict):
                        continue
                    for filename, file_cfg in folder_val.items():
                        if filename.startswith("__") or not isinstance(file_cfg, dict):
                            continue
                        sid = file_cfg.get("__station_id__", "")
                        if sid:
                            site_mgmt["assignments"][f"{folder}/{filename}"] = sid

                comp_mgmt["sites"][site] = site_mgmt

            mgmt["companies"][company] = comp_mgmt

        # ── 4. management.json 저장 ───────────────────────────
        try:
            self.data = mgmt
            with self._lock:
                self._save_raw(self.data)
            self._log("[Migration] management.json 생성 완료.")
        except Exception as e:
            self._log(f"[Migration] management.json 저장 실패: {e}", level="ERROR")
            return False

        # ── 5. config.json에서 관리 필드 제거 ────────────────
        try:
            self._strip_mgmt_fields_from_config(cfg)
            tmp = config_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
            os.replace(tmp, config_path)
            self._log("[Migration] config.json 관리 필드 제거 완료.")
        except Exception as e:
            self._log(f"[Migration] config.json 정리 실패: {e}  (management.json은 유지됨)", level="WARN")

        self._log("[Migration] 완료. config.json(변환 전용) + management.json(관리 전용) 분리됨.")
        return True

    @staticmethod
    def _strip_mgmt_fields_from_config(cfg: dict):
        """cfg dict를 in-place로 수정하여 관리 필드를 제거."""
        # 최상위 관리 필드 제거
        for field in _ROOT_MGMT_FIELDS:
            cfg.pop(field, None)

        for company, company_val in cfg.items():
            if company.startswith("__") or not isinstance(company_val, dict):
                continue

            # 업체 레벨 관리 필드 제거
            for field in _COMPANY_MGMT_FIELDS:
                company_val.pop(field, None)

            for site, site_val in company_val.items():
                if site.startswith("__") or not isinstance(site_val, dict):
                    continue

                # 현장 레벨 관리 필드 제거
                for cfg_key in _SITE_FIELD_MAP:
                    site_val.pop(cfg_key, None)

                # 파일 레벨 station_id 제거
                for folder, folder_val in site_val.items():
                    if folder.startswith("__") or not isinstance(folder_val, dict):
                        continue
                    for filename, file_cfg in folder_val.items():
                        if filename.startswith("__") or not isinstance(file_cfg, dict):
                            continue
                        for field in _FILE_MGMT_FIELDS:
                            file_cfg.pop(field, None)
