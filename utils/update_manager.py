"""
Convert Pro 3 - 업데이트 매니저
GitHub Release에서 새 버전을 확인하고 다운로드
"""

import os
import json
import requests
from pathlib import Path
from version import VERSION, VERSION_NUMBER


class UpdateManager:
    """GitHub Release 기반 자동 업데이트 관리"""
    
    GITHUB_REPO = "infoqmsys-art/Convert_pro3_updates"
    GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    
    def __init__(self, logger=None):
        self.logger = logger
        self.current_version = VERSION_NUMBER  # "1.5.3"
    
    def check_for_updates(self):
        """
        새 버전 확인
        
        Returns:
            dict: {
                'available': bool,
                'version': str,
                'download_url': str,
                'release_notes': str
            }
        """
        try:
            response = requests.get(self.GITHUB_API, timeout=5)
            response.raise_for_status()
            
            release_data = response.json()
            
            # 최신 버전 (v1.5.4 → 1.5.4)
            latest_version = release_data['tag_name'].lstrip('v')
            
            # 버전 비교
            is_newer = self._compare_versions(latest_version, self.current_version)
            
            if not is_newer:
                return {
                    'available': False,
                    'version': self.current_version,
                    'download_url': None,
                    'release_notes': None
                }
            
            # 다운로드 URL 찾기 (우선순위: _full.zip > .exe)
            download_url = None
            is_zip = False
            
            # 1순위: _full.zip (메인 프로그램 + updater 포함)
            for asset in release_data.get('assets', []):
                if asset['name'].endswith('_full.zip'):
                    download_url = asset['browser_download_url']
                    is_zip = True
                    break
            
            # 2순위: .exe (단일 실행 파일)
            if not download_url:
                for asset in release_data.get('assets', []):
                    if asset['name'].endswith('.exe') and 'updater' not in asset['name'].lower():
                        download_url = asset['browser_download_url']
                        break
            
            if not download_url:
                if self.logger:
                    self.logger.log("업데이트 파일을 찾을 수 없습니다.", level="WARNING")
                return {'available': False}
            
            return {
                'available': True,
                'version': latest_version,
                'download_url': download_url,
                'is_zip': is_zip,
                'release_notes': release_data.get('body', ''),
                'release_url': release_data.get('html_url', '')
            }
            
        except requests.exceptions.Timeout:
            if self.logger:
                self.logger.log("업데이트 확인 시간 초과", level="WARNING")
            return {'available': False, 'error': 'timeout'}
        
        except Exception as e:
            if self.logger:
                self.logger.log(f"업데이트 확인 실패: {e}", level="ERROR")
            return {'available': False, 'error': str(e)}
    
    def _compare_versions(self, v1, v2):
        """
        버전 비교 (v1이 v2보다 최신인지)
        
        Args:
            v1: "1.5.4"
            v2: "1.5.3"
        
        Returns:
            bool: v1 > v2
        """
        try:
            parts1 = [int(x) for x in v1.split('.')]
            parts2 = [int(x) for x in v2.split('.')]
            
            # [1, 5, 4] vs [1, 5, 3]
            return parts1 > parts2
        except:
            return False
    
    def download_update(self, download_url, save_path, progress_callback=None):
        """
        업데이트 파일 다운로드
        
        Args:
            download_url: 다운로드 URL
            save_path: 저장 경로
            progress_callback: 진행률 콜백 함수(percent)
        
        Returns:
            bool: 성공 여부
        """
        try:
            if self.logger:
                self.logger.log(f"업데이트 다운로드 시작: {download_url}", level="INFO")
            
            response = requests.get(download_url, stream=True, timeout=120)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback and total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            progress_callback(percent)
            
            if self.logger:
                self.logger.log(f"다운로드 완료: {save_path}", level="INFO")
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.log(f"다운로드 실패: {e}", level="ERROR")
            return False
    
    def start_updater(self, downloaded_file, is_zip=False):
        """
        업데이터 시작 (프로그램 종료 → 파일 교체 → 재시작)
        
        Args:
            downloaded_file: 다운로드된 파일 경로 (.exe 또는 .zip)
            is_zip: ZIP 파일 여부
        """
        import sys
        import subprocess
        import tempfile
        import zipfile
        
        # 현재 실행 파일 경로
        if getattr(sys, 'frozen', False):
            current_exe = sys.executable
        else:
            current_exe = os.path.abspath(sys.argv[0])
        
        app_dir = Path(current_exe).parent
        
        try:
            # ZIP 파일인 경우: 압축 해제 후 새 updater 사용
            if is_zip:
                if self.logger:
                    self.logger.log("ZIP 압축 해제 중...", level="INFO")
                
                # 임시 폴더에 압축 해제
                temp_extract_dir = Path(tempfile.mkdtemp(prefix="convertpro3_update_"))
                
                with zipfile.ZipFile(downloaded_file, 'r') as zip_ref:
                    zip_ref.extractall(temp_extract_dir)
                
                # 압축 해제된 파일에서 새 updater 찾기
                new_updater = temp_extract_dir / "tools" / "updater.exe"
                new_main_exe = None
                
                # 메인 exe 찾기
                for file in temp_extract_dir.glob("*.exe"):
                    if "updater" not in file.name.lower():
                        new_main_exe = file
                        break
                
                if not new_updater.exists():
                    if self.logger:
                        self.logger.log("압축 파일에 updater.exe가 없습니다.", level="ERROR")
                    return False
                
                if not new_main_exe:
                    if self.logger:
                        self.logger.log("압축 파일에 메인 프로그램이 없습니다.", level="ERROR")
                    return False
                
                # **새 버전의 updater 사용**
                updater_exe = new_updater
                target_file = new_main_exe
                
                if self.logger:
                    self.logger.log(f"새 버전 updater 사용: {updater_exe}", level="INFO")
                    self.logger.log(f"메인 프로그램: {target_file}", level="INFO")
                
                # updater 프로세스에 임시 폴더 정리 책임을 넘기기 위해 경로 기록
                # (updater.exe 실행 후 현재 프로세스는 종료되므로 여기서 정리 불가)
                # → perform_update 완료 후 temp_extract_dir을 삭제하도록 인자에 추가
                # 현재는 OS 재시작/임시 폴더 정리에 위임 (Windows %TEMP% 자동 정리)
            
            # 단일 EXE 파일인 경우: 기존 updater 사용
            else:
                updater_exe = app_dir / "tools" / "updater.exe"
                target_file = Path(downloaded_file)
                
                if not updater_exe.exists():
                    if self.logger:
                        self.logger.log(f"업데이터를 찾을 수 없습니다: {updater_exe}", level="ERROR")
                        self.logger.log("⚠️ _full.zip 패키지를 다운로드하세요 (updater 포함)", level="WARNING")
                    return False
            
            # updater.exe 실행 (창 없이, --silent로 백그라운드)
            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
            subprocess.Popen([
                str(updater_exe),
                str(current_exe),
                str(target_file),
                "restart",
                "--silent"
            ], creationflags=CREATE_NO_WINDOW)
            
            if self.logger:
                self.logger.log("업데이터 시작됨. 프로그램을 종료합니다.", level="INFO")
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.log(f"업데이터 시작 실패: {e}", level="ERROR")
            return False
