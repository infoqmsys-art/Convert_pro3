CREATE TABLE IF NOT EXISTS schema_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organization (
  id         BIGSERIAL PRIMARY KEY,
  name       TEXT NOT NULL UNIQUE,
  code       TEXT,
  memo       TEXT,
  created_at TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS site (
  id                 BIGSERIAL PRIMARY KEY,
  organization_id    BIGINT NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
  name               TEXT NOT NULL,
  site_code          TEXT,
  install_date       TEXT,
  image_main         TEXT,
  image_list         TEXT,
  floor_plan         TEXT,
  emergency_notice   TEXT,
  weather_label      TEXT,
  weather_lat        DOUBLE PRECISION,
  weather_lon        DOUBLE PRECISION,
  last_add_sensor_code TEXT,
  last_add_sensor_kind TEXT,
  address            TEXT,
  site_program       TEXT,
  memo               TEXT,
  created_at         TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS')),
  UNIQUE (organization_id, name)
);
CREATE INDEX IF NOT EXISTS idx_site_org ON site(organization_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_site_org_site_code_unique ON site (organization_id, site_code)
  WHERE site_code IS NOT NULL AND btrim(site_code) != '';

CREATE TABLE IF NOT EXISTS portal_user (
  id              BIGSERIAL PRIMARY KEY,
  username        TEXT NOT NULL UNIQUE,
  password_hash   TEXT NOT NULL,
  display_name    TEXT,
  role            TEXT NOT NULL DEFAULT 'viewer'
                  CHECK (role IN ('admin', 'editor', 'viewer')),
  access_level    INTEGER NOT NULL DEFAULT 4
                  CHECK (access_level IN (1, 2, 3, 4)),
  memo            TEXT,
  organization_id BIGINT REFERENCES organization(id) ON DELETE SET NULL,
  is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at      TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS')),
  updated_at      TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS portal_user_site (
  user_id BIGINT NOT NULL REFERENCES portal_user(id) ON DELETE CASCADE,
  site_id BIGINT NOT NULL REFERENCES site(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, site_id)
);
CREATE INDEX IF NOT EXISTS idx_portal_user_site_user ON portal_user_site(user_id);
CREATE INDEX IF NOT EXISTS idx_portal_user_site_site ON portal_user_site(site_id);

CREATE TABLE IF NOT EXISTS site_manager (
  id         BIGSERIAL PRIMARY KEY,
  site_id    BIGINT NOT NULL REFERENCES site(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  title      TEXT,
  phone      TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_site_manager_site ON site_manager(site_id);

CREATE TABLE IF NOT EXISTS site_sms_config (
  site_id          BIGINT PRIMARY KEY REFERENCES site(id) ON DELETE CASCADE,
  enabled          INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  message_template TEXT,
  time_from        TEXT,
  time_to          TEXT,
  updated_at       TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE TABLE IF NOT EXISTS site_sms_recipient (
  id           BIGSERIAL PRIMARY KEY,
  site_id      BIGINT NOT NULL REFERENCES site(id) ON DELETE CASCADE,
  send_enabled INTEGER NOT NULL DEFAULT 1 CHECK (send_enabled IN (0, 1)),
  name         TEXT NOT NULL,
  phone        TEXT NOT NULL,
  job_title    TEXT,
  department   TEXT,
  info         TEXT,
  sort_order   INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_sms_recipient_site ON site_sms_recipient(site_id);

CREATE TABLE IF NOT EXISTS measurement_group (
  id         BIGSERIAL PRIMARY KEY,
  site_id    BIGINT NOT NULL REFERENCES site(id) ON DELETE CASCADE,
  parent_id  BIGINT REFERENCES measurement_group(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  memo       TEXT,
  created_at TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_measurement_group_site ON measurement_group(site_id);
CREATE INDEX IF NOT EXISTS idx_measurement_group_parent ON measurement_group(parent_id);

CREATE TABLE IF NOT EXISTS logger_device (
  id                      BIGSERIAL PRIMARY KEY,
  site_id                 BIGINT NOT NULL REFERENCES site(id) ON DELETE CASCADE,
  name                    TEXT NOT NULL,
  logger_kind             TEXT NOT NULL DEFAULT 'manual'
                          CHECK (logger_kind IN ('manual', 'ftp', 'other')),
  serial_number           TEXT,
  is_active               INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  folder_path             TEXT,
  folder_owner            TEXT,
  folder_owner_set_at     TEXT,
  time_column_index       INTEGER NOT NULL DEFAULT 0,
  first_data_column_index INTEGER NOT NULL DEFAULT 1,
  csv_source              TEXT NOT NULL DEFAULT 'server_path'
                          CHECK (csv_source IN ('server_path', 'upload')),
  status                  TEXT NOT NULL DEFAULT 'normal'
                          CHECK (status IN ('normal', 'delayed', 'unconverted', 'ghost', 'offline')),
  last_comm_at            TEXT,
  memo                    TEXT,
  last_ingest_at          TEXT,
  last_ingest_bytes       BIGINT,
  created_at              TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS')),
  UNIQUE (site_id, name)
);
CREATE INDEX IF NOT EXISTS idx_logger_site ON logger_device(site_id);
CREATE INDEX IF NOT EXISTS idx_logger_status ON logger_device(status);

CREATE TABLE IF NOT EXISTS sensor_channel (
  id                 BIGSERIAL PRIMARY KEY,
  logger_device_id   BIGINT NOT NULL REFERENCES logger_device(id) ON DELETE CASCADE,
  measurement_group_id BIGINT REFERENCES measurement_group(id) ON DELETE SET NULL,
  channel_index      INTEGER NOT NULL,
  list_order         INTEGER NOT NULL DEFAULT 0,
  label              TEXT NOT NULL,
  sensor_code        TEXT,
  serial_number      TEXT,
  sensor_kind        TEXT,
  unit               TEXT,
  decimal_places     INTEGER DEFAULT 2,
  is_active          INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  sms_enabled        INTEGER NOT NULL DEFAULT 0 CHECK (sms_enabled IN (0, 1)),
  level1_primary     DOUBLE PRECISION,
  level1_secondary   DOUBLE PRECISION,
  level2_primary     DOUBLE PRECISION,
  level2_secondary   DOUBLE PRECISION,
  level3_primary     DOUBLE PRECISION,
  level3_secondary   DOUBLE PRECISION,
  scale_k            DOUBLE PRECISION DEFAULT 1.0,
  scale_b            DOUBLE PRECISION DEFAULT 0.0,
  install_location   TEXT,
  install_date       TEXT,
  memo               TEXT,
  chart_y_min        DOUBLE PRECISION,
  chart_y_max        DOUBLE PRECISION,
  linked_sensor_codes TEXT,
  pipe_depth_m       DOUBLE PRECISION,
  gauge_factor       DOUBLE PRECISION,
  sensor_length_mm   DOUBLE PRECISION,
  calc_formula_1     TEXT,
  calc_formula_2     TEXT,
  calc_formula_3     TEXT,
  calc_formula_4     TEXT,
  calc_formula_5     TEXT,
  calc_formula_6     TEXT,
  UNIQUE (logger_device_id, channel_index)
);
CREATE INDEX IF NOT EXISTS idx_channel_logger ON sensor_channel(logger_device_id);

CREATE TABLE IF NOT EXISTS import_batch (
  id               BIGSERIAL PRIMARY KEY,
  logger_device_id BIGINT NOT NULL REFERENCES logger_device(id) ON DELETE CASCADE,
  source_path      TEXT NOT NULL,
  source_mtime     BIGINT,
  row_count        BIGINT,
  note             TEXT,
  created_at       TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_import_logger ON import_batch(logger_device_id);
CREATE INDEX IF NOT EXISTS idx_import_created ON import_batch(created_at DESC);

CREATE TABLE IF NOT EXISTS measurement_sample (
  id                BIGSERIAL PRIMARY KEY,
  sensor_channel_id BIGINT NOT NULL REFERENCES sensor_channel(id) ON DELETE CASCADE,
  observed_at       TEXT NOT NULL,
  value_real        DOUBLE PRECISION,
  value_raw         DOUBLE PRECISION,
  value_step_1      DOUBLE PRECISION,
  value_step_2      DOUBLE PRECISION,
  value_step_3      DOUBLE PRECISION,
  value_step_4      DOUBLE PRECISION,
  value_step_5      DOUBLE PRECISION,
  value_step_6      DOUBLE PRECISION,
  quality_flag      TEXT NOT NULL DEFAULT 'ok'
                    CHECK (quality_flag IN ('ok', 'suspect', 'missing')),
  import_batch_id   BIGINT REFERENCES import_batch(id) ON DELETE SET NULL,
  source_file       TEXT,
  source_mtime      BIGINT,
  created_at        TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_measurement_channel_time
  ON measurement_sample(sensor_channel_id, observed_at);

CREATE TABLE IF NOT EXISTS measurement_purge_log (
  id               BIGSERIAL PRIMARY KEY,
  logger_device_id BIGINT REFERENCES logger_device(id) ON DELETE SET NULL,
  sensor_channel_id BIGINT REFERENCES sensor_channel(id) ON DELETE SET NULL,
  time_from        TEXT NOT NULL,
  time_to          TEXT NOT NULL,
  deleted_rows     BIGINT NOT NULL DEFAULT 0,
  note             TEXT,
  created_at       TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_purge_created ON measurement_purge_log(created_at DESC);

CREATE TABLE IF NOT EXISTS alert (
  id                 BIGSERIAL PRIMARY KEY,
  site_id            BIGINT REFERENCES site(id) ON DELETE SET NULL,
  logger_device_id   BIGINT REFERENCES logger_device(id) ON DELETE SET NULL,
  severity           TEXT NOT NULL CHECK (severity IN ('info', 'warn', 'error')),
  title              TEXT NOT NULL,
  body               TEXT,
  created_at         TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS')),
  acknowledged_at    TEXT,
  acknowledged_by_id BIGINT REFERENCES portal_user(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_alert_created ON alert(created_at DESC);

CREATE TABLE IF NOT EXISTS audit_log (
  id            BIGSERIAL PRIMARY KEY,
  table_name    TEXT NOT NULL,
  record_id     BIGINT,
  action        TEXT NOT NULL CHECK (action IN ('insert', 'update', 'delete')),
  actor_user_id BIGINT REFERENCES portal_user(id) ON DELETE SET NULL,
  payload_json  TEXT,
  created_at    TEXT NOT NULL DEFAULT (to_char(current_timestamp, 'YYYY-MM-DD HH24:MI:SS'))
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
