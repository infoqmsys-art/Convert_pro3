# Convert Pro 3 - 자동 업데이트 시스템 가이드

## 개요

Convert Pro 3는 서버 기반 자동 업데이트 시스템을 지원합니다. 앱 시작 시 자동으로 새 버전을 확인하고, 사용자가 원할 때 클릭 한 번으로 업데이트할 수 있습니다.

## 시스템 구조

### 1. 클라이언트 (Convert Pro 3 앱)
- 앱 시작 5초 후 자동으로 업데이트 확인
- 새 버전 발견 시 UI에 "⬇ 업데이트 있음" 버튼 표시
- 버튼 클릭 시 자동 다운로드 및 설치
- **update.exe가 있으면 사용 (권장), 없으면 배치 파일 사용 (폴백)**

### 2. 업데이터 (update.exe) - 독립 실행형
- 메인 프로그램과 별도로 실행되는 업데이트 전용 유틸리티
- 프로세스 안전성 보장 (실행 중인 파일을 교체하지 않음)
- GUI 진행 상황 표시
- 자동 백업 및 복구

### 3. 서버 (웹 호스팅)
서버에는 다음 파일들이 필요합니다:

#### a) `version.json` (버전 정보 파일)
```json
{
  "version": "v1.3",
  "download_url": "https://yourserver.com/updates/ConvertPro3_v1.3.exe",
  "release_notes": "- 주요 버그 수정\n- 새로운 기능 추가",
  "release_date": "2026-01-07",
  "mandatory": false
}
```

#### b) `ConvertPro3_vX.X.exe` (실제 업데이트 파일)
- PyInstaller로 빌드한 최신 실행 파일

## 서버 설정 방법

### 옵션 1: GitHub Pages (무료, 추천)

1. GitHub 저장소 생성 (예: `convert-pro3-updates`)

2. 저장소에 `updates` 폴더 생성

3. 다음 파일들 업로드:
   ```
   updates/
   ├── version.json
   └── ConvertPro3_v1.3.exe
   ```

4. GitHub Pages 활성화:
   - Settings → Pages → Source: main branch
   - URL 확인: `https://yourusername.github.io/convert-pro3-updates`

5. `Convert_pro3.py`에서 URL 수정:
   ```python
   self.updater = AutoUpdater(
       current_version=APP_VERSION,
       update_server_url="https://yourusername.github.io/convert-pro3-updates/updates",
       logger=self.logger
   )
   ```

### 옵션 2: AWS S3

1. S3 버킷 생성 (예: `convert-pro3-updates`)

2. 파일 업로드 및 퍼블릭 접근 허용

3. URL 형식: `https://convert-pro3-updates.s3.amazonaws.com/updates`

### 옵션 3: 자체 웹 서버

1. 웹 서버에 `updates` 폴더 생성

2. 파일 업로드 및 HTTP 접근 가능하도록 설정

3. URL 형식: `https://yourserver.com/updates`

## 새 버전 배포 프로세스

### 1. 메인 프로그램 빌드
```bash
# PyInstaller로 빌드
pyinstaller ConvertPro3_v1.0.spec

# 빌드된 파일 확인
dist/ConvertPro3_v1.3.exe
```

### 2. update.exe 빌드 (처음 한 번만)
```bash
# PowerShell에서 실행
.\build_updater.ps1

# 또는 직접 빌드
pyinstaller updater.spec --clean

# 빌드된 파일 확인
dist/update.exe
```

### 3. 서버에 업로드
```bash
# 1) 메인 실행 파일 업로드
ConvertPro3_v1.3.exe → updates/ConvertPro3_v1.3.exe

# 2) update.exe 업로드 (처음 한 번만, 또는 업데이터 개선 시)
update.exe → updates/update.exe

# 3) version.json 업데이트
{
  "version": "v1.3",
  "download_url": "https://yourserver.com/updates/ConvertPro3_v1.3.exe",
  "updater_url": "https://yourserver.com/updates/update.exe",
  "release_notes": "변경 내용 작성",
  "release_date": "2026-01-07",
  "mandatory": false
}
```

### 4. 클라이언트 배포
처음 배포 시 다음 두 파일을 함께 배포:
- `ConvertPro3.exe` (메인 프로그램)
- `update.exe` (업데이터)

이후부터는 자동 업데이트로 관리됩니다.

## version.json 필드 설명

| 필드 | 설명 | 예제 |
|------|------|------|
| `version` | 버전 번호 (v 접두사 포함) | `"v1.3"` |
| `download_url` | 실행 파일 다운로드 URL | `"https://..."` |
| `release_notes` | 업데이트 내용 설명 | `"- 버그 수정\n- 기능 추가"` |
| `release_date` | 배포 날짜 (YYYY-MM-DD) | `"2026-01-07"` |
| `mandatory` | 필수 업데이트 여부 (현재 미사용) | `false` |

## 업데이트 프로세스

### 방법 1: update.exe 사용 (권장)
1. **확인**: 앱 시작 5초 후 서버의 `version.json` 확인
2. **알림**: 새 버전 발견 시 UI에 버튼 표시
3. **다운로드**: 사용자가 버튼 클릭 시 업데이트 파일 다운로드
4. **실행**: `update.exe` 호출 및 메인 프로그램 종료
5. **설치** (update.exe가 수행):
   - 프로그램 종료 대기 (3초)
   - 현재 실행 파일 백업 (`.backup` 확장자)
   - 새 파일로 교체
   - 앱 자동 재시작
   - 백업 파일 삭제
6. **복구**: 설치 실패 시 백업에서 자동 복구

### 방법 2: 배치 파일 사용 (폴백)
update.exe가 없을 경우 자동으로 배치 파일 방식으로 전환됩니다.
(기존 방식과 동일)

## 개발 환경에서 테스트

개발 환경에서는 패키징되지 않은 상태이므로 실제 업데이트 설치는 불가능합니다. 
대신 버전 확인 기능만 테스트할 수 있습니다:

```python
# 테스트용 코드
from utils.updater import AutoUpdater

updater = AutoUpdater(
    current_version="v1.2",
    update_server_url="https://yourserver.com/updates"
)

has_update, info = updater.check_for_updates()
if has_update:
    print(f"새 버전 발견: {info}")
```

## 보안 고려사항

### 1. HTTPS 사용
반드시 HTTPS URL을 사용하여 중간자 공격 방지:
```python
update_server_url="https://yourserver.com/updates"  # ✅ 안전
update_server_url="http://yourserver.com/updates"   # ❌ 위험
```

### 2. 파일 무결성 검증 (선택)
필요 시 `version.json`에 SHA256 해시 추가:
```json
{
  "version": "v1.3",
  "download_url": "...",
  "sha256": "abc123..."
}
```

## 문제 해결

### 업데이트 버튼이 표시되지 않음
- 서버 URL 확인: `Convert_pro3.py`의 `update_server_url`
- `version.json` 접근 가능 여부 확인
- 로그 확인: `logs/` 폴더의 로그 파일

### 다운로드 실패
- 인터넷 연결 확인
- 방화벽/안티바이러스 설정 확인
- `download_url`이 실제 파일을 가리키는지 확인

### 설치 후 프로그램이 시작되지 않음
- 백업 파일(`.backup`) 확인
- 수동으로 복구: `.backup` 파일의 확장자 제거

## 코드 구조

```
utils/updater.py           # AutoUpdater 클래스 (update.exe 우선 사용)
updater_standalone.py      # 독립 실행형 업데이터 (update.exe 소스)
updater.spec               # update.exe PyInstaller 설정
build_updater.ps1          # update.exe 빌드 스크립트
Convert_pro3.py            # 업데이트 체크 통합
ui/main_ui.py              # 업데이트 버튼/알림 UI
version.json               # 서버 배포용 샘플
```

## update.exe 장점

1. **안전성**: 실행 중인 파일을 직접 교체하지 않음
2. **진행 상황 표시**: GUI로 사용자에게 시각적 피드백
3. **독립성**: 메인 프로그램과 분리되어 오류 격리
4. **폴백 지원**: update.exe가 없어도 배치 파일로 자동 전환

## 추가 기능 (향후)

- [ ] 자동 업데이트 옵션 (사용자 동의 없이)
- [ ] 델타 업데이트 (전체 파일이 아닌 변경 부분만)
- [ ] 업데이트 일정 예약
- [ ] 버전 롤백 기능

---

**참고**: 첫 배포 후 사용자에게 서버 URL을 안내하고, 이후부터는 자동으로 업데이트됩니다.
