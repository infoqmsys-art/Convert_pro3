"""
Convert Pro 3 - 통합 빌드 관리 스크립트

사용법:
    python make.py build          # 빌드만 (버전 유지)
    python make.py bump patch     # 버전 증가 (1.5.3 -> 1.5.4)
    python make.py bump minor     # 버전 증가 (1.5.3 -> 1.6.0)
    python make.py bump major     # 버전 증가 (1.5.3 -> 2.0.0)
    python make.py release        # 빌드 + 버전 증가(patch) + CHANGELOG 생성
    python make.py deploy         # GitHub Release 배포
    python make.py full           # 전체 (release + deploy)
"""

import sys
import os
import re
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

# 경로 설정 (PyInstaller 호환)
if getattr(sys, 'frozen', False):
    # PyInstaller로 빌드된 경우
    SCRIPT_DIR = Path(sys.executable).parent
else:
    # 일반 Python 스크립트로 실행된 경우
    SCRIPT_DIR = Path(__file__).parent

PROJECT_ROOT = SCRIPT_DIR.parent
VERSION_FILE = PROJECT_ROOT / "version.py"
CHANGELOG_FILE = PROJECT_ROOT / "CHANGELOG.md"
SPEC_FILE = PROJECT_ROOT / "Convert_pro3.spec"
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """헤더 출력"""
    print(f"\n{'='*60}")
    print(f"{text}")
    print(f"{'='*60}\n")


def print_success(text):
    """성공 메시지"""
    print(f"[OK] {text}")


def print_error(text):
    """에러 메시지"""
    print(f"[ERROR] {text}")


def print_warning(text):
    """경고 메시지"""
    print(f"[WARNING] {text}")


def print_info(text):
    """정보 메시지"""
    print(f"[INFO] {text}")


def read_version():
    """현재 버전 읽기"""
    with open(VERSION_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    major = int(re.search(r'VERSION_MAJOR = (\d+)', content).group(1))
    minor = int(re.search(r'VERSION_MINOR = (\d+)', content).group(1))
    patch = int(re.search(r'VERSION_PATCH = (\d+)', content).group(1))
    
    return major, minor, patch


def bump_version(bump_type):
    """버전 증가"""
    major, minor, patch = read_version()
    old_version = f"v{major}.{minor}.{patch}"
    
    if bump_type == 'major':
        major += 1
        minor = 0
        patch = 0
    elif bump_type == 'minor':
        minor += 1
        patch = 0
    elif bump_type == 'patch':
        patch += 1
    else:
        print_error(f"잘못된 버전 타입: {bump_type}")
        print_info("사용 가능: major, minor, patch")
        return False
    
    new_version = f"v{major}.{minor}.{patch}"
    
    # version.py를 정규식으로 수정 — APP_NAME 등 나머지 내용은 그대로 보존
    with open(VERSION_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = re.sub(r'VERSION_MAJOR\s*=\s*\d+', f'VERSION_MAJOR = {major}', content)
    content = re.sub(r'VERSION_MINOR\s*=\s*\d+', f'VERSION_MINOR = {minor}', content)
    content = re.sub(r'VERSION_PATCH\s*=\s*\d+', f'VERSION_PATCH = {patch}', content)
    
    with open(VERSION_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print_success(f"버전 증가: {old_version} → {new_version}")
    
    # CHANGELOG 업데이트
    update_changelog(major, minor, patch)
    
    return True


def update_changelog(major, minor, patch):
    """CHANGELOG.md에 새 버전 섹션 추가"""
    new_version = f"v{major}.{minor}.{patch}"
    today = datetime.now().strftime("%Y-%m-%d")
    
    new_section = f"""## {new_version} ({today})
### 추가
- (여기에 추가된 기능 작성)

### 수정
- (여기에 수정된 기능 작성)

### 버그 수정
- (여기에 수정된 버그 작성)

---

"""
    
    if CHANGELOG_FILE.exists():
        with open(CHANGELOG_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        title_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('## '):
                title_idx = i
                break
        
        lines.insert(title_idx, new_section)
        new_content = '\n'.join(lines)
    else:
        new_content = f"""# 큐엠 자동화 관리 프로그램 변경 이력

{new_section}
"""
    
    with open(CHANGELOG_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print_success("CHANGELOG.md 업데이트 완료")
    print_warning("CHANGELOG.md를 열어서 변경사항을 작성해주세요!")


def clean_build():
    """빌드 디렉토리 정리"""
    print_info("이전 빌드 정리 중...")
    
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    
    print_success("정리 완료")


def build():
    """PyInstaller로 빌드"""
    print_header("큐엠 자동화 관리 프로그램 빌드 시작")
    
    # 버전 정보
    major, minor, patch = read_version()
    version_short = f"v{major}.{minor}"
    version_full = f"v{major}.{minor}.{patch}"
    
    print_info(f"현재 버전: {version_full}")
    print_info(f"짧은 버전: {version_short}")
    print()
    
    # 빌드 디렉토리 정리
    print_info("이전 빌드 파일 정리 중...")
    clean_build()
    print_success("정리 완료")
    print()
    
    # 1. 메인 프로그램 빌드
    print_header("1단계: 메인 프로그램 빌드")
    print_info(f"출력 파일: ConvertPro3_{version_short}.exe")
    print_info("PyInstaller 실행 중... (잠시 기다려주세요)")
    print()
    
    result = subprocess.run(
        ['pyinstaller', 'Convert_pro3.spec', '--clean'],
        cwd=PROJECT_ROOT,
        capture_output=False
    )
    
    if result.returncode != 0:
        print_error("메인 프로그램 빌드 실패")
        return False
    
    main_exe = DIST_DIR / f"ConvertPro3_{version_short}.exe"
    if not main_exe.exists():
        print_error(f"빌드 파일을 찾을 수 없습니다: {main_exe}")
        return False
    
    size_mb = main_exe.stat().st_size / (1024 * 1024)
    print_success(f"메인 프로그램 빌드 완료! (크기: {size_mb:.2f} MB)")
    print()

    # ── monitoring 폴더 복사 (외부 편집 가능 파일) ──────────────────────
    print_info("monitoring 폴더 복사 중... (server.py / templates / static)")
    monitoring_src = PROJECT_ROOT / "monitoring"
    monitoring_dst = DIST_DIR / "monitoring"

    if monitoring_dst.exists():
        shutil.rmtree(monitoring_dst)
    monitoring_dst.mkdir(parents=True)

    # server.py, data_cache.py 복사
    for py_name in ("server.py", "data_cache.py"):
        src_py = monitoring_src / py_name
        if src_py.exists():
            shutil.copy2(src_py, monitoring_dst / py_name)

    # templates 폴더 복사
    templates_src = monitoring_src / "templates"
    if templates_src.exists():
        shutil.copytree(str(templates_src), str(monitoring_dst / "templates"))

    # static 폴더 복사 (CSS 등)
    static_src = monitoring_src / "static"
    if static_src.exists():
        shutil.copytree(str(static_src), str(monitoring_dst / "static"))

    # 패키지로 인식되도록 __init__.py 생성
    (monitoring_dst / "__init__.py").write_text("", encoding="utf-8")

    print_success("monitoring 폴더 복사 완료!")
    print_info("  server.py / templates/ / static/ 를 직접 수정하면 재빌드 없이 웹 화면이 바뀝니다.")
    print()

    # 2. 업데이터 빌드
    print_header("2단계: 업데이터 빌드 (자동 업데이트용)")
    print_info("업데이터 빌드 중...")
    
    result = subprocess.run(
        ['pyinstaller', str(PROJECT_ROOT / 'updater.spec'), '--clean'],
        cwd=PROJECT_ROOT,
        capture_output=False
    )
    
    if result.returncode == 0:
        updater_exe = DIST_DIR / "updater.exe"
        if updater_exe.exists():
            # tools 폴더로 이동
            tools_dir = DIST_DIR / "tools"
            tools_dir.mkdir(exist_ok=True)
            shutil.move(str(updater_exe), str(tools_dir / "updater.exe"))
            print_success("업데이터 빌드 완료!")
        else:
            print_warning("업데이터 파일을 찾을 수 없지만 메인 프로그램은 정상입니다.")
    else:
        print_warning("업데이터 빌드 실패 (메인 프로그램은 정상)")
    
    print()
    print_header("빌드 완료!")
    print_success(f"버전: {version_full}")
    print_info(f"파일 위치: {DIST_DIR}")
    print_info(f"  - ConvertPro3_{version_short}.exe (메인 프로그램)")
    print_info(f"  - tools/updater.exe (업데이터)")
    print()
    print_warning("다음 단계:")
    print_info("1. dist 폴더에서 exe 파일을 테스트하세요")
    print_info("2. CHANGELOG.md를 작성하세요")
    print_info("3. [6] GitHub 배포를 실행하세요")
    
    return True


def deploy():
    """GitHub Release 배포"""
    print_header("GitHub Release 배포")
    
    major, minor, patch = read_version()
    version_short = f"v{major}.{minor}"
    version_tag = f"v{major}.{minor}.{patch}"
    
    exe_file = DIST_DIR / f"ConvertPro3_{version_short}.exe"
    tools_dir = DIST_DIR / "tools"
    
    if not exe_file.exists():
        print_error(f"빌드 파일을 찾을 수 없습니다: {exe_file}")
        print_warning("먼저 빌드를 실행하세요: python make.py build")
        return False
    
    print_info(f"배포 버전: {version_tag}")
    print_info(f"파일: {exe_file}")
    
    # tools 폴더도 함께 압축
    import zipfile
    zip_file = DIST_DIR / f"ConvertPro3_{version_short}_full.zip"
    
    print_info("패키지 생성 중...")
    with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(exe_file, exe_file.name)

        # tools 폴더가 있으면 포함
        if tools_dir.exists():
            for tool_file in tools_dir.glob('*'):
                if tool_file.is_file():
                    zf.write(tool_file, f"tools/{tool_file.name}")
    
    print_success(f"패키지 생성 완료: {zip_file}")
    
    # GitHub CLI 확인
    result = subprocess.run(['gh', 'auth', 'status'], capture_output=True)
    if result.returncode != 0:
        print_warning("GitHub CLI 인증이 필요합니다.")
        subprocess.run(['gh', 'auth', 'login', '-h', 'github.com', '-w'])
    
    # Release 생성
    print_info("Release 생성 중...")
    
    # CHANGELOG에서 최신 변경사항 읽기
    release_notes = "## 변경사항\n- 버그 수정 및 개선"
    if CHANGELOG_FILE.exists():
        with open(CHANGELOG_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            # 첫 번째 ## 섹션 추출
            lines = content.split('\n')
            in_section = False
            notes = []
            for line in lines:
                if line.startswith(f'## {version_tag}'):
                    in_section = True
                    continue
                elif line.startswith('## ') and in_section:
                    break
                elif in_section and line.strip():
                    notes.append(line)
            if notes:
                release_notes = '\n'.join(notes)
    
    release_notes += f"\n\n## 다운로드\n- [ConvertPro3_{version_short}.exe](https://github.com/infoqmsys-art/Convert_pro3_updates/releases/download/{version_tag}/ConvertPro3_{version_short}.exe) (단일 파일)\n- [ConvertPro3_{version_short}_full.zip](https://github.com/infoqmsys-art/Convert_pro3_updates/releases/download/{version_tag}/ConvertPro3_{version_short}_full.zip) (자동 업데이트 지원)"
    
    result = subprocess.run([
        'gh', 'release', 'create', version_tag,
        '--repo', 'infoqmsys-art/Convert_pro3_updates',
        '--title', f'큐엠 자동화 관리 프로그램 {version_tag}',
        '--notes', release_notes,
        str(exe_file),
        str(zip_file)
    ], cwd=PROJECT_ROOT)
    
    if result.returncode == 0:
        print_success("배포 완료!")
        print_info(f"Release URL: https://github.com/infoqmsys-art/Convert_pro3_updates/releases/tag/{version_tag}")
        print_warning("\n사용자가 자동 업데이트를 받으려면 zip 파일을 다운로드하고 압축 해제해야 합니다.")
        print_info("tools 폴더가 포함된 전체 패키지가 필요합니다.")
        return True
    else:
        print_error("배포 실패")
        return False


def show_menu():
    """대화형 메뉴 표시"""
    major, minor, patch = read_version()
    current_version = f"v{major}.{minor}.{patch}"
    
    print_header(f"큐엠 자동화 관리 프로그램 - 빌드 관리 시스템 (현재: {current_version})")
    
    print("[0] 종료")
    print()
    print("[1] 빌드만 실행 (버전 변경 없음)")
    print("    현재 버전 그대로 exe 파일만 다시 생성")
    print()
    print("[2] 버전 증가 - Patch (1.5.3 -> 1.5.4)")
    print("    버그 수정, 작은 개선 시 사용")
    print()
    print("[3] 버전 증가 - Minor (1.5.3 -> 1.6.0)")
    print("    새 기능 추가 시 사용")
    print()
    print("[4] 버전 증가 - Major (1.5.3 -> 2.0.0)")
    print("    대규모 변경 시 사용")
    print()
    print("[5] Release (버전 증가 + 빌드) - 추천")
    print("    Patch 버전 자동 증가 후 빌드")
    print("    일반적인 업데이트 배포 시 사용")
    print()
    print("[6] GitHub 배포")
    print("    빌드된 파일을 GitHub Release에 업로드")
    print("    사용자들이 자동 업데이트 받을 수 있음")
    print()
    print("[7] 전체 (Release + 배포)")
    print("    버전 증가 + 빌드 + GitHub 배포 한 번에")
    print()
    print("="*60)
    
    while True:
        try:
            choice = input("\n선택 (0-7): ").strip()
            
            if choice == '0':
                print_info("종료합니다.")
                return
            
            elif choice == '1':
                print_header("빌드만 실행")
                build()
            
            elif choice == '2':
                print_header("버전 Patch 증가")
                bump_version('patch')
            
            elif choice == '3':
                print_header("버전 Minor 증가")
                bump_version('minor')
            
            elif choice == '4':
                print_header("버전 Major 증가")
                bump_version('major')
            
            elif choice == '5':
                print_header("Release 빌드")
                if bump_version('patch'):
                    build()
                    print_success("Release 완료!")
            
            elif choice == '6':
                print_header("GitHub Release 배포")
                deploy()
            
            elif choice == '7':
                print_header("전체 빌드 + 배포")
                if bump_version('patch'):
                    if build():
                        deploy()
                        print_success("모든 작업 완료!")
            
            else:
                print_error("잘못된 선택입니다.")
                continue
            
            print()
            cont = input("계속하려면 Enter를 누르세요 (종료: q)... ").strip().lower()
            if cont == 'q':
                break
            print("\n" * 2)
            show_menu()
            break
            
        except KeyboardInterrupt:
            print("\n")
            print_info("종료합니다.")
            break
        except Exception as e:
            print_error(f"오류 발생: {e}")
            break


def main():
    if len(sys.argv) < 2:
        # 인자가 없으면 대화형 메뉴
        show_menu()
        return
    
    command = sys.argv[1].lower()
    
    if command == 'build':
        success = build()
        sys.exit(0 if success else 1)
    
    elif command == 'bump':
        if len(sys.argv) < 3:
            print_error("버전 타입을 지정하세요: major, minor, patch")
            sys.exit(1)
        bump_type = sys.argv[2].lower()
        success = bump_version(bump_type)
        sys.exit(0 if success else 1)
    
    elif command == 'release':
        # 버전 증가 + 빌드
        print_header("Release 빌드")
        if not bump_version('patch'):
            sys.exit(1)
        if not build():
            sys.exit(1)
        print_success("Release 완료!")
        print_warning("CHANGELOG.md를 작성하고 배포하세요: python make.py deploy")
        sys.exit(0)
    
    elif command == 'deploy':
        success = deploy()
        sys.exit(0 if success else 1)
    
    elif command == 'full':
        # 전체 프로세스
        print_header("전체 빌드 + 배포")
        if not bump_version('patch'):
            sys.exit(1)
        if not build():
            sys.exit(1)
        if not deploy():
            sys.exit(1)
        print_success("모든 작업 완료!")
        sys.exit(0)
    
    else:
        print_error(f"알 수 없는 명령: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
