# 큐엠 자동화 관리 프로그램

계측 로거 데이터를 자동으로 변환·관리하고, 웹 대시보드로 현장 현황을 모니터링하는 통합 관리 도구입니다.

## 주요 기능

- **자동 변환**: 설정된 주기(기본 5·25·45분)마다 CSV 로거 파일을 자동 변환
- **센서 설정**: 채널별 오프셋·스케일·소수점·레이블 설정
- **웹 대시보드**: 브라우저에서 현장 현황, 로거 상태, 채널 차트 확인 (`http://localhost:5050`)
- **현장 관리**: 업체·현장·담당자 배정, XLSX 현황 내보내기
- **배터리 조회**: 로거 배터리 잔량 자동 읽기

## 스크린샷

> (추후 추가 예정)

## 요구사항

- Python 3.11 이상
- Windows 10/11 권장 (Tkinter GUI)

## 설치 및 실행

### 1. 저장소 복제

```bash
git clone https://github.com/infoqmsys-art/Convert_pro3.git
cd Convert_pro3
```

### 2. 가상환경 생성 및 패키지 설치

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

### 3. 설정 파일 준비

```bash
# 샘플 파일을 복사하여 실제 설정 파일 생성
copy config.example.json config.json
copy web_auth.example.json web_auth.json
```

`web_auth.json`의 `username`과 `password`를 원하는 값으로 변경하세요.  
`config.json`은 프로그램 실행 후 UI에서 업체·현장·파일을 등록하면 자동으로 채워집니다.

### 4. 실행

```bash
python Convert_pro3.py
```

웹 대시보드는 프로그램 시작 후 `http://localhost:5050` 에서 접속 가능합니다.

## 프로젝트 구조

```
Convert_pro3/
├── Convert_pro3.py          # 메인 진입점 (앱 컨트롤러)
├── version.py               # 버전 정보
├── requirements.txt
│
├── core/                    # 핵심 비즈니스 로직
│   ├── config_manager.py    # config.json 읽기/쓰기
│   ├── file_processor.py    # CSV 변환 엔진
│   ├── scheduler_manager.py # 자동 변환 스케줄러
│   ├── sensor_processor.py  # 센서 연산 처리
│   ├── tree_manager.py      # 업체·현장·파일 트리
│   └── fill_interval_processor.py
│
├── ui/                      # Tkinter GUI
│   ├── main_ui.py
│   ├── channel_settings_ui.py
│   └── ...
│
├── monitoring/              # Flask 웹 대시보드
│   ├── server.py            # Flask 앱
│   ├── data_cache.py        # 변환 캐시 관리
│   └── templates/
│
├── utils/                   # 공통 유틸리티
│   ├── logger.py            # 로그 (5MB 로테이션)
│   ├── battery_reader.py
│   └── update_manager.py
│
├── config.example.json      # 설정 파일 샘플
└── web_auth.example.json    # 웹 인증 샘플
```

## 설정 파일 설명

| 파일 | 용도 | git 추적 |
|------|------|----------|
| `config.json` | 업체·현장·센서 설정 (자동 생성) | ❌ 제외 |
| `web_auth.json` | 웹 대시보드 로그인 정보 | ❌ 제외 |
| `management.json` | 현장 관리 데이터 | ❌ 제외 |
| `monitoring_cache.json` | 변환 결과 캐시 (런타임) | ❌ 제외 |

## 기여 방법

[CONTRIBUTING.md](CONTRIBUTING.md)를 참고해 주세요.

## 라이선스

사내 전용 소프트웨어입니다. 외부 배포·재사용 시 허가가 필요합니다.
