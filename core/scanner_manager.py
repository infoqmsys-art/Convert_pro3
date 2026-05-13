"""
===============================================================
Convert Pro 3 - ScannerManager
===============================================================
미등록 파일 스캔 및 관리 시스템

역할:
    - 등록된 물리 폴더 내에 있으나 config.json에 없는 CSV 파일 찾기
    - 미등록 파일 정보 수집 (파일명, 경로, 크기, 수정일시)
    - 다중 파일을 특정 현장에 일괄 등록
===============================================================
"""

import os
from datetime import datetime


class ScannerManager:
    """미등록 파일 스캔 및 관리"""

    def __init__(self, config_manager, tree_manager, logger):
        self.config = config_manager
        self.tree = tree_manager
        self.logger = logger
        self.unregistered_files = []  # [(company, site, folder, filename, path, size, mtime), ...]

    def scan_all_folders(self):
        """
        미등록 파일 목록 스캔 (config.json의 __unregistered_files__에서 읽기)
        
        Returns:
            list: 미등록 파일 정보 리스트
                [
                    {
                        "company": None,  # 미등록 상태
                        "site": None,     # 미등록 상태
                        "folder": "폴더명",
                        "filename": "파일명.csv",
                        "path": "전체경로",
                        "size": 파일크기(바이트),
                        "mtime": 수정일시(datetime)
                    },
                    ...
                ]
        """
        self.unregistered_files = []

        # config.json의 __unregistered_files__에서 읽기
        unregistered_list = self.config.get_unregistered_files()

        for file_info in unregistered_list:
            folder_path = file_info.get("folder_path")
            filename = file_info.get("filename")

            if not folder_path or not filename:
                continue

            file_path = os.path.join(folder_path, filename)

            # 파일이 실제로 존재하는지 확인
            if not os.path.exists(file_path):
                continue

            try:
                stat = os.stat(file_path)
                folder_name = os.path.basename(folder_path.rstrip("/\\"))

                # mtime 파싱
                mtime_str = file_info.get("mtime")
                if mtime_str:
                    try:
                        if isinstance(mtime_str, str):
                            # ISO 형식 또는 일반 형식 파싱 시도
                            try:
                                mtime = datetime.fromisoformat(
                                    mtime_str.replace("Z", "+00:00")
                                )
                            except Exception:
                                # 일반 형식 시도
                                try:
                                    mtime = datetime.strptime(
                                        mtime_str, "%Y-%m-%d %H:%M:%S"
                                    )
                                except Exception:
                                    mtime = datetime.fromtimestamp(stat.st_mtime)
                        else:
                            mtime = datetime.fromtimestamp(stat.st_mtime)
                    except Exception:
                        mtime = datetime.fromtimestamp(stat.st_mtime)
                else:
                    mtime = datetime.fromtimestamp(stat.st_mtime)

                # size는 파일에서 읽거나 저장된 값 사용
                size = file_info.get("size", stat.st_size)

                self.unregistered_files.append(
                    {
                        "company": None,  # 미등록 상태
                        "site": None,  # 미등록 상태
                        "folder": folder_name,
                        "folder_path": folder_path,  # 삭제 기능을 위해 추가
                        "filename": filename,
                        "path": file_path,
                        "size": size,
                        "mtime": mtime,
                    }
                )
            except Exception as e:
                self.logger.log(
                    f"미등록 파일 정보 읽기 실패 {file_path}: {e}",
                    level="ERROR",
                )

        return self.unregistered_files

    # ------------------------------------------------------------
    # Ignore Functions
    # ------------------------------------------------------------
    def ignore_files(self, file_list):
        """
        미등록 목록에서 선택된 파일들을 제외 처리한다.
        - 실제 CSV 파일은 삭제하지 않고, 해당 폴더의 __ignored_unregistered__ 목록에 기록만 남긴다.
        """
        if not file_list:
            return 0

        ignored_count = 0

        for file_info in file_list:
            company = file_info.get("company")
            site = file_info.get("site")
            folder = file_info.get("folder")
            filename = file_info.get("filename")

            if not all([company, site, folder, filename]):
                continue

            try:
                folder_cfg = (
                    self.config.data
                    .get(company, {})
                    .get(site, {})
                    .get(folder, {})
                )
                if not isinstance(folder_cfg, dict):
                    continue

                ignored_list = folder_cfg.setdefault("__ignored_unregistered__", [])
                if filename not in ignored_list:
                    ignored_list.append(filename)
                    ignored_count += 1
            except Exception as e:
                self.logger.log(f"[Scanner] ignore_files 오류: {company}/{site}/{folder}/{filename} → {e}", level="ERROR")

        if ignored_count > 0:
            self.config.save()
            self.logger.log(f"[Scanner] 미등록 목록에서 제외된 파일: {ignored_count}개", level="INFO")

        return ignored_count

    def add_files_to_site(self, company, site, file_list):
        """
        다중 파일을 특정 현장에 등록 (미등록 목록에서 제거)
        
        Args:
            company: 회사명
            site: 현장명
            file_list: 파일 정보 리스트 (scan_all_folders() 결과)
        """
        if not file_list:
            return 0
        
        added_count = 0
        
        # 폴더별로 그룹화 (같은 폴더의 파일들은 같은 폴더에 등록)
        folder_groups = {}
        for file_info in file_list:
            folder = file_info["folder"]
            abs_path = file_info["path"]
            # 파일 경로에서 폴더 경로 추출
            folder_path = os.path.dirname(abs_path)
            
            if folder not in folder_groups:
                folder_groups[folder] = {
                    "abs_path": folder_path,
                    "files": []
                }
            folder_groups[folder]["files"].append(file_info)
        
        # 각 폴더별로 등록
        for folder_name, folder_data in folder_groups.items():
            abs_path = folder_data["abs_path"]
            
            # 폴더가 없으면 추가
            try:
                self.tree.add_folder(company, site, folder_name, abs_path)
            except:
                pass  # 이미 존재할 수 있음
            
            # 파일들 등록
            for file_info in folder_data["files"]:
                filename = file_info["filename"]
                # folder_path는 저장된 값 우선, 없으면 path에서 추출
                folder_path = file_info.get("folder_path") or os.path.dirname(file_info["path"])

                # 1) config 등록 시도 (실패해도 미등록 목록에서는 제거)
                registered_ok = False
                try:
                    self.tree.add_file(company, site, folder_name, filename)
                    added_count += 1
                    registered_ok = True
                    self.logger.log(
                        f"[Scanner] 파일 등록: {company}/{site}/{folder_name}/{filename}"
                    )
                except Exception as e:
                    self.logger.log(
                        f"[Scanner] 파일 등록 실패 {company}/{site}/{folder_name}/{filename}: {e}",
                        level="ERROR"
                    )

                # 2) 미등록 목록에서 제거 (등록 성공 여부 무관 — 한 번 시도했으면 목록에서 뺌)
                try:
                    self.config.remove_unregistered_file(folder_path, filename)
                    if registered_ok:
                        self.logger.log(
                            f"[Scanner] 미등록 목록 제거: {folder_path}/{filename}"
                        )
                except Exception as e:
                    self.logger.log(
                        f"[Scanner] 미등록 목록 제거 실패 {folder_path}/{filename}: {e}",
                        level="WARN"
                    )
        
        self.config.save()
        self.logger.log(
            f"[Scanner] 총 {added_count}개 파일이 {company}/{site}에 등록되었습니다."
        )
        
        return added_count
