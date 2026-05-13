"""
===========================================================
[Convert_pro3] ConfigManager Module (최종 통합 구조)
-----------------------------------------------------------
📌 설계 의도 (Design Intent)

이 모듈은 Convert_pro3의 설정 파일(config.json)을
일관된 구조로 관리하는 기능 전용 Core 모듈이다.

✔ TreeManager / FileProcessor / SensorProcessor가 모두 공통으로
  사용하는 데이터 구조를 보장한다.

✔ 구조 정의:
   회사(Company, UI 그룹)
      └── 업체폴더(Folder, 실제 경로명)
            └── 로거파일(LoggerFile, CSV)
                  └── CH0~CH7 (채널 설정)

✔ config.json은 프로그램의 단일 설정 저장소이며
  이 모듈만이 읽기/저장/보정 책임을 진다.

채널 설정은 'mode + parameters' 구조를 따른다.

1. mode
- 채널이 수행할 동작을 의미한다.
- 예: PASS, OFFSET, SCALE, INITIAL, EL, CR, V, SET, COPY 등
- 하나의 채널에는 반드시 하나의 mode만 적용된다.

2. parameters
- mode 수행 시 참고하는 값들이다.
- mode에 따라 사용/미사용이 결정된다.

  - base    : 기준값 / 오프셋 값
  - scale   : 배율
  - initial : 초기 기준값
  - decimal : 출력 소수점 자리수 (후처리, mode 아님)

3. 주의사항
- 과거 config에서는 'offset'이라는 키를 mode 용도로 사용했으나,
  이는 명명 오류이며 개념적으로는 'mode'가 올바른 표현이다.
- 향후 config 구조는 'offset' 대신 'mode'를 기준으로 정리한다.

===========================================================
"""

import json
import os
import threading


DEFAULT_STRUCTURE = {
    "__version__": 2  # 버전 2: Site 레벨 추가
}


class ConfigManager:
    """
    Convert_pro3의 설정 파일 관리 엔진.
    
    data 구조 예:
    {
        "__version__": 1,
        "새길이엔씨": {
            "SAEGL03504": {
                "__note__": "",
                "__absolute_path__": "C:/data/SAEGL03504",
                "1227998430.csv": {
                    "__fill_interval__": 0,
                    "__gen_interval__": 0,
                    "CH0": {...}, "CH1": {...}, ...
                }
            }
        }
    }
    """

    def __init__(self, path="config.json", logger=None):
        self.path = path
        self.logger = logger
        self.data = {}
        self.save_lock = threading.Lock()  # Thread-safe 저장을 위한 락

        # 미등록 파일 목록은 별도 파일로 관리
        self.unregistered_files_path = os.path.join(
            os.path.dirname(path), 
            "unregistered_files.json"
        )

        self.load()
        self._auto_correct_structure()
        self._migrate_unregistered_files()  # 기존 config.json의 미등록 파일을 별도 파일로 마이그레이션
        self.save()

    # -----------------------------------------------------
    # Logging helper
    # -----------------------------------------------------
    def _log(self, msg, level="INFO"):
        if self.logger:
            self.logger.log(msg, level=level)
        else:
            print(f"[{level}] {msg}")

    # -----------------------------------------------------
    # Load / Save
    # -----------------------------------------------------
    def load(self, quiet=False):
        """config.json 로딩. quiet=True면 웹 등 외부 반영용 재로드(로그 생략)."""
        if not os.path.exists(self.path):
            if not quiet:
                self._log("config.json 없음 → 새 파일 생성.")
            self.data = DEFAULT_STRUCTURE.copy()
            self.save()
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            if not quiet:
                self._log("config.json 로딩 완료.")
            
            # 마이그레이션 전 버전 확인 및 백업
            old_version = self.data.get("__version__", 1)
            if old_version < 2:
                self._backup_before_migration()
            
            # 구조 보정 및 마이그레이션
            self._auto_correct_structure()
            
            # 마이그레이션 후 검증 및 저장
            if old_version < 2:
                if self._verify_migration():
                    self.save()
                    self._log("[ConfigManager] 마이그레이션 완료 및 저장됨", level="INFO")
                else:
                    self._log("[ConfigManager] 마이그레이션 검증 실패 - 백업에서 복원 권장", level="ERROR")
        except Exception as e:
            self._log(f"config 로딩 실패: {e}", level="ERROR")
            self.data = DEFAULT_STRUCTURE.copy()

    def save(self):
        """config.json 원자적 저장 (Thread-safe).

        임시 파일에 먼저 기록 후 os.replace()로 교체하여
        Flask 웹 서버의 동시 쓰기가 발생해도 파일이 깨지지 않는다.
        """
        with self.save_lock:
            tmp = self.path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=4, ensure_ascii=False)
                os.replace(tmp, self.path)
                self._log("config 저장 완료.")
            except Exception as e:
                self._log(f"config 저장 실패: {e}", level="ERROR")
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    pass

    # -----------------------------------------------------
    # 자동 변환 스케줄 (__scheduler__ — 회사/현장과 별도 최상위 키)
    # -----------------------------------------------------
    def get_auto_convert_minutes(self) -> list[int]:
        """
        매 정시가 아니라 '매 시각의 분' 목록. 예: [5,25,45] → 각 시 05, 25, 45분에 convert_now.
        키가 없으면 기본 [5,25,45]. 빈 리스트는 자동 변환 끔.
        """
        sch = self.data.get("__scheduler__")
        if not isinstance(sch, dict):
            return [5, 25, 45]
        if "auto_convert_minutes" not in sch:
            return [5, 25, 45]
        raw = sch.get("auto_convert_minutes")
        if raw is None:
            return [5, 25, 45]
        if isinstance(raw, list) and len(raw) == 0:
            return []
        if not isinstance(raw, list):
            return [5, 25, 45]
        out: list[int] = []
        for x in raw:
            try:
                v = int(x)
            except (TypeError, ValueError):
                continue
            if 0 <= v <= 59:
                out.append(v)
        return sorted(set(out))

    def get_web_patch_repo_path(self) -> str:
        """웹 패치용 git 저장소 경로 반환. 미설정 시 빈 문자열."""
        sys_cfg = self.data.get("__system__")
        if not isinstance(sys_cfg, dict):
            return ""
        return str(sys_cfg.get("web_patch_repo_path") or "")

    def set_web_patch_repo_path(self, path: str) -> None:
        """웹 패치 저장소 경로 저장."""
        if "__system__" not in self.data or not isinstance(self.data.get("__system__"), dict):
            self.data["__system__"] = {}
        self.data["__system__"]["web_patch_repo_path"] = str(path)
        self.save()

    def set_auto_convert_minutes(self, minutes: list[int]) -> tuple[bool, str]:
        """분 단위 목록(0~59) 저장. 빈 리스트면 자동 변환 비활성."""
        clean: list[int] = []
        for m in minutes:
            try:
                v = int(m)
            except (TypeError, ValueError):
                return False, f"숫자가 아닌 값이 있습니다: {m!r}"
            if v < 0 or v > 59:
                return False, f"분은 0~59만 가능합니다 ({v})."
            clean.append(v)
        clean = sorted(set(clean))
        if "__scheduler__" not in self.data or not isinstance(self.data.get("__scheduler__"), dict):
            self.data["__scheduler__"] = {}
        self.data["__scheduler__"]["auto_convert_minutes"] = clean
        self.save()
        return True, ""

    # -----------------------------------------------------
    # Structure auto-fix
    # -----------------------------------------------------
    def _auto_correct_structure(self):
        """최소한의 필드 보정 및 버전 마이그레이션"""
        if "__version__" not in self.data:
            self.data["__version__"] = 1
        
        # 버전 1 → 2 마이그레이션 (Site 레벨 추가)
        if self.data.get("__version__", 1) < 2:
            self._migrate_v1_to_v2()
    
    def _migrate_unregistered_files(self):
        """config.json의 __unregistered_files__를 별도 파일로 마이그레이션"""
        if "__unregistered_files__" not in self.data:
            return
        
        unregistered_list = self.data.get("__unregistered_files__", [])
        if not unregistered_list:
            # 빈 배열이면 그냥 제거
            self.data.pop("__unregistered_files__", None)
            return
        
        # 기존 별도 파일이 있으면 병합, 없으면 그대로 이동
        existing_files = self._load_unregistered_files()
        existing_paths = {
            (item.get("folder_path"), item.get("filename"))
            for item in existing_files
        }
        
        # 중복 제거하며 병합
        for item in unregistered_list:
            key = (item.get("folder_path"), item.get("filename"))
            if key not in existing_paths:
                existing_files.append(item)
                existing_paths.add(key)
        
        # 별도 파일로 저장
        self._save_unregistered_files(existing_files)
        
        # config.json에서 제거
        self.data.pop("__unregistered_files__", None)
        
        if unregistered_list:
            self._log(
                f"[ConfigManager] 미등록 파일 {len(unregistered_list)}개를 별도 파일로 마이그레이션 완료",
                level="INFO"
            )

    # -----------------------------------------------------
    # Migration Functions
    # -----------------------------------------------------
    def _migrate_v1_to_v2(self):
        """버전 1 → 2 마이그레이션: Site 레벨 추가"""
        self._log("[ConfigManager] 버전 1 → 2 마이그레이션 시작", level="INFO")
        
        for company, company_data in list(self.data.items()):
            if company.startswith("__") or not isinstance(company_data, dict):
                continue
            
            # Default 현장 생성
            if "Default" not in company_data or not isinstance(company_data.get("Default"), dict):
                company_data["Default"] = {
                    "__note__": "마이그레이션된 기본 현장"
                }
                self._log(f"[ConfigManager] Default 현장 생성: {company}")
            
            default_site = company_data["Default"]
            
            # 기존 폴더들을 Default 현장으로 이동
            folders_to_move = []
            for key, value in company_data.items():
                if key == "Default" or key.startswith("__"):
                    continue
                
                # 폴더인지 확인 (CSV 파일을 포함하고 있거나 __absolute_path__가 있으면 폴더)
                if isinstance(value, dict):
                    has_csv = any(k.endswith(".csv") for k in value.keys())
                    has_path = "__absolute_path__" in value
                    
                    if has_csv or has_path:
                        folders_to_move.append((key, value))
            
            # 폴더 이동
            for folder_name, folder_data in folders_to_move:
                default_site[folder_name] = folder_data
                del company_data[folder_name]
                self._log(f"[ConfigManager] 폴더 이동: {company}/{folder_name} → Default")
            
            # 모든 파일에 __order__ 추가
            self._add_order_to_files(company, "Default")
        
        # 버전 업데이트
        self.data["__version__"] = 2
        self._log("[ConfigManager] 버전 1 → 2 마이그레이션 완료", level="INFO")
    
    def _add_order_to_files(self, company, site):
        """특정 현장의 모든 파일에 __order__ 추가"""
        if company not in self.data or site not in self.data[company]:
            return
        
        site_data = self.data[company][site]
        order = 0
        
        for folder_name, folder_data in site_data.items():
            if folder_name.startswith("__") or not isinstance(folder_data, dict):
                continue
            
            for filename, file_data in folder_data.items():
                if filename.endswith(".csv") and isinstance(file_data, dict):
                    if "__order__" not in file_data:
                        file_data["__order__"] = order
                        order += 1
    
    def _backup_before_migration(self):
        """마이그레이션 전 백업 생성"""
        import shutil
        from datetime import datetime
        
        try:
            backup_path = self.path + f".backup_v{self.data.get('__version__', 1)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(self.path, backup_path)
            self._log(f"[ConfigManager] 마이그레이션 전 백업 생성: {backup_path}", level="INFO")
        except Exception as e:
            self._log(f"[ConfigManager] 백업 생성 실패: {e}", level="WARN")
    
    def _verify_migration(self):
        """마이그레이션 검증"""
        try:
            # 1. 버전이 2로 업데이트되었는지 확인
            if self.data.get("__version__") != 2:
                self._log("[ConfigManager] 마이그레이션 검증 실패: 버전이 2가 아님", level="ERROR")
                return False
            
            # 2. 모든 회사에 최소 하나의 현장이 있는지 확인
            for company, company_data in self.data.items():
                if company.startswith("__") or not isinstance(company_data, dict):
                    continue
                
                # 현장이 있는지 확인
                sites = [k for k in company_data.keys() if not k.startswith("__") and isinstance(company_data.get(k), dict)]
                if not sites:
                    self._log(f"[ConfigManager] 마이그레이션 검증 실패: {company}에 현장이 없음", level="ERROR")
                    return False
                
                # 각 현장에 폴더가 있는지 확인
                for site in sites:
                    site_data = company_data[site]
                    folders = [k for k in site_data.keys() if not k.startswith("__") and isinstance(site_data.get(k), dict)]
                    if not folders:
                        self._log(f"[ConfigManager] 마이그레이션 검증 경고: {company}/{site}에 폴더가 없음", level="WARN")
            
            self._log("[ConfigManager] 마이그레이션 검증 성공", level="INFO")
            return True
            
        except Exception as e:
            self._log(f"[ConfigManager] 마이그레이션 검증 중 오류: {e}", level="ERROR")
            return False

    # -----------------------------------------------------
    # Ensure Functions (버전 2: Site 레벨 포함)
    # -----------------------------------------------------
    def ensure_company(self, company):
        """회사 노드 생성"""
        if company not in self.data:
            self.data[company] = {}
            self._log(f"[ConfigManager] 회사 생성: {company}")
        return self.data[company]
    
    def ensure_site(self, company, site):
        """현장 노드 생성"""
        comp = self.ensure_company(company)
        
        if site not in comp:
            comp[site] = {
                "__note__": ""
            }
            self._log(f"[ConfigManager] 현장 생성: {company}/{site}")
        
        return comp[site]

    def ensure_folder(self, company, site, folder, absolute_path=""):
        """업체폴더 노드 생성 (Site 레벨 포함)"""
        site_dict = self.ensure_site(company, site)

        if folder not in site_dict:
            site_dict[folder] = {
                "__note__": "",
                "__absolute_path__": absolute_path,
                "__is_ghost__": False
            }
            self._log(f"[ConfigManager] 폴더 생성: {company}/{site}/{folder}")

        else:
            # absolute path 갱신
            if absolute_path and not site_dict[folder].get("__absolute_path__"):
                site_dict[folder]["__absolute_path__"] = absolute_path
                site_dict[folder]["__is_ghost__"] = False

        return site_dict[folder]

    def ensure_logger(self, company, site, folder, filename):
        """로거파일 노드 생성 + CH0~CH7 기본 생성 (Site 레벨 포함)"""
        folder_dict = self.ensure_folder(company, site, folder)

        if filename not in folder_dict:
            # 최대 order 값 찾기
            max_order = self._get_max_order(company, site, folder)
            
            folder_dict[filename] = {
                "__order__": max_order + 1,
                "__fill_interval__": 0,
                "__gen_interval__": 0,
                "__is_ghost__": False
            }

            # 정석 CH 구조 생성
            for ch in range(8):
                folder_dict[filename][f"CH{ch}"] = {
                    "offset": "PASS",
                    "base": "",
                    "scale": "",
                    "decimal": "",
                    "label": "",
                    "initial": ""
                }

            self._log(f"[ConfigManager] 파일 생성: {company}/{site}/{folder}/{filename}")

        return folder_dict[filename]
    
    def _get_max_order(self, company, site, folder):
        """폴더 내 파일들의 최대 __order__ 값 반환"""
        if (company not in self.data or 
            site not in self.data[company] or
            folder not in self.data[company][site]):
            return -1
        
        folder_data = self.data[company][site][folder]
        max_order = -1
        
        for key, value in folder_data.items():
            if key.endswith(".csv") and isinstance(value, dict):
                order = value.get("__order__", 0)
                if isinstance(order, int) and order > max_order:
                    max_order = order
        
        return max_order

    # -----------------------------------------------------
    # Path 기반 접근
    # -----------------------------------------------------
    def get(self, path, default=None):
        """예: cfg.get('새길이엔씨.SAEGL03504.1227998430.csv.CH0')"""
        try:
            keys = path.split(".")
            d = self.data
            for k in keys:
                if k not in d:
                    return default
                d = d[k]
            return d
        except:
            return default

    def set(self, path, value):
        """예: cfg.set('새길이엔씨.SAEGL03504.__note__', '지중경사계 현장')"""
        keys = path.split(".")
        d = self.data

        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]

        d[keys[-1]] = value
        self.save()
    
    # -----------------------------------------------------
    # Ghosting 시스템 (경로 유효성 검사)
    # -----------------------------------------------------
    def check_path_validity(self):
        """
        모든 폴더의 경로 유효성 검사 및 Ghosting 처리
        
        Returns:
            dict: {"ghost_count": int, "valid_count": int}
        """
        ghost_count = 0
        valid_count = 0
        
        for company, sites in self.data.items():
            if company.startswith("__"):
                continue
            
            for site_name, site_data in sites.items():
                if site_name.startswith("__") or not isinstance(site_data, dict):
                    continue
                
                for folder_name, folder_data in site_data.items():
                    if folder_name.startswith("__") or not isinstance(folder_data, dict):
                        continue
                    
                    abs_path = folder_data.get("__absolute_path__")
                    is_valid = abs_path and os.path.exists(abs_path)
                    
                    # Ghost 상태 업데이트
                    folder_data["__is_ghost__"] = not is_valid
                    
                    if not is_valid:
                        ghost_count += 1
                    else:
                        valid_count += 1
                    
                    # 파일도 Ghost 상태 상속
                    for key in folder_data.keys():
                        if key.endswith(".csv") and isinstance(folder_data[key], dict):
                            folder_data[key]["__is_ghost__"] = not is_valid
        
        self.save()
        return {"ghost_count": ghost_count, "valid_count": valid_count}
    
    def restore_path(self, company, site, folder, new_path):
        """
        경로 재지정 (Ghost 상태 해제)
        
        Args:
            company: 회사명
            site: 현장명
            folder: 폴더명
            new_path: 새로운 경로
            
        Returns:
            bool: 성공 여부
        """
        if (company not in self.data or 
            site not in self.data[company] or
            folder not in self.data[company][site]):
            return False
        
        folder_data = self.data[company][site][folder]
        
        # 경로 업데이트
        folder_data["__absolute_path__"] = new_path
        folder_data["__is_ghost__"] = False
        
        # 파일 Ghost 상태도 해제
        for key in folder_data.keys():
            if key.endswith(".csv") and isinstance(folder_data[key], dict):
                folder_data[key]["__is_ghost__"] = False
        
        self.save()
        self._log(f"[ConfigManager] 경로 재지정: {company}/{site}/{folder} → {new_path}")
        return True
    
    # -----------------------------------------------------
    # 미등록 파일 관리 (별도 파일: unregistered_files.json)
    # 로거 파일만, 변환 대상 아님
    # -----------------------------------------------------
    def _load_unregistered_files(self):
        """미등록 파일 목록 로드"""
        if not os.path.exists(self.unregistered_files_path):
            return []
        
        try:
            with open(self.unregistered_files_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            self._log(f"미등록 파일 목록 로드 실패: {e}", level="ERROR")
            return []
    
    def _save_unregistered_files(self, files_list):
        """미등록 파일 목록 저장"""
        try:
            with open(self.unregistered_files_path, "w", encoding="utf-8") as f:
                json.dump(files_list, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self._log(f"미등록 파일 목록 저장 실패: {e}", level="ERROR")
    
    def add_unregistered_file(self, folder_path, filename, size=None, mtime=None):
        """
        미등록 파일 목록에 추가 (로거 등록 시 사용)
        
        Args:
            folder_path: 폴더 경로
            filename: 파일명
            size: 파일 크기 (선택)
            mtime: 수정일시 (선택)
        """
        # 이미 config에 등록된 파일이면 미등록 목록에 추가하지 않음
        folder_name = os.path.basename(folder_path.rstrip("/\\")) if folder_path else ""
        for company_data in self.data.values():
            if not isinstance(company_data, dict):
                continue
            for site_data in company_data.values():
                if not isinstance(site_data, dict):
                    continue
                for f_key, f_val in site_data.items():
                    if f_key.startswith("__") or not isinstance(f_val, dict):
                        continue
                    if filename in f_val:
                        self._log(
                            f"[ConfigManager] 미등록 추가 스킵 (이미 등록됨): {folder_path}/{filename}"
                        )
                        return False

        files_list = self._load_unregistered_files()
        
        # 중복 확인
        for item in files_list:
            if item.get("folder_path") == folder_path and item.get("filename") == filename:
                return False  # 이미 존재
        
        # 추가
        file_info = {
            "folder_path": folder_path,
            "filename": filename
        }
        if size is not None:
            file_info["size"] = size
        if mtime is not None:
            file_info["mtime"] = mtime.isoformat() if hasattr(mtime, 'isoformat') else str(mtime)
        
        files_list.append(file_info)
        self._save_unregistered_files(files_list)
        self._log(f"[ConfigManager] 미등록 파일 추가: {folder_path}/{filename}")
        return True
    
    def remove_unregistered_file(self, folder_path, filename):
        """
        미등록 파일 목록에서 제거 (현장 등록 시 사용)
        
        Args:
            folder_path: 폴더 경로
            filename: 파일명
            
        Returns:
            bool: 제거 성공 여부
        """
        files_list = self._load_unregistered_files()
        original_count = len(files_list)
        
        # 경로 정규화 함수 (대소문자, 구분자 통일)
        def normalize_path(path):
            if not path:
                return ""
            # 절대 경로로 변환 후 정규화
            try:
                abs_path = os.path.abspath(path)
                normalized = os.path.normpath(abs_path)
                # Windows에서는 대소문자 구분 안 함
                return normalized.lower() if os.name == 'nt' else normalized
            except:
                # 경로 변환 실패 시 원본 경로 정규화만
                return os.path.normpath(path).lower() if os.name == 'nt' else os.path.normpath(path)
        
        normalized_target_path = normalize_path(folder_path)
        
        new_files_list = []
        removed = False
        for item in files_list:
            item_folder_path = item.get("folder_path", "")
            item_filename = item.get("filename", "")
            
            # 경로 정규화하여 비교
            normalized_item_path = normalize_path(item_folder_path)
            
            if normalized_item_path == normalized_target_path and item_filename == filename:
                removed = True
                self._log(f"[ConfigManager] 미등록 파일 제거: {folder_path}/{filename}")
            else:
                new_files_list.append(item)
        
        files_list = new_files_list
        
        if removed:
            self._save_unregistered_files(files_list)
        
        return removed
    
    def get_unregistered_files(self):
        """미등록 파일 목록 반환"""
        return self._load_unregistered_files()