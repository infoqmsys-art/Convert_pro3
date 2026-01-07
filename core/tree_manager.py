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
        """특정 회사의 폴더/파일 정보를 반환"""
        return self.cfg.data.get(company, {})

    def get_file_config(self, company, folder, filename):
        """특정 파일 설정 반환"""
        return self.cfg.data.get(company, {}).get(folder, {}).get(filename, {})

    # ============================================================
    # 회사 / 폴더 / 파일 추가
    # ============================================================
    def add_company(self, company):
        if company not in self.cfg.data:
            self.cfg.data[company] = {}
            self.cfg.save()
            self.logger.log(f"[Tree] 회사 추가: {company}")

    def add_folder(self, company, folder, abs_path):
        if company not in self.cfg.data:
            self.cfg.data[company] = {}

        if folder not in self.cfg.data[company]:
            self.cfg.data[company][folder] = {
                "__note__": "",
                "__absolute_path__": abs_path
            }
            self.cfg.save()
            self.logger.log(f"[Tree] 폴더 추가: {company}/{folder}")

    def add_file(self, company, folder, filename):

        # 회사/폴더 보장
        self.cfg.ensure_company(company)
        self.cfg.ensure_folder(company, folder)

        # ⭐ 중요: 파일 생성은 ConfigManager가 한다
        self.cfg.ensure_logger(company, folder, filename)

        self.cfg.save()
        self.logger.log(f"[Tree] 파일 추가: {company}/{folder}/{filename}")

    # ============================================================
    # 삭제 기능
    # ============================================================
    def delete_company(self, company):
        if company in self.cfg.data:
            del self.cfg.data[company]
            self.cfg.save()
            self.logger.log(f"[Tree] 회사 삭제: {company}")

    def delete_folder(self, company, folder):
        if company in self.cfg.data and folder in self.cfg.data[company]:
            del self.cfg.data[company][folder]
            self.cfg.save()
            self.logger.log(f"[Tree] 폴더 삭제: {company}/{folder}")

    def delete_file(self, company, folder, filename):
        if (company in self.cfg.data and
            folder in self.cfg.data[company] and
            filename in self.cfg.data[company][folder]):

            del self.cfg.data[company][folder][filename]
            self.cfg.save()
            self.logger.log(f"[Tree] 파일 삭제: {company}/{folder}/{filename}")

    # ============================================================
    # 비고 설정
    # ============================================================
    def set_note(self, company, folder, note):
        if company in self.cfg.data and folder in self.cfg.data[company]:
            self.cfg.data[company][folder]["__note__"] = note
            self.cfg.save()
            self.logger.log(f"[Tree] 비고 설정: {company}/{folder} → {note}")

    # ============================================================
    # 파일 설정 저장 (CH0~CH7 등)
    # ============================================================
    def set_file_config(self, company, folder, filename, new_cfg):
        """
        UI에서 전달된 CH0~CH7 설정 딕셔너리를 config.json에 반영한다.
        예: new_cfg = {
                "CH0": {"offset": "NONE", "label": "", "base": ""},
                "CH1": {...},
                ...
            }
        """

        if company not in self.cfg.data:
            return

        if folder not in self.cfg.data[company]:
            return

        if filename not in self.cfg.data[company][folder]:
            return

        # 기존 설정 가져오기
        file_cfg = self.cfg.data[company][folder][filename]

        # CH 설정 업데이트
        for ch_key, ch_values in new_cfg.items():
            file_cfg[ch_key] = ch_values

        # 저장
        self.cfg.save()
        self.logger.log(f"[Tree] 파일 설정 저장: {company}/{folder}/{filename}")

    def get_file_label_summary(self, company, folder, filename):
        """
        summary 규칙 (최종 확정):
        - 기본값 NONE → summary에 표시하지 않음
        - PASS는 NONE과 동일하게 취급 (표시하지 않음)
        - label이 있으면 label 우선
        - OFFSET, EL, CR, V 등 모드만 표시
        - 전체 NONE이면 "" 반환
        """

        try:
            file_cfg = self.cfg.data[company][folder][filename]
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

