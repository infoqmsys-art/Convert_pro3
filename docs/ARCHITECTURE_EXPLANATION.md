# Convert Pro 3 - 프로그램 아키텍처 설명서

## 📋 목차
1. [프로그램 개요](#프로그램-개요)
2. [데이터 구조](#데이터-구조)
3. [코어 모듈 구조](#코어-모듈-구조)
4. [UI 구조](#ui-구조)
5. [주요 기능 흐름](#주요-기능-흐름)
6. [설정 파일 구조](#설정-파일-구조)
7. [제안된 기능 확장](#제안된-기능-확장)

---

## 프로그램 개요

**Convert Pro 3**는 센서 데이터를 변환하고 관리하는 Windows 데스크톱 애플리케이션입니다.

### 주요 기능
- CSV 원본 파일을 표준 형식으로 변환
- 센서 모드별 데이터 가공 (EL, CR, V, TS, VIBROMETER 등)
- 증분 변환 (마지막 변환 이후 데이터만 추가)
- 자동 스케줄링 (주기적 변환, 간격 데이터 생성)
- 배터리 레벨 모니터링
- 자동 업데이트 기능

### 기술 스택
- **언어**: Python 3.x
- **GUI 프레임워크**: Tkinter (ttk)
- **데이터 처리**: pandas, numpy
- **설정 관리**: JSON (config.json)
- **빌드**: PyInstaller

---

## 데이터 구조

### 현재 계층 구조 (3단계)
```
회사 (Company)
  └── 폴더 (Folder) - 실제 물리적 디렉토리
        └── 파일 (File) - CSV 파일
              └── 채널 설정 (CH0~CH7)
```

### 예시
```
SAEGIL (회사)
  └── SAEGL03504 (폴더)
        └── 1227998453.csv (파일)
              ├── CH0: {mode: "EL_LOW", base: "", scale: "", ...}
              ├── CH1: {mode: "PASS", ...}
              └── ...
```

### 제안된 확장 구조 (4단계)
```
회사 (Company)
  └── 현장 (Site) - 가상 상위 디렉토리 (새로 추가)
        └── 폴더 (Folder) - 실제 물리적 디렉토리
              └── 파일 (File) - CSV 파일
                    └── 채널 설정 (CH0~CH7)
```

---

## 코어 모듈 구조

### 1. ConfigManager (`core/config_manager.py`)
**역할**: 설정 파일(config.json)의 단일 진실 원본(Source of Truth) 관리

**주요 메서드**:
- `load()`: config.json 로드
- `save()`: config.json 저장
- `ensure_company(company)`: 회사 노드 생성/보장
- `ensure_folder(company, folder, absolute_path)`: 폴더 노드 생성/보장
- `ensure_logger(company, folder, filename)`: 파일 노드 + CH0~CH7 기본 구조 생성

**데이터 접근**:
- `self.data`: 전체 설정 딕셔너리 (직접 참조)
- 모든 모듈이 `ConfigManager.data`를 공유하여 단일 진실 원본 유지

---

### 2. TreeManager (`core/tree_manager.py`)
**역할**: 트리 구조 조작 및 UI용 데이터 제공

**주요 메서드**:
- `get_tree()`: 전체 트리 구조 반환
- `get_company_data(company)`: 특정 회사 데이터 반환
- `add_company(company)`: 회사 추가
- `add_folder(company, folder, abs_path)`: 폴더 추가
- `add_file(company, folder, filename)`: 파일 추가
- `delete_company/folder/file()`: 삭제 기능
- `get_file_label_summary()`: 파일의 채널 설정 요약 문자열 생성

**특징**:
- 별도의 데이터 사본을 가지지 않음
- 항상 `self.cfg.data`를 직접 참조

---

### 3. FileProcessor (`core/file_processor.py`)
**역할**: CSV 파일 변환 파이프라인

**핵심 원칙**:
1. **증분 변환**: 최초 변환 시 전체 변환, 이후는 마지막 timestamp 이후만 append
2. **24컬럼 고정**: 변환본은 항상 24개 컬럼 (timestamp, deviceId, battery, CH0~CH7 등)
3. **배터리 이동**: 원본 56열(batLevel) → 변환본 3열(battery)
4. **안정성 우선**: 일부 행 오류 시에도 전체 변환 계속

**주요 메서드**:
- `convert_file(company, folder, filename)`: 단일 파일 변환
- `_get_last_converted_time(out_path)`: 마지막 변환 시점 확인
- `_collect_target_lines(src_path, base_time)`: 변환 대상 행 수집
- `_move_battery(df)`: 배터리 데이터 이동
- `_process_channels(df, file_cfg)`: CH0~CH7 센서 모드 적용

**변환 경로**:
- 원본: `{folder.__absolute_path__}/{filename}`
- 변환본: `C:\data\Convertfile\{company}\{folder}\{filename}`

---

### 4. SensorProcessor (`core/sensor_processor.py`)
**역할**: 센서 모드별 데이터 생성/변환

**지원 모드**:
- `PASS`: 원값 유지
- `OFFSET`: base 값 더하기
- `EL`, `EL_LOW`: 경사/변위 센서
- `CR`, `CR_TAEAM`: 균열계 (누적)
- `V`: 전압형 아날로그 센서
- `CHANG_SM`: 소음계
- `EL_TAEAM`: 정규 분포 노이즈 (scale=표준편차)
- `TS`: BASE 기준 ±0.0005 확률 분포
- `VIBROMETER`: BASE 기준 확률 분포 (0/0.001/0.002/0.003/0.005)

**주요 메서드**:
- `process_file(df, file_cfg)`: 파일 전체 채널 처리
- `generate_XXX(df, cfg)`: 각 모드별 데이터 생성 메서드

**모드 메타데이터**:
```python
MODE_META = {
    "EL_TAEAM": {"use_base": True, "use_scale": True, "desc": "..."},
    "VIBROMETER": {"use_base": True, "use_scale": False, "desc": "..."},
    ...
}
```

---

### 5. SchedulerManager (`core/scheduler_manager.py`)
**역할**: 자동 스케줄링 (변환, gen_interval)

**주요 기능**:
- 주기적 변환 실행 (`__gen_interval__` 설정 기반)
- 간격 데이터 생성 (10분, 60분 등)
- 백그라운드 스레드에서 실행

**스케줄링 로직**:
- `_handle_gen_interval()`: 파일별 `__gen_interval__` 값 확인
- `last_interval_time`: `(hour, minute)` 튜플로 저장하여 중복 실행 방지

---

### 6. FillIntervalProcessor (`core/fill_interval_processor.py`)
**역할**: 누락 데이터 보정

**기능**:
- `__fill_interval__` 설정 기반으로 누락된 시간대 데이터 생성
- 변환 후 자동 적용

---

## UI 구조

### 1. MainUI (`ui/main_ui.py`)
**역할**: 메인 애플리케이션 창

**주요 구성 요소**:
- **헤더**: 제목, 회사 선택 콤보박스, 새로고침 버튼
- **TreeView**: 회사/폴더/파일 트리 구조 표시
  - 컬럼: 파일명, 비고, 배터리(%)
  - 더블클릭: 채널 설정 UI 열기
  - 우클릭: 컨텍스트 메뉴 (변환, 삭제, 스캔 등)
- **상태 영역**: 진행률 바, 상태 메시지
- **버튼 영역**: 변환 실행, 폴더 추가, 업데이트
- **로그창**: 실시간 로그 출력
- **상태바**: 하단 상태 표시

**주요 메서드**:
- `refresh_tree()`: 트리뷰 새로고침
- `refresh_company_list()`: 회사 목록 갱신
- `_add_folder()`: 폴더 추가 다이얼로그
- `_delete_selected()`: 선택 항목 삭제
- `update_battery()`: 배터리 값 UI 업데이트

---

### 2. ChannelSettingsUI (`ui/channel_settings_ui.py`)
**역할**: 파일별 채널 설정 UI

**주요 기능**:
- CH0~CH7 각 채널 설정
  - Mode 선택 (Combobox)
  - Base, Scale, Decimal, Label 입력
  - Excel 컬럼 표시 (예: "CH0\n(칼럼Q)")
  - 초기값 표시 (CSV 첫 데이터 행에서 읽음)
- 파일 전역 설정
  - Fill Interval, Gen Interval
  - 비고 (Note)

**데이터 저장**:
- `TreeManager.set_file_config()` 호출하여 config.json에 저장

---

### 3. FolderContextMenu (`ui/context_menu.py`)
**역할**: 트리뷰 우클릭 컨텍스트 메뉴

**메뉴 항목**:
- **폴더 우클릭**:
  - 폴더 전체 변환
  - 새 파일 스캔
  - 폴더 업로드
  - 선택 삭제
- **파일 우클릭**:
  - 파일 변환
  - 폴더 업로드
  - 선택 삭제

---

## 주요 기능 흐름

### 1. 변환 프로세스
```
사용자: "변환 실행" 버튼 클릭
  ↓
ConvertPro3App.convert_now()
  ↓
_thread_convert() (별도 스레드)
  ↓
iter_config_files() → (company, folder, filename) 순회
  ↓
FileProcessor.convert_file(company, folder, filename)
  ↓
1. 마지막 변환 시점 확인 (_get_last_converted_time)
2. 변환 대상 행 수집 (_collect_target_lines)
3. DataFrame 생성
4. 배터리 이동 (_move_battery)
5. 채널 처리 (_process_channels) → SensorProcessor 호출
6. 누락 보정 (FillIntervalProcessor)
7. 변환본 파일 저장/추가
  ↓
UI 업데이트 (진행률, 로그, 트리뷰)
```

### 2. 폴더 추가 프로세스
```
사용자: "폴더 추가" 버튼 클릭
  ↓
MainUI._add_folder()
  ↓
1. 폴더 선택 다이얼로그
2. 회사 선택 팝업
3. TreeManager.add_folder(company, folder_name, folder_path)
4. CSV 파일 자동 스캔
5. TreeManager.add_file() 각 파일에 대해 호출
  ↓
refresh_tree() → 트리뷰 새로고침
```

### 3. 채널 설정 저장 프로세스
```
사용자: 채널 설정 UI에서 설정 변경 후 저장
  ↓
ChannelSettingsUI._on_save()
  ↓
TreeManager.set_file_config(company, folder, filename, new_cfg)
  ↓
ConfigManager.data 직접 수정
  ↓
ConfigManager.save() → config.json 저장
```

---

## 설정 파일 구조

### config.json 구조
```json
{
  "__version__": 1,
  "회사명": {
    "폴더명": {
      "__note__": "비고",
      "__absolute_path__": "C:/data/폴더경로",
      "파일명.csv": {
        "__fill_interval__": 10,
        "__gen_interval__": 0,
        "__note__": "파일 비고",
        "CH0": {
          "mode": "EL_LOW",
          "base": "",
          "scale": "",
          "decimal": "2",
          "label": "",
          "initial": ""
        },
        "CH1": { ... },
        ...
      }
    }
  }
}
```

### 특수 키
- `__version__`: 설정 파일 버전
- `__note__`: 비고 (폴더/파일 레벨)
- `__absolute_path__`: 폴더의 실제 물리적 경로
- `__fill_interval__`: 누락 보정 간격 (분)
- `__gen_interval__`: 자동 생성 간격 (분)

---

## 제안된 기능 확장

### 요구사항
1. **현장(Site) 레벨 추가**: 회사와 폴더 사이에 가상 상위 디렉토리 추가
2. **현장 추가 버튼**: UI에 "현장 추가" 버튼 추가
3. **파일 순서 번호**: 각 파일에 `__order__` 필드 추가하여 트리뷰 정렬

### 확장된 데이터 구조
```json
{
  "__version__": 1,
  "회사명": {
    "현장명": {
      "__note__": "현장 비고",
      "폴더명": {
        "__note__": "폴더 비고",
        "__absolute_path__": "C:/data/폴더경로",
        "파일명.csv": {
          "__order__": 1,  // 새로 추가: 순서 번호
          "__fill_interval__": 10,
          "__gen_interval__": 0,
          "__note__": "파일 비고",
          "CH0": { ... },
          ...
        }
      }
    }
  }
}
```

### 필요한 수정 사항

#### 1. ConfigManager
- `ensure_site(company, site)`: 현장 노드 생성 메서드 추가
- `ensure_folder()`: `(company, site, folder)` 시그니처로 변경

#### 2. TreeManager
- 모든 메서드에 `site` 파라미터 추가
- `add_site(company, site)`: 현장 추가
- `delete_site(company, site)`: 현장 삭제
- `get_site_data(company, site)`: 현장 데이터 반환

#### 3. FileProcessor
- `convert_file()`: `(company, site, folder, filename)` 시그니처로 변경
- 변환 경로: `C:\data\Convertfile\{company}\{site}\{folder}\{filename}`

#### 4. MainUI
- 트리뷰 구조: 회사 → 현장 → 폴더 → 파일
- "현장 추가" 버튼 추가
- `_add_site()`: 현장 추가 다이얼로그
- `refresh_tree()`: 파일을 `__order__` 기준으로 정렬하여 표시

#### 5. ChannelSettingsUI
- 파일 순서 번호 입력 필드 추가
- 저장 시 `__order__` 값 포함

#### 6. ContextMenu
- 현장 우클릭 메뉴 추가
- 현장 삭제 기능

### 마이그레이션 고려사항
- 기존 config.json 호환성: `site` 레벨이 없는 경우 기본 현장("Default")으로 자동 마이그레이션
- `__order__` 기본값: 파일 추가 시 자동으로 다음 순서 번호 할당

---

## 핵심 설계 원칙

1. **단일 진실 원본**: 모든 모듈이 `ConfigManager.data`를 직접 참조
2. **계층적 구조**: 회사 → (현장) → 폴더 → 파일 → 채널
3. **증분 변환**: 효율성을 위한 마지막 시점 이후만 변환
4. **UI와 로직 분리**: UI는 표현만, 모든 데이터 처리는 Core 모듈에서
5. **확장성**: 새로운 센서 모드 추가가 용이한 구조

---

## 파일 구조 요약

```
Convert_pro3/
├── Convert_pro3.py          # 메인 애플리케이션 진입점
├── config.json              # 설정 파일 (단일 진실 원본)
├── core/
│   ├── config_manager.py    # 설정 파일 관리
│   ├── tree_manager.py      # 트리 구조 관리
│   ├── file_processor.py    # 파일 변환 파이프라인
│   ├── sensor_processor.py  # 센서 모드 처리
│   ├── scheduler_manager.py # 자동 스케줄링
│   └── fill_interval_processor.py # 누락 보정
├── ui/
│   ├── main_ui.py           # 메인 UI
│   ├── channel_settings_ui.py # 채널 설정 UI
│   └── context_menu.py      # 우클릭 메뉴
└── utils/
    ├── logger.py            # 로깅
    ├── battery_reader.py    # 배터리 읽기
    └── updater.py           # 자동 업데이트
```

---

이 문서는 Convert Pro 3의 전체 아키텍처를 설명하며, 제안된 기능 확장(현장 레벨 추가, 파일 순서 번호)을 위한 설계 가이드입니다.
