"""
===============================================================
Convert Pro 3 - TreeManager
===============================================================
이 파일은 회사 / 폴더 / 파일 트리 구조를 관리한다.

역할:
    - ConfigManager.data 를 기반으로 트리 구조를 구성하고 수정한다.
    - 회사/폴더/파일 추가/삭제
    - 라벨(summary) 문자열 생성
    - UI에서 사용할 형태로 트리 구조 반환

핵심 원칙:
    - TreeManager는 별도의 데이터 사본을 가지지 않는다.
    - 항상 self.cfg.data 를 직접 참조하여 "단일 진실 원본"을 유지한다.
===============================================================
"""

class TreeManager:

    def __init__(self, cfg, logger):
        self.cfg = cfg
        self.logger = logger

    # ============================================================
    # 내부 데이터 접근 → 항상 self.cfg.data
    # ============================================================
    def get_tree(self):
        """전체 트리 구조 반환"""
        return self.cfg.data

    def get_company_data(self, company):
        """특정 회사의 현장/폴더/파일 정보를 반환"""
        return self.cfg.data.get(company, {})

    def get_site_data(self, company, site):
        """특정 현장의 폴더/파일 정보를 반환"""
        return self.cfg.data.get(company, {}).get(site, {})

    def get_file_config(self, company, site, folder, filename):
        """특정 파일 설정 반환 (Site 레벨 포함)"""
        return self.cfg.data.get(company, {}).get(site, {}).get(folder, {}).get(filename, {})

    # ============================================================
    # 회사 / 현장 / 폴더 / 파일 추가
    # ============================================================
    def add_company(self, company):
        if company not in self.cfg.data:
            self.cfg.data[company] = {}
            self.cfg.save()
            self.logger.log(f"[Tree] 회사 추가: {company}")

    def add_site(self, company, site):
        """현장 추가"""
        if company not in self.cfg.data:
            self.cfg.data[company] = {}
        
        if site not in self.cfg.data[company]:
            self.cfg.data[company][site] = {
                "__note__": ""
            }
            self.cfg.save()
            self.logger.log(f"[Tree] 현장 추가: {company}/{site}")

    def add_folder(self, company, site, folder, abs_path):
        """폴더 추가 (Site 레벨 포함)"""
        if company not in self.cfg.data:
            self.cfg.data[company] = {}

        if site not in self.cfg.data[company]:
            self.cfg.data[company][site] = {}

        if folder not in self.cfg.data[company][site]:
            self.cfg.data[company][site][folder] = {
                "__note__": "",
                "__absolute_path__": abs_path,
                "__is_ghost__": False
            }
            self.cfg.save()
            self.logger.log(f"[Tree] 폴더 추가: {company}/{site}/{folder}")

    def add_file(self, company, site, folder, filename):
        """파일 추가 (Site 레벨 포함)"""
        # 회사/현장/폴더 보장
        self.cfg.ensure_company(company)
        self.cfg.ensure_site(company, site)
        self.cfg.ensure_folder(company, site, folder)

        # ⭐ 중요: 파일 생성은 ConfigManager가 한다
        self.cfg.ensure_logger(company, site, folder, filename)

        self.cfg.save()
        self.logger.log(f"[Tree] 파일 추가: {company}/{site}/{folder}/{filename}")

    # ============================================================
    # 삭제 기능 (Site 레벨 포함)
    # ============================================================
    def delete_company(self, company):
        if company in self.cfg.data:
            del self.cfg.data[company]
            self.cfg.save()
            self.logger.log(f"[Tree] 회사 삭제: {company}")

    def delete_site(self, company, site):
        """현장 삭제"""
        if (company in self.cfg.data and 
            site in self.cfg.data[company]):
            del self.cfg.data[company][site]
            self.cfg.save()
            self.logger.log(f"[Tree] 현장 삭제: {company}/{site}")

    def delete_folder(self, company, site, folder):
        """폴더 삭제 (Site 레벨 포함)"""
        if (company in self.cfg.data and 
            site in self.cfg.data[company] and
            folder in self.cfg.data[company][site]):
            del self.cfg.data[company][site][folder]
            self.cfg.save()
            self.logger.log(f"[Tree] 폴더 삭제: {company}/{site}/{folder}")

    def delete_file(self, company, site, folder, filename):
        """파일 삭제 (Site 레벨 포함)"""
        if (company in self.cfg.data and
            site in self.cfg.data[company] and
            folder in self.cfg.data[company][site] and
            filename in self.cfg.data[company][site][folder]):

            del self.cfg.data[company][site][folder][filename]
            self.cfg.save()
            self.logger.log(f"[Tree] 파일 삭제: {company}/{site}/{folder}/{filename}")

    def reorder_files(self, company, site, folder, file_order_list):
        """
        폴더 내 파일 순서 재정렬
        
        Args:
            company: 회사명
            site: 현장명
            folder: 폴더명
            file_order_list: [(filename, new_order), ...] 형태의 리스트
                           순서대로 정렬된 파일명과 새로운 order 값
        """
        if (company not in self.cfg.data or
            site not in self.cfg.data[company] or
            folder not in self.cfg.data[company][site]):
            return False
        
        folder_data = self.cfg.data[company][site][folder]
        
        # 각 파일의 __order__ 업데이트
        for filename, new_order in file_order_list:
            if filename in folder_data and isinstance(folder_data[filename], dict):
                folder_data[filename]["__order__"] = new_order
        
        self.cfg.save()
        self.logger.log(f"[Tree] 파일 순서 재정렬: {company}/{site}/{folder} ({len(file_order_list)}개 파일)")
        return True

    def move_folder(self, src_company, src_site, folder, dst_company, dst_site):
        """
        폴더 전체를 다른 회사/현장으로 이동 (설정 + 경로 그대로)
        - 폴더 아래의 모든 로거 파일 설정, 비고, __absolute_path__, __is_ghost__ 등을 통째로 옮긴다.
        - 실제 CSV 파일이 위치한 경로(__absolute_path__)는 그대로 유지된다.
        """
        try:
            data = self.cfg.data

            # 소스 폴더 존재 여부 확인
            if (src_company not in data or
                src_site not in data[src_company] or
                folder not in data[src_company][src_site]):
                self.logger.log(
                    f"[Tree] move_folder 실패: 소스 없음 {src_company}/{src_site}/{folder}",
                    level="WARN",
                )
                return False

            src_site_dict = data[src_company][src_site]
            folder_dict = src_site_dict.get(folder)
            if not isinstance(folder_dict, dict):
                self.logger.log(
                    f"[Tree] move_folder 실패: 폴더 설정이 dict 아님 {src_company}/{src_site}/{folder}",
                    level="WARN",
                )
                return False

            # 대상 회사/현장 보장
            self.cfg.ensure_company(dst_company)
            self.cfg.ensure_site(dst_company, dst_site)

            dst_site_dict = data[dst_company][dst_site]

            # 대상에 동일 이름 폴더가 이미 있으면 이동 불가 (충돌 방지)
            if folder in dst_site_dict:
                self.logger.log(
                    f"[Tree] move_folder 경고: 대상에 동일 폴더 존재 {dst_company}/{dst_site}/{folder}",
                    level="WARN",
                )
                return False

            # 이동: 대상에 폴더 추가 후 소스에서 삭제
            dst_site_dict[folder] = folder_dict
            del src_site_dict[folder]

            self.cfg.save()
            self.logger.log(
                f"[Tree] 폴더 이동: "
                f"{src_company}/{src_site}/{folder} → "
                f"{dst_company}/{dst_site}/{folder}"
            )
            return True
        except Exception as e:
            self.logger.log(f"[Tree] move_folder 예외: {e}", level="ERROR")
            return False

    def move_file(self, src_company, src_site, src_folder, filename, dst_company, dst_site):
        """
        파일을 다른 회사/현장으로 이동 (설정 그대로 복사)
        - 원본 config 엔트리를 그대로 옮기므로, 채널/센서 설정, 비고, __order__ 등이 모두 유지된다.
        - 실제 CSV 파일은 이동/복사하지 않고, 동일 폴더(경로)를 공유한다고 가정한다.
        """
        try:
            data = self.cfg.data

            # 소스 존재 여부 확인
            if (src_company not in data or
                src_site not in data[src_company] or
                src_folder not in data[src_company][src_site] or
                filename not in data[src_company][src_site][src_folder]):
                self.logger.log(
                    f"[Tree] move_file 실패: 소스 없음 {src_company}/{src_site}/{src_folder}/{filename}",
                    level="WARN",
                )
                return False

            src_folder_dict = data[src_company][src_site][src_folder]
            file_cfg = src_folder_dict.get(filename)
            if not isinstance(file_cfg, dict):
                self.logger.log(
                    f"[Tree] move_file 실패: 파일 설정이 dict 아님 {src_company}/{src_site}/{src_folder}/{filename}",
                    level="WARN",
                )
                return False

            # 대상 회사/현장 보장
            self.cfg.ensure_company(dst_company)
            self.cfg.ensure_site(dst_company, dst_site)

            # 대상 폴더 준비 (같은 폴더명을 사용하고, 가능한 한 동일 경로 유지)
            dst_company_dict = data[dst_company]
            dst_site_dict = dst_company_dict[dst_site]

            # 소스 폴더 메타데이터 참조
            src_abs_path = src_folder_dict.get("__absolute_path__")
            src_note = src_folder_dict.get("__note__", "")
            src_is_ghost = src_folder_dict.get("__is_ghost__", False)

            if src_folder not in dst_site_dict or not isinstance(dst_site_dict.get(src_folder), dict):
                # 대상에 폴더가 없으면 새로 생성 (경로/비고 복사)
                dst_site_dict[src_folder] = {
                    "__note__": src_note,
                    "__absolute_path__": src_abs_path,
                    "__is_ghost__": src_is_ghost,
                }

            dst_folder_dict = dst_site_dict[src_folder]

            # __order__ 재조정: 대상 폴더의 최대 order 뒤에 붙이기
            try:
                max_order = self.cfg._get_max_order(dst_company, dst_site, src_folder)
                if isinstance(file_cfg.get("__order__"), int):
                    file_cfg["__order__"] = max_order + 1
            except Exception:
                # 실패해도 치명적이지 않으므로 무시
                pass

            # 대상에 동일 이름 파일이 이미 있으면 덮어쓰기 전에 로그
            if filename in dst_folder_dict:
                self.logger.log(
                    f"[Tree] move_file 경고: 대상에 같은 이름 파일이 있어 덮어씀 "
                    f"{dst_company}/{dst_site}/{src_folder}/{filename}",
                    level="WARN",
                )

            # 이동: 대상에 복사 후 소스에서 삭제
            dst_folder_dict[filename] = file_cfg
            del src_folder_dict[filename]

            self.cfg.save()
            self.logger.log(
                f"[Tree] 파일 이동: "
                f"{src_company}/{src_site}/{src_folder}/{filename} → "
                f"{dst_company}/{dst_site}/{src_folder}/{filename}"
            )
            return True
        except Exception as e:
            self.logger.log(f"[Tree] move_file 예외: {e}", level="ERROR")
            return False

    # ============================================================
    # 비고 설정 (Site 레벨 포함)
    # ============================================================
    def set_site_note(self, company, site, note):
        """현장 비고 설정"""
        if (company in self.cfg.data and 
            site in self.cfg.data[company]):
            self.cfg.data[company][site]["__note__"] = note
            self.cfg.save()
            self.logger.log(f"[Tree] 현장 비고 설정: {company}/{site} → {note}")
    
    def set_folder_note(self, company, site, folder, note):
        """폴더 비고 설정 (Site 레벨 포함)"""
        if (company in self.cfg.data and 
            site in self.cfg.data[company] and
            folder in self.cfg.data[company][site]):
            if "__note__" not in self.cfg.data[company][site][folder]:
                self.cfg.data[company][site][folder]["__note__"] = ""
            self.cfg.data[company][site][folder]["__note__"] = note
            self.cfg.save()
            self.logger.log(f"[Tree] 폴더 비고 설정: {company}/{site}/{folder} → {note}")
    
    def set_file_note(self, company, site, folder, filename, note):
        """파일 비고 설정 (Site 레벨 포함)"""
        if (company in self.cfg.data and 
            site in self.cfg.data[company] and
            folder in self.cfg.data[company][site] and
            filename in self.cfg.data[company][site][folder]):
            if "__note__" not in self.cfg.data[company][site][folder][filename]:
                self.cfg.data[company][site][folder][filename]["__note__"] = ""
            self.cfg.data[company][site][folder][filename]["__note__"] = note
            self.cfg.save()
            self.logger.log(f"[Tree] 파일 비고 설정: {company}/{site}/{folder}/{filename} → {note}")
    
    def set_note(self, company, site, folder, note):
        """폴더 비고 설정 (하위 호환성)"""
        self.set_folder_note(company, site, folder, note)

    # ============================================================
    # 파일 설정 저장 (CH0~CH7 등)
    # ============================================================
    def set_file_config(self, company, site, folder, filename, new_cfg):
        """
        UI에서 전달된 CH0~CH7 설정 딕셔너리를 config.json에 반영한다. (Site 레벨 포함)
        예: new_cfg = {
                "CH0": {"offset": "NONE", "label": "", "base": ""},
                "CH1": {...},
                ...
            }
        """

        if company not in self.cfg.data:
            return

        if site not in self.cfg.data[company]:
            return

        if folder not in self.cfg.data[company][site]:
            return

        if filename not in self.cfg.data[company][site][folder]:
            return

        # 기존 설정 가져오기
        file_cfg = self.cfg.data[company][site][folder][filename]

        # CH 설정 업데이트
        for ch_key, ch_values in new_cfg.items():
            file_cfg[ch_key] = ch_values

        # 저장
        self.cfg.save()
        self.logger.log(f"[Tree] 파일 설정 저장: {company}/{site}/{folder}/{filename}")

    def get_file_label_summary(self, company, site, folder, filename):
        """
        summary 규칙 (최종 확정):
        - 기본값 NONE → summary에 표시하지 않음
        - PASS는 NONE과 동일하게 취급 (표시하지 않음)
        - label이 있으면 label 우선
        - OFFSET, EL, CR, V 등 모드만 표시
        - 전체 NONE이면 "" 반환
        """

        try:
            file_cfg = self.cfg.data[company][site][folder][filename]
            summary_list = []

            for ch in range(8):
                ch_key = f"CH{ch}"
                cfg = file_cfg.get(ch_key, {})

                mode = (cfg.get("offset") or "NONE").upper()
                label = cfg.get("label", "")
                base = cfg.get("base", "")

                # ===========================
                # 1) label 존재 → label 표시
                # ===========================
                if label and str(label).upper() != "NONE":
                    summary_list.append(f"{ch_key}: {label}")
                    continue

                # ===========================
                # 2) NONE (기본값) → 표시 안함
                # ===========================
                if mode in ("NONE", "PASS", ""):
                    continue

                # ===========================
                # 3) OFFSET 모드
                # ===========================
                if mode == "OFFSET":
                    if base not in ("", None):
                        summary_list.append(f"{ch_key}: OFFSET({base})")
                    else:
                        summary_list.append(f"{ch_key}: OFFSET")
                    continue

                # ===========================
                # 4) 그 외 모드 (EL, CR, V 등)
                # ===========================
                summary_list.append(f"{ch_key}: {mode}")

            # ---------------------------------------------------------
            # 전체가 NONE이면 summary를 표시하지 않음
            # ---------------------------------------------------------
            if not summary_list:
                return ""

            return " / ".join(summary_list)

        except Exception:
            return ""

