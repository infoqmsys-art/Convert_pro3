# Convert Pro 3 - 프로젝트 구조

```
Convert_pro3/
│
├── 📄 메인 실행 파일
│   └── Convert_pro3.py          # 메인 프로그램
│
├── 📁 core/                     # 핵심 로직
│   ├── config_manager.py
│   ├── file_processor.py
│   ├── fill_interval_processor.py
│   ├── scheduler_manager.py
│   ├── sensor_processor.py
│   └── tree_manager.py
│
├── 📁 ui/                       # 사용자 인터페이스
│   ├── main_ui.py
│   ├── channel_settings_ui.py
│   ├── context_menu.py
│   └── widgets.py
│
├── 📁 utils/                    # 유틸리티
│   ├── battery_reader.py
│   ├── logger.py
│   ├── memory_tracker.py
│   ├── path_utils.py
│   └── updater.py
│
├── 📁 docs/                     # 문서 (정리됨)
│   ├── UPDATE_GUIDE.md
│   └── WORKFLOW_GUIDE.md
│
├── 📁 build_scripts/            # 빌드 관련 (정리됨)
│   ├── build.bat               # 빌드 (더블클릭)
│   ├── build.ps1
│   ├── build_updater.bat       # 업데이터 빌드
│   ├── build_updater.ps1
│   ├── bump_patch.bat          # 패치 버전 증가
│   ├── bump_minor.bat          # 마이너 버전 증가
│   ├── bump_major.bat          # 메이저 버전 증가
│   ├── bump_version.py
│   ├── ConvertPro3_v1.0.spec
│   ├── Convert_pro3.spec
│   ├── Convert_Pro_3_PROTO.spec
│   └── updater.spec
│
├── 📁 tools/                    # 개발 도구 (정리됨)
│   ├── check_parsed_time.py
│   └── updater_standalone.py
│
├── 📄 설정 파일 (루트 유지)
│   ├── version.py              # 버전 관리
│   ├── version.json            # 서버용 버전 정보
│   ├── config.json             # 앱 설정
│   └── runtime_memory.json
│
├── 📁 build/                    # 빌드 임시 파일
├── 📁 dist/                     # 빌드 결과물
├── 📁 logs/                     # 로그 파일
│
└── 📄 기타
    ├── .gitignore
    ├── README.md
    └── 1222504313.csv           # 테스트 데이터
```

## 📋 파일 분류

### ✅ 그대로 두는 것 (루트)
- `Convert_pro3.py` - 메인 실행 파일
- `version.py` - 버전 정보
- `version.json` - 서버 배포용
- `config.json` - 설정
- `runtime_memory.json` - 메모리 추적

### 📦 정리할 것

#### docs/ 폴더로 이동
- `UPDATE_GUIDE.md`
- `WORKFLOW_GUIDE.md`

#### build_scripts/ 폴더로 이동
- 모든 .spec 파일
- 모든 .ps1 파일
- 모든 .bat 파일 (빌드 관련)
- `bump_version.py`

#### tools/ 폴더로 이동
- `check_parsed_time.py`
- `updater_standalone.py`

## 🎯 정리 후 사용법

### 빌드하기
```
build_scripts/build.bat 더블클릭
```

### 버전 올리기
```
build_scripts/bump_patch.bat 더블클릭
```

### 실행하기
```
Convert_pro3.py (그대로 루트)
```
