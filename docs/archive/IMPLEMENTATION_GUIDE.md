# 🚀 빌드/배포/UI 시스템 구현 가이드

이 문서는 Convert Pro 3에 구현된 **자동 빌드**, **자동 업데이트**, **UI 개선 사항**을 다른 프로젝트에 적용하기 위한 완벽한 가이드입니다.

---

## 📋 목차

1. [프로젝트 구조](#1-프로젝트-구조)
2. [자동 버전 관리 시스템](#2-자동-버전-관리-시스템)
3. [통합 빌드 시스템](#3-통합-빌드-시스템)
4. [자동 업데이트 시스템](#4-자동-업데이트-시스템)
5. [단일 인스턴스 체크 (중복 실행 방지)](#5-단일-인스턴스-체크-중복-실행-방지)
6. [팝업 중복 방지](#6-팝업-중복-방지)
7. [전체 적용 체크리스트](#7-전체-적용-체크리스트)

---

## 1. 프로젝트 구조

### 📁 필요한 파일/폴더 구조

```
your_project/
├── version.py                        # 버전 정보
├── CHANGELOG.md                      # 변경 이력
├── requirements.txt                  # 패키지 의존성
├── your_main.py                      # 메인 프로그램
├── your_app.spec                     # PyInstaller spec 파일
├── build_scripts/
│   ├── make.py                       # 통합 빌드 스크립트
│   ├── make.bat                      # Windows 실행 파일
│   └── updater.spec                  # 업데이터 spec 파일
├── tools/
│   └── updater_standalone.py         # 독립 업데이터
├── utils/
│   └── update_manager.py             # 업데이트 매니저
└── ui/
    └── update_dialog.py              # 업데이트 다이얼로그
```

---

## 2. 자동 버전 관리 시스템

### 📄 `version.py` 생성

```python
"""
버전 정보 관리 모듈
자동 버전 업데이트를 위한 중앙 관리 파일
"""

# 프로그램 버전 (자동 업데이트됨)
VERSION = "1.5.0"

# 프로그램 정보
APP_NAME = "YourApp"
APP_FULL_NAME = f"{APP_NAME} v{VERSION}"
APP_DESCRIPTION = "Your Application Description"

# GitHub 정보 (자동 업데이트용)
GITHUB_REPO_OWNER = "your-username"
GITHUB_REPO_NAME = "your-repo-name"
GITHUB_REPO = f"{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}"

# 업데이트 체크 URL
UPDATE_CHECK_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
```

### 📄 `CHANGELOG.md` 생성

```markdown
# Changelog

All notable changes to this project will be documented in this file.

## [1.5.0] - 2026-02-20

### Added
- 초기 버전 릴리스
- 자동 업데이트 시스템 구현
- 단일 인스턴스 체크 (중복 실행 방지)

### Changed
- N/A

### Fixed
- N/A
```

### 📄 `requirements.txt` 업데이트

```txt
# 기존 패키지들...

# 자동 업데이트 시스템 필수 패키지
requests>=2.31.0
psutil>=5.9.0
```

---

## 3. 통합 빌드 시스템

### 📄 `build_scripts/make.py`

**전체 코드 복사 (Convert Pro 3에서):**

```python
"""
통합 빌드 스크립트
- 버전 관리 (patch/minor/major)
- PyInstaller 빌드
- GitHub 배포
"""

import os
import sys
import json
import subprocess
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

# ============================================
# 경로 설정 (PyInstaller 호환)
# ============================================
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = Path(sys.executable).parent
else:
    SCRIPT_DIR = Path(__file__).parent

PROJECT_ROOT = SCRIPT_DIR.parent
VERSION_FILE = PROJECT_ROOT / "version.py"
CHANGELOG_FILE = PROJECT_ROOT / "CHANGELOG.md"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"

# ============================================
# 색상 출력 (Windows CMD 지원)
# ============================================
def print_header(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")

def print_success(msg):
    print(f"✅ {msg}")

def print_error(msg):
    print(f"❌ {msg}")

def print_info(msg):
    print(f"ℹ️  {msg}")

# ============================================
# 버전 관리
# ============================================
def get_current_version():
    """version.py에서 현재 버전 읽기"""
    with open(VERSION_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('VERSION ='):
                return line.split('=')[1].strip().strip('"').strip("'")
    return "0.0.0"

def bump_version(bump_type='patch'):
    """
    버전 업데이트
    bump_type: 'patch' (0.0.1), 'minor' (0.1.0), 'major' (1.0.0)
    """
    current = get_current_version()
    major, minor, patch = map(int, current.split('.'))
    
    if bump_type == 'major':
        major += 1
        minor = 0
        patch = 0
    elif bump_type == 'minor':
        minor += 1
        patch = 0
    else:  # patch
        patch += 1
    
    new_version = f"{major}.{minor}.{patch}"
    
    # version.py 업데이트
    with open(VERSION_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace(
        f'VERSION = "{current}"',
        f'VERSION = "{new_version}"'
    )
    
    with open(VERSION_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print_success(f"버전 업데이트: {current} → {new_version}")
    return new_version

def update_changelog(version, bump_type):
    """CHANGELOG.md 업데이트"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 변경 타입별 기본 템플릿
    templates = {
        'major': "### Changed\n- 주요 기능 대폭 개선\n",
        'minor': "### Added\n- 새로운 기능 추가\n",
        'patch': "### Fixed\n- 버그 수정 및 안정성 개선\n"
    }
    
    new_entry = f"""
## [{version}] - {today}

{templates.get(bump_type, templates['patch'])}
"""
    
    with open(CHANGELOG_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # "# Changelog" 다음에 새 엔트리 삽입
    content = content.replace(
        "# Changelog\n",
        f"# Changelog\n{new_entry}"
    )
    
    with open(CHANGELOG_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print_success(f"CHANGELOG 업데이트 완료")

# ============================================
# 빌드
# ============================================
def clean_build():
    """빌드 폴더 정리"""
    print_info("이전 빌드 파일 정리 중...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    print_success("정리 완료!")

def build_main_app():
    """메인 프로그램 빌드"""
    print_header("메인 프로그램 빌드 시작")
    
    # PyInstaller 실행 (your_app.spec 사용)
    spec_file = PROJECT_ROOT / "your_app.spec"  # ⚠️ 실제 spec 파일명으로 변경
    
    if not spec_file.exists():
        print_error(f"spec 파일을 찾을 수 없습니다: {spec_file}")
        return False
    
    cmd = [
        "pyinstaller",
        str(spec_file),
        "--clean",
        "--noconfirm"
    ]
    
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    
    if result.returncode == 0:
        print_success("메인 프로그램 빌드 완료!")
        return True
    else:
        print_error("메인 프로그램 빌드 실패")
        return False

def build_updater():
    """업데이터 빌드"""
    print_header("업데이터 빌드 시작")
    
    spec_file = SCRIPT_DIR / "updater.spec"
    
    if not spec_file.exists():
        print_error(f"updater.spec을 찾을 수 없습니다: {spec_file}")
        return False
    
    cmd = [
        "pyinstaller",
        str(spec_file),
        "--clean",
        "--noconfirm"
    ]
    
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    
    updater_exe_name = "updater.exe"
    
    if result.returncode == 0:
        # updater.exe를 dist/tools/ 폴더로 이동
        updater_exe_path_in_dist = DIST_DIR / updater_exe_name
        if updater_exe_path_in_dist.exists():
            tools_dir = DIST_DIR / "tools"
            tools_dir.mkdir(exist_ok=True)
            shutil.move(str(updater_exe_path_in_dist), str(tools_dir / updater_exe_name))
            print_success("업데이터 빌드 완료!")
            return True
    
    print_error("업데이터 빌드 실패")
    return False

def create_full_package():
    """_full.zip 패키지 생성"""
    print_header("전체 패키지 생성 중...")
    
    version = get_current_version()
    zip_name = f"YourApp_v{version}_full.zip"  # ⚠️ 앱 이름 변경
    zip_path = DIST_DIR / zip_name
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # 메인 exe 추가
        for exe in DIST_DIR.glob("*.exe"):
            zipf.write(exe, exe.name)
        
        # tools 폴더 추가
        tools_dir = DIST_DIR / "tools"
        if tools_dir.exists():
            for file in tools_dir.rglob("*"):
                if file.is_file():
                    arcname = str(file.relative_to(DIST_DIR))
                    zipf.write(file, arcname)
    
    print_success(f"패키지 생성 완료: {zip_name}")

# ============================================
# GitHub 배포
# ============================================
def deploy_to_github():
    """GitHub Release 생성 및 업로드"""
    print_header("GitHub 배포 시작")
    
    version = get_current_version()
    tag = f"v{version}"
    
    # GitHub CLI 설치 확인
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except:
        print_error("GitHub CLI가 설치되지 않았습니다.")
        print_info("설치: https://cli.github.com/")
        return False
    
    # Release 생성
    print_info(f"Release 생성 중: {tag}")
    
    # CHANGELOG에서 최신 항목 추출
    with open(CHANGELOG_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    notes = []
    in_current_version = False
    for line in lines:
        if line.startswith(f"## [{version}]"):
            in_current_version = True
            continue
        elif line.startswith("## [") and in_current_version:
            break
        elif in_current_version:
            notes.append(line)
    
    release_notes = ''.join(notes).strip()
    
    # Release 생성
    cmd = [
        "gh", "release", "create", tag,
        "--title", f"YourApp {tag}",  # ⚠️ 앱 이름 변경
        "--notes", release_notes or "버그 수정 및 개선"
    ]
    
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    
    if result.returncode != 0:
        print_error("Release 생성 실패")
        return False
    
    print_success(f"Release 생성 완료: {tag}")
    
    # 파일 업로드
    print_info("파일 업로드 중...")
    
    # _full.zip 업로드
    zip_file = DIST_DIR / f"YourApp_v{version}_full.zip"  # ⚠️ 앱 이름 변경
    if zip_file.exists():
        cmd = ["gh", "release", "upload", tag, str(zip_file)]
        subprocess.run(cmd, cwd=PROJECT_ROOT)
    
    # .exe 파일 업로드
    for exe in DIST_DIR.glob("*.exe"):
        cmd = ["gh", "release", "upload", tag, str(exe)]
        subprocess.run(cmd, cwd=PROJECT_ROOT)
    
    print_success("GitHub 배포 완료!")
    print_info(f"릴리스 URL: https://github.com/YOUR_USERNAME/YOUR_REPO/releases/tag/{tag}")
    
    return True

# ============================================
# 메인 메뉴
# ============================================
def show_menu():
    """빌드 메뉴 표시"""
    print_header("빌드 시스템")
    
    version = get_current_version()
    print(f"📦 현재 버전: {version}\n")
    
    print("0️⃣  빌드만 (버전 유지)")
    print("1️⃣  빌드 + Patch 버전 증가 (x.x.1)")
    print("2️⃣  빌드 + Minor 버전 증가 (x.1.0)")
    print("3️⃣  빌드 + Major 버전 증가 (1.0.0)")
    print("4️⃣  업데이터만 빌드")
    print("5️⃣  정리 (빌드 폴더 삭제)")
    print("6️⃣  GitHub 배포 (현재 버전)")
    print("7️⃣  전체 플로우 (버전 증가 + 빌드 + 배포)")
    print("9️⃣  종료")
    print()

def main():
    """메인 실행"""
    while True:
        show_menu()
        choice = input("선택 (0-9): ").strip()
        
        if choice == '0':
            # 빌드만
            clean_build()
            build_updater()
            build_main_app()
            create_full_package()
            print_success("✨ 빌드 완료!")
            
        elif choice in ['1', '2', '3']:
            # 버전 증가 + 빌드
            bump_types = {'1': 'patch', '2': 'minor', '3': 'major'}
            bump_type = bump_types[choice]
            
            new_version = bump_version(bump_type)
            update_changelog(new_version, bump_type)
            
            clean_build()
            build_updater()
            build_main_app()
            create_full_package()
            
            print_success(f"✨ 빌드 완료! (v{new_version})")
            
        elif choice == '4':
            # 업데이터만
            build_updater()
            
        elif choice == '5':
            # 정리
            clean_build()
            
        elif choice == '6':
            # GitHub 배포
            deploy_to_github()
            
        elif choice == '7':
            # 전체 플로우
            bump_type = 'patch'
            new_version = bump_version(bump_type)
            update_changelog(new_version, bump_type)
            
            clean_build()
            build_updater()
            if build_main_app():
                create_full_package()
                deploy_to_github()
                print_success(f"🚀 전체 배포 완료! (v{new_version})")
            
        elif choice == '9':
            # 종료
            print_info("종료합니다.")
            break
        
        else:
            print_error("잘못된 선택입니다.")
        
        input("\n계속하려면 Enter를 누르세요...")
        print("\n" * 2)

if __name__ == "__main__":
    main()
```

### 📄 `build_scripts/make.bat`

```batch
@echo off
chcp 65001 >nul
title 빌드 시스템

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║           YourApp 빌드 시스템                          ║
echo ╚════════════════════════════════════════════════════════╝
echo.

REM Python 가상환경 확인
if exist "..\venv\Scripts\activate.bat" (
    echo [정보] 가상환경 활성화 중...
    call ..\venv\Scripts\activate.bat
)

REM Python 및 필수 패키지 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되지 않았습니다.
    pause
    exit /b 1
)

REM make.py 실행
python make.py

pause
```

### 📄 `build_scripts/updater.spec`

```python
# -*- mode: python ; coding: utf-8 -*-

import os
import sys

# spec_root 경로 설정 (PyInstaller 호환)
if getattr(sys, 'frozen', False):
    spec_root = os.path.abspath(os.path.join(os.path.dirname(sys.executable), '..'))
else:
    spec_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# 업데이터 소스 경로
updater_script = os.path.join(spec_root, 'tools', 'updater_standalone.py')

a = Analysis(
    [updater_script],
    pathex=[spec_root],
    binaries=[],
    datas=[],
    hiddenimports=['psutil'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='updater',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

---

## 4. 자동 업데이트 시스템

### 📄 `utils/update_manager.py`

```python
"""
자동 업데이트 관리자
GitHub Releases API를 통한 업데이트 확인 및 다운로드
"""

import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

class UpdateManager:
    def __init__(self, logger=None):
        self.logger = logger
        
        # version.py에서 정보 가져오기
        try:
            from version import VERSION, GITHUB_REPO, UPDATE_CHECK_URL
            self.current_version = VERSION
            self.github_repo = GITHUB_REPO
            self.update_check_url = UPDATE_CHECK_URL
        except ImportError:
            if logger:
                logger.log("version.py를 찾을 수 없습니다.", level="ERROR")
            self.current_version = "0.0.0"
            self.github_repo = ""
            self.update_check_url = ""
    
    def check_for_updates(self):
        """업데이트 확인"""
        try:
            req = Request(self.update_check_url)
            req.add_header('User-Agent', 'Python-App-Updater')
            
            with urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            latest_version = data['tag_name'].lstrip('v')
            
            if self._version_compare(latest_version, self.current_version) > 0:
                return {
                    'available': True,
                    'version': latest_version,
                    'url': data['html_url'],
                    'assets': data.get('assets', []),
                    'body': data.get('body', '')
                }
            else:
                return {'available': False}
        
        except Exception as e:
            if self.logger:
                self.logger.log(f"업데이트 확인 실패: {e}", level="ERROR")
            return {'available': False, 'error': str(e)}
    
    def _version_compare(self, v1, v2):
        """버전 비교 (v1 > v2 이면 양수)"""
        parts1 = [int(x) for x in v1.split('.')]
        parts2 = [int(x) for x in v2.split('.')]
        
        for i in range(max(len(parts1), len(parts2))):
            p1 = parts1[i] if i < len(parts1) else 0
            p2 = parts2[i] if i < len(parts2) else 0
            
            if p1 > p2:
                return 1
            elif p1 < p2:
                return -1
        
        return 0
    
    def download_update(self, update_info, progress_callback=None):
        """업데이트 다운로드"""
        try:
            # _full.zip 우선 다운로드
            assets = update_info.get('assets', [])
            download_url = None
            
            for asset in assets:
                if asset['name'].endswith('_full.zip'):
                    download_url = asset['browser_download_url']
                    break
            
            if not download_url:
                # .exe 파일 찾기
                for asset in assets:
                    if asset['name'].endswith('.exe'):
                        download_url = asset['browser_download_url']
                        break
            
            if not download_url:
                raise Exception("다운로드 가능한 파일을 찾을 수 없습니다.")
            
            # 다운로드
            temp_dir = Path(tempfile.gettempdir()) / "app_update"
            temp_dir.mkdir(exist_ok=True)
            
            filename = download_url.split('/')[-1]
            download_path = temp_dir / filename
            
            req = Request(download_url)
            req.add_header('User-Agent', 'Python-App-Updater')
            
            with urlopen(req) as response:
                total_size = int(response.headers.get('Content-Length', 0))
                downloaded = 0
                
                with open(download_path, 'wb') as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback and total_size > 0:
                            progress = (downloaded / total_size) * 100
                            progress_callback(progress)
            
            return str(download_path)
        
        except Exception as e:
            if self.logger:
                self.logger.log(f"다운로드 실패: {e}", level="ERROR")
            raise
    
    def install_update(self, download_path):
        """업데이트 설치 (업데이터 실행)"""
        try:
            app_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path.cwd()
            updater_exe = app_dir / "tools" / "updater.exe"
            
            if not updater_exe.exists():
                raise Exception(f"업데이터를 찾을 수 없습니다: {updater_exe}")
            
            # 업데이터 실행
            subprocess.Popen([
                str(updater_exe),
                str(download_path),
                str(app_dir)
            ])
            
            if self.logger:
                self.logger.log("업데이터 실행 중...", level="INFO")
            
            return True
        
        except Exception as e:
            if self.logger:
                self.logger.log(f"업데이트 실행 실패: {e}", level="ERROR")
            raise
```

### 📄 `ui/update_dialog.py`

```python
"""
업데이트 다이얼로그
자동 업데이트 진행 UI
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading

class UpdateDialog:
    def __init__(self, parent, update_manager, update_info):
        self.parent = parent
        self.update_manager = update_manager
        self.update_info = update_info
        
        self.win = tk.Toplevel(parent)
        self.win.title("업데이트 가능")
        self.win.geometry("500x300")
        self.win.resizable(False, False)
        
        # 모달 설정
        self.win.transient(parent)
        self.win.grab_set()
        
        self._create_ui()
        
        # 자동 업데이트 시작
        self.win.after(500, self._start_auto_update)
    
    def _create_ui(self):
        """UI 생성"""
        # 제목
        title_frame = tk.Frame(self.win, bg="#4CAF50", height=60)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="🎉 새 버전이 있습니다!",
            font=("맑은 고딕", 14, "bold"),
            bg="#4CAF50",
            fg="white"
        )
        title_label.pack(expand=True)
        
        # 버전 정보
        info_frame = tk.Frame(self.win, padx=20, pady=20)
        info_frame.pack(fill="both", expand=True)
        
        version_text = f"현재 버전: {self.update_manager.current_version}\n"
        version_text += f"최신 버전: {self.update_info['version']}"
        
        version_label = tk.Label(
            info_frame,
            text=version_text,
            font=("맑은 고딕", 11),
            justify="left"
        )
        version_label.pack(anchor="w", pady=(0, 10))
        
        # 변경사항
        changes_label = tk.Label(
            info_frame,
            text="📝 변경사항:",
            font=("맑은 고딕", 10, "bold"),
            justify="left"
        )
        changes_label.pack(anchor="w")
        
        changes_text = tk.Text(
            info_frame,
            height=6,
            wrap="word",
            font=("맑은 고딕", 9),
            bg="#f5f5f5"
        )
        changes_text.pack(fill="both", expand=True, pady=(5, 10))
        changes_text.insert("1.0", self.update_info.get('body', '업데이트 내용을 확인하세요.'))
        changes_text.config(state="disabled")
        
        # 진행바
        self.progress_frame = tk.Frame(self.win, padx=20, pady=10)
        self.progress_frame.pack(fill="x")
        
        self.progress_label = tk.Label(
            self.progress_frame,
            text="자동 업데이트를 시작합니다...",
            font=("맑은 고딕", 9)
        )
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            mode='indeterminate',
            length=400
        )
        self.progress_bar.pack(pady=(5, 0))
    
    def _start_auto_update(self):
        """자동 업데이트 시작"""
        self.progress_bar.start(10)
        
        thread = threading.Thread(target=self._update_thread, daemon=True)
        thread.start()
    
    def _update_thread(self):
        """업데이트 스레드"""
        try:
            # 다운로드
            self.win.after(0, lambda: self.progress_label.config(text="📥 업데이트 다운로드 중..."))
            
            download_path = self.update_manager.download_update(
                self.update_info,
                progress_callback=self._update_progress
            )
            
            # 설치
            self.win.after(0, lambda: self.progress_label.config(text="⚙️ 업데이트 설치 중..."))
            
            self.update_manager.install_update(download_path)
            
            # 종료
            self.win.after(0, self._finish_update)
        
        except Exception as e:
            self.win.after(0, lambda: self._show_error(str(e)))
    
    def _update_progress(self, percent):
        """진행률 업데이트"""
        def update():
            self.progress_bar.stop()
            self.progress_bar.config(mode='determinate', value=percent)
            self.progress_label.config(text=f"📥 다운로드 중... {int(percent)}%")
        
        self.win.after(0, update)
    
    def _finish_update(self):
        """업데이트 완료"""
        self.progress_bar.stop()
        self.progress_label.config(text="✅ 업데이트 완료! 프로그램을 재시작합니다...")
        
        # 1초 후 프로그램 종료
        self.win.after(1000, lambda: self.parent.quit())
    
    def _show_error(self, error_msg):
        """오류 표시"""
        self.progress_bar.stop()
        self.progress_label.config(text=f"❌ 업데이트 실패: {error_msg}")
        
        messagebox.showerror(
            "업데이트 실패",
            f"업데이트 중 오류가 발생했습니다:\n\n{error_msg}",
            parent=self.win
        )
        
        self.win.destroy()
```

### 📄 `tools/updater_standalone.py`

```python
"""
독립 실행형 업데이터
메인 프로그램 종료 후 파일 교체 및 재시작
"""

import os
import sys
import time
import shutil
import zipfile
import subprocess
import psutil
from pathlib import Path

def wait_for_process_exit(process_name, timeout=30):
    """프로세스 종료 대기"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        found = False
        for proc in psutil.process_iter(['name']):
            if process_name.lower() in proc.info['name'].lower():
                found = True
                break
        
        if not found:
            return True
        
        time.sleep(0.5)
    
    return False

def extract_update(zip_path, target_dir):
    """업데이트 파일 압축 해제"""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(target_dir)

def replace_files(source_dir, target_dir, main_exe_name):
    """파일 교체"""
    # .exe 파일 교체
    for file in Path(source_dir).glob("*.exe"):
        target_file = Path(target_dir) / file.name
        if target_file.exists():
            target_file.unlink()
        shutil.move(str(file), str(target_file))
    
    # tools 폴더 교체 (업데이터 제외)
    source_tools = Path(source_dir) / "tools"
    target_tools = Path(target_dir) / "tools"
    
    if source_tools.exists():
        for file in source_tools.glob("*"):
            if file.name != "updater.exe":  # 자기 자신 제외
                target_file = target_tools / file.name
                if target_file.exists():
                    target_file.unlink()
                shutil.move(str(file), str(target_file))

def main():
    """메인 실행"""
    if len(sys.argv) < 3:
        print("사용법: updater.exe <zip_path> <app_dir>")
        sys.exit(1)
    
    zip_path = sys.argv[1]
    app_dir = sys.argv[2]
    
    # 메인 프로그램 종료 대기
    main_exe_name = "YourApp"  # ⚠️ 실제 exe 이름으로 변경 (확장자 제외)
    print(f"[1/4] {main_exe_name} 종료 대기 중...")
    
    if not wait_for_process_exit(main_exe_name, timeout=30):
        print(f"[오류] {main_exe_name}가 종료되지 않았습니다.")
        input("계속하려면 Enter를 누르세요...")
        sys.exit(1)
    
    time.sleep(2)  # 안전을 위한 추가 대기
    
    # 압축 해제
    print("[2/4] 업데이트 파일 압축 해제 중...")
    temp_dir = Path(zip_path).parent / "extracted"
    temp_dir.mkdir(exist_ok=True)
    
    extract_update(zip_path, temp_dir)
    
    # 파일 교체
    print("[3/4] 파일 교체 중...")
    replace_files(temp_dir, app_dir, main_exe_name)
    
    # 정리
    shutil.rmtree(temp_dir, ignore_errors=True)
    
    # 메인 프로그램 재시작
    print("[4/4] 프로그램 재시작 중...")
    main_exe = Path(app_dir) / f"{main_exe_name}.exe"
    
    subprocess.Popen([str(main_exe)], cwd=app_dir)
    
    print("✅ 업데이트 완료!")
    time.sleep(2)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[오류] {e}")
        input("계속하려면 Enter를 누르세요...")
        sys.exit(1)
```

---

## 5. 단일 인스턴스 체크 (중복 실행 방지)

### 📄 메인 프로그램에 추가 (`your_main.py`)

**파일 맨 위에 import 추가:**

```python
import sys
import tkinter as tk
from tkinter import messagebox
```

**`if __name__ == "__main__":` 블록 수정:**

```python
if __name__ == "__main__":
    # ============================================
    # 단일 인스턴스 체크 (중복 실행 방지)
    # ============================================
    import tempfile
    
    lock_file_path = os.path.join(tempfile.gettempdir(), 'YourApp.lock')  # ⚠️ 앱 이름 변경
    lock_file = None
    
    try:
        if sys.platform == 'win32':
            # Windows: 파일 잠금 사용
            import msvcrt
            try:
                lock_file = open(lock_file_path, 'w')
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except (IOError, OSError):
                # 이미 실행 중
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror(
                    "YourApp",  # ⚠️ 앱 이름 변경
                    "YourApp이 이미 실행 중입니다.\n\n"
                    "작업 표시줄에서 실행 중인 프로그램을 확인하세요."
                )
                sys.exit(1)
        else:
            # Linux/Mac: fcntl 사용
            import fcntl
            lock_file = open(lock_file_path, 'w')
            fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        # 정상 실행
        YourApp().run()  # ⚠️ 실제 앱 클래스명으로 변경
        
    except BlockingIOError:
        # 이미 실행 중
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "YourApp",  # ⚠️ 앱 이름 변경
            "YourApp이 이미 실행 중입니다."
        )
        sys.exit(1)
    finally:
        # 프로그램 종료 시 잠금 해제
        if lock_file:
            try:
                if sys.platform == 'win32':
                    import msvcrt
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                lock_file.close()
                os.remove(lock_file_path)
            except:
                pass
```

---

## 6. 팝업 중복 방지

### 📄 메인 앱 클래스 `__init__`에 추가

```python
class YourApp:
    def __init__(self):
        # ... 기존 초기화 코드 ...
        
        # 열린 설정 창 추적
        self.open_settings_windows = {}  # {창키: 창객체}
```

### 📄 설정 창 열기 메서드 수정

```python
def open_settings(self, item_id):
    """설정 창 열기 (중복 방지)"""
    # 고유 키 생성 (아이템마다 다른 키)
    window_key = f"settings_{item_id}"
    
    # 이미 열린 창이 있는지 확인
    if window_key in self.open_settings_windows:
        existing_window = self.open_settings_windows[window_key]
        try:
            # 창이 아직 존재하면 포커스
            existing_window.lift()
            existing_window.focus_force()
            self.logger.log(f"설정 창이 이미 열려있습니다: {item_id}", level="INFO")
            return
        except:
            # 창이 닫혔으면 딕셔너리에서 제거
            del self.open_settings_windows[window_key]
    
    # 새 창 열기
    settings_window = YourSettingsUI(self.root, item_id)
    self.open_settings_windows[window_key] = settings_window
    
    # 창이 닫힐 때 딕셔너리에서 제거하는 콜백 등록
    def on_close():
        if window_key in self.open_settings_windows:
            del self.open_settings_windows[window_key]
        try:
            settings_window.destroy()
        except:
            pass
    
    settings_window.protocol("WM_DELETE_WINDOW", on_close)
```

---

## 7. 전체 적용 체크리스트

### ✅ 1단계: 기본 파일 생성

- [ ] `version.py` 생성 (앱 이름, GitHub 정보 수정)
- [ ] `CHANGELOG.md` 생성
- [ ] `requirements.txt`에 `requests`, `psutil` 추가

### ✅ 2단계: 빌드 시스템

- [ ] `build_scripts/` 폴더 생성
- [ ] `make.py` 복사 및 수정 (앱 이름 변경)
- [ ] `make.bat` 복사 및 수정
- [ ] `updater.spec` 복사
- [ ] 메인 앱 `.spec` 파일 확인/생성

### ✅ 3단계: 업데이트 시스템

- [ ] `tools/updater_standalone.py` 복사 및 수정 (exe 이름 변경)
- [ ] `utils/update_manager.py` 복사
- [ ] `ui/update_dialog.py` 복사
- [ ] 메인 앱에 `UpdateManager` 통합

### ✅ 4단계: UI 개선

- [ ] 메인 앱에 **단일 인스턴스 체크** 추가
- [ ] 메인 앱에 **팝업 중복 방지** 추가

### ✅ 5단계: 테스트

- [ ] 로컬 빌드 테스트: `make.bat` → 0번
- [ ] 버전 증가 테스트: `make.bat` → 1번
- [ ] 중복 실행 방지 테스트
- [ ] 설정 창 중복 방지 테스트

### ✅ 6단계: GitHub 배포 설정

- [ ] GitHub 저장소 생성
- [ ] GitHub CLI 설치: https://cli.github.com/
- [ ] `gh auth login` 실행
- [ ] `make.bat` → 7번 (전체 플로우 테스트)

### ✅ 7단계: 자동 업데이트 테스트

- [ ] 다른 컴퓨터에 이전 버전 설치
- [ ] 새 버전 GitHub 배포
- [ ] 이전 버전 실행 → 업데이트 버튼 클릭
- [ ] 자동 업데이트 동작 확인

---

## 📝 주의사항

### ⚠️ 반드시 변경해야 할 부분

1. **앱 이름 변경:**
   - `version.py`: `APP_NAME`
   - `make.py`: "YourApp" → 실제 앱 이름
   - `updater_standalone.py`: `main_exe_name`
   - `your_main.py`: lock 파일명

2. **GitHub 정보 변경:**
   - `version.py`: `GITHUB_REPO_OWNER`, `GITHUB_REPO_NAME`

3. **spec 파일명 변경:**
   - `make.py`: `your_app.spec` → 실제 spec 파일명

---

## 🎯 핵심 기능 요약

| 기능 | 설명 | 파일 |
|------|------|------|
| 🔢 **자동 버전 관리** | Patch/Minor/Major 버전 자동 증가 | `version.py`, `make.py` |
| 📦 **통합 빌드** | 메인 + 업데이터 빌드, ZIP 패키징 | `make.py`, `make.bat` |
| 🚀 **GitHub 배포** | GitHub Releases 자동 생성/업로드 | `make.py` (gh CLI) |
| 🔄 **자동 업데이트** | 확인 → 다운로드 → 설치 → 재시작 | `update_manager.py`, `update_dialog.py`, `updater_standalone.py` |
| 🔒 **중복 실행 방지** | 단일 인스턴스 체크 (파일 잠금) | `your_main.py` (if __name__) |
| 🚫 **팝업 중복 방지** | 같은 설정 창 여러 개 안 열림 | `your_main.py` (open_settings_windows) |

---

## 📞 문제 해결

### Q1: "GitHub CLI를 찾을 수 없습니다"
```bash
# Windows (chocolatey)
choco install gh

# 또는 직접 설치
https://cli.github.com/
```

### Q2: "업데이터를 찾을 수 없습니다"
```bash
# updater.exe가 dist/tools/ 에 있는지 확인
# make.bat → 4번 (업데이터만 빌드)
```

### Q3: "requests 모듈이 없습니다"
```bash
pip install requests psutil
```

### Q4: "중복 실행 방지가 안됩니다"
- PyInstaller로 빌드된 `.exe`에서만 정상 동작
- Python 스크립트로 직접 실행 시 여러 개 실행 가능

---

## 🎉 완료!

이제 485 프로그램에 이 문서를 참고하여 동일한 시스템을 적용하세요!

**적용 순서:**
1. 체크리스트 1단계부터 차례대로 진행
2. 각 파일의 ⚠️ 표시된 부분을 실제 앱에 맞게 수정
3. 로컬 테스트 완료 후 GitHub 배포

질문이 있으면 이 문서를 참고하거나 Cursor AI에게 이 문서와 함께 질문하세요!
