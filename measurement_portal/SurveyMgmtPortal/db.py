"""
SQLite 연결, 스키마 적용, 데모 시드, 대시보드 집계.

DB 경로: 환경변수 SURVEY_PORTAL_DB 또는 이 폴더 기준 data/survey_portal.sqlite3
(Convert Pro 저장소와 파일을 공유하지 않음.)
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

_APP_DIR = Path(__file__).resolve().parent
_DEFAULT_DB = _APP_DIR / "data" / "survey_portal.sqlite3"
SCHEMA_FILE = _APP_DIR / "schema.sql"

# 부트스트랩·1회 마이그레이션 기본값. 환경변수 SURVEY_PORTAL_PASS 가 있으면 그 값이 우선합니다.
DEFAULT_PORTAL_ADMIN_PASSWORD = "1524"


class SensorCodeDuplicateError(Exception):
    """동일 현장(site)에서 sensor_code 가 이미 사용 중일 때."""


def _normalize_sensor_code(val: str | None) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def split_linked_sensor_codes(raw: str | None) -> list[str]:
    """연결센서코드: 쉼표·세미콜론·공백으로 구분."""
    if not raw or not str(raw).strip():
        return []
    parts = re.split(r"[,;\s]+", str(raw).strip())
    return [p for p in (s.strip() for s in parts) if p]


def expand_linked_sensor_code_relative(primary_sensor_code: str | None, token: str) -> str:
    """
    연결코드 단축 표기: 토큰이 '-Y', '-Z', '-2', '-3' 처럼 하이픈으로 시작하면
    대표 센서코드 + 토큰 으로 풉니다 (예: 대표 V1 + -Y → V1-Y, 대표 LC1 + -2 → LC1-2).
    그 외는 토큰을 그대로 사용(전체 코드 입력 호환).
    """
    t = str(token).strip()
    if not t:
        return t
    base = _normalize_sensor_code(primary_sensor_code)
    if base and t.startswith("-") and len(t) >= 2:
        return base + t
    return t


def _site_sensor_code_taken_conn(
    conn: sqlite3.Connection,
    site_id: int,
    sensor_code: str,
    *,
    exclude_channel_id: int | None = None,
) -> bool:
    code = _normalize_sensor_code(sensor_code)
    if not code:
        return False
    q = """
        SELECT 1 FROM sensor_channel sc
        INNER JOIN logger_device ld ON ld.id = sc.logger_device_id
        WHERE ld.site_id = ?
          AND TRIM(COALESCE(sc.sensor_code, '')) = ?
    """
    params: list = [site_id, code]
    if exclude_channel_id is not None:
        q += " AND sc.id != ?"
        params.append(exclude_channel_id)
    q += " LIMIT 1"
    return conn.execute(q, params).fetchone() is not None


def get_sensor_channel_by_site_and_code(site_id: int, code: str) -> dict | None:
    """현장 내 sensor_code(정규화 후 TRIM 일치)로 채널 1건."""
    norm = _normalize_sensor_code(code)
    if not norm:
        return None
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT sc.*, ld.name AS logger_name, ld.id AS logger_device_id,
                   s.id AS site_id, s.name AS site_name, s.site_code,
                   o.name AS org_name, mg.name AS group_name
            FROM sensor_channel sc
            JOIN logger_device ld ON ld.id = sc.logger_device_id
            JOIN site s ON s.id = ld.site_id
            JOIN organization o ON o.id = s.organization_id
            LEFT JOIN measurement_group mg ON mg.id = sc.measurement_group_id
            WHERE s.id = ? AND TRIM(COALESCE(sc.sensor_code, '')) = ?
            LIMIT 1
            """,
            (site_id, norm),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def resolve_measurement_bundle_channels(
    primary: dict,
) -> tuple[list[dict], list[str]]:
    """대표 센서 + linked_sensor_codes 순서로 채널 행을 모은다. 없는 코드는 missing 에 담는다.

    지중경사 다단: 관례상 대표=가장 하부 단(예: I1-1), 연결란=그 위로 하부→상부 순( I1-2, I1-3 … ).
    """
    site_id = int(primary["site_id"])
    out: list[dict] = [primary]
    seen: set[str] = set()
    pco = _normalize_sensor_code(primary.get("sensor_code"))
    if pco:
        seen.add(pco)
    missing: list[str] = []
    linked = split_linked_sensor_codes(primary.get("linked_sensor_codes"))
    if not linked:
        sk = (primary.get("sensor_kind") or "").strip()
        if sk in ("inclinometer", "internal_displacement", "rail_displacement"):
            code = _normalize_sensor_code(primary.get("sensor_code"))
            if code:
                m = re.fullmatch(r"(.+?)-(\d+)", code)
            else:
                m = None
            if m:
                prefix = m.group(1) + "-"
                conn = connect()
                try:
                    rows = conn.execute(
                        """
                        SELECT sc.*, ld.name AS logger_name, ld.id AS logger_device_id,
                               s.id AS site_id, s.name AS site_name, s.site_code,
                               o.name AS org_name, mg.name AS group_name
                        FROM sensor_channel sc
                        JOIN logger_device ld ON ld.id = sc.logger_device_id
                        JOIN site s ON s.id = ld.site_id
                        JOIN organization o ON o.id = s.organization_id
                        LEFT JOIN measurement_group mg ON mg.id = sc.measurement_group_id
                        WHERE s.id = ?
                          AND TRIM(COALESCE(sc.sensor_code, '')) LIKE ?
                        """,
                        (site_id, prefix + "%"),
                    ).fetchall()
                finally:
                    conn.close()
                cand: list[tuple[int, dict]] = []
                for r in rows:
                    row = dict(r)
                    rk = (row.get("sensor_kind") or "").strip()
                    if rk not in ("inclinometer", "internal_displacement", "rail_displacement"):
                        continue
                    scode = (row.get("sensor_code") or "").strip()
                    if not scode.startswith(prefix):
                        continue
                    suf = scode[len(prefix) :]
                    if not suf.isdigit():
                        continue
                    nc = _normalize_sensor_code(scode)
                    if not nc or nc in seen:
                        continue
                    cand.append((int(suf), row))
                cand.sort(key=lambda x: x[0])
                for _n, row in cand:
                    nc2 = _normalize_sensor_code(row.get("sensor_code"))
                    if nc2 and nc2 not in seen:
                        seen.add(nc2)
                        out.append(row)

    for raw_c in linked:
        expanded = expand_linked_sensor_code_relative(primary.get("sensor_code"), raw_c)
        nc = _normalize_sensor_code(expanded)
        if not nc or nc in seen:
            continue
        row = get_sensor_channel_by_site_and_code(site_id, expanded)
        if row:
            seen.add(nc)
            out.append(dict(row))
        else:
            miss_lbl = raw_c.strip()
            if miss_lbl != expanded:
                miss_lbl = f"{miss_lbl}→{expanded}"
            missing.append(miss_lbl)
    return out, missing


def get_db_path() -> Path:
    raw = os.environ.get("SURVEY_PORTAL_DB", "").strip()
    return Path(raw) if raw else _DEFAULT_DB


def connect() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        path, detect_types=sqlite3.PARSE_DECLTYPES, timeout=30
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.OperationalError:
        pass
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _ensure_bootstrap_admin(conn: sqlite3.Connection) -> None:
    """portal_user 가 비어 있으면 admin 계정 1개 생성 (비밀번호는 환경변수 또는 기본값)."""
    if not _table_exists(conn, "portal_user"):
        return
    n = conn.execute("SELECT COUNT(*) AS c FROM portal_user").fetchone()["c"]
    if n > 0:
        return
    pw = os.environ.get("SURVEY_PORTAL_PASS", DEFAULT_PORTAL_ADMIN_PASSWORD)
    conn.execute(
        """
        INSERT INTO portal_user(
          username, password_hash, display_name, role, access_level, memo)
        VALUES (?,?,?,?,1,?)
        """,
        (
            "admin",
            generate_password_hash(pw),
            "관리자",
            "admin",
            "자동 생성: DB에 계정이 없을 때",
        ),
    )


def _apply_default_admin_password_once(conn: sqlite3.Connection) -> None:
    """username=admin 계정 비밀번호를 기본값으로 한 번 동기화 (schema_meta 로 1회만)."""
    if not _table_exists(conn, "schema_meta") or not _table_exists(conn, "portal_user"):
        return
    key = "portal_admin_default_pw_1524_v1"
    if conn.execute("SELECT 1 FROM schema_meta WHERE key = ?", (key,)).fetchone():
        return
    pw = os.environ.get("SURVEY_PORTAL_PASS", DEFAULT_PORTAL_ADMIN_PASSWORD)
    row = conn.execute(
        "SELECT id FROM portal_user WHERE username = ?", ("admin",)
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE portal_user
            SET password_hash = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (generate_password_hash(pw), row["id"]),
        )
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, '1')",
        (key,),
    )


def migrate_schema(conn: sqlite3.Connection) -> None:
    """기존 SQLite에 컬럼만 추가 (이미 있으면 생략)."""
    cols = _table_columns(conn, "site")
    if "site_code" not in cols:
        conn.execute("ALTER TABLE site ADD COLUMN site_code TEXT")
    if "install_date" not in cols:
        conn.execute("ALTER TABLE site ADD COLUMN install_date TEXT")
    if "image_main" not in cols:
        conn.execute("ALTER TABLE site ADD COLUMN image_main TEXT")
    if "image_list" not in cols:
        conn.execute("ALTER TABLE site ADD COLUMN image_list TEXT")
    if "last_add_sensor_code" not in _table_columns(conn, "site"):
        conn.execute("ALTER TABLE site ADD COLUMN last_add_sensor_code TEXT")
    if "last_add_sensor_kind" not in _table_columns(conn, "site"):
        conn.execute("ALTER TABLE site ADD COLUMN last_add_sensor_kind TEXT")

    cols = _table_columns(conn, "logger_device")
    if "logger_kind" not in cols:
        conn.execute(
            "ALTER TABLE logger_device ADD COLUMN logger_kind TEXT DEFAULT 'manual'"
        )
    if "serial_number" not in cols:
        conn.execute("ALTER TABLE logger_device ADD COLUMN serial_number TEXT")
    if "is_active" not in cols:
        conn.execute(
            "ALTER TABLE logger_device ADD COLUMN is_active INTEGER DEFAULT 1"
        )

    cols = _table_columns(conn, "logger_device")
    if "time_column_index" not in cols:
        conn.execute(
            "ALTER TABLE logger_device ADD COLUMN time_column_index INTEGER DEFAULT 0"
        )
        conn.execute("UPDATE logger_device SET time_column_index = 0 WHERE time_column_index IS NULL")
    if "first_data_column_index" not in cols:
        conn.execute(
            "ALTER TABLE logger_device ADD COLUMN first_data_column_index INTEGER DEFAULT 1"
        )
        conn.execute(
            "UPDATE logger_device SET first_data_column_index = 1 "
            "WHERE first_data_column_index IS NULL"
        )
    if "csv_source" not in cols:
        conn.execute(
            "ALTER TABLE logger_device ADD COLUMN csv_source TEXT DEFAULT 'server_path'"
        )
        conn.execute(
            "UPDATE logger_device SET csv_source = 'server_path' WHERE csv_source IS NULL"
        )

    cols = _table_columns(conn, "logger_device")
    if "last_ingest_at" not in cols:
        conn.execute("ALTER TABLE logger_device ADD COLUMN last_ingest_at TEXT")
    if "last_ingest_bytes" not in cols:
        conn.execute("ALTER TABLE logger_device ADD COLUMN last_ingest_bytes INTEGER")

    cols = _table_columns(conn, "sensor_channel")
    if "list_order" not in cols:
        conn.execute(
            "ALTER TABLE sensor_channel ADD COLUMN list_order INTEGER DEFAULT 0"
        )
        conn.execute("UPDATE sensor_channel SET list_order = channel_index")
    if "sensor_code" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN sensor_code TEXT")
    if "serial_number" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN serial_number TEXT")
    if "sensor_kind" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN sensor_kind TEXT")
    if "decimal_places" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN decimal_places INTEGER DEFAULT 2")
    if "is_active" not in cols:
        conn.execute(
            "ALTER TABLE sensor_channel ADD COLUMN is_active INTEGER DEFAULT 1"
        )
    if "sms_enabled" not in cols:
        conn.execute(
            "ALTER TABLE sensor_channel ADD COLUMN sms_enabled INTEGER DEFAULT 0"
        )
    if "level1_primary" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN level1_primary REAL")
    if "level1_secondary" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN level1_secondary REAL")
    if "level2_primary" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN level2_primary REAL")
    if "level2_secondary" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN level2_secondary REAL")
    if "level3_primary" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN level3_primary REAL")
    if "level3_secondary" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN level3_secondary REAL")
    if "scale_k" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN scale_k REAL DEFAULT 1.0")
    if "scale_b" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN scale_b REAL DEFAULT 0.0")
    if "install_location" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN install_location TEXT")
    if "install_date" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN install_date TEXT")
    if "memo" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN memo TEXT")

    if not _table_exists(conn, "measurement_group"):
        conn.execute(
            """
            CREATE TABLE measurement_group (
              id         INTEGER PRIMARY KEY AUTOINCREMENT,
              site_id    INTEGER NOT NULL REFERENCES site(id) ON DELETE CASCADE,
              parent_id  INTEGER REFERENCES measurement_group(id) ON DELETE CASCADE,
              name       TEXT NOT NULL,
              sort_order INTEGER NOT NULL DEFAULT 0,
              memo       TEXT,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_measurement_group_site "
            "ON measurement_group(site_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_measurement_group_parent "
            "ON measurement_group(parent_id)"
        )

    cols = _table_columns(conn, "sensor_channel")
    if "measurement_group_id" not in cols:
        conn.execute(
            "ALTER TABLE sensor_channel ADD COLUMN measurement_group_id INTEGER"
        )

    if "list_order" in _table_columns(conn, "sensor_channel"):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_channel_list "
            "ON sensor_channel(logger_device_id, list_order)"
        )

    if "measurement_group_id" in _table_columns(conn, "sensor_channel"):
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_channel_group "
            "ON sensor_channel(measurement_group_id)"
        )

    cols = _table_columns(conn, "sensor_channel")
    if "chart_y_min" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN chart_y_min REAL")
    if "chart_y_max" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN chart_y_max REAL")

    cols = _table_columns(conn, "sensor_channel")
    for i in range(1, 7):
        cname = f"calc_formula_{i}"
        if cname not in cols:
            conn.execute(f"ALTER TABLE sensor_channel ADD COLUMN {cname} TEXT")

    cols = _table_columns(conn, "sensor_channel")
    if "linked_sensor_codes" not in cols:
        conn.execute(
            "ALTER TABLE sensor_channel ADD COLUMN linked_sensor_codes TEXT"
        )

    cols = _table_columns(conn, "sensor_channel")
    if "pipe_depth_m" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN pipe_depth_m REAL")
    if "gauge_factor" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN gauge_factor REAL")
    if "sensor_length_mm" not in cols:
        conn.execute("ALTER TABLE sensor_channel ADD COLUMN sensor_length_mm REAL")

    if not _table_exists(conn, "import_batch"):
        conn.execute(
            """
            CREATE TABLE import_batch (
              id                INTEGER PRIMARY KEY AUTOINCREMENT,
              logger_device_id  INTEGER NOT NULL REFERENCES logger_device(id) ON DELETE CASCADE,
              source_path       TEXT NOT NULL,
              source_mtime      INTEGER,
              row_count         INTEGER,
              note              TEXT,
              created_at        TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_import_logger ON import_batch(logger_device_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_import_created ON import_batch(created_at DESC)"
        )

    if not _table_exists(conn, "measurement_purge_log"):
        conn.execute(
            """
            CREATE TABLE measurement_purge_log (
              id                 INTEGER PRIMARY KEY AUTOINCREMENT,
              logger_device_id   INTEGER REFERENCES logger_device(id) ON DELETE SET NULL,
              sensor_channel_id  INTEGER REFERENCES sensor_channel(id) ON DELETE SET NULL,
              time_from          TEXT NOT NULL,
              time_to            TEXT NOT NULL,
              deleted_rows       INTEGER NOT NULL DEFAULT 0,
              note               TEXT,
              created_at         TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_purge_created "
            "ON measurement_purge_log(created_at DESC)"
        )

    cols = _table_columns(conn, "measurement_sample")
    if "value_raw" not in cols:
        conn.execute("ALTER TABLE measurement_sample ADD COLUMN value_raw REAL")
    if "import_batch_id" not in cols:
        conn.execute(
            "ALTER TABLE measurement_sample ADD COLUMN import_batch_id INTEGER"
        )
    if "source_file" not in cols:
        conn.execute("ALTER TABLE measurement_sample ADD COLUMN source_file TEXT")
    if "source_mtime" not in cols:
        conn.execute("ALTER TABLE measurement_sample ADD COLUMN source_mtime INTEGER")
    for i in range(1, 7):
        cname = f"value_step_{i}"
        if cname not in cols:
            conn.execute(f"ALTER TABLE measurement_sample ADD COLUMN {cname} REAL")

    if _table_exists(conn, "portal_user"):
        cols = _table_columns(conn, "portal_user")
        if "access_level" not in cols:
            conn.execute(
                "ALTER TABLE portal_user ADD COLUMN access_level INTEGER DEFAULT 4"
            )
            conn.execute(
                """
                UPDATE portal_user SET access_level = CASE role
                  WHEN 'admin' THEN 1
                  WHEN 'editor' THEN 3
                  ELSE 4 END
                """
            )
        if "memo" not in cols:
            conn.execute("ALTER TABLE portal_user ADD COLUMN memo TEXT")

    if _table_exists(conn, "portal_user") and _table_exists(conn, "site"):
        if not _table_exists(conn, "portal_user_site"):
            conn.execute(
                """
                CREATE TABLE portal_user_site (
                  user_id INTEGER NOT NULL REFERENCES portal_user(id) ON DELETE CASCADE,
                  site_id INTEGER NOT NULL REFERENCES site(id) ON DELETE CASCADE,
                  PRIMARY KEY (user_id, site_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_portal_user_site_user "
                "ON portal_user_site(user_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_portal_user_site_site "
                "ON portal_user_site(site_id)"
            )

    if _table_exists(conn, "site"):
        try:
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_site_org_site_code_unique ON site (
                  organization_id, site_code
                ) WHERE site_code IS NOT NULL AND TRIM(site_code) != ''
                """
            )
        except sqlite3.OperationalError:
            pass

    if _table_exists(conn, "site") and not _table_exists(conn, "site_sms_config"):
        conn.execute(
            """
            CREATE TABLE site_sms_config (
              site_id          INTEGER PRIMARY KEY REFERENCES site(id) ON DELETE CASCADE,
              enabled          INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
              message_template TEXT,
              time_from        TEXT,
              time_to          TEXT,
              updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
    if _table_exists(conn, "site") and not _table_exists(conn, "site_sms_recipient"):
        conn.execute(
            """
            CREATE TABLE site_sms_recipient (
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
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sms_recipient_site "
            "ON site_sms_recipient(site_id)"
        )

    _ensure_bootstrap_admin(conn)
    _apply_default_admin_password_once(conn)

    if _table_exists(conn, "measurement_sample"):
        try:
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uniq_measurement_sample_ch_obs
                ON measurement_sample(sensor_channel_id, observed_at)
                """
            )
        except sqlite3.OperationalError:
            pass

    conn.commit()


def init_schema(conn: sqlite3.Connection) -> None:
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    conn.executescript(sql)
    migrate_schema(conn)
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', '7')"
    )
    conn.commit()


def seed_if_empty(conn: sqlite3.Connection) -> bool:
    """데이터가 없을 때만 데모 데이터 삽입. True면 시드 수행."""
    n = conn.execute("SELECT COUNT(*) AS c FROM organization").fetchone()["c"]
    if n > 0:
        return False

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO organization(name, code, memo) VALUES (?,?,?)",
        ("한국측량", "HANT", "데모 업체"),
    )
    org_id = cur.lastrowid
    cur.execute(
        """INSERT INTO site(organization_id, name, site_code, address, site_program, memo)
           VALUES (?,?,?,?,?,?)""",
        (org_id, "○○ 터널", "tunnel_a", "경기 ○○시", "AMS 휴먼프로그램", None),
    )
    site1 = cur.lastrowid
    cur.execute(
        """INSERT INTO site(organization_id, name, site_code, address, site_program, memo)
           VALUES (?,?,?,?,?,?)""",
        (org_id, "△△ 교량", "bridge_b", "인천 △△군", "새길 계측 프로그램", "게이트웨이 점검 주기: 일 1회"),
    )
    site2 = cur.lastrowid

    if not cur.execute(
        "SELECT 1 FROM portal_user WHERE username = ?", ("guest",)
    ).fetchone():
        cur.execute(
            """
            INSERT INTO portal_user(
              username, password_hash, display_name, role, access_level, memo)
            VALUES (?,?,?,?,4,?)
            """,
            (
                "guest",
                generate_password_hash("guest123"),
                "게스트 데모",
                "viewer",
                "△△ 교량(site)만 조회·편집 불가 데모",
            ),
        )
        guest_uid = cur.lastrowid
        cur.execute(
            "INSERT INTO portal_user_site(user_id, site_id) VALUES (?,?)",
            (guest_uid, site2),
        )

    cur.executemany(
        "INSERT INTO site_manager(site_id, name, title, phone, sort_order) VALUES (?,?,?,?,?)",
        [
            (site1, "김현장", "소장", "010-0000-0001", 0),
            (site2, "이계측", "담당", "010-0000-0002", 0),
        ],
    )

    cur.execute(
        """INSERT INTO logger_device(
             site_id, name, logger_kind, serial_number, is_active, folder_path, status, last_comm_at)
           VALUES (?,?,?,?,?,?,?, datetime('now', '-5 minutes'))""",
        (
            site1,
            "logger_tunnel_01",
            "manual",
            "1575",
            1,
            r"C:\data\Convertfile\...\1220262005.csv",
            "normal",
        ),
    )
    log1 = cur.lastrowid
    cur.execute(
        """INSERT INTO logger_device(
             site_id, name, logger_kind, serial_number, is_active, folder_path, status, last_comm_at)
           VALUES (?,?,?,?,?,?,?, datetime('now', '-2 hours'))""",
        (
            site2,
            "logger_bridge_gw",
            "ftp",
            "4363",
            1,
            r"C:\data\Convertfile\...\1220268004.csv",
            "delayed",
        ),
    )
    log2 = cur.lastrowid

    cur.executemany(
        """INSERT INTO sensor_channel(
             logger_device_id, channel_index, list_order, label, sensor_code, serial_number,
             sensor_kind, unit, decimal_places, is_active, sms_enabled,
             level1_primary, level1_secondary, level2_primary, level2_secondary,
             level3_primary, level3_secondary, scale_k, scale_b, install_location, memo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                log1,
                0,
                0,
                "변위 CH0",
                "SP1-1",
                None,
                "surface_settlement",
                "mm",
                2,
                1,
                1,
                5.0,
                3.0,
                10.0,
                8.0,
                15.0,
                12.0,
                1.0,
                0.0,
                "터널 상단",
                "데모: 지표침하",
            ),
            (
                log1,
                1,
                1,
                "변위 CH1",
                "SP1-2",
                None,
                "surface_settlement",
                "mm",
                2,
                1,
                0,
                None,
                None,
                None,
                None,
                None,
                None,
                1.0,
                0.0,
                None,
                None,
            ),
            (
                log2,
                0,
                0,
                "경사 CH0",
                "INC-1",
                None,
                "inclinometer",
                "°",
                3,
                1,
                1,
                0.01,
                0.005,
                0.02,
                0.015,
                0.03,
                0.025,
                1.0,
                0.0,
                "교량 교좌",
                "데모: 지중경사",
            ),
        ],
    )
    ch_ids = [
        r["id"]
        for r in cur.execute("SELECT id FROM sensor_channel ORDER BY id").fetchall()
    ]

    for i, ch_id in enumerate(ch_ids):
        cur.execute(
            """INSERT INTO measurement_sample(sensor_channel_id, observed_at, value_real, quality_flag)
               VALUES (?, datetime('now', ?), ?, 'ok')""",
            (ch_id, f"-{i * 10} minutes", 0.12 + i * 0.01),
        )

    cur.executemany(
        """INSERT INTO alert(site_id, logger_device_id, severity, title, body)
           VALUES (?,?,?,?,?)""",
        [
            (
                site2,
                log2,
                "warn",
                "통신 지연",
                "게이트웨이 응답이 2시간 이상 지연되었습니다. (데모)",
            ),
            (
                site1,
                None,
                "info",
                "일일 리포트",
                "자동 리포트가 생성되었습니다. (데모)",
            ),
        ],
    )

    conn.commit()
    return True


def init_database() -> None:
    """스키마 적용 + 빈 DB면 시드."""
    conn = connect()
    try:
        init_schema(conn)
        seed_if_empty(conn)
    finally:
        conn.close()


def create_import_batch(
    conn: sqlite3.Connection,
    logger_device_id: int,
    source_path: str,
    source_mtime: int | None,
    row_count: int | None,
    note: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO import_batch(
          logger_device_id, source_path, source_mtime, row_count, note)
        VALUES (?,?,?,?,?)
        """,
        (logger_device_id, source_path, source_mtime, row_count, note),
    )
    return int(cur.lastrowid)


def update_import_batch_row_count(
    conn: sqlite3.Connection, batch_id: int, row_count: int
) -> None:
    conn.execute(
        "UPDATE import_batch SET row_count = ? WHERE id = ?",
        (row_count, batch_id),
    )


def purge_measurements_by_sensor(
    conn: sqlite3.Connection,
    sensor_channel_id: int,
    time_from: str,
    time_to: str,
    note: str | None = None,
) -> int:
    cur = conn.execute(
        """
        DELETE FROM measurement_sample
        WHERE sensor_channel_id = ?
          AND observed_at >= ? AND observed_at <= ?
        """,
        (sensor_channel_id, time_from, time_to),
    )
    deleted = cur.rowcount if cur.rowcount >= 0 else 0
    conn.execute(
        """
        INSERT INTO measurement_purge_log(
          sensor_channel_id, time_from, time_to, deleted_rows, note)
        VALUES (?,?,?,?,?)
        """,
        (sensor_channel_id, time_from, time_to, deleted, note),
    )
    return deleted


def purge_measurements_by_logger(
    conn: sqlite3.Connection,
    logger_device_id: int,
    time_from: str,
    time_to: str,
    note: str | None = None,
) -> int:
    cur = conn.execute(
        """
        DELETE FROM measurement_sample
        WHERE sensor_channel_id IN (
          SELECT id FROM sensor_channel WHERE logger_device_id = ?
        )
          AND observed_at >= ? AND observed_at <= ?
        """,
        (logger_device_id, time_from, time_to),
    )
    deleted = cur.rowcount if cur.rowcount >= 0 else 0
    conn.execute(
        """
        INSERT INTO measurement_purge_log(
          logger_device_id, time_from, time_to, deleted_rows, note)
        VALUES (?,?,?,?,?)
        """,
        (logger_device_id, time_from, time_to, deleted, note),
    )
    return deleted


def authenticate_user(username: str, password: str) -> dict | None:
    """username + 평문 비밀번호 검증. 성공 시 id, username, access_level, role, display_name."""
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT id, username, password_hash, display_name, role, access_level, is_active
            FROM portal_user WHERE username = ?
            """,
            (username.strip(),),
        ).fetchone()
        if row is None or not row["is_active"]:
            return None
        if not check_password_hash(row["password_hash"], password):
            return None
        return {
            "id": int(row["id"]),
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "access_level": int(row["access_level"]),
        }
    finally:
        conn.close()


def get_allowed_site_ids(user_id: int | None) -> list[int]:
    if user_id is None:
        return []
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT site_id FROM portal_user_site WHERE user_id = ? ORDER BY site_id",
            (user_id,),
        ).fetchall()
        return [int(r["site_id"]) for r in rows]
    finally:
        conn.close()


def user_can_access_site(
    user_id: int | None, access_level: int, site_id: int
) -> bool:
    if user_id is None:
        return False
    if access_level == 1:
        return True
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT 1 FROM portal_user_site
            WHERE user_id = ? AND site_id = ?
            """,
            (user_id, site_id),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def user_can_edit_site(access_level: int) -> bool:
    """게스트(4)는 조회만."""
    return access_level in (1, 3)


def list_sites_for_user_in_organization(
    user_id: int, access_level: int, organization_id: int
) -> list[dict]:
    conn = connect()
    try:
        if access_level == 1:
            rows = conn.execute(
                """
                SELECT s.id, s.name, s.site_code, s.organization_id, o.name AS org_name,
                       s.created_at, s.install_date, s.image_main, s.image_list,
                       (SELECT COUNT(*) FROM logger_device ld WHERE ld.site_id = s.id) AS logger_count
                FROM site s
                JOIN organization o ON o.id = s.organization_id
                WHERE s.organization_id = ?
                ORDER BY o.name, s.name
                """,
                (organization_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        ids = get_allowed_site_ids(user_id)
        if not ids:
            return []
        ph = ",".join("?" * len(ids))
        rows = conn.execute(
            f"""
            SELECT s.id, s.name, s.site_code, s.organization_id, o.name AS org_name,
                   s.created_at, s.install_date, s.image_main, s.image_list,
                   (SELECT COUNT(*) FROM logger_device ld WHERE ld.site_id = s.id) AS logger_count
            FROM site s
            JOIN organization o ON o.id = s.organization_id
            WHERE s.organization_id = ? AND s.id IN ({ph})
            ORDER BY o.name, s.name
            """,
            (organization_id, *ids),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_sites_for_user(user_id: int, access_level: int) -> list[dict]:
    if access_level == 1:
        return list_sites()
    ids = get_allowed_site_ids(user_id)
    if not ids:
        return []
    conn = connect()
    try:
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"""
            SELECT s.id, s.name, s.site_code, s.organization_id, o.name AS org_name,
                   s.created_at,
                   (SELECT COUNT(*) FROM logger_device ld WHERE ld.site_id = s.id) AS logger_count
            FROM site s
            JOIN organization o ON o.id = s.organization_id
            WHERE s.id IN ({placeholders})
            ORDER BY o.name, s.name
            """,
            ids,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_portal_users() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT id, username, display_name, role, access_level, is_active, memo,
                   created_at, updated_at
            FROM portal_user
            ORDER BY username COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_portal_user(user_id: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM portal_user WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_portal_user_site_ids(user_id: int) -> list[int]:
    return get_allowed_site_ids(user_id)


def update_portal_user_fields(
    user_id: int,
    *,
    display_name: str | None = None,
    access_level: int | None = None,
    role: str | None = None,
    memo: str | None = None,
    is_active: int | None = None,
) -> None:
    conn = connect()
    try:
        fields: list[str] = []
        args: list = []
        if display_name is not None:
            fields.append("display_name = ?")
            args.append(display_name)
        if access_level is not None:
            fields.append("access_level = ?")
            args.append(access_level)
        if role is not None:
            fields.append("role = ?")
            args.append(role)
        if memo is not None:
            fields.append("memo = ?")
            args.append(memo)
        if is_active is not None:
            fields.append("is_active = ?")
            args.append(is_active)
        if not fields:
            return
        fields.append("updated_at = datetime('now')")
        args.append(user_id)
        conn.execute(
            f"UPDATE portal_user SET {', '.join(fields)} WHERE id = ?",
            args,
        )
        conn.commit()
    finally:
        conn.close()


def set_portal_user_password(user_id: int, plain_password: str) -> None:
    conn = connect()
    try:
        conn.execute(
            """
            UPDATE portal_user SET password_hash = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (generate_password_hash(plain_password), user_id),
        )
        conn.commit()
    finally:
        conn.close()


def replace_portal_user_sites(user_id: int, site_ids: list[int]) -> None:
    conn = connect()
    try:
        conn.execute("DELETE FROM portal_user_site WHERE user_id = ?", (user_id,))
        for sid in site_ids:
            conn.execute(
                "INSERT INTO portal_user_site(user_id, site_id) VALUES (?,?)",
                (user_id, int(sid)),
            )
        conn.commit()
    finally:
        conn.close()


def create_portal_user(
    username: str,
    plain_password: str,
    *,
    display_name: str | None = None,
    access_level: int = 4,
    role: str = "viewer",
    memo: str | None = None,
) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO portal_user(
              username, password_hash, display_name, role, access_level, memo)
            VALUES (?,?,?,?,?,?)
            """,
            (
                username.strip(),
                generate_password_hash(plain_password),
                display_name,
                role,
                access_level,
                memo,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def delete_portal_user(user_id: int) -> None:
    conn = connect()
    try:
        conn.execute("DELETE FROM portal_user WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def list_organizations() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, name, code FROM organization ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_organizations_with_counts() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT o.id, o.name, o.code, o.memo,
                   (SELECT COUNT(*) FROM site s WHERE s.organization_id = o.id) AS site_count
            FROM organization o
            ORDER BY o.name
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_organization(organization_id: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT id, name, code, memo, created_at FROM organization WHERE id = ?
            """,
            (organization_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def user_can_access_org(user_id: int, access_level: int, organization_id: int) -> bool:
    """관리자(1): 업체 존재 시 허용. 그 외: 할당 현장 중 해당 업체에 속한 현장이 있으면 허용."""
    conn = connect()
    try:
        ex = conn.execute(
            "SELECT 1 FROM organization WHERE id = ?",
            (organization_id,),
        ).fetchone()
        if not ex:
            return False
        if access_level == 1:
            return True
        aids = get_allowed_site_ids(user_id)
        if not aids:
            return False
        ph = ",".join("?" * len(aids))
        row = conn.execute(
            f"""
            SELECT 1 FROM site
            WHERE organization_id = ? AND id IN ({ph})
            LIMIT 1
            """,
            (organization_id, *aids),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def list_organizations_for_user(user_id: int, access_level: int) -> list[dict]:
    """로그인 사용자가 접근 가능한 업체 목록(site_count 은 접근 가능한 현장만 집계)."""
    if access_level == 1:
        return list_organizations_with_counts()
    aids = get_allowed_site_ids(user_id)
    if not aids:
        return []
    conn = connect()
    try:
        ph = ",".join("?" * len(aids))
        rows = conn.execute(
            f"""
            SELECT o.id, o.name, o.code, o.memo,
              (SELECT COUNT(*) FROM site x WHERE x.organization_id = o.id AND x.id IN ({ph})) AS site_count
            FROM organization o
            WHERE o.id IN (SELECT DISTINCT organization_id FROM site WHERE id IN ({ph}))
            ORDER BY o.name COLLATE NOCASE
            """,
            [*aids, *aids],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_organization(
    name: str,
    *,
    code: str | None = None,
    memo: str | None = None,
) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO organization(name, code, memo) VALUES (?,?,?)",
            (name.strip(), code, memo),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def delete_organization(organization_id: int) -> tuple[bool, list[int]]:
    """
    업체 행 삭제. 소속 site·logger·측정행 등은 FK CASCADE 로 정리.
    반환: (조직이 존재해 삭제했으면 True, 삭제 전 site id 목록 — 업로드 미디어 폴더 제거용).
    """
    conn = connect()
    try:
        if not conn.execute(
            "SELECT 1 FROM organization WHERE id = ?",
            (organization_id,),
        ).fetchone():
            return False, []
        site_rows = conn.execute(
            "SELECT id FROM site WHERE organization_id = ?",
            (organization_id,),
        ).fetchall()
        site_ids = [int(r["id"]) for r in site_rows]
        conn.execute("DELETE FROM organization WHERE id = ?", (organization_id,))
        conn.commit()
        return True, site_ids
    finally:
        conn.close()


def list_sites() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT s.id, s.name, s.site_code, s.organization_id, o.name AS org_name,
                   s.created_at,
                   (SELECT COUNT(*) FROM logger_device ld WHERE ld.site_id = s.id) AS logger_count
            FROM site s
            JOIN organization o ON o.id = s.organization_id
            ORDER BY o.name, s.name
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_site_last_sensor_add(
    site_id: int,
    *,
    sensor_code: str | None,
    sensor_kind: str | None,
) -> None:
    conn = connect()
    try:
        conn.execute(
            """
            UPDATE site SET
              last_add_sensor_code = ?,
              last_add_sensor_kind = ?
            WHERE id = ?
            """,
            (sensor_code, sensor_kind, site_id),
        )
        conn.commit()
    finally:
        conn.close()


def next_channel_index(logger_device_id: int) -> int:
    """이 로거에서 아직 쓰이지 않은 가장 작은 channel_index(0부터, CSV 열 인덱스).

    화면에서는 보통 이 값에 +1 한 「칼럼 번호」로 표시한다.
    """
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT channel_index FROM sensor_channel
            WHERE logger_device_id = ?
            """,
            (logger_device_id,),
        ).fetchall()
        used = {int(r["channel_index"]) for r in rows}
        n = 0
        while n in used:
            n += 1
        return n
    finally:
        conn.close()


def get_site(site_id: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT s.*, o.name AS org_name
            FROM site s
            JOIN organization o ON o.id = s.organization_id
            WHERE s.id = ?
            """,
            (site_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_site(
    organization_id: int,
    name: str,
    *,
    site_code: str | None = None,
    install_date: str | None = None,
    image_main: str | None = None,
    image_list: str | None = None,
    address: str | None = None,
    site_program: str | None = None,
    memo: str | None = None,
) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO site(
              organization_id, name, site_code, install_date, image_main, image_list,
              address, site_program, memo)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                organization_id,
                name,
                site_code,
                install_date,
                image_main,
                image_list,
                address,
                site_program,
                memo,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def is_site_code_available(
    organization_id: int,
    site_code_normalized: str,
    *,
    exclude_site_id: int | None = None,
) -> bool:
    """영문 코드는 소문자로 통일되어 저장된다고 가정."""
    conn = connect()
    try:
        q = """
            SELECT 1 FROM site
            WHERE organization_id = ? AND lower(trim(site_code)) = ?
        """
        args: list = [organization_id, site_code_normalized]
        if exclude_site_id is not None:
            q += " AND id != ?"
            args.append(exclude_site_id)
        row = conn.execute(q, args).fetchone()
        return row is None
    finally:
        conn.close()


def update_site_media_paths(
    site_id: int,
    *,
    image_main: str | None = None,
    image_list: str | None = None,
) -> None:
    conn = connect()
    try:
        conn.execute(
            """
            UPDATE site SET image_main = ?, image_list = ? WHERE id = ?
            """,
            (image_main, image_list, site_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_site_fields(
    site_id: int,
    *,
    name: str,
    site_code: str | None,
    install_date: str | None,
    address: str | None,
    site_program: str | None,
    memo: str | None,
) -> None:
    """현장 텍스트 필드 일괄 갱신(None·빈 문자열 필드는 NULL 저장)."""

    def _nz(s: str | None) -> str | None:
        if s is None:
            return None
        t = str(s).strip()
        return t if t else None

    conn = connect()
    try:
        conn.execute(
            """
            UPDATE site SET
              name = ?,
              site_code = ?,
              install_date = ?,
              address = ?,
              site_program = ?,
              memo = ?
            WHERE id = ?
            """,
            (
                name.strip(),
                _nz(site_code),
                _nz(install_date),
                _nz(address),
                _nz(site_program),
                _nz(memo),
                site_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_site_sms_config(site_id: int) -> dict:
    """현장 SMS 설정. 행이 없으면 기본값(dict)."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM site_sms_config WHERE site_id = ?", (site_id,)
        ).fetchone()
        if row:
            return dict(row)
        return {
            "site_id": site_id,
            "enabled": 0,
            "message_template": "",
            "time_from": "00:00:00",
            "time_to": "23:59:59",
        }
    finally:
        conn.close()


def upsert_site_sms_config(
    site_id: int,
    *,
    enabled: int,
    message_template: str,
    time_from: str,
    time_to: str,
) -> None:
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO site_sms_config(
              site_id, enabled, message_template, time_from, time_to, updated_at)
            VALUES (?,?,?,?,?, datetime('now'))
            ON CONFLICT(site_id) DO UPDATE SET
              enabled = excluded.enabled,
              message_template = excluded.message_template,
              time_from = excluded.time_from,
              time_to = excluded.time_to,
              updated_at = datetime('now')
            """,
            (
                site_id,
                1 if enabled else 0,
                message_template or "",
                time_from or "00:00:00",
                time_to or "23:59:59",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_site_sms_recipients(site_id: int) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM site_sms_recipient
            WHERE site_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (site_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_site_sms_recipient(site_id: int, recipient_id: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT * FROM site_sms_recipient
            WHERE site_id = ? AND id = ?
            """,
            (site_id, recipient_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_site_sms_recipient(
    site_id: int,
    *,
    recipient_id: int | None,
    send_enabled: int,
    name: str,
    phone: str,
    job_title: str,
    department: str,
    info: str,
) -> int:
    """삽입 또는 갱신. 반환값: recipient id."""
    conn = connect()
    try:
        if recipient_id is not None:
            cur = conn.execute(
                """
                UPDATE site_sms_recipient SET
                  send_enabled = ?, name = ?, phone = ?, job_title = ?,
                  department = ?, info = ?
                WHERE site_id = ? AND id = ?
                """,
                (
                    send_enabled,
                    name,
                    phone,
                    job_title,
                    department,
                    info,
                    site_id,
                    recipient_id,
                ),
            )
            if cur.rowcount == 0:
                raise ValueError("recipient_not_found")
            conn.commit()
            return int(recipient_id)
        mx = conn.execute(
            """
            SELECT COALESCE(MAX(sort_order), -1) + 1 AS n
            FROM site_sms_recipient WHERE site_id = ?
            """,
            (site_id,),
        ).fetchone()[0]
        cur = conn.execute(
            """
            INSERT INTO site_sms_recipient(
              site_id, send_enabled, name, phone, job_title, department, info, sort_order)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                site_id,
                send_enabled,
                name,
                phone,
                job_title,
                department,
                info,
                int(mx),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def delete_site_sms_recipient(site_id: int, recipient_id: int) -> bool:
    conn = connect()
    try:
        cur = conn.execute(
            "DELETE FROM site_sms_recipient WHERE site_id = ? AND id = ?",
            (site_id, recipient_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_site(site_id: int) -> None:
    conn = connect()
    try:
        conn.execute("DELETE FROM site WHERE id = ?", (site_id,))
        conn.commit()
    finally:
        conn.close()


def list_loggers(site_id: int) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT ld.*,
                   (SELECT COUNT(*) FROM sensor_channel sc WHERE sc.logger_device_id = ld.id) AS ch_count
            FROM logger_device ld
            WHERE ld.site_id = ?
            ORDER BY ld.name
            """,
            (site_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _site_logger_name_base(site_row: dict) -> str:
    """app._logger_name_base_from_site 와 동일 규칙 (순환 import 방지용)."""
    code = (site_row.get("site_code") or "").strip().lower()
    code = re.sub(r"[^a-z0-9_]+", "_", code).strip("_")
    if code:
        return code
    return f"site{int(site_row['id'])}"


def ensure_default_logger_for_site(site_id: int) -> int | None:
    """
    현장 코드 기준 기본 로거 `{code}_0` 이 없으면 생성한다.
    레거시 데이터수집·자동 DB 업로드가 최소 한 행으로 목록을 맞추도록 쓴다.
    """
    row = get_site(site_id)
    if not row:
        return None
    site_d = dict(row)
    default_name = f"{_site_logger_name_base(site_d)}_0"
    conn = connect()
    try:
        ex = conn.execute(
            "SELECT id FROM logger_device WHERE site_id = ? AND name = ?",
            (site_id, default_name),
        ).fetchone()
        if ex:
            return int(ex["id"])
    finally:
        conn.close()
    try:
        return create_logger(site_id, default_name)
    except sqlite3.IntegrityError:
        conn = connect()
        try:
            ex = conn.execute(
                "SELECT id FROM logger_device WHERE site_id = ? AND name = ?",
                (site_id, default_name),
            ).fetchone()
            return int(ex["id"]) if ex else None
        finally:
            conn.close()


def latest_observed_at_by_channel(sensor_channel_ids: list[int]) -> dict[int, str | None]:
    """센서 채널별 measurement_sample 에서 가장 마지막 observed_at."""
    ids = sorted({int(i) for i in sensor_channel_ids})
    if not ids:
        return {}
    conn = connect()
    try:
        ph = ",".join("?" * len(ids))
        rows = conn.execute(
            f"""
            SELECT sensor_channel_id, MAX(observed_at) AS mx
            FROM measurement_sample
            WHERE sensor_channel_id IN ({ph})
            GROUP BY sensor_channel_id
            """,
            ids,
        ).fetchall()
        out: dict[int, str | None] = {i: None for i in ids}
        for r in rows:
            if r["sensor_channel_id"] is not None:
                out[int(r["sensor_channel_id"])] = r["mx"]
        return out
    finally:
        conn.close()


def get_logger(logger_id: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT ld.*, s.id AS site_id, s.name AS site_name, s.site_code,
                   o.name AS org_name
            FROM logger_device ld
            JOIN site s ON s.id = ld.site_id
            JOIN organization o ON o.id = s.organization_id
            WHERE ld.id = ?
            """,
            (logger_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_logger(
    site_id: int,
    name: str,
    *,
    logger_kind: str = "manual",
    serial_number: str | None = None,
    folder_path: str | None = None,
) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO logger_device(
              site_id, name, logger_kind, serial_number, folder_path, status, is_active)
            VALUES (?,?,?,?,?,'normal',1)
            """,
            (site_id, name, logger_kind, serial_number, folder_path),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_logger(
    logger_id: int,
    *,
    folder_path: str | None = None,
    time_column_index: int | None = None,
    first_data_column_index: int | None = None,
    logger_kind: str | None = None,
    serial_number: str | None = None,
    is_active: int | None = None,
    memo: str | None = None,
    last_comm_at: str | None = None,
    last_ingest_at: str | None = None,
    last_ingest_bytes: int | None = None,
) -> None:
    conn = connect()
    try:
        fields: list[str] = []
        args: list = []
        if folder_path is not None:
            fields.append("folder_path = ?")
            args.append(folder_path)
        if time_column_index is not None:
            fields.append("time_column_index = ?")
            args.append(time_column_index)
        if first_data_column_index is not None:
            fields.append("first_data_column_index = ?")
            args.append(first_data_column_index)
        if logger_kind is not None:
            fields.append("logger_kind = ?")
            args.append(logger_kind)
        if serial_number is not None:
            fields.append("serial_number = ?")
            args.append(serial_number)
        if is_active is not None:
            fields.append("is_active = ?")
            args.append(is_active)
        if memo is not None:
            fields.append("memo = ?")
            args.append(memo)
        if last_comm_at is not None:
            fields.append("last_comm_at = ?")
            args.append(last_comm_at)
        if last_ingest_at is not None:
            fields.append("last_ingest_at = ?")
            args.append(last_ingest_at)
        if last_ingest_bytes is not None:
            fields.append("last_ingest_bytes = ?")
            args.append(last_ingest_bytes)
        if not fields:
            return
        args.append(logger_id)
        conn.execute(
            f"UPDATE logger_device SET {', '.join(fields)} WHERE id = ?",
            args,
        )
        conn.commit()
    finally:
        conn.close()


def delete_logger(logger_id: int, *, site_id: int) -> bool:
    """현장에 속한 로거만 삭제. 센서·측정행 등은 FK CASCADE 로 정리된다."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id FROM logger_device WHERE id = ? AND site_id = ?",
            (logger_id, site_id),
        ).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM logger_device WHERE id = ?", (logger_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def list_measurement_groups(site_id: int) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT id, name, sort_order, parent_id
            FROM measurement_group
            WHERE site_id = ?
            ORDER BY sort_order, name
            """,
            (site_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def ensure_measurement_group_leaf(
    site_id: int,
    major_name: str,
    minor_name: str,
) -> int:
    """
    대분류(parent_id NULL) · 소분류( parent = 대분류 ) 노드를 이름으로 찾거나 생성 후 소분류 id 반환.
    센서 추가 시 sensor_kind 의 kind_group / label_ko 로 트리에 자동 편입할 때 사용.
    """
    major_name = (major_name or "").strip() or "기타"
    minor_name = (minor_name or "").strip() or "기타"
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT id FROM measurement_group
            WHERE site_id = ? AND parent_id IS NULL AND name = ?
            """,
            (site_id, major_name),
        ).fetchone()
        if row:
            major_id = int(row["id"])
        else:
            mx = conn.execute(
                """
                SELECT COALESCE(MAX(sort_order), -1) AS m FROM measurement_group
                WHERE site_id = ? AND parent_id IS NULL
                """,
                (site_id,),
            ).fetchone()
            sort_m = int(mx["m"]) + 1
            cur = conn.execute(
                """
                INSERT INTO measurement_group(site_id, parent_id, name, sort_order)
                VALUES (?, NULL, ?, ?)
                """,
                (site_id, major_name, sort_m),
            )
            major_id = int(cur.lastrowid)

        row2 = conn.execute(
            """
            SELECT id FROM measurement_group
            WHERE site_id = ? AND parent_id = ? AND name = ?
            """,
            (site_id, major_id, minor_name),
        ).fetchone()
        if row2:
            leaf_id = int(row2["id"])
        else:
            mx2 = conn.execute(
                """
                SELECT COALESCE(MAX(sort_order), -1) AS m FROM measurement_group
                WHERE site_id = ? AND parent_id = ?
                """,
                (site_id, major_id),
            ).fetchone()
            sort_c = int(mx2["m"]) + 1
            cur2 = conn.execute(
                """
                INSERT INTO measurement_group(site_id, parent_id, name, sort_order)
                VALUES (?, ?, ?, ?)
                """,
                (site_id, major_id, minor_name, sort_c),
            )
            leaf_id = int(cur2.lastrowid)
        conn.commit()
        return leaf_id
    finally:
        conn.close()


def create_measurement_group(site_id: int, name: str, parent_id: int | None = None) -> int:
    """현장 카테고리 노드 추가(대분류/소분류)."""
    nm = (name or "").strip()
    if not nm:
        raise ValueError("empty_name")
    conn = connect()
    try:
        if parent_id is None:
            dup = conn.execute(
                """
                SELECT id FROM measurement_group
                WHERE site_id = ? AND parent_id IS NULL AND name = ?
                """,
                (site_id, nm),
            ).fetchone()
            if dup:
                return int(dup["id"])
            mx = conn.execute(
                """
                SELECT COALESCE(MAX(sort_order), -1) AS m
                FROM measurement_group
                WHERE site_id = ? AND parent_id IS NULL
                """,
                (site_id,),
            ).fetchone()
            sort_order = int(mx["m"]) + 1
            cur = conn.execute(
                """
                INSERT INTO measurement_group(site_id, parent_id, name, sort_order)
                VALUES (?, NULL, ?, ?)
                """,
                (site_id, nm, sort_order),
            )
        else:
            parent = conn.execute(
                """
                SELECT id FROM measurement_group
                WHERE id = ? AND site_id = ? AND parent_id IS NULL
                """,
                (parent_id, site_id),
            ).fetchone()
            if not parent:
                raise ValueError("parent_not_found")
            dup = conn.execute(
                """
                SELECT id FROM measurement_group
                WHERE site_id = ? AND parent_id = ? AND name = ?
                """,
                (site_id, parent_id, nm),
            ).fetchone()
            if dup:
                return int(dup["id"])
            mx = conn.execute(
                """
                SELECT COALESCE(MAX(sort_order), -1) AS m
                FROM measurement_group
                WHERE site_id = ? AND parent_id = ?
                """,
                (site_id, parent_id),
            ).fetchone()
            sort_order = int(mx["m"]) + 1
            cur = conn.execute(
                """
                INSERT INTO measurement_group(site_id, parent_id, name, sort_order)
                VALUES (?, ?, ?, ?)
                """,
                (site_id, parent_id, nm, sort_order),
            )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def set_sensor_channels_measurement_group(
    site_id: int, channel_ids: list[int], measurement_group_id: int | None
) -> int:
    """현장 센서들의 카테고리 소속을 일괄 변경. 반환값: 실제 변경 건수."""
    if not channel_ids:
        return 0
    ids = [int(x) for x in channel_ids]
    conn = connect()
    try:
        if measurement_group_id is not None:
            row = conn.execute(
                """
                SELECT id FROM measurement_group
                WHERE id = ? AND site_id = ?
                """,
                (int(measurement_group_id), site_id),
            ).fetchone()
            if not row:
                raise ValueError("group_not_found")
        q_marks = ",".join("?" for _ in ids)
        params: list = [measurement_group_id]
        params.extend(ids)
        params.append(site_id)
        cur = conn.execute(
            f"""
            UPDATE sensor_channel
            SET measurement_group_id = ?
            WHERE id IN ({q_marks})
              AND logger_device_id IN (
                SELECT id FROM logger_device WHERE site_id = ?
              )
            """,
            tuple(params),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def rename_measurement_group(site_id: int, group_id: int, new_name: str) -> None:
    """카테고리(대/소분류) 이름 변경."""
    nm = (new_name or "").strip()
    if not nm:
        raise ValueError("empty_name")
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT id, parent_id
            FROM measurement_group
            WHERE id = ? AND site_id = ?
            """,
            (group_id, site_id),
        ).fetchone()
        if not row:
            raise ValueError("group_not_found")
        pid = row["parent_id"]
        if pid is None:
            dup = conn.execute(
                """
                SELECT id FROM measurement_group
                WHERE site_id = ? AND parent_id IS NULL AND name = ? AND id <> ?
                """,
                (site_id, nm, group_id),
            ).fetchone()
        else:
            dup = conn.execute(
                """
                SELECT id FROM measurement_group
                WHERE site_id = ? AND parent_id = ? AND name = ? AND id <> ?
                """,
                (site_id, int(pid), nm, group_id),
            ).fetchone()
        if dup:
            raise ValueError("duplicate_name")
        conn.execute(
            "UPDATE measurement_group SET name = ? WHERE id = ?",
            (nm, group_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_measurement_group(site_id: int, group_id: int) -> None:
    """카테고리 삭제(소분류/대분류, 하위는 CASCADE)."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id FROM measurement_group WHERE id = ? AND site_id = ?",
            (group_id, site_id),
        ).fetchone()
        if not row:
            raise ValueError("group_not_found")
        conn.execute("DELETE FROM measurement_group WHERE id = ?", (group_id,))
        conn.commit()
    finally:
        conn.close()


def move_measurement_group(site_id: int, group_id: int, direction: str) -> None:
    """같은 부모 내에서 sort_order 기준 위/아래 이동."""
    if direction not in ("up", "down"):
        raise ValueError("invalid_direction")
    conn = connect()
    try:
        cur = conn.execute(
            """
            SELECT id, parent_id, sort_order
            FROM measurement_group
            WHERE id = ? AND site_id = ?
            """,
            (group_id, site_id),
        ).fetchone()
        if not cur:
            raise ValueError("group_not_found")
        pid = cur["parent_id"]
        my_sort = int(cur["sort_order"] or 0)
        if pid is None:
            sibs = conn.execute(
                """
                SELECT id, sort_order FROM measurement_group
                WHERE site_id = ? AND parent_id IS NULL
                ORDER BY sort_order ASC, id ASC
                """,
                (site_id,),
            ).fetchall()
        else:
            sibs = conn.execute(
                """
                SELECT id, sort_order FROM measurement_group
                WHERE site_id = ? AND parent_id = ?
                ORDER BY sort_order ASC, id ASC
                """,
                (site_id, int(pid)),
            ).fetchall()
        ids = [int(r["id"]) for r in sibs]
        if group_id not in ids:
            raise ValueError("group_not_found")
        idx = ids.index(group_id)
        if direction == "up":
            if idx == 0:
                return
            target_id = ids[idx - 1]
        else:
            if idx >= len(ids) - 1:
                return
            target_id = ids[idx + 1]
        other = next((r for r in sibs if int(r["id"]) == target_id), None)
        if other is None:
            return
        other_sort = int(other["sort_order"] or 0)
        conn.execute(
            "UPDATE measurement_group SET sort_order = ? WHERE id = ?",
            (other_sort, group_id),
        )
        conn.execute(
            "UPDATE measurement_group SET sort_order = ? WHERE id = ?",
            (my_sort, target_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_sensor_channels_for_site(site_id: int) -> list[dict]:
    """현장 소속 모든 센서(로거·카테고리 연동). 워크스페이스 좌측 트리용."""
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT sc.id, sc.label, sc.unit, sc.measurement_group_id, sc.list_order,
                   sc.channel_index, sc.is_active, sc.sensor_code, sc.sensor_kind,
                   sc.decimal_places,
                   ld.id AS logger_device_id, ld.name AS logger_name, ld.status AS logger_status
            FROM sensor_channel sc
            JOIN logger_device ld ON ld.id = sc.logger_device_id
            WHERE ld.site_id = ?
            ORDER BY sc.channel_index, ld.name COLLATE NOCASE, sc.id
            """,
            (site_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def site_measurement_workspace_tree(site_id: int) -> dict:
    """
    measurement_group 트리 + 그룹에 매핑된 센서(Convert Pro 쪽 ‘카테고리·측점’ 개념과 동일하게 DB 상으로만 반영).
    반환: { roots: [...], unassigned_channels: [...] }
    각 루트/자식 노드: { group, children, channels }
    """
    groups = list_measurement_groups(site_id)
    channels = list_sensor_channels_for_site(site_id)
    by_gid: dict[int, dict] = {}
    for g in groups:
        by_gid[g["id"]] = {
            "group": dict(g),
            "children": [],
            "channels": [],
        }

    roots: list[dict] = []
    for g in sorted(groups, key=lambda x: (x.get("sort_order") or 0, x.get("name") or "")):
        gid = int(g["id"])
        node = by_gid[gid]
        pid = g.get("parent_id")
        if pid and int(pid) in by_gid:
            by_gid[int(pid)]["children"].append(node)
        else:
            roots.append(node)

    def _sort_ch(n: dict) -> None:
        n["children"].sort(
            key=lambda x: (
                x["group"].get("sort_order") or 0,
                x["group"].get("name") or "",
            )
        )
        for c in n["children"]:
            _sort_ch(c)

    unassigned: list[dict] = []
    for ch in channels:
        mg_id = ch.get("measurement_group_id")
        if mg_id is not None and int(mg_id) in by_gid:
            by_gid[int(mg_id)]["channels"].append(dict(ch))
        else:
            unassigned.append(dict(ch))

    def _sort_channels_in_node(n: dict) -> None:
        n["channels"].sort(
            key=lambda x: (int(x.get("channel_index") or 0), int(x.get("id") or 0))
        )
        for c in n["children"]:
            _sort_channels_in_node(c)

    roots.sort(key=lambda x: (x["group"].get("sort_order") or 0, x["group"].get("name") or ""))
    for r in roots:
        _sort_ch(r)
        _sort_channels_in_node(r)
    unassigned.sort(key=lambda x: (int(x.get("channel_index") or 0), int(x.get("id") or 0)))

    return {"roots": roots, "unassigned_channels": unassigned}


def list_sensor_channels(logger_id: int) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT sc.*,
                   mg.name AS group_name
            FROM sensor_channel sc
            LEFT JOIN measurement_group mg ON mg.id = sc.measurement_group_id
            WHERE sc.logger_device_id = ?
            ORDER BY sc.channel_index, sc.id
            """,
            (logger_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_sensor_channel(channel_id: int) -> dict | None:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT sc.*, ld.name AS logger_name, ld.id AS logger_device_id,
                   s.id AS site_id, s.name AS site_name, s.site_code,
                   o.name AS org_name, mg.name AS group_name
            FROM sensor_channel sc
            JOIN logger_device ld ON ld.id = sc.logger_device_id
            JOIN site s ON s.id = ld.site_id
            JOIN organization o ON o.id = s.organization_id
            LEFT JOIN measurement_group mg ON mg.id = sc.measurement_group_id
            WHERE sc.id = ?
            """,
            (channel_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_sensor_channel(
    logger_device_id: int,
    channel_index: int,
    label: str,
    *,
    sensor_code: str | None = None,
    list_order: int | None = None,
    sensor_kind: str | None = None,
    unit: str | None = None,
    scale_k: float = 1.0,
    scale_b: float = 0.0,
    measurement_group_id: int | None = None,
    decimal_places: int = 2,
    is_active: int = 0,
) -> int:
    conn = connect()
    try:
        lo = list_order if list_order is not None else channel_index
        code_db = _normalize_sensor_code(
            sensor_code if sensor_code is not None else label
        )
        lg = conn.execute(
            "SELECT site_id FROM logger_device WHERE id = ?",
            (logger_device_id,),
        ).fetchone()
        if not lg:
            raise ValueError("logger_not_found")
        site_id = int(lg["site_id"])
        if code_db and _site_sensor_code_taken_conn(
            conn, site_id, code_db, exclude_channel_id=None
        ):
            raise SensorCodeDuplicateError()
        cur = conn.execute(
            """
            INSERT INTO sensor_channel(
              logger_device_id, measurement_group_id, channel_index, list_order,
              label, sensor_code, sensor_kind, unit, decimal_places, is_active,
              scale_k, scale_b)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                logger_device_id,
                measurement_group_id,
                channel_index,
                lo,
                label,
                code_db,
                sensor_kind,
                unit,
                decimal_places,
                1 if int(is_active) else 0,
                scale_k,
                scale_b,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_sensor_channel_index_only(
    channel_id: int,
    logger_device_id: int,
    channel_index: int,
) -> None:
    """칼럼(값 열) 번호만 갱신. list_order 는 channel_index 에 맞춤."""
    if channel_index < 0:
        raise ValueError("channel_index_negative")
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT id FROM sensor_channel
            WHERE id = ? AND logger_device_id = ?
            """,
            (channel_id, logger_device_id),
        ).fetchone()
        if not row:
            raise ValueError("channel_not_found_or_logger_mismatch")
        conn.execute(
            """
            UPDATE sensor_channel SET channel_index = ?, list_order = ?
            WHERE id = ?
            """,
            (channel_index, channel_index, channel_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_sensor_channel_index_and_activate(
    channel_id: int,
    logger_device_id: int,
    channel_index: int,
) -> None:
    """CSV 값 열 인덱스(0부터)를 저장하고 적재·표시 대상으로 켠다(is_active=1)."""
    if channel_index < 0:
        raise ValueError("channel_index_negative")
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT id FROM sensor_channel
            WHERE id = ? AND logger_device_id = ?
            """,
            (channel_id, logger_device_id),
        ).fetchone()
        if not row:
            raise ValueError("channel_not_found_or_logger_mismatch")
        conn.execute(
            """
            UPDATE sensor_channel
            SET channel_index = ?, list_order = ?, is_active = 1
            WHERE id = ?
            """,
            (channel_index, channel_index, channel_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_sensor_channel_management_levels(channel_id: int, levels: dict[str, float]) -> None:
    """관리기준 1~3차 주·보조만 갱신."""
    keys = (
        "level1_primary",
        "level1_secondary",
        "level2_primary",
        "level2_secondary",
        "level3_primary",
        "level3_secondary",
    )
    for k in keys:
        if k not in levels:
            raise ValueError(f"missing_level_key:{k}")
    conn = connect()
    try:
        conn.execute(
            """
            UPDATE sensor_channel SET
              level1_primary = ?, level1_secondary = ?,
              level2_primary = ?, level2_secondary = ?,
              level3_primary = ?, level3_secondary = ?
            WHERE id = ?
            """,
            (
                levels["level1_primary"],
                levels["level1_secondary"],
                levels["level2_primary"],
                levels["level2_secondary"],
                levels["level3_primary"],
                levels["level3_secondary"],
                channel_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_sensor_channel_chart_axes(
    channel_id: int,
    chart_y_min: float | None,
    chart_y_max: float | None,
) -> None:
    """차트 Y축 최소·최대만 갱신."""
    conn = connect()
    try:
        conn.execute(
            """
            UPDATE sensor_channel SET chart_y_min = ?, chart_y_max = ?
            WHERE id = ?
            """,
            (chart_y_min, chart_y_max, channel_id),
        )
        conn.commit()
    finally:
        conn.close()


def apply_channel_template_defaults(channel_id: int, tpl: dict) -> None:
    """센서종류 기본값(단위·분해능·스케일·관리기준·차트·계산식)을 채널 한 건에 반영."""
    conn = connect()
    try:
        conn.execute(
            """
            UPDATE sensor_channel SET
              unit = ?, decimal_places = ?,
              scale_k = ?, scale_b = ?,
              level1_primary = ?, level1_secondary = ?,
              level2_primary = ?, level2_secondary = ?,
              level3_primary = ?, level3_secondary = ?,
              chart_y_min = ?, chart_y_max = ?,
              pipe_depth_m = ?,
              gauge_factor = ?,
              sensor_length_mm = ?,
              calc_formula_1 = ?, calc_formula_2 = ?, calc_formula_3 = ?,
              calc_formula_4 = ?, calc_formula_5 = ?, calc_formula_6 = ?
            WHERE id = ?
            """,
            (
                tpl.get("unit"),
                int(tpl.get("decimal_places") or 2),
                float(tpl["scale_k"] if tpl.get("scale_k") is not None else 1.0),
                float(tpl["scale_b"] if tpl.get("scale_b") is not None else 0.0),
                tpl.get("level1_primary"),
                tpl.get("level1_secondary"),
                tpl.get("level2_primary"),
                tpl.get("level2_secondary"),
                tpl.get("level3_primary"),
                tpl.get("level3_secondary"),
                tpl.get("chart_y_min"),
                tpl.get("chart_y_max"),
                tpl.get("pipe_depth_m"),
                tpl.get("gauge_factor"),
                tpl.get("sensor_length_mm"),
                tpl.get("calc_formula_1"),
                tpl.get("calc_formula_2"),
                tpl.get("calc_formula_3"),
                tpl.get("calc_formula_4"),
                tpl.get("calc_formula_5"),
                tpl.get("calc_formula_6"),
                channel_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_sensor_channel_calc_formula_1(
    channel_id: int,
    calc_formula_1: str | None,
) -> None:
    """1번 계산식만 갱신 (균열 등 기본값 주입용)."""
    conn = connect()
    try:
        conn.execute(
            "UPDATE sensor_channel SET calc_formula_1 = ? WHERE id = ?",
            (calc_formula_1, channel_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_sensor_channel_row(
    channel_id: int,
    *,
    label: str,
    channel_index: int,
    list_order: int,
    measurement_group_id: int | None,
    sensor_code: str | None,
    serial_number: str | None,
    sensor_kind: str | None,
    unit: str | None,
    decimal_places: int,
    is_active: int,
    sms_enabled: int,
    level1_primary: float | None,
    level1_secondary: float | None,
    level2_primary: float | None,
    level2_secondary: float | None,
    level3_primary: float | None,
    level3_secondary: float | None,
    install_location: str | None,
    install_date: str | None,
    memo: str | None,
    chart_y_min: float | None,
    chart_y_max: float | None,
    linked_sensor_codes: str | None,
    pipe_depth_m: float | None,
    gauge_factor: float | None,
    sensor_length_mm: float | None,
    calc_formula_1: str | None,
    calc_formula_2: str | None,
    calc_formula_3: str | None,
    calc_formula_4: str | None,
    calc_formula_5: str | None,
    calc_formula_6: str | None,
    scale_k: float,
    scale_b: float,
) -> None:
    conn = connect()
    try:
        sc_norm = _normalize_sensor_code(sensor_code)
        loc = conn.execute(
            """
            SELECT ld.site_id FROM sensor_channel sc
            INNER JOIN logger_device ld ON ld.id = sc.logger_device_id
            WHERE sc.id = ?
            """,
            (channel_id,),
        ).fetchone()
        if not loc:
            raise ValueError("channel_not_found")
        site_id = int(loc["site_id"])
        if sc_norm and _site_sensor_code_taken_conn(
            conn, site_id, sc_norm, exclude_channel_id=channel_id
        ):
            raise SensorCodeDuplicateError()
        conn.execute(
            """
            UPDATE sensor_channel SET
              label = ?, channel_index = ?, list_order = ?,
              measurement_group_id = ?,
              sensor_code = ?, serial_number = ?, sensor_kind = ?, unit = ?, decimal_places = ?,
              is_active = ?, sms_enabled = ?,
              level1_primary = ?, level1_secondary = ?,
              level2_primary = ?, level2_secondary = ?,
              level3_primary = ?, level3_secondary = ?,
              install_location = ?, install_date = ?, memo = ?,
              chart_y_min = ?, chart_y_max = ?, linked_sensor_codes = ?,
              pipe_depth_m = ?,
              gauge_factor = ?,
              sensor_length_mm = ?,
              calc_formula_1 = ?, calc_formula_2 = ?, calc_formula_3 = ?,
              calc_formula_4 = ?, calc_formula_5 = ?, calc_formula_6 = ?,
              scale_k = ?, scale_b = ?
            WHERE id = ?
            """,
            (
                label,
                channel_index,
                list_order,
                measurement_group_id,
                sc_norm,
                serial_number,
                sensor_kind,
                unit,
                decimal_places,
                is_active,
                sms_enabled,
                level1_primary,
                level1_secondary,
                level2_primary,
                level2_secondary,
                level3_primary,
                level3_secondary,
                install_location,
                install_date,
                memo,
                chart_y_min,
                chart_y_max,
                linked_sensor_codes,
                pipe_depth_m,
                gauge_factor,
                sensor_length_mm,
                calc_formula_1,
                calc_formula_2,
                calc_formula_3,
                calc_formula_4,
                calc_formula_5,
                calc_formula_6,
                scale_k,
                scale_b,
                channel_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def delete_sensor_channel(channel_id: int, *, logger_device_id: int) -> bool:
    conn = connect()
    try:
        cur = conn.execute(
            "DELETE FROM sensor_channel WHERE id = ? AND logger_device_id = ?",
            (channel_id, logger_device_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_sensor_channel_list_order(
    channel_id: int, list_order: int, *, logger_device_id: int
) -> bool:
    conn = connect()
    try:
        cur = conn.execute(
            """
            UPDATE sensor_channel SET list_order = ?
            WHERE id = ? AND logger_device_id = ?
            """,
            (list_order, channel_id, logger_device_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_measurement_series(
    sensor_channel_id: int,
    time_from: str | None = None,
    time_to: str | None = None,
    limit: int = 5000,
) -> list[dict]:
    limit = max(1, min(int(limit), 50_000))
    conn = connect()
    try:
        q = [
            "SELECT observed_at, value_real, value_raw, quality_flag, import_batch_id,",
            "value_step_1, value_step_2, value_step_3, value_step_4, value_step_5, value_step_6",
            "FROM measurement_sample WHERE sensor_channel_id = ?",
        ]
        args: list = [sensor_channel_id]
        if time_from:
            q.append("AND observed_at >= ?")
            args.append(time_from)
        if time_to:
            q.append("AND observed_at <= ?")
            args.append(time_to)
        q.append("ORDER BY observed_at ASC LIMIT ?")
        args.append(limit)
        rows = conn.execute(" ".join(q), args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_dashboard_stats(
    user_id: int | None = None,
    access_level: int | None = None,
) -> dict:
    conn = connect()
    try:
        restricted = (
            user_id is not None
            and access_level is not None
            and access_level != 1
        )
        allowed: list[int] | None = None
        if restricted:
            allowed = get_allowed_site_ids(user_id)
            allowed_set = set(allowed)

        orgs = conn.execute("SELECT COUNT(*) AS c FROM organization").fetchone()["c"]
        sites = conn.execute("SELECT COUNT(*) AS c FROM site").fetchone()["c"]
        loggers = conn.execute("SELECT COUNT(*) AS c FROM logger_device").fetchone()["c"]
        channels = conn.execute("SELECT COUNT(*) AS c FROM sensor_channel").fetchone()["c"]
        samples = conn.execute("SELECT COUNT(*) AS c FROM measurement_sample").fetchone()["c"]
        issue = conn.execute(
            """SELECT COUNT(*) AS c FROM logger_device
               WHERE status IN ('delayed', 'unconverted', 'offline')"""
        ).fetchone()["c"]

        if restricted and not allowed:
            site_summary: list[dict] = []
            sites = loggers = channels = samples = issue = 0
        elif restricted and allowed:
            allowed_set = set(allowed)
            ph = ",".join("?" * len(allowed))
            sites = len(allowed_set)
            loggers = conn.execute(
                f"SELECT COUNT(*) AS c FROM logger_device WHERE site_id IN ({ph})",
                allowed,
            ).fetchone()["c"]
            channels = conn.execute(
                f"""SELECT COUNT(*) AS c FROM sensor_channel sc
                    JOIN logger_device ld ON ld.id = sc.logger_device_id
                    WHERE ld.site_id IN ({ph})""",
                allowed,
            ).fetchone()["c"]
            samples = conn.execute(
                f"""SELECT COUNT(*) AS c FROM measurement_sample ms
                    JOIN sensor_channel sc ON sc.id = ms.sensor_channel_id
                    JOIN logger_device ld ON ld.id = sc.logger_device_id
                    WHERE ld.site_id IN ({ph})""",
                allowed,
            ).fetchone()["c"]
            issue = conn.execute(
                f"""SELECT COUNT(*) AS c FROM logger_device
                    WHERE status IN ('delayed', 'unconverted', 'offline')
                    AND site_id IN ({ph})""",
                allowed,
            ).fetchone()["c"]
            rows = conn.execute(
                f"""SELECT s.id AS site_id, s.name AS site_name, s.site_code AS site_code, o.name AS org_name,
                           ld.status, ld.name AS logger_name, ld.logger_kind, ld.serial_number,
                           (SELECT COUNT(*) FROM sensor_channel sc WHERE sc.logger_device_id = ld.id) AS ch_count
                    FROM logger_device ld
                    JOIN site s ON s.id = ld.site_id
                    JOIN organization o ON o.id = s.organization_id
                    WHERE s.id IN ({ph})
                    ORDER BY ld.status != 'normal', s.name
                    LIMIT 12""",
                allowed,
            ).fetchall()
            site_summary = [dict(r) for r in rows]
        else:
            rows = conn.execute(
                """SELECT s.id AS site_id, s.name AS site_name, s.site_code AS site_code, o.name AS org_name,
                          ld.status, ld.name AS logger_name, ld.logger_kind, ld.serial_number,
                          (SELECT COUNT(*) FROM sensor_channel sc WHERE sc.logger_device_id = ld.id) AS ch_count
                   FROM logger_device ld
                   JOIN site s ON s.id = ld.site_id
                   JOIN organization o ON o.id = s.organization_id
                   ORDER BY ld.status != 'normal', s.name
                   LIMIT 12"""
            ).fetchall()
            site_summary = [dict(r) for r in rows]

        alerts = conn.execute(
            """SELECT severity, title, body, created_at,
                      (SELECT name FROM site WHERE id = alert.site_id) AS site_name
               FROM alert
               ORDER BY created_at DESC
               LIMIT 8"""
        ).fetchall()
        alert_list = [dict(r) for r in alerts]

        return {
            "counts": {
                "organizations": orgs,
                "sites": sites,
                "loggers": loggers,
                "channels": channels,
                "samples": samples,
                "issue_loggers": issue,
            },
            "site_summary": site_summary,
            "alerts": alert_list,
            "db_path": str(get_db_path()),
        }
    finally:
        conn.close()
