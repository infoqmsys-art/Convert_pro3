# Convert Pro 3 - 잠재적 이슈 및 부족한 부분

코드베이스 점검 결과, 이상 동작 가능성이 있는 부분들을 정리했습니다.

---

## 1. 치명적 가능성 (우선 확인 권장)

### 1-1. config의 `offset` vs `mode` 불일치 ✅ 수정됨

**현상**
- `config.json`과 `ConfigManager.ensure_logger`는 채널 설정에 `"offset": "PASS"` 사용
- `SensorProcessor._load_channels`는 `raw.get("mode")`만 읽음
- `"offset"` → `"mode"` 변환은 **ChannelSettingsUI 로딩 시**에만 수행

**영향**
- 설정을 저장한 적 없는(채널 설정 창을 열지 않은) config는 `mode`가 없음
- 이 경우 `raw.get("mode")` → `None` → `"PASS"`로만 해석
- FM, EL, CR 등 다른 모드로 설정했어도, 저장이 `offset`으로만 되어 있으면 모두 PASS로 동작할 수 있음

**해결됨**: `SensorProcessor._load_channels`에서 `raw.get("mode") or raw.get("offset")` fallback 추가

---

### 1-2. 변환본 경로: 폴더명 매핑 (설계 반영)

**설계**
- 변환본 경로: `{convert_root}/{company}/{folder}/{filename}`
- **폴더명(로거 식별자)**으로 매핑
- `site`(현장)는 트리 UI용 논리 레벨, 경로에는 미포함

---

## 2. 주의 필요

### 2-1. base_time 이하 데이터가 하나라도 있으면 전체 스킵

**위치**: `file_processor.py` 216~222행

**현상**
- `base_time` 이하 시간이 **하나라도** 있으면 해당 파일 전체를 스킵
- 원본 행 순서가 뒤섞여 있으면 (예: 18:00, 17:00, 19:00) 17:00 때문에 전체 스킵될 수 있음

**해결 방향**
- 행 단위로 base_time 이후만 선택하고, 이하 행만 제외하는 방식 검토
- 또는 정렬 후 base_time 이후 구간만 처리

---

### 2-2. gen_interval: 원본 CSV 직접 수정

**위치**: `scheduler_manager.py` `_append_interval_row`

**현상**
- `__gen_interval__` 설정 시 **원본 로거 CSV**에 0값 행을 append
- 원본 구조(헤더 유무, 컬럼 수 등)에 따라 포맷이 깨지거나 예상과 다르게 쓸 수 있음

**해결 방향**
- 원본 수정 대신 변환본만 생성하는 방식 검토
- 또는 원본 포맷을 엄격히 검증한 뒤에만 append

---

### 2-3. _get_last_converted_data: 마지막 10줄만 사용

**위치**: `file_processor.py` `_get_last_converted_data`

**현상**
- `pd.read_csv(..., nrows=마지막부분)`이 아니라 전체를 읽음 (실제로는 마지막 10줄 미사용)
- 현재는 `df_tail = pd.read_csv(...)` 전체 로드 후 `iloc[-1]`만 사용
- 대용량 변환본에서 메모리 사용 증가

**추가 이슈**
- 변환본 첫 행이 헤더인데 `header=None`으로 읽으면, 헤더 행도 데이터로 들어감
- 데이터가 1행뿐이면 `iloc[-1]`이 헤더 행이 되어 timestamp 파싱 실패 가능

---

### 2-4. 변환본 첫 저장 시 헤더 처리

**위치**: `file_processor._save_append`

**현상**
- 최초 저장: `df.to_csv(..., header=True)`
- 이후 append: `df.to_csv(..., header=False)`
- `_get_last_converted_data`는 `header=None`으로 읽어 첫 행을 데이터로 취급
- 데이터가 1행만 있으면 그 행이 헤더일 수 있어, last_row 해석이 잘못될 수 있음

---

## 3. 개선 여지

### 3-1. convert_root 하드코딩

- `r"C:\data\Convertfile"`로 고정
- 설정으로 변경 가능하게 하면 다양한 환경 대응에 유리

### 3-2. Config와 변환 동시 접근

- 채널 설정 저장과 변환 실행이 동시에 일어날 수 있음
- Config 저장에 Lock이 있으나, 변환 시점에 읽는 config가 갱신 직전/직후 상태와 어긋날 수 있음

### 3-3. 배터리 56열 가정

- `_move_battery`에서 56열(인덱스 56)이 batLevel이라고 가정
- 원본 구조가 다르면 잘못된 열을 배터리로 사용할 수 있음

### 3-4. 채널 설정 저장 시 mode만 저장

- ChannelSettingsUI는 저장 시 `offset`을 제거하고 `mode`만 저장
- `ensure_logger`로 새로 만든 파일은 `offset`만 있음
- 새 파일에 대해 채널 창을 한 번도 열지 않으면 SensorProcessor가 `mode`를 못 찾음 (1-1과 동일)

---

## 4. 요약 체크리스트

| 우선순위 | 이슈 | 영향 |
|----------|------|------|
| 높음 | offset/mode 불일치 | 센서 모드가 모두 PASS로 처리될 수 있음 |
| 높음 | site 경로 미포함 | 다른 현장 간 변환본 덮어쓰기 |
| 중간 | base_time 스킵 로직 | 순서가 섞인 원본에서 변환 누락 |
| 중간 | gen_interval 원본 수정 | 원본 CSV 손상 가능성 |
| 낮음 | convert_root 고정 | 경로 유연성 부족 |
| 낮음 | Config 동시 접근 | 설정과 변환 결과 불일치 가능성 |
