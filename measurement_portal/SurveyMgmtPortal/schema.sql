-- 계측관리 통합시스템 — SQLite 스키마 (프로토타입)
-- 개념: 업체 → 현장 → 로거(게이트웨이) → 센서 채널 → 측정값(시계열) / 알림 / 감사
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- 포털 로그인 계정
-- access_level: 1=최고관리자(모든 현장), 3=계측자(할당 현장·편집), 4=게스트(할당 현장·조회)
-- 할당 현장은 portal_user_site (level 1 은 행 없이 전체 허용)
CREATE TABLE IF NOT EXISTS portal_user (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name  TEXT,
  role          TEXT NOT NULL DEFAULT 'viewer'
                CHECK (role IN ('admin', 'editor', 'viewer')),
  access_level  INTEGER NOT NULL DEFAULT 4
                CHECK (access_level IN (1, 3, 4)),
  memo          TEXT,
  is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 사용자별 접근 가능 현장 (access_level 1 은 무시·전체 허용)
CREATE TABLE IF NOT EXISTS portal_user_site (
  user_id INTEGER NOT NULL REFERENCES portal_user(id) ON DELETE CASCADE,
  site_id INTEGER NOT NULL REFERENCES site(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, site_id)
);
CREATE INDEX IF NOT EXISTS idx_portal_user_site_user ON portal_user_site(user_id);
CREATE INDEX IF NOT EXISTS idx_portal_user_site_site ON portal_user_site(site_id);

-- 업체
CREATE TABLE IF NOT EXISTS organization (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL UNIQUE,
  code       TEXT,
  memo       TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 현장 (site_code: 영문·숫자 소문자, 로거 접두 tunnel_0 등 — 기존 ansan 레거시 호환)
CREATE TABLE IF NOT EXISTS site (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  organization_id INTEGER NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  site_code       TEXT,
  install_date    TEXT,
  image_main      TEXT,
  image_list      TEXT,
  last_add_sensor_code TEXT,
  last_add_sensor_kind TEXT,
  address         TEXT,
  site_program    TEXT,
  memo            TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (organization_id, name)
);
CREATE INDEX IF NOT EXISTS idx_site_org ON site(organization_id);
-- 동일 업체 내 영문 코드 중복 금지(비움 허용: 구 데이터)
CREATE UNIQUE INDEX IF NOT EXISTS idx_site_org_site_code_unique ON site (organization_id, site_code)
  WHERE site_code IS NOT NULL AND TRIM(site_code) != '';

-- 현장 담당자 (정규화는 나중에 person 테이블로 확장 가능)
CREATE TABLE IF NOT EXISTS site_manager (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id    INTEGER NOT NULL REFERENCES site(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  title      TEXT,
  phone      TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_site_manager_site ON site_manager(site_id);

-- 현장 단위 SMS 알림 설정 (웹 전용)
CREATE TABLE IF NOT EXISTS site_sms_config (
  site_id          INTEGER PRIMARY KEY REFERENCES site(id) ON DELETE CASCADE,
  enabled          INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  message_template TEXT,
  time_from        TEXT,
  time_to          TEXT,
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 현장별 SMS 발송 대상자
CREATE TABLE IF NOT EXISTS site_sms_recipient (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id       INTEGER NOT NULL REFERENCES site(id) ON DELETE CASCADE,
  send_enabled  INTEGER NOT NULL DEFAULT 1 CHECK (send_enabled IN (0, 1)),
  name          TEXT NOT NULL,
  phone         TEXT NOT NULL,
  job_title     TEXT,
  department    TEXT,
  info          TEXT,
  sort_order    INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sms_recipient_site ON site_sms_recipient(site_id);

-- 측정 카테고리 (좌측 트리 "지하수위계", "유량계" 등 — 현장 단위)
-- parent_id: 하위 그룹이 필요할 때만 사용 (NULL = 최상위)
CREATE TABLE IF NOT EXISTS measurement_group (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id    INTEGER NOT NULL REFERENCES site(id) ON DELETE CASCADE,
  parent_id  INTEGER REFERENCES measurement_group(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  memo       TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_measurement_group_site ON measurement_group(site_id);
CREATE INDEX IF NOT EXISTS idx_measurement_group_parent ON measurement_group(parent_id);

-- 로거 / 게이트웨이 / 수집 단말
-- logger_kind: 수동계측→manual, FTP→ftp (레거시 데이터수집프로그램과 동일 구분)
-- time_column_index / first_data_column_index: CSV 열 매핑 (scripts/measurement_ingest 기본값)
-- csv_source: server_path = 서버가 읽을 로컬/공유 경로(folder_path) — upload 는 추후 업로드 저장소와 조합
CREATE TABLE IF NOT EXISTS logger_device (
  id                        INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id                   INTEGER NOT NULL REFERENCES site(id) ON DELETE CASCADE,
  name                      TEXT NOT NULL,
  logger_kind               TEXT NOT NULL DEFAULT 'manual'
                            CHECK (logger_kind IN ('manual', 'ftp', 'other')),
  serial_number             TEXT,
  is_active                 INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  folder_path               TEXT,
  time_column_index         INTEGER NOT NULL DEFAULT 0,
  first_data_column_index   INTEGER NOT NULL DEFAULT 1,
  csv_source                TEXT NOT NULL DEFAULT 'server_path'
                            CHECK (csv_source IN ('server_path', 'upload')),
  status                    TEXT NOT NULL DEFAULT 'normal'
                            CHECK (status IN ('normal', 'delayed', 'unconverted', 'ghost', 'offline')),
  last_comm_at              TEXT,
  memo                      TEXT,
  last_ingest_at            TEXT,
  last_ingest_bytes         INTEGER,
  created_at                TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (site_id, name)
);
CREATE INDEX IF NOT EXISTS idx_logger_site ON logger_device(site_id);
CREATE INDEX IF NOT EXISTS idx_logger_status ON logger_device(status);

-- 센서 (로거당 다수 추가)
-- channel_index : CSV 파일 한 줄에서 맨 왼쪽 칸을 0으로 세는 값 열 인덱스 (화면 「칼럼」번호−1).
-- list_order    : 레거시·DB 유지용. 저장 시 channel_index 와 동기화되며 목록 정렬은 channel_index 기준
-- sensor_code : 현장(site) 단위로 중복 불가 (애플리케이션에서 검증, 공백 제거 후 비교)
-- sensor_kind   : 종류 코드 — sensor_catalog.py 의 id 와 동일하게 저장 권장
-- level*_primary / *_secondary : 관리기준 1·2·3단계 주값·보조값 (경사계·균열 등은 mm 스케일 권장; 경사 기본 sensor_catalog.TILT_MANAGEMENT_DEFAULTS_MM, 균열 기본 CRACK_MANAGEMENT_DEFAULTS_MM)
-- scale_k, scale_b            : 스케일 적용 후 m = scale_k * 원시값 + scale_b → calc_formula_* 에서 m, r1.. 참조
-- sensor_length_mm            : 지중경사계 등. 적재 시 계산식 extra_env 의 L (기본 mm 단위 길이)
-- linked_sensor_codes         : 대표 센서에만 저장. 같은 현장의 다른 sensor_code(쉼표·공백 구분) — 워크스페이스에서 다중 시계열·통합 표
--   단축: '-Y','-Z' 는 대표 sensor_code 에 접미 (예: 대표 V1 → V1-Y, V1-Z)
--   지중경사 다단: 대표=가장 하부 단(예: I1-1), 연결란=하부→상부 순( I1-2, I1-3 … 또는 -2 -3 )
-- calc_formula_1..6           : 적재 시 순차 평가(비어 있으면 이전 단계 값 유지). 최종 value_real 은 비어 있지 않은 마지막 식 결과
CREATE TABLE IF NOT EXISTS sensor_channel (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  logger_device_id      INTEGER NOT NULL REFERENCES logger_device(id) ON DELETE CASCADE,
  measurement_group_id  INTEGER REFERENCES measurement_group(id) ON DELETE SET NULL,
  channel_index         INTEGER NOT NULL,
  list_order            INTEGER NOT NULL DEFAULT 0,
  label                 TEXT NOT NULL,
  sensor_code        TEXT,
  serial_number      TEXT,
  sensor_kind        TEXT,
  unit               TEXT,
  decimal_places     INTEGER DEFAULT 2,
  is_active          INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  sms_enabled        INTEGER NOT NULL DEFAULT 0 CHECK (sms_enabled IN (0, 1)),
  level1_primary     REAL,
  level1_secondary   REAL,
  level2_primary     REAL,
  level2_secondary   REAL,
  level3_primary     REAL,
  level3_secondary   REAL,
  scale_k            REAL DEFAULT 1.0,
  scale_b            REAL DEFAULT 0.0,
  install_location   TEXT,
  install_date       TEXT,
  memo               TEXT,
  chart_y_min        REAL,
  chart_y_max        REAL,
  linked_sensor_codes TEXT,
  pipe_depth_m       REAL,
  gauge_factor       REAL,
  sensor_length_mm   REAL,
  calc_formula_1     TEXT,
  calc_formula_2     TEXT,
  calc_formula_3     TEXT,
  calc_formula_4     TEXT,
  calc_formula_5     TEXT,
  calc_formula_6     TEXT,
  UNIQUE (logger_device_id, channel_index)
);
CREATE INDEX IF NOT EXISTS idx_channel_logger ON sensor_channel(logger_device_id);

-- 파일(재)수집 단위 — 그래프용 측정행이 어느 파일·배치에서 왔는지 추적
CREATE TABLE IF NOT EXISTS import_batch (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  logger_device_id  INTEGER NOT NULL REFERENCES logger_device(id) ON DELETE CASCADE,
  source_path       TEXT NOT NULL,
  source_mtime      INTEGER,
  row_count         INTEGER,
  note              TEXT,
  created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_import_logger ON import_batch(logger_device_id);
CREATE INDEX IF NOT EXISTS idx_import_created ON import_batch(created_at DESC);

-- 그래프·통계용 시계열 (파일에서 적재; 웹에서 구간 DELETE 후 재수집으로 갱신)
-- value_raw = CSV 셀, value_step_1..6 = 계산식 체인 단계별 값, value_real = 비어 있지 않은 마지막 계산식 결과(없으면 m)
CREATE TABLE IF NOT EXISTS measurement_sample (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  sensor_channel_id  INTEGER NOT NULL REFERENCES sensor_channel(id) ON DELETE CASCADE,
  observed_at        TEXT NOT NULL,
  value_real         REAL,
  value_raw          REAL,
  value_step_1       REAL,
  value_step_2       REAL,
  value_step_3       REAL,
  value_step_4       REAL,
  value_step_5       REAL,
  value_step_6       REAL,
  quality_flag       TEXT NOT NULL DEFAULT 'ok'
                     CHECK (quality_flag IN ('ok', 'suspect', 'missing')),
  import_batch_id    INTEGER REFERENCES import_batch(id) ON DELETE SET NULL,
  source_file        TEXT,
  source_mtime       INTEGER,
  created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_measurement_channel_time
  ON measurement_sample(sensor_channel_id, observed_at);

-- 웹·API에서 구간 삭제 시 감사(선택)
CREATE TABLE IF NOT EXISTS measurement_purge_log (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  logger_device_id   INTEGER REFERENCES logger_device(id) ON DELETE SET NULL,
  sensor_channel_id  INTEGER REFERENCES sensor_channel(id) ON DELETE SET NULL,
  time_from          TEXT NOT NULL,
  time_to            TEXT NOT NULL,
  deleted_rows       INTEGER NOT NULL DEFAULT 0,
  note               TEXT,
  created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_purge_created ON measurement_purge_log(created_at DESC);

-- 알림
CREATE TABLE IF NOT EXISTS alert (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  site_id            INTEGER REFERENCES site(id) ON DELETE SET NULL,
  logger_device_id   INTEGER REFERENCES logger_device(id) ON DELETE SET NULL,
  severity           TEXT NOT NULL CHECK (severity IN ('info', 'warn', 'error')),
  title              TEXT NOT NULL,
  body               TEXT,
  created_at         TEXT NOT NULL DEFAULT (datetime('now')),
  acknowledged_at    TEXT,
  acknowledged_by_id INTEGER REFERENCES portal_user(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_alert_created ON alert(created_at DESC);

-- 감사 로그 (설정 변경·삭제 추적)
CREATE TABLE IF NOT EXISTS audit_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  table_name   TEXT NOT NULL,
  record_id    INTEGER,
  action       TEXT NOT NULL CHECK (action IN ('insert', 'update', 'delete')),
  actor_user_id INTEGER REFERENCES portal_user(id) ON DELETE SET NULL,
  payload_json TEXT,
  created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
