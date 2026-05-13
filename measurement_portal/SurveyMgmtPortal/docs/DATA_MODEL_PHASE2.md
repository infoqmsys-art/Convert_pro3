# 2단계 — 데이터 모델 확정 (필드·정책)

[화면 맵](./SCREEN_MAP_AND_ENTITIES.md)

스키마 버전 메타: `schema_meta.schema_version` = **5** (신규 설치·`init_schema` 기준).

---

## 1. 결정 요약

| 주제 | 결정 |
|------|------|
| **시간·데이터 열** | 로거마다 `time_column_index`(기본 0), `first_data_column_index`(기본 1). 값 열 = `first_data_column_index + sensor_channel.channel_index`. |
| **카테고리(트리)** | 현장 단위 `measurement_group` 테이블 + `sensor_channel.measurement_group_id`(NULL 허용). `sensor_kind`는 종류 코드로 병행. |
| **파일 소스** | `logger_device.csv_source`: `server_path`(기본) \| `upload`. 지금은 경로·CLI 적재 중심; `upload`는 저장소·UI 연동 시 사용. |
| **Convert Pro** | 연동 없음. 웹 DB만 사용. |

---

## 2. 테이블·컬럼 (추가·변경분)

### `measurement_group`

| 컬럼 | 설명 |
|------|------|
| `site_id` | 소속 현장 |
| `parent_id` | 하위 그룹(선택). NULL = 최상위 |
| `name` | 표시명 (예: 지하수위계) |
| `sort_order` | 트리·목록 정렬 |

### `logger_device` (추가 컬럼)

| 컬럼 | 기본값 | 설명 |
|------|--------|------|
| `time_column_index` | 0 | CSV 시각 열 (0부터) |
| `first_data_column_index` | 1 | CH0 원시값이 시작하는 열 |
| `csv_source` | `server_path` | `server_path` \| `upload` |

`folder_path`는 기존과 동일: 서버가 읽을 파일 경로(또는 추후 업로드와 매핑).

### `sensor_channel` (추가 컬럼)

| 컬럼 | 설명 |
|------|------|
| `measurement_group_id` | 좌측 카테고리 노드 (없으면 NULL) |

---

## 3. 적재 스크립트와의 관계

`scripts/measurement_ingest.py`는 `--time-col` / `--data-base-col`을 **생략하면** 위 로거 컬럼을 사용한다.

---

## 4. 미구현(의도적)

- 업로드 파일 저장 경로·`csv_source = upload` 동작
- `measurement_group` CRUD UI
- 다중 사용자·감사 로그 자동 기록

필요 시 3단계 이후에 추가한다.
