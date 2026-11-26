# 🔄 자동 업데이트 시스템 구조 설명

## ❓ 문제 상황

### 기존 방식의 문제점
```
❌ 단일 .exe만 다운로드하는 경우:

1. 현재 프로그램 (v1.0)
   └─ tools/updater.exe (v1.0의 updater)

2. 새 버전 다운로드
   → ConvertPro3_v2.0.exe (단일 파일)

3. 업데이트 시도
   → v1.0의 updater로 v2.0 설치
   
🚨 문제:
- updater 구조가 바뀌면 업데이트 실패!
- updater 자체는 업데이트 안됨!
```

---

## ✅ 해결 방법

### 새 방식: _full.zip 사용

```
✅ _full.zip 패키지 다운로드:

1. 현재 프로그램 (v1.0)
   ├─ ConvertPro3_v1.0.exe
   └─ tools/updater.exe (v1.0)

2. 새 버전 다운로드
   → ConvertPro3_v2.0_full.zip
       ├─ ConvertPro3_v2.0.exe
       └─ tools/updater.exe (v2.0) ✨ 새 버전!

3. 업데이트 과정
   ① ZIP 압축 해제 (임시 폴더)
   ② **새 버전의 updater.exe 사용** 🎯
   ③ 새 updater가:
      - 기존 프로그램 종료 대기
      - 파일 교체 (메인 exe + updater)
      - 프로그램 재시작

✨ 장점:
- 항상 새 버전의 updater로 업데이트!
- updater 구조 변경에도 안전!
- 자기 자신도 업데이트 가능!
```

---

## 🏗️ 업데이트 시스템 구조

### 1. GitHub Release 구조

```
GitHub Release (v1.5.0):
├─ ConvertPro3_v1.5.0.exe          (단일 실행 파일)
└─ ConvertPro3_v1.5.0_full.zip     (전체 패키지) ← 우선 다운로드
    ├─ ConvertPro3_v1.5.0.exe
    └─ tools/
        └─ updater.exe
```

### 2. 다운로드 우선순위

```python
# update_manager.py - check_for_updates()

다운로드 우선순위:
1순위: _full.zip  ← updater 포함, 안전함
2순위: .exe       ← 단일 파일, updater 없음 (위험)
```

### 3. 업데이트 플로우

```
┌─────────────────────────────────────────┐
│ 1. 업데이트 확인                          │
│   - GitHub API 호출                      │
│   - 최신 버전 확인                        │
│   - _full.zip 다운로드 URL 획득           │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 2. 다운로드 (update_manager.py)         │
│   - _full.zip → temp 폴더                │
│   - 진행률 표시 (UI)                     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 3. 압축 해제 (update_manager.py)        │
│   - temp_extract_dir/ ← ZIP 압축 해제    │
│     ├─ ConvertPro3_vX.X.X.exe           │
│     └─ tools/updater.exe ✨ 새 버전!     │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 4. 새 updater 실행                       │
│   - 압축 해제된 **새 updater.exe** 사용   │
│   - 인자: [현재exe] [새exe] [restart]    │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│ 5. 파일 교체 (updater_standalone.py)    │
│   ① 기존 프로그램 종료 대기               │
│   ② 파일 교체:                           │
│      - ConvertPro3.exe → 새 버전         │
│      - tools/updater.exe → 새 버전       │
│   ③ 프로그램 재시작                       │
└──────────────┬──────────────────────────┘
               │
               ▼
          [완료! 🎉]
```

---

## 📁 파일별 역할

### `utils/update_manager.py`

```python
class UpdateManager:
    def check_for_updates():
        """
        GitHub Release에서 업데이트 확인
        
        우선순위:
        1. _full.zip (메인 + updater)
        2. .exe (메인만)
        
        Returns:
            {
                'available': True/False,
                'version': "1.5.0",
                'download_url': "...",
                'is_zip': True/False  ← 중요!
            }
        """
    
    def download_update(url, save_path, callback):
        """다운로드 (진행률 콜백)"""
    
    def start_updater(downloaded_file, is_zip=False):
        """
        업데이터 시작
        
        is_zip=True:
          ① ZIP 압축 해제
          ② 새 updater.exe 찾기
          ③ **새 updater 실행** ✨
        
        is_zip=False:
          ① 기존 updater.exe 찾기
          ② 기존 updater 실행
        """
```

### `tools/updater_standalone.py`

```python
"""
독립 실행형 업데이터
메인 프로그램과 별도 프로세스로 실행

실행 방법:
updater.exe [현재exe경로] [새exe경로] [restart]

동작:
1. 메인 프로그램 종료 대기 (psutil)
2. 파일 교체:
   - 현재exe → 새exe로 교체
   - tools/updater.exe도 교체 (자기 자신 제외)
3. 메인 프로그램 재시작
"""
```

### `ui/update_dialog.py`

```python
class UpdateDialog:
    def _download_and_apply():
        """
        다운로드 및 적용
        
        is_zip 처리:
        - ZIP: ConvertPro3_update.zip
        - EXE: ConvertPro3_update.exe
        
        update_manager.start_updater(file, is_zip=True/False)
        """
```

---

## 🧪 테스트 시나리오

### 시나리오 1: _full.zip 업데이트 (권장)

```
1. 현재 버전: v1.0.0
2. GitHub Release 올림: v1.1.0_full.zip
3. 프로그램에서 업데이트 버튼 클릭
4. 다운로드: ConvertPro3_v1.1.0_full.zip
5. 압축 해제: temp/ConvertPro3_v1.1.0.exe + tools/updater.exe
6. 새 updater 실행
7. 파일 교체 완료
8. v1.1.0 실행됨 ✅
```

### 시나리오 2: 단일 .exe 업데이트 (비권장)

```
1. 현재 버전: v1.0.0 (tools/updater.exe 있음)
2. GitHub Release 올림: v1.1.0.exe (단일 파일)
3. 프로그램에서 업데이트 버튼 클릭
4. 다운로드: ConvertPro3_v1.1.0.exe
5. 기존 updater 실행 (v1.0.0의 updater)
6. 파일 교체:
   - ConvertPro3.exe → v1.1.0 ✅
   - tools/updater.exe → 변경 없음 ⚠️
7. v1.1.0 실행됨 (updater는 v1.0.0 그대로)
```

### 시나리오 3: updater 없는 경우 (오류)

```
1. 현재 버전: v1.0.0 (tools/updater.exe 없음!)
2. GitHub Release: v1.1.0.exe
3. 업데이트 시도
4. 오류: "업데이터를 찾을 수 없습니다"
5. 안내: "_full.zip 패키지를 다운로드하세요"
```

---

## 🎯 배포 시 주의사항

### 1. 항상 _full.zip 패키지 제공

```bash
# make.bat 실행
[1] 빌드 + Patch 버전 증가

결과:
dist/
├── ConvertPro3_v1.5.1.exe
├── ConvertPro3_v1.5.1_full.zip  ← 이것도 함께 업로드!
└── tools/
    └── updater.exe
```

### 2. GitHub Release에 모두 업로드

```bash
# GitHub Release 생성
[6] GitHub 배포

업로드 파일:
✅ ConvertPro3_v1.5.1_full.zip  (자동 업데이트용)
✅ ConvertPro3_v1.5.1.exe       (수동 다운로드용)
```

### 3. 첫 배포 시 반드시 updater 포함

```
초기 배포 (v1.0.0):
ConvertPro3_v1.0.0_full.zip
├── ConvertPro3_v1.0.0.exe
└── tools/
    └── updater.exe  ← 반드시 포함!

→ 이후 자동 업데이트 가능!
```

---

## 💡 FAQ

### Q1: 왜 updater가 필요한가요?
**A:** 프로그램이 **실행 중일 때는 자기 자신을 교체할 수 없기 때문**입니다.
- Windows는 실행 중인 .exe를 덮어쓸 수 없음
- 별도 프로세스(updater)가 프로그램 종료 후 파일 교체

### Q2: updater 구조가 바뀌면요?
**A:** _full.zip 방식은 **새 updater를 사용**하므로 안전합니다!
- 단일 .exe: 기존 updater 사용 (위험)
- _full.zip: 새 updater 사용 (안전) ✅

### Q3: 단일 .exe만 올리면 안되나요?
**A:** 가능하지만 **updater가 업데이트 안됨**:
- 메인 프로그램만 교체
- updater는 예전 버전 그대로
- updater 구조 변경 시 문제 발생 가능

### Q4: File_Converter에도 적용 가능한가요?
**A:** 네! 똑같이 적용 가능합니다:
1. `utils/update_manager.py` 복사
2. `ui/update_dialog.py` 복사
3. `tools/updater_standalone.py` 복사
4. `build_scripts/updater.spec` 설정
5. `make.bat` 실행 → _full.zip 생성

---

## 🚀 최종 권장 사항

### ✅ 배포 체크리스트
- [ ] `make.bat` → [1]/[2]/[3] (버전 업 + 빌드)
- [ ] `dist/` 폴더에 _full.zip 확인
- [ ] GitHub Release 생성
- [ ] **_full.zip 우선 업로드** ⭐
- [ ] .exe도 업로드 (수동 다운로드용)

### ✅ 사용자 안내
```
자동 업데이트:
- 프로그램 내 [업데이트] 버튼 클릭
- 자동으로 _full.zip 다운로드 및 적용

수동 업데이트:
- GitHub에서 _full.zip 다운로드
- 압축 해제 후 실행
```

---

🎉 **이제 updater도 자동 업데이트됩니다!**

핵심 포인트:
1. 항상 **_full.zip** 패키지 배포
2. 자동 업데이트는 **새 updater** 사용
3. updater 구조 변경에도 안전!
