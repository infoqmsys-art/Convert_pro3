"""
버전 업데이트 헬퍼 스크립트
새 버전으로 업데이트하고 version.json도 자동 생성
"""

import sys
from datetime import datetime

def update_version(major=None, minor=None, patch=None):
    """버전 업데이트"""
    # 현재 버전 읽기
    version_path = '../version.py'
    with open(version_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    current_major = current_minor = current_patch = None
    
    for i, line in enumerate(lines):
        if line.startswith('VERSION_MAJOR'):
            current_major = int(line.split('=')[1].strip())
            if major is not None:
                lines[i] = f'VERSION_MAJOR = {major}\n'
        elif line.startswith('VERSION_MINOR'):
            current_minor = int(line.split('=')[1].strip())
            if minor is not None:
                lines[i] = f'VERSION_MINOR = {minor}\n'
        elif line.startswith('VERSION_PATCH'):
            current_patch = int(line.split('=')[1].strip())
            if patch is not None:
                lines[i] = f'VERSION_PATCH = {patch}\n'
    
    # 업데이트할 버전 결정
    new_major = major if major is not None else current_major
    new_minor = minor if minor is not None else current_minor
    new_patch = patch if patch is not None else current_patch
    
    # version.py 저장
    with open(version_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✅ 버전 업데이트: v{current_major}.{current_minor}.{current_patch} → v{new_major}.{new_minor}.{new_patch}")
    
    # version.json 생성
    version_short = f"v{new_major}.{new_minor}"
    version_json = {
        "version": version_short,
        "download_url": f"https://yourserver.com/updates/ConvertPro3_{version_short}.exe",
        "updater_url": "https://yourserver.com/updates/update.exe",
        "release_notes": "- 버그 수정\n- 기능 개선",
        "release_date": datetime.now().strftime("%Y-%m-%d"),
        "mandatory": False
    }
    
    import json
    with open('../version.json', 'w', encoding='utf-8') as f:
        json.dump(version_json, f, indent=2, ensure_ascii=False)
    
    print(f"✅ version.json 생성 완료")
    print(f"\n📝 다음 단계:")
    print(f"   1. version.json의 release_notes 수정")
    print(f"   2. .\build.ps1 실행하여 빌드")
    print(f"   3. dist\ConvertPro3_{version_short}.exe 서버에 업로드")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법:")
        print("  python bump_version.py patch    # 1.2.0 → 1.2.1")
        print("  python bump_version.py minor    # 1.2.0 → 1.3.0")
        print("  python bump_version.py major    # 1.2.0 → 2.0.0")
        print("  python bump_version.py 1.3.0    # 직접 지정")
        sys.exit(1)
    
    arg = sys.argv[1].lower()
    
    # 현재 버전 읽기
    import sys
    sys.path.insert(0, '..')
    import version
    major = version.VERSION_MAJOR
    minor = version.VERSION_MINOR
    patch = version.VERSION_PATCH
    
    if arg == "patch":
        update_version(patch=patch + 1)
    elif arg == "minor":
        update_version(minor=minor + 1, patch=0)
    elif arg == "major":
        update_version(major=major + 1, minor=0, patch=0)
    else:
        # 직접 버전 지정 (예: 1.3.0)
        try:
            parts = arg.replace('v', '').split('.')
            new_major = int(parts[0]) if len(parts) > 0 else major
            new_minor = int(parts[1]) if len(parts) > 1 else 0
            new_patch = int(parts[2]) if len(parts) > 2 else 0
            update_version(new_major, new_minor, new_patch)
        except:
            print(f"❌ 잘못된 버전 형식: {arg}")
            sys.exit(1)
