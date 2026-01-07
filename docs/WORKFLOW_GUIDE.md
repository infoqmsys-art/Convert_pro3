# Convert Pro 3 - 운용 가이드

## 📋 일상적인 개발 및 배포 워크플로우

### 1️⃣ 개발 단계

#### 코드 수정
```bash
# 평소처럼 코드 수정
# - core/sensor_processor.py
# - ui/main_ui.py
# - 등등...

# 개발 환경에서 테스트
python Convert_pro3.py
```

#### 버그 수정이나 작은 변경
```bash
# 아무것도 안해도 됨 - 그냥 코드 수정만 하면 됨
```

---

### 2️⃣ 새 버전 릴리즈 준비

#### 버전 번호 결정
- **Patch** (1.2.0 → 1.2.1): 버그 수정, 작은 개선
- **Minor** (1.2.0 → 1.3.0): 새로운 기능 추가
- **Major** (1.2.0 → 2.0.0): 대규모 변경, API 변경

#### 버전 업데이트
```powershell
# 예: 버그 수정 릴리즈
python bump_version.py patch

# 결과:
# ✅ 버전 업데이트: v1.2.0 → v1.2.1
# ✅ version.json 생성 완료
# 
# 📝 다음 단계:
#    1. version.json의 release_notes 수정
#    2. .\build.ps1 실행하여 빌드
#    3. dist\ConvertPro3_v1.2.exe 서버에 업로드
```

#### release_notes 수정
```json
// version.json 파일 열기
{
  "version": "v1.2",
  "release_notes": "- 주기 생성 시 timestamp 버그 수정\n- UI 개선\n- 성능 최적화"
  // ... 실제 변경 내용 작성
}
```

---

### 3️⃣ 빌드

```powershell
# 메인 프로그램 빌드
.\build.ps1

# 결과:
# ✅ 빌드 완료!
# 생성된 파일:
#   - dist\ConvertPro3_v1.2.exe
#   - 크기: 25.34 MB
```

#### 첫 배포라면 update.exe도 빌드
```powershell
.\build_updater.ps1

# 결과:
# ✅ update.exe 빌드 완료!
# 생성된 파일:
#   - dist\update.exe
```

---

### 4️⃣ 서버에 업로드

#### GitHub Pages 사용 예시
```bash
# 1. GitHub 저장소의 updates/ 폴더에 업로드
updates/
├── version.json                  # 수정된 버전 정보
├── ConvertPro3_v1.2.exe          # 새로 빌드한 파일
└── update.exe                     # (처음 한 번만)

# 2. Git push
git add updates/
git commit -m "Release v1.2"
git push
```

#### FTP/웹 서버 사용 예시
```
서버의 updates 폴더에 FTP로 업로드:
- version.json (덮어쓰기)
- ConvertPro3_v1.2.exe (새 파일)
- update.exe (처음 한 번만)
```

---

### 5️⃣ 자동 배포 완료! 🎉

이제 사용자들이 프로그램을 실행하면:

1. **자동 확인** (앱 시작 5초 후)
   ```
   [Updater] 버전 확인 중...
   [Updater] 현재 버전: v1.1, 최신 버전: v1.2
   [Updater] 새 버전 발견: v1.2
   ```

2. **UI에 알림 표시**
   ```
   ┌─────────────────────────────────┐
   │ [⬇ 업데이트 v1.2 사용 가능]     │  ← 버튼 나타남
   └─────────────────────────────────┘
   상태바: 새 버전 v1.2 발견! 업데이트 버튼을 클릭하세요.
   ```

3. **사용자가 버튼 클릭**
   ```
   팝업:
   ┌────────────────────────────────┐
   │ 새로운 버전이 있습니다!         │
   │                                │
   │ 버전: v1.2                     │
   │ 발표일: 2026-01-07             │
   │                                │
   │ 변경 내용:                     │
   │ - 주기 생성 시 버그 수정       │
   │ - UI 개선                      │
   │                                │
   │ 지금 업데이트하시겠습니까?     │
   │ (프로그램이 재시작됩니다)      │
   │                                │
   │   [예]          [아니오]       │
   └────────────────────────────────┘
   ```

4. **자동 업데이트 진행**
   ```
   1. 다운로드 중... 50%
   2. update.exe 실행
   3. Convert Pro 3 종료
   4. [update.exe 창]
      "Convert Pro 3 업데이트 중..."
      - 기존 버전 백업 중...
      - 새 버전 설치 중...
      - 프로그램 재시작 중...
   5. 새 버전으로 자동 실행! ✨
   ```

---

## 🔄 실제 시나리오 예시

### 시나리오 1: 버그 수정 (긴급)
```powershell
# 1. 버그 수정 코드 작성
# 2. 테스트
python Convert_pro3.py

# 3. 패치 버전 증가
python bump_version.py patch

# 4. version.json 수정 (release_notes)
# "- timestamp 0으로 들어가는 버그 긴급 수정"

# 5. 빌드
.\build.ps1

# 6. 서버 업로드
# dist\ConvertPro3_v1.2.exe → 서버
# version.json → 서버

# 완료! 사용자들이 자동으로 업데이트 받음
```

### 시나리오 2: 새 기능 추가
```powershell
# 1. 새 기능 개발 (예: 자동 백업 기능)
# 2. 테스트 완료

# 3. 마이너 버전 증가
python bump_version.py minor  # v1.2 → v1.3

# 4. version.json 수정
# "- 자동 백업 기능 추가\n- 파일 탐색기 개선"

# 5. 빌드 & 업로드
.\build.ps1
# 서버에 업로드

# 사용자들에게 자동 배포
```

### 시나리오 3: 대규모 리뉴얼
```powershell
# 1. 대규모 변경 완료
# 2. 충분한 테스트

# 3. 메이저 버전 증가
python bump_version.py major  # v1.2 → v2.0

# 4. version.json 수정
# "- 전체 UI 리뉴얼\n- 새로운 센서 모드 추가\n- 성능 대폭 개선"

# 5. 빌드 & 업로드
.\build.ps1
# 서버에 업로드
```

---

## 📊 버전 관리 전략

### Semantic Versioning (권장)
```
MAJOR.MINOR.PATCH
  ↓     ↓     ↓
  2  .  3  .  1

MAJOR: 하위 호환성 없는 변경
MINOR: 하위 호환성 있는 기능 추가
PATCH: 하위 호환성 있는 버그 수정
```

### 예시
- `v1.2.0 → v1.2.1`: 버그 수정
- `v1.2.1 → v1.3.0`: 새 기능 추가
- `v1.3.0 → v2.0.0`: 대규모 변경

---

## 🎯 핵심 포인트

### ✅ 매번 하는 것
1. 코드 수정
2. `python bump_version.py patch/minor/major`
3. `version.json`의 release_notes 수정
4. `.\build.ps1`
5. 서버 업로드

### ✅ 한 번만 하는 것
1. `update.exe` 빌드 및 배포
2. 서버 설정
3. `Convert_pro3.py`에서 `update_server_url` 설정

### ✅ 자동으로 되는 것
- 파일명에 버전 자동 적용
- 사용자에게 업데이트 알림
- 다운로드 및 설치
- 프로그램 재시작

---

## 🛠️ 팁

### 개발 중에는
```python
# version.py
VERSION_MAJOR = 1
VERSION_MINOR = 2
VERSION_PATCH = 0  # 개발 중

# 그냥 코드 수정하고 테스트만 반복
```

### 릴리즈 준비되면
```powershell
# 버전 증가만 하면 끝
python bump_version.py patch
```

### 서버 URL 확인
```python
# Convert_pro3.py
self.updater = AutoUpdater(
    current_version=APP_VERSION,
    update_server_url="https://yourserver.com/updates",  # 이 부분 실제 URL로
    logger=self.logger
)
```

---

## ❓ FAQ

**Q: 개발 중에 매번 버전을 올려야 하나요?**
A: 아니요! 릴리즈할 때만 `bump_version.py`를 실행하세요.

**Q: update.exe도 매번 업로드해야 하나요?**
A: 아니요! 처음 한 번만 업로드하면 됩니다. updater 자체를 수정했을 때만 다시 빌드하세요.

**Q: 사용자가 업데이트를 건너뛰면?**
A: 다음번 실행 시 다시 알림이 표시됩니다.

**Q: 여러 버전을 건너뛴 사용자는?**
A: 괜찮습니다! 항상 최신 버전으로 업데이트됩니다.

---

## 🎬 요약

```
코딩 → 테스트 → bump_version.py → build.ps1 → 서버 업로드 → 끝!
                                                          ↓
                                                    사용자 자동 업데이트
```

간단하죠? 😊
