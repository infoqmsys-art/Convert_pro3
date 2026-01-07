"""
===============================================================
Convert Pro 3 - Auto Updater
===============================================================
서버에서 최신 버전을 확인하고 자동 업데이트를 수행하는 모듈

서버 구조:
    - version.json: 버전 정보 파일
        {
            "version": "v1.3",
            "download_url": "https://yourserver.com/updates/ConvertPro3_v1.3.exe",
            "release_notes": "새로운 기능 추가",
            "release_date": "2026-01-07",
            "mandatory": false
        }
    - ConvertPro3_vX.X.exe: 실제 업데이트 파일

사용법:
    updater = AutoUpdater(
        current_version="v1.2",
        update_server_url="https://yourserver.com/updates"
    )
    
    has_update, info = updater.check_for_updates()
    if has_update:
        updater.download_and_install(info)
===============================================================
"""

import os
import sys
import json
import urllib.request
import urllib.error
import subprocess
import tempfile
from typing import Tuple, Optional, Dict


class AutoUpdater:
    """
    자동 업데이트 관리 클래스
    """
    
    def __init__(self, current_version: str, update_server_url: str, logger=None):
        """
        Args:
            current_version: 현재 버전 (예: "v1.2")
            update_server_url: 업데이트 서버 URL (예: "https://yourserver.com/updates")
            logger: Logger 인스턴스 (선택)
        """
        self.current_version = current_version.replace("v", "").strip()
        self.update_server_url = update_server_url.rstrip("/")
        self.logger = logger
    
    @staticmethod
    def _parse_version(version_str: str) -> Tuple[int, ...]:
        """
        버전 문자열을 튜플로 파싱 (예: "1.2" -> (1, 2), "1.2.3" -> (1, 2, 3))
        
        Args:
            version_str: 버전 문자열
            
        Returns:
            버전 숫자 튜플
        """
        try:
            return tuple(int(x) for x in version_str.replace("v", "").split("."))
        except:
            return (0,)
    
    @staticmethod
    def _compare_versions(v1: str, v2: str) -> int:
        """
        두 버전을 비교
        
        Args:
            v1: 첫 번째 버전
            v2: 두 번째 버전
            
        Returns:
            v1 > v2: 양수
            v1 == v2: 0
            v1 < v2: 음수
        """
        parsed_v1 = AutoUpdater._parse_version(v1)
        parsed_v2 = AutoUpdater._parse_version(v2)
        
        # 길이를 맞춰서 비교
        max_len = max(len(parsed_v1), len(parsed_v2))
        v1_padded = parsed_v1 + (0,) * (max_len - len(parsed_v1))
        v2_padded = parsed_v2 + (0,) * (max_len - len(parsed_v2))
        
        for a, b in zip(v1_padded, v2_padded):
            if a > b:
                return 1
            elif a < b:
                return -1
        return 0
        
    def _log(self, message: str, level: str = "INFO"):
        """로그 출력"""
        if self.logger:
            self.logger.log(f"[Updater] {message}", level=level)
        else:
            print(f"[Updater] {message}")
    
    def check_for_updates(self, timeout: int = 10) -> Tuple[bool, Optional[Dict]]:
        """
        서버에서 최신 버전 확인
        
        Args:
            timeout: 요청 타임아웃 (초)
            
        Returns:
            (업데이트 필요 여부, 업데이트 정보 딕셔너리)
            업데이트 정보: {
                "version": str,
                "download_url": str,
                "release_notes": str,
                "release_date": str,
                "mandatory": bool
            }
        """
        version_url = f"{self.update_server_url}/version.json"
        
        try:
            self._log(f"버전 확인 중: {version_url}")
            
            # 서버에서 버전 정보 가져오기
            with urllib.request.urlopen(version_url, timeout=timeout) as response:
                content = response.read()
                # UTF-8 BOM 제거 후 디코딩
                if content.startswith(b'\xef\xbb\xbf'):
                    content = content[3:]
                data = json.loads(content.decode('utf-8'))
            
            latest_version = data.get("version", "").replace("v", "").strip()
            
            if not latest_version:
                self._log("서버에서 버전 정보를 찾을 수 없습니다", level="WARN")
                return False, None
            
            self._log(f"현재 버전: v{self.current_version}, 최신 버전: v{latest_version}")
            
            # 버전 비교
            if self._compare_versions(latest_version, self.current_version) > 0:
                self._log(f"새 버전 발견: v{latest_version}", level="INFO")
                return True, data
            else:
                self._log("최신 버전입니다")
                return False, None
                
        except urllib.error.URLError as e:
            self._log(f"서버 연결 실패: {e}", level="ERROR")
            return False, None
        except json.JSONDecodeError as e:
            self._log(f"버전 정보 파싱 실패: {e}", level="ERROR")
            return False, None
        except Exception as e:
            self._log(f"업데이트 확인 중 오류: {e}", level="ERROR")
            return False, None
    
    def download_update(self, download_url: str, progress_callback=None) -> Optional[str]:
        """
        업데이트 파일 다운로드
        
        Args:
            download_url: 다운로드 URL
            progress_callback: 진행률 콜백 함수 (percent: int)
            
        Returns:
            다운로드된 파일 경로 또는 None
        """
        try:
            self._log(f"업데이트 다운로드 중: {download_url}")
            
            # 임시 파일 경로
            temp_dir = tempfile.gettempdir()
            filename = os.path.basename(download_url)
            temp_file = os.path.join(temp_dir, f"update_{filename}")
            
            # 다운로드
            def report_hook(block_num, block_size, total_size):
                if progress_callback and total_size > 0:
                    downloaded = block_num * block_size
                    percent = min(int(downloaded * 100 / total_size), 100)
                    progress_callback(percent)
            
            urllib.request.urlretrieve(download_url, temp_file, reporthook=report_hook)
            
            self._log(f"다운로드 완료: {temp_file}")
            return temp_file
            
        except Exception as e:
            self._log(f"다운로드 실패: {e}", level="ERROR")
            return None
    
    def install_update(self, update_file: str):
        """
        업데이트 설치 (update.exe 사용)
        
        Args:
            update_file: 다운로드된 업데이트 파일 경로
        """
        try:
            # 현재 실행 파일 경로
            if getattr(sys, 'frozen', False):
                # PyInstaller로 패키징된 경우
                current_exe = sys.executable
            else:
                # 개발 환경
                self._log("개발 환경에서는 업데이트를 실행할 수 없습니다", level="WARN")
                return
            
            self._log(f"업데이트 설치 준비: {current_exe}")
            
            # update.exe 경로 확인
            updater_exe = os.path.join(os.path.dirname(current_exe), "update.exe")
            
            if os.path.exists(updater_exe):
                # update.exe가 있으면 사용 (권장)
                self._log("update.exe를 통한 업데이트 시작")
                
                subprocess.Popen(
                    [updater_exe, current_exe, update_file],
                    shell=False
                )
                
                # 현재 프로그램 종료
                self._log("프로그램 종료 (업데이트 적용)")
                sys.exit(0)
            else:
                # update.exe가 없으면 배치 파일 방식 사용 (폴백)
                self._log("update.exe가 없습니다. 배치 파일 방식 사용", level="WARN")
                self._install_update_batch(current_exe, update_file)
            
        except Exception as e:
            self._log(f"업데이트 설치 실패: {e}", level="ERROR")
            raise
    
    def _install_update_batch(self, current_exe: str, update_file: str):
        """
        배치 파일을 통한 업데이트 (폴백 방식)
        
        Args:
            current_exe: 현재 실행 파일 경로
            update_file: 업데이트 파일 경로
        """
        batch_file = os.path.join(os.path.dirname(current_exe), "update_installer.bat")
        
        with open(batch_file, "w", encoding="utf-8") as f:
            f.write(f"""@echo off
chcp 65001 > nul
echo Convert Pro 3 업데이트 설치 중...
echo.

REM 2초 대기 (현재 프로세스 종료 대기)
timeout /t 2 /nobreak > nul

REM 기존 파일 백업
if exist "{current_exe}" (
    echo 기존 버전 백업 중...
    move /y "{current_exe}" "{current_exe}.backup"
)

REM 새 버전 설치
echo 새 버전 설치 중...
move /y "{update_file}" "{current_exe}"

REM 설치 완료 확인
if exist "{current_exe}" (
    echo 업데이트 완료!
    echo 프로그램을 다시 시작합니다...
    timeout /t 2 /nobreak > nul
    start "" "{current_exe}"
    
    REM 백업 파일 삭제
    if exist "{current_exe}.backup" (
        del "{current_exe}.backup"
    )
) else (
    echo 업데이트 실패! 백업에서 복구합니다...
    if exist "{current_exe}.backup" (
        move /y "{current_exe}.backup" "{current_exe}"
        start "" "{current_exe}"
    )
)

REM 배치 파일 자체 삭제
del "%~f0"
""")
        
        self._log("업데이트 배치 스크립트 실행")
        
        subprocess.Popen(
            f'cmd /c "{batch_file}"',
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        # 현재 프로그램 종료
        self._log("프로그램 종료 (업데이트 적용)")
        sys.exit(0)
    
    def download_and_install(self, update_info: Dict, progress_callback=None):
        """
        업데이트 다운로드 및 설치 (통합 메서드)
        
        Args:
            update_info: check_for_updates()에서 반환된 업데이트 정보
            progress_callback: 진행률 콜백 함수
        """
        download_url = update_info.get("download_url")
        if not download_url:
            self._log("다운로드 URL이 없습니다", level="ERROR")
            return
        
        # 다운로드
        update_file = self.download_update(download_url, progress_callback)
        if not update_file:
            return
        
        # 설치
        self.install_update(update_file)


# ===============================================================
# 사용 예제
# ===============================================================
if __name__ == "__main__":
    # 테스트용
    updater = AutoUpdater(
        current_version="v1.2",
        update_server_url="https://example.com/updates"
    )
    
    has_update, info = updater.check_for_updates()
    if has_update:
        print(f"새 버전 발견: {info}")
    else:
        print("최신 버전입니다")
