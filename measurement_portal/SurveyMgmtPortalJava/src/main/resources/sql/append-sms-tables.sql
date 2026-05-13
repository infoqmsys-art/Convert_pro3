-- Python schema.sql / db.migrate_schema 와 동일 (기존 DB에만 보강)
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS site_sms_config (
  site_id          INTEGER PRIMARY KEY REFERENCES site(id) ON DELETE CASCADE,
  enabled          INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  message_template TEXT,
  time_from        TEXT,
  time_to          TEXT,
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
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
