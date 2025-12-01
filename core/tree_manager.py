class TreeManager:
    """
    Convert Pro 2의 회사/폴더/파일 구조를 관리하는 핵심 모듈.
    UI와 file_processor가 참조하는 모든 데이터를 제공함.
    """

    def __init__(self, config_manager, logger):
        self.cfg = config_manager         # ConfigManager instance
        self.logger = logger
        self.tree_data = self.cfg.data    # config.json 전체 구조 dict

    # ======================================================
    #  CRUD: 회사/폴더/파일 추가/삭제
    # ======================================================
    def add_company(self, company):
        if company not in self.tree_data:
            self.tree_data[company] = {}
            self.logger.log(f"[TreeManager] 회사 추가: {company}")
            self.cfg.save()

    def add_folder(self, company, folder, absolute_path=""):
        self.add_company(company)

        if folder not in self.tree_data[company]:
            self.tree_data[company][folder] = {
                "__note__": "",
                "__absolute_path__": absolute_path
            }
            self.logger.log(f"[TreeManager] 폴더 추가: {company}/{folder}")
            self.cfg.save()

    def add_file(self, company, folder, filename):
        self.add_folder(company, folder)

        folder_dict = self.tree_data[company][folder]
        if filename not in folder_dict:
            folder_dict[filename] = {
                "__fill_interval__": 0,
                "__gen_interval__": 0,
            }
            # CH0~CH7 기본 설정 생성
            for ch in range(8):
                folder_dict[filename][f"CH{ch}"] = {
                    "offset": "PASS",
                    "base": "",
                    "scale": 0,
                    "label": "None"
                }

            self.logger.log(f"[TreeManager] 파일 추가: {company}/{folder}/{filename}")
            self.cfg.save()

    def get_file_config(self, company, folder, filename):
        return self.tree_data.get(company, {}).get(folder, {}).get(filename, {})

    def set_file_config(self, company, folder, filename, config_dict):
        if company not in self.tree_data:
            return
        if folder not in self.tree_data[company]:
            return
        if filename not in self.tree_data[company][folder]:
            self.tree_data[company][folder][filename] = {}

        self.tree_data[company][folder][filename] = config_dict

        self.cfg.save()

    # ======================================================
    #  삭제
    # ======================================================
    def delete_company(self, company):
        if company in self.tree_data:
            del self.tree_data[company]
            self.logger.log(f"[TreeManager] 회사 삭제: {company}")
            self.cfg.save()

    def delete_folder(self, company, folder):
        if company in self.tree_data and folder in self.tree_data[company]:
            del self.tree_data[company][folder]
            self.logger.log(f"[TreeManager] 폴더 삭제: {company}/{folder}")
            self.cfg.save()

    def delete_file(self, company, folder, filename):
        try:
            del self.tree_data[company][folder][filename]
            self.logger.log(f"[TreeManager] 파일 삭제: {company}/{folder}/{filename}")
            self.cfg.save()
        except KeyError:
            self.logger.log("[TreeManager] 파일 삭제 실패 (경로 없음)", level="WARN")

    # ======================================================
    #  Note 설정
    # ======================================================
    def set_note(self, company, folder, note):
        try:
            self.tree_data[company][folder]["__note__"] = note
            self.logger.log(f"[TreeManager] 비고 변경: {company}/{folder} → {note}")
            self.cfg.save()
        except KeyError:
            self.logger.log("[TreeManager] 비고 설정 실패 (경로 없음)", level="ERROR")

    # ======================================================
    #  label summary (CH0:EL, CH1:PASS ...)
    # ======================================================
    def get_file_label_summary(self, company, folder, filename):
        try:
            ch_info = []
            file_cfg = self.tree_data[company][folder][filename]

            for ch in range(8):
                mode = file_cfg.get(f"CH{ch}", {}).get("offset", "PASS")
                label = file_cfg.get(f"CH{ch}", {}).get("label", "None")

                # "PASS"이면 표시하지 않음
                if mode.upper() != "PASS":
                    ch_info.append(f"{ch}:{mode}")

            return ", ".join(ch_info)
        except Exception:
            return ""

    # ======================================================
    #  회사별 데이터 제공 (UI에서 회사 선택 시 사용)
    # ======================================================
    def get_company_data(self, company):
        return self.tree_data.get(company, {})

    # ======================================================
    #  TreeView 전체 반환
    # ======================================================
    def get_tree(self):
        return self.tree_data
