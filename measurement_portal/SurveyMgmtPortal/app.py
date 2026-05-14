"""
================================================================================
계측관리 통합시스템
================================================================================
현장·업체·로거·센서를 통합 관리하는 독립 웹 포털.
Convert Pro 본 프로그램과 import·경로를 공유하지 않으며 단독으로 실행된다.

주요 기능
---------
- 업체(Organization) / 현장(Site) / 로거 계층 관리
- 센서 설정·채널 매핑 및 계측 데이터 조회·그래프
- 계정·권한 관리 (관리자 / 일반 사용자)
- 수집 스크립트(scripts/) 를 통한 원본 데이터 수집·적재

화면 구조
---------
  /org-list                업체 목록 (로그인 후 첫 화면)
  /site-list?org_id=…      현장 목록
  /legacy/…                로거 경로·센서·그래프·계정 (북마크·API 호환 유지)

실행 방법
---------
  Windows  : run_portal.bat  (프로젝트 .venv 자동 사용)
  수동     : cd measurement_portal/SurveyMgmtPortal
             pip install -r requirements.txt && python app.py
  버전 관리: python scripts/bump_versions.py auto

접속 주소
---------
  로컬      : http://127.0.0.1:8765/
  LAN 공유  : run_portal_lan.bat 실행 후 콘솔에 표시된 LAN IP 로 접속

환경변수 (호스팅·운영 시)
--------------------------
  SURVEY_PORTAL_HOST        바인드 주소 (기본 127.0.0.1, 서버 운영 시 0.0.0.0)
  SURVEY_PORTAL_PORT        포트 (기본 8765)
  SURVEY_PORTAL_THREADS     waitress 스레드 수 (기본 4)
  SURVEY_PORTAL_SECRET      세션 비밀키 (미설정 시 data/.portal_secret_key 자동 생성·재사용)
  SURVEY_PORTAL_DB          SQLite 경로
  SURVEY_PORTAL_DEV=1       로컬 개발 모드 (Flask dev server, 파일 변경 시 자동 재시작)
  SURVEY_PORTAL_DEPLOY_POLL_SEC  배포 알림 폴링 간격(초), 0=수동 버튼만
  프로덕션 WSGI: wsgi.py 의 application (gunicorn 등)

기본 계정 (데모·시드)
---------------------
  admin / 1524   |   guest / guest123

프로젝트 내 위치
----------------
  measurement_portal/SurveyMgmtPortal/app.py  ← 이 파일 (계측관리 통합시스템 진입점)
  Convert_pro3.py                              컨버트 프로그램
  monitoring/server.py                         QM 자동화 관제시스템
================================================================================
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import sqlite3
import sys
from datetime import date
from functools import wraps
from io import BytesIO
from pathlib import Path
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_SITE_MEDIA_ROOT = Path(_APP_DIR) / "data" / "site_media"
_IMG_EXT_ALLOWED = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_SITE_ENG_CODE = re.compile(r"^[a-z0-9]{1,64}$")
_INSTALL_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _normalize_hms_time(raw: str | None, default: str = "00:00:00") -> str:
    """HTML time 등에서 HH:MM(:SS) 정규화."""
    if raw is None or not str(raw).strip():
        return default
    s = str(raw).strip()
    parts = re.split(r"[:.]", s)
    parts = [p for p in parts if p != ""]
    try:
        if len(parts) >= 3:
            h, m, sec = int(parts[0]), int(parts[1]), int(parts[2][:2])
        elif len(parts) == 2:
            h, m, sec = int(parts[0]), int(parts[1]), 0
        else:
            return default
        h = max(0, min(23, h))
        m = max(0, min(59, m))
        sec = max(0, min(59, sec))
        return f"{h:02d}:{m:02d}:{sec:02d}"
    except ValueError:
        return default


def _optional_float_from_form(form, key: str) -> float | None:
    v = (form.get(key) or "").strip()
    if not v:
        return None
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def _optional_formula_from_form(form, key: str) -> str | None:
    s = (form.get(key) or "").strip()
    return s if s else None


# 리스트 참고 UI: 메인 배너
_SITE_MAIN_IMG_SIZE_WH = (934, 760)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import portal_version

import db
import sensor_catalog
from flask import (
    Blueprint,
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)


def _resolved_selected_sensor_kind_id(channel_row: dict | None) -> str:
    """센서 상세 드롭다운 selected 용 — 예전 kind id 를 현행 catalog id 로 해석."""
    if not channel_row:
        return ""
    raw = (channel_row.get("sensor_kind") or "").strip()
    if not raw:
        return ""
    hit = sensor_catalog.kind_by_id(raw)
    return hit["id"] if hit else raw


def _portal_secret_key() -> str:
    """Flask 세션 서명용 비밀키.

    환경변수 SURVEY_PORTAL_SECRET 이 있으면 그대로 사용한다.
    없으면 data/.portal_secret_key 에 한 번 생성해 두고 재시작·디버그 리로더 후에도 같은 값을 쓴다
    (미설정 시 매 실행마다 무작위 키가 되면 새로고침·재시작할 때마다 로그인이 풀린다).
    """
    env = (os.environ.get("SURVEY_PORTAL_SECRET") or "").strip()
    if env:
        return env
    path = Path(_APP_DIR) / "data" / ".portal_secret_key"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            raw = path.read_text(encoding="utf-8").strip()
            if raw:
                return raw
        key = secrets.token_hex(32)
        path.write_text(key + "\n", encoding="utf-8")
        return key
    except OSError:
        return secrets.token_hex(32)


app = Flask(
    __name__,
    template_folder=os.path.join(_APP_DIR, "templates"),
    static_folder=os.path.join(_APP_DIR, "static"),
)
app.secret_key = _portal_secret_key()
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024


@app.route("/favicon.ico")
def favicon():
    from flask import send_from_directory
    ico = os.path.join(_APP_DIR, "static", "favicon.ico")
    if os.path.exists(ico):
        return send_from_directory(os.path.join(_APP_DIR, "static"), "favicon.ico",
                                   mimetype="image/vnd.microsoft.icon")
    return "", 204


class _ScriptNamePrefixMiddleware:
    def __init__(self, wsgi_app, prefix: str):
        self.wsgi_app = wsgi_app
        self.prefix = (prefix or "").strip().rstrip("/")

    def __call__(self, environ, start_response):
        prefix = self.prefix
        if not prefix:
            return self.wsgi_app(environ, start_response)
        path = (environ.get("PATH_INFO") or "").strip() or "/"
        script = (environ.get("SCRIPT_NAME") or "").rstrip("/")
        if path == prefix:
            environ["SCRIPT_NAME"] = script + prefix
            environ["PATH_INFO"] = "/"
        elif path.startswith(prefix + "/"):
            environ["SCRIPT_NAME"] = script + prefix
            environ["PATH_INFO"] = path[len(prefix) :] or "/"
        elif not script:
            environ["SCRIPT_NAME"] = prefix
        return self.wsgi_app(environ, start_response)


app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
_forced_prefix = (
    (os.environ.get("SURVEY_PORTAL_URL_PREFIX") or "").strip()
    or (os.environ.get("SURVEY_PORTAL_SCRIPT_NAME") or "").strip()
)
if _forced_prefix:
    app.wsgi_app = _ScriptNamePrefixMiddleware(app.wsgi_app, _forced_prefix)


@app.template_filter("sns_ch_tree")
def _filter_sns_ch_tree(row: dict) -> str:
    return sensor_catalog.channel_tree_caption(row or {})


@app.template_filter("sns_ch_auto_name")
def _filter_sns_ch_auto_name(row: dict) -> str:
    return sensor_catalog.channel_auto_label(row or {})


@app.template_filter("sns_ch_kind_title")
def _filter_sns_ch_kind_title(row: dict) -> str:
    return sensor_catalog.channel_kind_title(row or {})


with app.app_context():
    db.init_database()

legacy_bp = Blueprint("legacy", __name__, url_prefix="/legacy")


def _collector_version_info() -> tuple[str | None, str | None]:
    """데이터수집프로그램(로컬) 버전 — `scripts/collector_version.py`. 웹과 독립 semver."""
    scripts_d = os.path.join(_APP_DIR, "scripts")
    if scripts_d not in sys.path:
        sys.path.insert(0, scripts_d)
    try:
        import collector_version as cv  # type: ignore

        return cv.VERSION_LABEL, cv.VERSION
    except ImportError:
        return None, None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("survey_user") or session.get("survey_user_id") is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("access_level") != 1:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def _logger_name_base_from_site(site: dict) -> str:
    """현장 코드(site_code)를 로거 접두로 쓴다. 없으면 site{id}."""
    code = (site.get("site_code") or "").strip().lower()
    code = re.sub(r"[^a-z0-9_]+", "_", code).strip("_")
    if code:
        return code
    return f"site{int(site['id'])}"


def _suggest_next_logger_name(site: dict, loggers: list[dict]) -> str:
    """기존 이름이 code_0, code_1 … 패턴이면 그 다음 번호, 아니면 code_0."""
    base = _logger_name_base_from_site(site)
    pat = re.compile(rf"^{re.escape(base)}_(\d+)$")
    max_n = -1
    for lg in loggers:
        nm = (lg.get("name") or "").strip().lower()
        m = pat.match(nm)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"{base}_{max_n + 1}"


def _normalize_eng_site_code(raw: str | None) -> str | None:
    if not raw:
        return None
    t = str(raw).strip().lower()
    return t if _SITE_ENG_CODE.fullmatch(t) else None


def _guess_image_ext(upload_name: str | None, default: str) -> str:
    suf = Path(upload_name or "").suffix.lower()
    return suf if suf in _IMG_EXT_ALLOWED else default


def _save_disk_image(rel_dir: Path, outfile: str, data: bytes) -> None:
    rel_dir.mkdir(parents=True, exist_ok=True)
    (rel_dir / outfile).write_bytes(data)


def _persist_site_media(
    site_id: int,
    main_upload,
    list_upload,
) -> tuple[str | None, str | None]:
    """업로드를 site_media/<id>/ 에 저장하고 DB용 상대경로 문자열(site_id/name.ext) 반환."""
    sid = str(site_id)
    base_dir = _SITE_MEDIA_ROOT / sid

    main_rel = list_rel = None
    if main_upload and getattr(main_upload, "filename", "") and main_upload.filename.strip():
        raw = main_upload.read()
        if PILImage is None:
            raise ValueError("메인 이미지 해상도 검사에는 Pillow 패키지가 필요합니다.")
        im = PILImage.open(BytesIO(raw))
        w, h = im.size
        if (w, h) != _SITE_MAIN_IMG_SIZE_WH:
            raise ValueError(
                f"메인 이미지는 {_SITE_MAIN_IMG_SIZE_WH[0]}×{_SITE_MAIN_IMG_SIZE_WH[1]} 픽셀이어야 합니다. (현재 {w}×{h})"
            )
        ext = _guess_image_ext(main_upload.filename, ".jpg")
        name = f"main{ext}"
        _save_disk_image(base_dir, name, raw)
        main_rel = f"{sid}/{name}"

    if list_upload and getattr(list_upload, "filename", "") and list_upload.filename.strip():
        raw = list_upload.read()
        ext = _guess_image_ext(list_upload.filename, ".jpg")
        name = f"list{ext}"
        _save_disk_image(base_dir, name, raw)
        list_rel = f"{sid}/{name}"

    return main_rel, list_rel


def _safe_media_path(rel: str) -> Path | None:
    """site_media 이하만 허용 (site_id/filename)."""
    rel = rel.replace("\\", "/").strip("/")
    if not rel or ".." in rel:
        return None
    parts = rel.split("/")
    if len(parts) != 2:
        return None
    sid, fname = parts
    if not sid.isdigit() or not fname:
        return None
    low = fname.lower()
    if not any(low.endswith(x) for x in (".jpg", ".jpeg", ".png", ".webp")):
        return None
    if secure_filename(fname) != fname:
        return None
    base = (_SITE_MEDIA_ROOT / sid).resolve()
    cand = (base / fname).resolve()
    try:
        cand.relative_to(_SITE_MEDIA_ROOT.resolve())
    except ValueError:
        return None
    if cand.parent != base:
        return None
    return cand if cand.is_file() else None


def _cleanup_site_media_dir(site_id: int) -> None:
    sid = Path(_SITE_MEDIA_ROOT) / str(site_id)
    if sid.is_dir():
        shutil.rmtree(sid, ignore_errors=True)


def _portal_build_marker_ms() -> int:
    """app.py / portal_version.py 최신 수정 시각(밀리초) — 배포·수정 감지 표시용."""
    mark = 0.0
    for name in ("app.py", "portal_version.py"):
        p = Path(_APP_DIR) / name
        try:
            if p.is_file():
                mark = max(mark, p.stat().st_mtime)
        except OSError:
            pass
    return int(mark * 1000)


@app.context_processor
def inject_acl():
    lvl = session.get("access_level")
    cv_lbl, cv_num = _collector_version_info()
    return {
        "is_admin": lvl == 1,
        "can_edit": lvl in (1, 3),
        "access_level": lvl,
        "portal_version": portal_version.VERSION_LABEL,
        "portal_version_number": portal_version.VERSION,
        # 예전 템플릿·스크립트 호환 (값은 semver 와 동일)
        "portal_ui_build": portal_version.VERSION_LABEL,
        "portal_app_dir": _APP_DIR,
        "collector_version_label": cv_lbl or "",
        "collector_version_number": cv_num or "",
    }


@app.context_processor
def inject_portal_deploy_ui():
    """배포·버전 변경 알림 배너(portal_deploy_banner.html)에 필요한 변수 주입.

    SURVEY_PORTAL_DEPLOY_POLL_SEC 환경변수:
      - 미설정 또는 0 → pollSec=null (자동폴링 없음, 수동 버튼만)
      - 양의 정수(초) → 해당 초마다 자동폴링
    """
    raw = (os.environ.get("SURVEY_PORTAL_DEPLOY_POLL_SEC") or "").strip()
    try:
        poll_sec: int | None = int(raw) if raw else None
        if poll_sec is not None and poll_sec <= 0:
            poll_sec = None
    except ValueError:
        poll_sec = None
    return {
        "portal_deploy_poll_interval_sec": poll_sec,
        "portal_deploy_marker_ms": _portal_build_marker_ms(),
    }


@app.route("/__portal_ping")
def portal_ping():
    """배포 알림 배너용 — 현재 빌드 타임스탬프 및 버전을 반환."""
    return jsonify(
        build_mtime_ms=_portal_build_marker_ms(),
        portal_version_label=portal_version.VERSION_LABEL,
    )


@app.errorhandler(403)
def forbidden(_e):
    return (
        render_template(
            "errors/403.html",
            username=session.get("survey_user", "") or "",
        ),
        403,
    )


def _username() -> str:
    return session.get("survey_user", "") or ""


def _client_ip() -> str:
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return (request.remote_addr or "").strip() or "—"


def _session_uid_level() -> tuple[int | None, int]:
    return session.get("survey_user_id"), int(session.get("access_level") or 4)


def _require_site(site_id: int) -> None:
    uid, lvl = _session_uid_level()
    if uid is None or not db.user_can_access_site(uid, lvl, site_id):
        abort(403)


def _require_site_edit(site_id: int) -> None:
    _require_site(site_id)
    if not db.user_can_edit_site(int(session.get("access_level") or 4)):
        abort(403)


def _level_to_role(level: int) -> str:
    return {1: "admin", 3: "editor", 4: "viewer"}.get(level, "viewer")


@app.route("/")
def index():
    if session.get("survey_user") and session.get("survey_user_id") is not None:
        return redirect(url_for("organization_list"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        uid = (request.form.get("username") or "").strip()
        pwd = request.form.get("password") or ""
        row = db.authenticate_user(uid, pwd)
        if row:
            session["survey_user"] = row["username"]
            session["survey_user_id"] = row["id"]
            session["access_level"] = row["access_level"]
            session.permanent = True
            # 로그인 직후 첫 화면은 업체 리스트 (next 파라미터 무시)
            return redirect(url_for("organization_list"))
        err = "아이디 또는 비밀번호가 올바르지 않습니다."
    return render_template("login.html", error=err)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@legacy_bp.route("/dashboard")
@login_required
def dashboard():
    """구 대시보드는 숨김. 북마크·옛 링크는 업체 리스트(신규 홈)로 보냄."""
    return redirect(url_for("organization_list"))


def _account_url() -> str:
    return (
        url_for("legacy.admin_users_list")
        if session.get("access_level") == 1
        else url_for("legacy.account_settings")
    )


@app.route("/org-list", methods=["GET", "POST"])
@login_required
def organization_list():
    """업체 리스트(로그인 후 첫 화면). 할당 현장이 속한 업체만 표시, 관리자(1)는 전체."""
    uid, lvl = _session_uid_level()
    if request.method == "POST":
        if lvl != 1:
            abort(403)
        action = (request.form.get("_action") or "").strip()
        if action == "delete_organization":
            oid = request.form.get("organization_id", type=int)
            if oid is None:
                flash("삭제할 업체가 올바르지 않습니다.", "error")
            elif not db.get_organization(oid):
                flash("삭제할 업체를 찾을 수 없습니다.", "error")
            else:
                ok, site_ids = db.delete_organization(oid)
                if ok:
                    for sid in site_ids:
                        _cleanup_site_media_dir(sid)
                    flash(
                        "업체와 소속 현장·로거·측정 데이터가 모두 삭제되었습니다.",
                    )
                else:
                    flash("업체를 삭제할 수 없습니다.", "error")
            return redirect(url_for("organization_list"))

        oname = (request.form.get("org_name") or "").strip()
        ocode = (request.form.get("org_code") or "").strip() or None
        omemo = (request.form.get("org_memo") or "").strip() or None
        if not oname:
            flash("업체 이름은 필수입니다.", "error")
        else:
            try:
                db.create_organization(oname, code=ocode, memo=omemo)
                flash("업체가 추가되었습니다.")
            except sqlite3.IntegrityError:
                flash("이미 같은 이름의 업체가 있습니다.", "error")
        return redirect(url_for("organization_list"))

    orgs = db.list_organizations_for_user(uid, lvl)
    return render_template(
        "org_list_smart.html",
        username=_username(),
        client_ip=_client_ip(),
        orgs=orgs,
        nav_active="org_list",
        account_url=_account_url(),
        show_org_add=session.get("access_level") == 1,
    )


@app.route("/site-list", methods=["GET", "POST"])
@login_required
def site_list():
    """선택한 업체 소속 현장 리스트. org_id 필수. 현장 추가는 영문 코드(site_code)=로거 접두."""
    uid, lvl = _session_uid_level()
    org_id = request.args.get("org_id", type=int)
    if request.method == "POST":
        if lvl != 1:
            abort(403)
        org_id = request.form.get("organization_id", type=int)
        rd = (
            url_for("organization_list")
            if org_id is None
            else url_for("site_list", org_id=org_id)
        )

        def _reload_with_error(msg: str):
            flash(msg, "error")
            return redirect(rd)

        action = (request.form.get("_action") or "").strip()
        if action == "delete_site":
            if org_id is None:
                flash("업체 정보가 없습니다.", "error")
                return redirect(url_for("organization_list"))
            if not db.user_can_access_org(uid, lvl, org_id):
                abort(403)
            sid = request.form.get("site_id", type=int)
            if sid is None:
                flash("삭제할 현장이 올바르지 않습니다.", "error")
                return redirect(rd)
            site_row = db.get_site(sid)
            if (
                not site_row
                or int(site_row["organization_id"]) != org_id
            ):
                flash("해당 업체의 현장이 아니거나 이미 삭제되었습니다.", "error")
                return redirect(rd)
            _cleanup_site_media_dir(sid)
            db.delete_site(sid)
            flash("현장과 소속 로거·측정 데이터가 삭제되었습니다.")
            return redirect(rd)

        name = (request.form.get("site_name") or "").strip()
        eng_code = _normalize_eng_site_code((request.form.get("site_code") or "").strip())
        verified = (request.form.get("site_code_verified") or "").strip() == "1"
        raw_install = (request.form.get("install_date") or "").strip()
        install_date = raw_install if _INSTALL_DATE.fullmatch(raw_install) else None

        if not org_id or not name:
            flash("업체와 현장 이름은 필수입니다.", "error")
            return redirect(rd)
        if not eng_code:
            return _reload_with_error(
                "현장 영어명은 영문 소문자와 숫자만 1~64자까지 입력할 수 있습니다."
            )
        if not verified:
            return _reload_with_error("현장 영어명 «중복확인»을 완료해 주세요.")
        if not db.user_can_access_org(uid, lvl, org_id):
            abort(403)
        if not db.is_site_code_available(org_id, eng_code):
            return _reload_with_error("이미 같은 영어명(코드)의 현장이 있습니다. 변경 후 다중복확인 해 주세요.")

        main_upload = request.files.get("image_main")
        lst_upload = request.files.get("image_list")
        try:
            sid = db.create_site(
                org_id,
                name,
                site_code=eng_code,
                install_date=install_date,
            )
        except sqlite3.IntegrityError:
            flash(
                "같은 업체에 이미 같은 한글 현장명이거나 같은 영문 코드입니다.",
                "error",
            )
            return redirect(url_for("site_list", org_id=org_id))

        try:
            mrel, lrel = _persist_site_media(sid, main_upload, lst_upload)
            if mrel or lrel:
                db.update_site_media_paths(sid, image_main=mrel, image_list=lrel)
        except ValueError as ex:
            db.delete_site(sid)
            _cleanup_site_media_dir(sid)
            flash(str(ex), "error")
            return redirect(url_for("site_list", org_id=org_id))

        flash(f"현장이 추가되었습니다. (id={sid})")
        db.ensure_default_logger_for_site(sid)
        return redirect(url_for("site_workspace", site_id=sid))

    if org_id is None:
        return redirect(url_for("organization_list"))
    if not db.user_can_access_org(uid, lvl, org_id):
        abort(403)
    org = db.get_organization(org_id)
    if not org:
        abort(404)
    sites = db.list_sites_for_user_in_organization(uid, lvl, org_id)
    return render_template(
        "site_list_smart.html",
        username=_username(),
        client_ip=_client_ip(),
        sites=sites,
        org=org,
        nav_active="site_list",
        account_url=_account_url(),
        show_site_add=session.get("access_level") == 1,
        default_install_date=date.today().isoformat(),
        site_main_px_w=_SITE_MAIN_IMG_SIZE_WH[0],
        site_main_px_h=_SITE_MAIN_IMG_SIZE_WH[1],
    )


@app.route("/api/site/check-site-code", methods=["GET"])
@login_required
def api_check_site_code():
    uid, lvl = _session_uid_level()
    org_id = request.args.get("organization_id", type=int)
    eng_code = _normalize_eng_site_code((request.args.get("site_code") or "").strip())
    if org_id is None:
        return jsonify(ok=False, message="organization_id 가 필요합니다."), 400
    if not db.user_can_access_org(uid, lvl, org_id):
        abort(403)
    if not eng_code:
        return jsonify(
            ok=True,
            available=False,
            message="영문 소문자와 숫자만 1~64자까지 입력할 수 있습니다.",
        )
    avail = db.is_site_code_available(org_id, eng_code)
    if avail:
        return jsonify(ok=True, available=True, message="사용 가능한 영어명입니다.")
    return jsonify(
        ok=True,
        available=False,
        message="이미 해당 업체에 같은 영어명(코드)의 현장이 있습니다.",
    )


@app.route("/site-media/<path:rel>")
@login_required
def site_media_file(rel: str):
    path = _safe_media_path(rel)
    if path is None:
        abort(404)
    return send_file(path)


def _workspace_updated_display(site_row: dict, loggers: list[dict]) -> str:
    """헤더에 표시할 ‘마지막 갱신’ 문자열."""
    latest = None
    for lg in loggers:
        t = lg.get("last_comm_at") or lg.get("created_at")
        if isinstance(t, str) and len(t) >= 10:
            cand = (t.replace("T", " "))[:19]
            if latest is None or cand > latest:
                latest = cand
    if latest:
        return latest
    c = site_row.get("created_at") or ""
    return (str(c).replace("T", " ")[:19]) if c else "—"


@app.route("/site/<int:site_id>/workspace")
@login_required
def site_workspace(site_id: int):
    _require_site(site_id)
    uid, lvl = _session_uid_level()
    site = db.get_site(site_id)
    if not site:
        abort(404)
    loggers = db.list_loggers(site_id)
    tree_data = db.site_measurement_workspace_tree(site_id)
    raw_ch = request.args.get("channel_id", type=int)
    ws_channel = None
    ws_kind_label = ""
    if raw_ch is not None:
        ch_row = db.get_sensor_channel(raw_ch)
        if (
            ch_row
            and int(ch_row["site_id"]) == site_id
            and db.user_can_access_site(uid, lvl, site_id)
        ):
            ws_channel = dict(ch_row)
            kdx = sensor_catalog.kind_by_id(
                (ch_row.get("sensor_kind") or "").strip()
            )
            ws_kind_label = (
                kdx["label_ko"]
                if kdx
                else (ch_row.get("sensor_kind") or "—")
            )
    ws_tilt_chart = (
        ws_channel is not None
        and sensor_catalog.sensor_kind_supports_tilt_derived_table(
            (ws_channel.get("sensor_kind") or "").strip()
        )
    )
    ws_inclinometer_chart = (
        ws_channel is not None
        and sensor_catalog.sensor_kind_supports_inclinometer_derived_table(
            (ws_channel.get("sensor_kind") or "").strip()
        )
    )
    ws_crack_chart = (
        ws_channel is not None
        and sensor_catalog.sensor_kind_supports_crack_derived_table(
            (ws_channel.get("sensor_kind") or "").strip()
        )
    )
    ws_flow_chart = (
        ws_channel is not None
        and sensor_catalog.sensor_kind_supports_flow_derived_table(
            (ws_channel.get("sensor_kind") or "").strip()
        )
    )
    ws_groundwater_chart = (
        ws_channel is not None
        and sensor_catalog.sensor_kind_supports_groundwater_derived_table(
            (ws_channel.get("sensor_kind") or "").strip()
        )
    )
    kd_wv = (
        sensor_catalog.kind_by_id((ws_channel.get("sensor_kind") or "").strip())
        if ws_channel
        else None
    )
    ws_vibration_3axis = ws_channel is not None and (kd_wv or {}).get("id") == "vibration_3axis"
    ws_vibration_scalar_pvs = ws_channel is not None and (kd_wv or {}).get("id") == "vibration"
    ws_chart_y_min_eff = ws_chart_y_max_eff = None
    if ws_channel:
        ymin_e, ymax_e = sensor_catalog.effective_chart_y_bounds_for_kind(
            (ws_channel.get("sensor_kind") or "").strip(),
            ws_channel.get("chart_y_min"),
            ws_channel.get("chart_y_max"),
        )
        ws_chart_y_min_eff, ws_chart_y_max_eff = ymin_e, ymax_e
    ws_latest_observed = None
    if ws_channel is not None:
        mx = db.latest_observed_at_by_channel([int(ws_channel["id"])])
        ws_latest_observed = mx.get(int(ws_channel["id"]))
    ws_mgmt_levels = (
        sensor_catalog.mgmt_levels_for_chart(ws_channel)
        if ws_channel
        else {k: None for k in sensor_catalog.MGMT_CHART_LEVEL_KEYS}
    )
    return render_template(
        "site_workspace.html",
        username=_username(),
        site=site,
        org_name=site.get("org_name") or "",
        loggers=loggers,
        ws_tree_roots=tree_data["roots"],
        ws_unassigned=tree_data["unassigned_channels"],
        ws_updated=_workspace_updated_display(dict(site), loggers),
        ws_channel=ws_channel,
        ws_mgmt_levels=ws_mgmt_levels,
        ws_tilt_chart=ws_tilt_chart,
        ws_inclinometer_chart=ws_inclinometer_chart,
        ws_crack_chart=ws_crack_chart,
        ws_flow_chart=ws_flow_chart,
        ws_groundwater_chart=ws_groundwater_chart,
        ws_vibration_3axis=ws_vibration_3axis,
        ws_vibration_scalar_pvs=ws_vibration_scalar_pvs,
        ws_chart_y_min_eff=ws_chart_y_min_eff,
        ws_chart_y_max_eff=ws_chart_y_max_eff,
        ws_latest_observed=ws_latest_observed,
        ws_kind_label=ws_kind_label,
        ws_can_purge=db.user_can_edit_site(int(lvl)),
        report_badge_count=0,
        nav_active="site_workspace",
        header_breadcrumb=f"{site.get('org_name') or ''} · 현장 워크스페이스",
        account_url=_account_url(),
        site_list_url=url_for("site_list", org_id=int(site["organization_id"])),
    )


@app.route("/site/<int:site_id>/reports")
@login_required
def site_workspace_reports(site_id: int):
    _require_site(site_id)
    site = db.get_site(site_id)
    if not site:
        abort(404)
    return render_template(
        "site_workspace_placeholder.html",
        username=_username(),
        site=site,
        nav_active="site_workspace",
        header_breadcrumb=f"{site.get('org_name') or ''} · 보고서",
        account_url=_account_url(),
        site_list_url=url_for("site_list", org_id=int(site["organization_id"])),
        placeholder_title="보고서",
        placeholder_lead="보고서 생성·목록은 구현 예정입니다.",
    )


@app.route("/site/<int:site_id>/site-settings", methods=["GET", "POST"])
@login_required
def site_workspace_site_settings(site_id: int):
    _require_site(site_id)
    site_row = db.get_site(site_id)
    if not site_row:
        abort(404)
    org_id = int(site_row["organization_id"])
    can_edit = session.get("access_level") in (1, 3)

    def _rd(**extra):
        return redirect(url_for("site_workspace_site_settings", site_id=site_id, **extra))

    if request.method == "POST":
        _require_site_edit(site_id)
        action = (request.form.get("_action") or "save_site").strip()

        if action == "save_sms":
            en = 1 if request.form.get("sms_enabled") else 0
            msg = (request.form.get("sms_message") or "").strip()
            tf = _normalize_hms_time(request.form.get("sms_time_from"), "00:00:00")
            tt = _normalize_hms_time(request.form.get("sms_time_to"), "23:59:59")
            db.upsert_site_sms_config(
                site_id,
                enabled=en,
                message_template=msg,
                time_from=tf,
                time_to=tt,
            )
            flash("SMS 설정이 저장되었습니다.")
            return _rd()

        if action == "save_recipient":
            rid = request.form.get("recipient_id", type=int)
            if rid is not None and rid <= 0:
                rid = None
            send = 1 if request.form.get("recipient_send") else 0
            rn = (request.form.get("recipient_name") or "").strip()
            rp = (request.form.get("recipient_phone") or "").strip()
            rj = (request.form.get("recipient_job") or "").strip()
            rdpt = (request.form.get("recipient_dept") or "").strip()
            rinfo = (request.form.get("recipient_info") or "").strip()
            if not rn or not rp:
                flash("수신자 이름과 전화번호는 필수입니다.", "error")
                return _rd(edit=rid) if rid else _rd()
            try:
                db.upsert_site_sms_recipient(
                    site_id,
                    recipient_id=rid,
                    send_enabled=send,
                    name=rn,
                    phone=rp,
                    job_title=rj,
                    department=rdpt,
                    info=rinfo,
                )
            except ValueError:
                flash("수신자를 찾을 수 없습니다.", "error")
                return _rd()
            flash("발송 대상자가 저장되었습니다.")
            return _rd()

        if action == "delete_recipient":
            dr = request.form.get("delete_recipient_id", type=int)
            if dr:
                db.delete_site_sms_recipient(site_id, dr)
                flash("삭제되었습니다.")
            return _rd()

        # save_site (기본)
        name = (request.form.get("site_name") or "").strip()
        raw_code = (request.form.get("site_code") or "").strip()
        raw_install = (request.form.get("install_date") or "").strip()

        rd = _rd()

        if not name:
            flash("현장명은 필수입니다.", "error")
            return rd

        eng_code = _normalize_eng_site_code(raw_code) if raw_code else None
        if raw_code and not eng_code:
            flash(
                "현장 영문 코드는 소문자·숫자 1~64자만 허용됩니다.",
                "error",
            )
            return rd
        if eng_code is not None and (
            not db.is_site_code_available(org_id, eng_code, exclude_site_id=site_id)
        ):
            flash("해당 업체에 이미 같은 영문 코드의 현장이 있습니다.", "error")
            return rd

        if raw_install == "":
            parsed_install = None
        elif _INSTALL_DATE.fullmatch(raw_install):
            parsed_install = raw_install
        else:
            flash("설치일은 YYYY-MM-DD 형식이어야 합니다.", "error")
            return rd

        addr_s = (request.form.get("address") or "").strip()
        prog_s = (request.form.get("site_program") or "").strip()
        memo_s = (request.form.get("memo") or "").strip()

        try:
            db.update_site_fields(
                site_id,
                name=name,
                site_code=eng_code,
                install_date=parsed_install,
                address=addr_s,
                site_program=prog_s,
                memo=memo_s,
            )
        except sqlite3.IntegrityError:
            flash("같은 업체에 같은 한글 현장명이거나 영문 코드가 충돌합니다.", "error")
            return rd

        main_up = request.files.get("image_main")
        lst_up = request.files.get("image_list")
        prev_m = site_row.get("image_main")
        prev_l = site_row.get("image_list")
        try:
            mrel, lrel = _persist_site_media(site_id, main_up, lst_up)
        except ValueError as ex:
            flash(str(ex), "error")
            return rd
        new_m = mrel if mrel is not None else prev_m
        new_l = lrel if lrel is not None else prev_l
        if mrel is not None or lrel is not None:
            db.update_site_media_paths(site_id, image_main=new_m, image_list=new_l)

        flash("현장 정보가 저장되었습니다.")
        return redirect(url_for("site_workspace_site_settings", site_id=site_id))

    edit_arg = request.args.get("edit", type=int)
    editing = None
    if edit_arg:
        editing = db.get_site_sms_recipient(site_id, edit_arg)

    return render_template(
        "site_workspace_site_settings.html",
        username=_username(),
        site=site_row,
        nav_active="site_workspace",
        header_breadcrumb=f"{site_row.get('org_name') or ''} · 현장설정",
        account_url=_account_url(),
        site_list_url=url_for("site_list", org_id=org_id),
        can_edit=can_edit,
        site_main_px_w=_SITE_MAIN_IMG_SIZE_WH[0],
        site_main_px_h=_SITE_MAIN_IMG_SIZE_WH[1],
        sms=db.get_site_sms_config(site_id),
        sms_recipients=db.list_site_sms_recipients(site_id),
        editing_recipient=editing,
    )


@app.route("/site/<int:site_id>/sensor-settings", methods=["GET", "POST"])
@login_required
def site_workspace_sensor_settings(site_id: int):
    _require_site(site_id)
    site_row = db.get_site(site_id)
    if not site_row:
        abort(404)
    db.ensure_default_logger_for_site(site_id)
    loggers = db.list_loggers(site_id)

    if request.method == "POST":
        _require_site_edit(site_id)
        action = (request.form.get("_action") or "").strip()
        if action == "add_logger":
            name = (request.form.get("logger_name") or "").strip()
            lg_list = db.list_loggers(site_id)
            if not name:
                name = _suggest_next_logger_name(site_row, lg_list)
            kind = (request.form.get("logger_kind") or "manual").strip()
            if kind not in ("manual", "ftp", "other"):
                kind = "manual"
            serial = (request.form.get("serial_number") or "").strip() or None
            try:
                new_id = db.create_logger(
                    site_id, name, logger_kind=kind, serial_number=serial
                )
                flash(f'로거 "{name}" 을(를) 추가했습니다.')
                return redirect(
                    url_for(
                        "site_workspace_sensor_settings",
                        site_id=site_id,
                        logger_id=new_id,
                    )
                )
            except sqlite3.IntegrityError:
                flash("같은 현장에 이미 같은 이름의 로거가 있습니다.", "error")
        elif action == "add_sensor":
            lg_id_f = request.form.get("sensor_logger_id", type=int)
            code = (request.form.get("sensor_code") or "").strip()
            if not code:
                code = (request.form.get("sensor_label") or "").strip()
            if lg_id_f is None or not code:
                flash("센서코드·로거는 필수입니다.", "error")
            else:
                lg_own = db.get_logger(lg_id_f)
                if not lg_own or int(lg_own["site_id"]) != site_id:
                    flash("잘못된 로거입니다.", "error")
                else:
                    sk = (request.form.get("sensor_kind") or "").strip() or None
                    if not sk:
                        flash("센서 타입을 선택해 주세요.", "error")
                    else:
                        col_req = request.form.get("sensor_column_1based", type=int)
                        if col_req is None:
                            ch_idx = db.next_channel_index(lg_id_f)
                        elif col_req < 0:
                            flash("인덱스는 0 이상이어야 합니다.", "error")
                            return redirect(
                                url_for(
                                    "site_workspace_sensor_settings",
                                    site_id=site_id,
                                    logger_id=lg_id_f,
                                )
                            )
                        else:
                            ch_idx = col_req
                        unit = (request.form.get("unit") or "").strip() or None
                        kd = sensor_catalog.kind_by_id(sk)
                        if (not unit) and kd and (kd.get("default_unit") or "").strip():
                            unit = kd["default_unit"].strip() or None
                        try:
                            auto_lbl = sensor_catalog.channel_auto_label(
                                None, sensor_code=code, sensor_kind=sk
                            )
                            new_ch_id = db.create_sensor_channel(
                                lg_id_f,
                                ch_idx,
                                auto_lbl,
                                sensor_code=code,
                                sensor_kind=sk,
                                unit=unit,
                                measurement_group_id=None,
                                is_active=0,
                            )
                            db.apply_channel_template_defaults(
                                new_ch_id,
                                sensor_catalog.channel_template_defaults(sk),
                            )
                            db.update_site_last_sensor_add(
                                site_id,
                                sensor_code=code,
                                sensor_kind=sk,
                            )
                            flash(
                                "센서를 추가했습니다(미사용·적재 제외). 카테고리 편집에서 센서를 등록해야 워크스페이스 "
                                "계측기 리스트에 나타납니다. 왼쪽 「인덱스」에 CSV 열 인덱스(0부터)를 맞춘 뒤 「변경」을 누르면 "
                                "적재·순환 대상으로 켜집니다."
                            )
                            return redirect(
                                url_for(
                                    "site_workspace_sensor_settings",
                                    site_id=site_id,
                                    logger_id=lg_id_f,
                                    channel_id=new_ch_id,
                                )
                            )
                        except sqlite3.IntegrityError:
                            flash(
                                "이 로거에 같은 칼럼 인덱스(channel_index)가 이미 있습니다.",
                                "error",
                            )
                        except db.SensorCodeDuplicateError:
                            flash(
                                "이 현장에 동일한 센서코드가 이미 있습니다. 코드를 바꿔 주세요.",
                                "error",
                            )
            if lg_id_f:
                return redirect(
                    url_for(
                        "site_workspace_sensor_settings",
                        site_id=site_id,
                        logger_id=lg_id_f,
                    )
                )
            return redirect(url_for("site_workspace_sensor_settings", site_id=site_id))
        elif action == "update_logger_meta":
            lg_meta_id = request.form.get("logger_id", type=int)
            serial_raw = (request.form.get("serial_number") or "").strip()
            memo_raw = (request.form.get("memo") or "").strip()
            if lg_meta_id is None:
                flash("로거를 지정할 수 없습니다.", "error")
            else:
                lg_own = db.get_logger(lg_meta_id)
                if not lg_own or int(lg_own["site_id"]) != site_id:
                    flash("잘못된 로거입니다.", "error")
                else:
                    kind_raw = (request.form.get("logger_kind") or "").strip().lower()
                    if kind_raw not in ("manual", "ftp", "other"):
                        kind_raw = (lg_own.get("logger_kind") or "manual")
                    db.update_logger(
                        lg_meta_id,
                        serial_number=serial_raw or None,
                        memo=memo_raw,
                        logger_kind=kind_raw,
                    )
                    flash("로거 정보를 저장했습니다.")
                    return redirect(
                        url_for(
                            "site_workspace_sensor_settings",
                            site_id=site_id,
                            logger_id=lg_meta_id,
                        )
                    )
            return redirect(url_for("site_workspace_sensor_settings", site_id=site_id))
        elif action == "delete_logger":
            lg_del = request.form.get("logger_id", type=int)
            if lg_del is None:
                flash("삭제할 로거가 올바르지 않습니다.", "error")
            else:
                lg_own = db.get_logger(lg_del)
                if not lg_own or int(lg_own["site_id"]) != site_id:
                    flash("해당 현장에 속한 로거가 아니거나 이미 삭제되었습니다.", "error")
                elif db.delete_logger(lg_del, site_id=site_id):
                    flash(
                        "로거를 삭제했습니다. (연결된 센서·측정 데이터도 함께 삭제되었을 수 있습니다.)"
                    )
                else:
                    flash("로거를 삭제할 수 없습니다.", "error")
            return redirect(url_for("site_workspace_sensor_settings", site_id=site_id))
        elif action == "update_sensor_channel_only":
            cid = request.form.get("sensor_channel_id", type=int)
            lg_id = request.form.get("sensor_logger_id", type=int)
            col_idx = request.form.get("channel_index", type=int)
            if cid is None or lg_id is None or col_idx is None:
                flash("센서·칼럼 정보가 올바르지 않습니다.", "error")
                return redirect(
                    url_for("site_workspace_sensor_settings", site_id=site_id)
                )
            if col_idx < 0:
                flash("인덱스는 0 이상이어야 합니다.", "error")
                return redirect(
                    url_for(
                        "site_workspace_sensor_settings",
                        site_id=site_id,
                        logger_id=lg_id,
                        channel_id=cid,
                    )
                )
            ch_idx = col_idx
            lg_own = db.get_logger(lg_id)
            if not lg_own or int(lg_own["site_id"]) != site_id:
                abort(403)
            ch = db.get_sensor_channel(cid)
            if not ch or int(ch["logger_device_id"]) != lg_id:
                flash("해당 로거의 센서가 아닙니다.", "error")
                return redirect(
                    url_for(
                        "site_workspace_sensor_settings",
                        site_id=site_id,
                        logger_id=lg_id,
                    )
                )
            try:
                db.update_sensor_channel_index_and_activate(cid, lg_id, ch_idx)
                flash(
                    "칼럼을 저장했고 이 센서를 적재·표시 대상으로 켰습니다(is_active=1). "
                    "수집 프로그램은 DB를 매 순환마다 다시 읽습니다.",
                )
            except sqlite3.IntegrityError:
                flash(
                    "이 로거에 이미 같은 칼럼 번호(channel_index)가 있습니다.",
                    "error",
                )
            except ValueError:
                flash("칼럼을 저장할 수 없습니다.", "error")
            return redirect(
                url_for(
                    "site_workspace_sensor_settings",
                    site_id=site_id,
                    logger_id=lg_id,
                    channel_id=cid,
                )
            )
        elif action == "update_sensor_detail":
            cid = request.form.get("sensor_channel_id", type=int)
            lg_id = request.form.get("sensor_logger_id", type=int)
            if cid is None or lg_id is None:
                flash("센서 정보가 올바르지 않습니다.", "error")
                return redirect(
                    url_for("site_workspace_sensor_settings", site_id=site_id)
                )
            lg_own = db.get_logger(lg_id)
            if not lg_own or int(lg_own["site_id"]) != site_id:
                abort(403)
            ch = db.get_sensor_channel(cid)
            if not ch or int(ch["logger_device_id"]) != lg_id:
                flash("해당 로거의 센서가 아닙니다.", "error")
                return redirect(
                    url_for(
                        "site_workspace_sensor_settings",
                        site_id=site_id,
                        logger_id=lg_id,
                    )
                )
            try:
                ch_idx = int(ch["channel_index"])
            except (TypeError, ValueError):
                ch_idx = 0
            lo = ch_idx
            sensor_code = (request.form.get("sensor_code") or "").strip() or None
            serial_ch = (request.form.get("sensor_serial") or "").strip() or None
            sk = (request.form.get("sensor_kind") or "").strip() or None
            unit = (request.form.get("unit") or "").strip() or None
            memo_ch = (request.form.get("sensor_memo") or "").strip() or None
            inst_loc = (request.form.get("install_location") or "").strip() or None
            raw_id_ch = (request.form.get("install_date") or "").strip()
            inst_date = raw_id_ch if _INSTALL_DATE.fullmatch(raw_id_ch) else None
            if raw_id_ch and not inst_date:
                flash("설치일은 YYYY-MM-DD 형식이어야 합니다.", "error")
                return redirect(
                    url_for(
                        "site_workspace_sensor_settings",
                        site_id=site_id,
                        logger_id=lg_id,
                        channel_id=cid,
                    )
                )
            prev_sk = (ch.get("sensor_kind") or "").strip()
            kind_changed = prev_sk != (sk or "").strip()
            kind_tpl = sensor_catalog.channel_template_defaults(sk)
            if kind_changed:
                unit = kind_tpl.get("unit")
                dp = int(kind_tpl.get("decimal_places") or 2)
                try:
                    scale_k_use = float(
                        kind_tpl["scale_k"]
                        if kind_tpl.get("scale_k") is not None
                        else 1.0
                    )
                    scale_b_use = float(
                        kind_tpl["scale_b"]
                        if kind_tpl.get("scale_b") is not None
                        else 0.0
                    )
                except (TypeError, ValueError):
                    scale_k_use, scale_b_use = 1.0, 0.0
                lvl1p = kind_tpl.get("level1_primary")
                lvl1s = kind_tpl.get("level1_secondary")
                lvl2p = kind_tpl.get("level2_primary")
                lvl2s = kind_tpl.get("level2_secondary")
                lvl3p = kind_tpl.get("level3_primary")
                lvl3s = kind_tpl.get("level3_secondary")
                cyt_min = kind_tpl.get("chart_y_min")
                cyt_max = kind_tpl.get("chart_y_max")
                cf1 = kind_tpl.get("calc_formula_1")
                cf2 = kind_tpl.get("calc_formula_2")
                cf3 = kind_tpl.get("calc_formula_3")
                cf4 = kind_tpl.get("calc_formula_4")
                cf5 = kind_tpl.get("calc_formula_5")
                cf6 = kind_tpl.get("calc_formula_6")
                pipe_dm = kind_tpl.get("pipe_depth_m")
                gauge_factor = kind_tpl.get("gauge_factor")
                sensor_len_mm = kind_tpl.get("sensor_length_mm")
            else:
                dp = request.form.get("decimal_places", type=int)
                if dp is None:
                    dp = int(ch.get("decimal_places") or 2)
                try:
                    scale_k_use = float(ch.get("scale_k") or 1.0)
                except (TypeError, ValueError):
                    scale_k_use = 1.0
                try:
                    scale_b_use = float(ch.get("scale_b") or 0.0)
                except (TypeError, ValueError):
                    scale_b_use = 0.0
                lvl1p = _optional_float_from_form(request.form, "level1_primary")
                lvl1s = _optional_float_from_form(request.form, "level1_secondary")
                lvl2p = _optional_float_from_form(request.form, "level2_primary")
                lvl2s = _optional_float_from_form(request.form, "level2_secondary")
                lvl3p = _optional_float_from_form(request.form, "level3_primary")
                lvl3s = _optional_float_from_form(request.form, "level3_secondary")
                cyt_min = _optional_float_from_form(request.form, "chart_y_min")
                cyt_max = _optional_float_from_form(request.form, "chart_y_max")
                cf1 = _optional_formula_from_form(request.form, "calc_formula_1")
                cf2 = _optional_formula_from_form(request.form, "calc_formula_2")
                cf3 = _optional_formula_from_form(request.form, "calc_formula_3")
                cf4 = _optional_formula_from_form(request.form, "calc_formula_4")
                cf5 = _optional_formula_from_form(request.form, "calc_formula_5")
                cf6 = _optional_formula_from_form(request.form, "calc_formula_6")
                pipe_dm = _optional_float_from_form(request.form, "pipe_depth_m")
                gauge_factor = _optional_float_from_form(request.form, "gauge_factor")
                sensor_len_mm = _optional_float_from_form(
                    request.form, "sensor_length_mm"
                )
            ia = 1 if request.form.get("is_active") == "1" else 0
            sms = 1 if request.form.get("sms_enabled") == "1" else 0
            if not (sensor_code or "").strip():
                flash("센서코드는 필수입니다.", "error")
                return redirect(
                    url_for(
                        "site_workspace_sensor_settings",
                        site_id=site_id,
                        logger_id=lg_id,
                        channel_id=cid,
                    )
                )
            if not sk:
                flash("센서 종류를 선택해 주세요.", "error")
                return redirect(
                    url_for(
                        "site_workspace_sensor_settings",
                        site_id=site_id,
                        logger_id=lg_id,
                        channel_id=cid,
                    )
                )
            linked_raw = (request.form.get("linked_sensor_codes") or "").strip() or None
            sc_key = (sensor_code or "").strip()
            if linked_raw:
                for raw_link in db.split_linked_sensor_codes(linked_raw):
                    expanded_link = db.expand_linked_sensor_code_relative(sc_key, raw_link)
                    if (expanded_link or "").strip() == sc_key.strip():
                        flash(
                            "연결센서코드에 대표 센서와 같은 코드를 넣을 수 없습니다.",
                            "error",
                        )
                        return redirect(
                            url_for(
                                "site_workspace_sensor_settings",
                                site_id=site_id,
                                logger_id=lg_id,
                                channel_id=cid,
                            )
                        )
                    if not db.get_sensor_channel_by_site_and_code(site_id, expanded_link):
                        disp = raw_link.strip()
                        if disp != expanded_link.strip():
                            disp = f"{disp} → {expanded_link.strip()}"
                        flash(
                            f'연결센서코드 「{disp}」 을(를) 이 현장에서 찾을 수 없습니다.',
                            "error",
                        )
                        return redirect(
                            url_for(
                                "site_workspace_sensor_settings",
                                site_id=site_id,
                                logger_id=lg_id,
                                channel_id=cid,
                            )
                        )
            label = sensor_catalog.channel_auto_label(
                dict(ch),
                sensor_code=sensor_code,
                sensor_kind=sk,
            )
            mg_id = ch.get("measurement_group_id")
            if mg_id is not None:
                try:
                    mg_id = int(mg_id)
                except (TypeError, ValueError):
                    mg_id = None
            if sk:
                kd_u = sensor_catalog.kind_by_id(sk)
                if kd_u:
                    mg_id = db.ensure_measurement_group_leaf(
                        site_id,
                        kd_u["kind_group"],
                        kd_u["label_ko"],
                    )
            try:
                db.update_sensor_channel_row(
                    cid,
                    label=label,
                    channel_index=ch_idx,
                    list_order=lo,
                    measurement_group_id=mg_id,
                    sensor_code=sensor_code,
                    serial_number=serial_ch,
                    sensor_kind=sk,
                    unit=unit,
                    decimal_places=dp,
                    is_active=ia,
                    sms_enabled=sms,
                    level1_primary=lvl1p,
                    level1_secondary=lvl1s,
                    level2_primary=lvl2p,
                    level2_secondary=lvl2s,
                    level3_primary=lvl3p,
                    level3_secondary=lvl3s,
                    install_location=inst_loc,
                    install_date=inst_date,
                    memo=memo_ch,
                    chart_y_min=cyt_min,
                    chart_y_max=cyt_max,
                    linked_sensor_codes=linked_raw,
                    pipe_depth_m=pipe_dm,
                    gauge_factor=gauge_factor,
                    sensor_length_mm=sensor_len_mm,
                    calc_formula_1=cf1,
                    calc_formula_2=cf2,
                    calc_formula_3=cf3,
                    calc_formula_4=cf4,
                    calc_formula_5=cf5,
                    calc_formula_6=cf6,
                    scale_k=scale_k_use,
                    scale_b=scale_b_use,
                )
                flash("센서 정보를 저장했습니다.")
            except db.SensorCodeDuplicateError:
                flash(
                    "이 현장에 동일한 센서코드가 이미 있습니다. 코드를 바꿔 주세요.",
                    "error",
                )
            except sqlite3.IntegrityError:
                flash(
                    "같은 로거에 이미 같은 칼럼 번호(channel_index)가 있습니다.",
                    "error",
                )
            return redirect(
                url_for(
                    "site_workspace_sensor_settings",
                    site_id=site_id,
                    logger_id=lg_id,
                    channel_id=cid,
                )
            )
        elif action == "delete_sensor":
            cid = request.form.get("sensor_channel_id", type=int)
            lg_id = request.form.get("sensor_logger_id", type=int)
            if cid is None or lg_id is None:
                flash("삭제할 센서가 올바르지 않습니다.", "error")
            else:
                lg_own = db.get_logger(lg_id)
                if not lg_own or int(lg_own["site_id"]) != site_id:
                    abort(403)
                if db.delete_sensor_channel(cid, logger_device_id=lg_id):
                    flash("센서를 삭제했습니다.")
                else:
                    flash("센서를 삭제할 수 없습니다.", "error")
            return redirect(
                url_for(
                    "site_workspace_sensor_settings",
                    site_id=site_id,
                    logger_id=lg_id,
                )
                if lg_id is not None
                else url_for("site_workspace_sensor_settings", site_id=site_id)
            )
        return redirect(url_for("site_workspace_sensor_settings", site_id=site_id))

    raw_lgid = request.args.get("logger_id", type=int)
    selected_logger = None
    if raw_lgid is not None:
        for lg in loggers:
            if int(lg["id"]) == raw_lgid:
                selected_logger = lg
                break
    if selected_logger is None and loggers:
        def _lg_sort_key(x: dict) -> tuple:
            try:
                ch_n = int(x.get("ch_count") or 0)
            except (TypeError, ValueError):
                ch_n = 0
            t = (x.get("last_comm_at") or x.get("created_at") or "")
            t_s = str(t).replace("T", " ")[:19] if t else ""
            nm = (x.get("name") or "").strip().lower()
            return (-ch_n, t_s, nm)

        selected_logger = sorted(loggers, key=_lg_sort_key)[0]

    lg_id_for_list = (
        int(selected_logger["id"]) if selected_logger is not None else None
    )
    channels = (
        db.list_sensor_channels(lg_id_for_list) if lg_id_for_list is not None else []
    )

    raw_chid = request.args.get("channel_id", type=int)
    selected_channel = None
    if lg_id_for_list is not None and channels:
        if raw_chid is not None:
            ch_row = db.get_sensor_channel(raw_chid)
            if (
                ch_row
                and int(ch_row["logger_device_id"]) == lg_id_for_list
            ):
                selected_channel = dict(ch_row)
        if selected_channel is None:
            selected_channel = dict(channels[0])

    _next_ci = (
        db.next_channel_index(lg_id_for_list)
        if lg_id_for_list is not None
        else 0
    )
    sensor_add_suggested_column_1based = _next_ci + 1
    sensor_add_suggested_channel_index = _next_ci

    return render_template(
        "site_workspace_sensor_settings.html",
        username=_username(),
        site=site_row,
        nav_active="site_workspace",
        header_breadcrumb=f"{site_row.get('org_name') or ''} · 센서설정",
        account_url=_account_url(),
        site_list_url=url_for("site_workspace", site_id=site_id),
        can_edit=session.get("access_level") in (1, 3),
        loggers=loggers,
        suggested_logger_name=_suggest_next_logger_name(site_row, loggers),
        logger_name_base=_logger_name_base_from_site(site_row),
        selected_logger=selected_logger,
        channels=channels,
        selected_channel=selected_channel,
        selected_sensor_kind_id=_resolved_selected_sensor_kind_id(selected_channel),
        tilt_mgmt_mm=sensor_catalog.tilt_management_defaults_mm(),
        crack_mgmt_mm=sensor_catalog.crack_management_defaults_mm(),
        surface_settlement_mgmt_mm=sensor_catalog.surface_settlement_management_defaults_mm(),
        vibration_form_defaults=sensor_catalog.vibration_sensor_form_defaults(),
        crack_calc_formula_1_default=sensor_catalog.CRACK_CALC_FORMULA_1_DEFAULT,
        groundwater_calc_formula_1_default=sensor_catalog.GROUNDWATER_CALC_FORMULA_1_DEFAULT,
        load_cell_calc_formula_1_default=sensor_catalog.LOAD_CELL_CALC_FORMULA_1_DEFAULT,
        surface_settlement_calc_formula_1_default=sensor_catalog.SURFACE_SETTLEMENT_CALC_FORMULA_1_DEFAULT,
        kind_template_defaults_map=sensor_catalog.kind_template_defaults_map_for_json(),
        sensor_kinds=sensor_catalog.SENSOR_KINDS,
        sensor_add_suggested_channel_index=sensor_add_suggested_channel_index,
        sensor_panel_fragments_url=url_for(
            "site_sensor_settings_panel_fragments", site_id=site_id
        ),
    )


@app.route("/site/<int:site_id>/sensor-settings/panel-fragments")
@login_required
def site_sensor_settings_panel_fragments(site_id: int):
    """센서설정: 목록 클릭 시 패널·왼쪽 칼럼 바·로거 블록 등 부분 갱신(스크롤 유지).

    항상 detail_html 과 channels_aside_html 을 반환한다(칼럼 폼의 sensor_channel_id 가 선택과 일치하게).
    zones=workspace 일 때만 logger_detail_html 을 추가한다.
    """
    _require_site(site_id)
    logger_id = request.args.get("logger_id", type=int)
    channel_id = request.args.get("channel_id", type=int)
    if logger_id is None:
        return jsonify({"error": "logger_id 가 필요합니다."}), 400
    lg = db.get_logger(logger_id)
    if not lg or int(lg["site_id"]) != site_id:
        return jsonify({"error": "로거를 찾을 수 없습니다."}), 404
    site_row = db.get_site(site_id)
    if not site_row:
        abort(404)
    uid, lvl = _session_uid_level()
    if not db.user_can_access_site(uid, lvl, site_id):
        return jsonify({"error": "접근 권한이 없습니다."}), 403

    selected_logger = dict(lg)
    channels = db.list_sensor_channels(logger_id)
    selected_channel = None
    if channel_id is not None:
        ch_row = db.get_sensor_channel(channel_id)
        if ch_row and int(ch_row["logger_device_id"]) == logger_id:
            selected_channel = dict(ch_row)
    if selected_channel is None and channels:
        selected_channel = dict(channels[0])

    can_edit = session.get("access_level") in (1, 3)
    tpl_ctx = {
        "site": site_row,
        "selected_logger": selected_logger,
        "selected_channel": selected_channel,
        "channels": channels,
        "can_edit": can_edit,
        "sensor_add_suggested_channel_index": db.next_channel_index(logger_id),
        "sensor_kinds": sensor_catalog.SENSOR_KINDS,
        "selected_sensor_kind_id": _resolved_selected_sensor_kind_id(
            selected_channel
        ),
        "tilt_mgmt_mm": sensor_catalog.tilt_management_defaults_mm(),
        "crack_mgmt_mm": sensor_catalog.crack_management_defaults_mm(),
        "surface_settlement_mgmt_mm": sensor_catalog.surface_settlement_management_defaults_mm(),
        "vibration_form_defaults": sensor_catalog.vibration_sensor_form_defaults(),
        "crack_calc_formula_1_default": sensor_catalog.CRACK_CALC_FORMULA_1_DEFAULT,
        "groundwater_calc_formula_1_default": sensor_catalog.GROUNDWATER_CALC_FORMULA_1_DEFAULT,
        "load_cell_calc_formula_1_default": sensor_catalog.LOAD_CELL_CALC_FORMULA_1_DEFAULT,
        "surface_settlement_calc_formula_1_default": sensor_catalog.SURFACE_SETTLEMENT_CALC_FORMULA_1_DEFAULT,
        "kind_template_defaults_map": sensor_catalog.kind_template_defaults_map_for_json(),
    }
    active_id = int(selected_channel["id"]) if selected_channel else None
    zones = (request.args.get("zones") or "sensor").strip().lower()
    detail_html = render_template(
        "partials/sensor_settings_detail_replaceable.html", **tpl_ctx
    )
    channels_aside_html = render_template(
        "partials/sensor_settings_channels_aside_replaceable.html", **tpl_ctx
    )
    payload = {
        "detail_html": detail_html,
        "channels_aside_html": channels_aside_html,
        "channel_id": active_id,
        "logger_id": logger_id,
    }
    if zones == "workspace":
        payload["logger_detail_html"] = render_template(
            "partials/sensor_settings_logger_detail_replaceable.html", **tpl_ctx
        )
    return jsonify(payload)


@app.route("/site/<int:site_id>/categories", methods=["GET", "POST"])
@login_required
def site_workspace_categories(site_id: int):
    _require_site(site_id)
    site = db.get_site(site_id)
    if not site:
        abort(404)
    if request.method == "POST":
        _require_site_edit(site_id)
        action = (request.form.get("action") or "").strip()
        try:
            if action == "add_major":
                name = (request.form.get("major_name") or "").strip()
                if not name:
                    flash("대분류명을 입력해 주세요.", "error")
                else:
                    gid = db.create_measurement_group(site_id, name, parent_id=None)
                    flash("대분류를 추가했습니다.")
                    return redirect(
                        url_for(
                            "site_workspace_categories",
                            site_id=site_id,
                            major_id=gid,
                        )
                    )
            elif action == "add_minor":
                major_id = request.form.get("major_id", type=int)
                name = (request.form.get("minor_name") or "").strip()
                if not major_id:
                    flash("소분류를 추가할 대분류를 선택해 주세요.", "error")
                elif not name:
                    flash("소분류명을 입력해 주세요.", "error")
                else:
                    minor_id = db.create_measurement_group(
                        site_id, name, parent_id=major_id
                    )
                    flash("소분류를 추가했습니다.")
                    return redirect(
                        url_for(
                            "site_workspace_categories",
                            site_id=site_id,
                            major_id=major_id,
                            minor_id=minor_id,
                        )
                    )
            elif action == "rename_major":
                major_id = request.form.get("major_id", type=int)
                name = (request.form.get("major_name") or "").strip()
                if not major_id:
                    flash("이름변경할 대분류를 선택해 주세요.", "error")
                elif not name:
                    flash("새 대분류명을 입력해 주세요.", "error")
                else:
                    db.rename_measurement_group(site_id, major_id, name)
                    flash("대분류명을 변경했습니다.")
                    return redirect(
                        url_for(
                            "site_workspace_categories",
                            site_id=site_id,
                            major_id=major_id,
                        )
                    )
            elif action == "rename_minor":
                major_id = request.form.get("major_id", type=int)
                minor_id = request.form.get("minor_id", type=int)
                name = (request.form.get("minor_name") or "").strip()
                if not major_id or not minor_id:
                    flash("이름변경할 소분류를 선택해 주세요.", "error")
                elif not name:
                    flash("새 소분류명을 입력해 주세요.", "error")
                else:
                    db.rename_measurement_group(site_id, minor_id, name)
                    flash("소분류명을 변경했습니다.")
                    return redirect(
                        url_for(
                            "site_workspace_categories",
                            site_id=site_id,
                            major_id=major_id,
                            minor_id=minor_id,
                        )
                    )
            elif action == "delete_major":
                major_id = request.form.get("major_id", type=int)
                if not major_id:
                    flash("삭제할 대분류를 선택해 주세요.", "error")
                else:
                    db.delete_measurement_group(site_id, major_id)
                    flash("대분류를 삭제했습니다.")
                    return redirect(url_for("site_workspace_categories", site_id=site_id))
            elif action == "delete_minor":
                major_id = request.form.get("major_id", type=int)
                minor_id = request.form.get("minor_id", type=int)
                if not minor_id:
                    flash("삭제할 소분류를 선택해 주세요.", "error")
                else:
                    db.delete_measurement_group(site_id, minor_id)
                    flash("소분류를 삭제했습니다.")
                    return redirect(
                        url_for(
                            "site_workspace_categories",
                            site_id=site_id,
                            major_id=major_id if major_id else None,
                        )
                    )
            elif action == "move_major":
                major_id = request.form.get("major_id", type=int)
                direction = (request.form.get("direction") or "").strip().lower()
                if not major_id:
                    flash("이동할 대분류를 선택해 주세요.", "error")
                else:
                    db.move_measurement_group(site_id, major_id, direction)
                    return redirect(
                        url_for(
                            "site_workspace_categories",
                            site_id=site_id,
                            major_id=major_id,
                        )
                    )
            elif action == "move_minor":
                major_id = request.form.get("major_id", type=int)
                minor_id = request.form.get("minor_id", type=int)
                direction = (request.form.get("direction") or "").strip().lower()
                if not minor_id:
                    flash("이동할 소분류를 선택해 주세요.", "error")
                else:
                    db.move_measurement_group(site_id, minor_id, direction)
                    return redirect(
                        url_for(
                            "site_workspace_categories",
                            site_id=site_id,
                            major_id=major_id if major_id else None,
                            minor_id=minor_id,
                        )
                    )
            elif action == "assign":
                major_id = request.form.get("major_id", type=int)
                minor_id = request.form.get("minor_id", type=int)
                channel_ids = request.form.getlist("unregistered_channel_ids")
                if not minor_id:
                    flash("배정할 소분류를 선택해 주세요.", "error")
                elif not channel_ids:
                    flash("등록할 센서를 선택해 주세요.", "error")
                else:
                    changed = db.set_sensor_channels_measurement_group(
                        site_id, [int(x) for x in channel_ids], minor_id
                    )
                    flash(f"{changed}개 센서를 소분류에 등록했습니다.")
                    return redirect(
                        url_for(
                            "site_workspace_categories",
                            site_id=site_id,
                            major_id=major_id if major_id else None,
                            minor_id=minor_id,
                        )
                    )
            elif action == "unassign":
                major_id = request.form.get("major_id", type=int)
                minor_id = request.form.get("minor_id", type=int)
                channel_ids = request.form.getlist("registered_channel_ids")
                if not channel_ids:
                    flash("해제할 센서를 선택해 주세요.", "error")
                else:
                    changed = db.set_sensor_channels_measurement_group(
                        site_id, [int(x) for x in channel_ids], None
                    )
                    flash(f"{changed}개 센서를 카테고리에서 해제했습니다.")
                    return redirect(
                        url_for(
                            "site_workspace_categories",
                            site_id=site_id,
                            major_id=major_id if major_id else None,
                            minor_id=minor_id if minor_id else None,
                        )
                    )
        except ValueError as e:
            code = str(e)
            if "duplicate_name" in code:
                flash("같은 위치에 동일한 이름이 이미 있습니다.", "error")
            elif "group_not_found" in code or "parent_not_found" in code:
                flash("선택한 카테고리를 찾을 수 없습니다.", "error")
            elif "invalid_direction" in code:
                flash("이동 방향이 올바르지 않습니다.", "error")
            else:
                flash("요청 처리 중 오류가 발생했습니다. 입력값을 확인해 주세요.", "error")
        return redirect(url_for("site_workspace_categories", site_id=site_id))

    groups = db.list_measurement_groups(site_id)
    channels = db.list_sensor_channels_for_site(site_id)
    majors = [g for g in groups if g.get("parent_id") is None]
    minors_by_major: dict[int, list[dict]] = {}
    for g in groups:
        pid = g.get("parent_id")
        if pid is None:
            continue
        k = int(pid)
        minors_by_major.setdefault(k, []).append(g)
    for k in minors_by_major:
        minors_by_major[k].sort(key=lambda x: (x.get("sort_order") or 0, x.get("name") or ""))
    majors.sort(key=lambda x: (x.get("sort_order") or 0, x.get("name") or ""))

    selected_major_id = request.args.get("major_id", type=int)
    if not selected_major_id and majors:
        selected_major_id = int(majors[0]["id"])
    selected_major = None
    if selected_major_id:
        selected_major = next((m for m in majors if int(m["id"]) == selected_major_id), None)
    selected_minors = minors_by_major.get(int(selected_major_id), []) if selected_major_id else []
    selected_minor_id = request.args.get("minor_id", type=int)
    if not selected_minor_id and selected_minors:
        selected_minor_id = int(selected_minors[0]["id"])
    selected_minor = None
    if selected_minor_id:
        selected_minor = next((m for m in selected_minors if int(m["id"]) == selected_minor_id), None)

    registered_channels: list[dict] = []
    unregistered_channels: list[dict] = []
    if selected_minor:
        sel_gid = int(selected_minor["id"])
        for ch in channels:
            if (ch.get("measurement_group_id") is not None) and int(ch.get("measurement_group_id")) == sel_gid:
                registered_channels.append(ch)
            else:
                unregistered_channels.append(ch)
    else:
        unregistered_channels = channels

    def _ch_sort_key(ch: dict) -> tuple:
        return (
            int(ch.get("channel_index") or 0),
            int(ch.get("id") or 0),
        )

    registered_channels.sort(key=_ch_sort_key)
    unregistered_channels.sort(key=_ch_sort_key)
    return render_template(
        "site_workspace_categories.html",
        username=_username(),
        site=site,
        nav_active="site_workspace",
        header_breadcrumb=f"{site.get('org_name') or ''} · 카테고리",
        account_url=_account_url(),
        site_list_url=url_for("site_list", org_id=int(site["organization_id"])),
        majors=majors,
        minors=selected_minors,
        selected_major=selected_major,
        selected_minor=selected_minor,
        registered_channels=registered_channels,
        unregistered_channels=unregistered_channels,
    )


@legacy_bp.route("/account")
@login_required
def account_settings():
    uid = session.get("survey_user_id")
    row = db.get_portal_user(uid) if uid else None
    if not row:
        abort(404)
    return render_template(
        "account_settings.html",
        username=_username(),
        nav_active="account",
        header_breadcrumb="계정 설정",
        user_row=row,
    )


@legacy_bp.route("/sites", methods=["GET", "POST"])
@login_required
def sites_list():
    """구형 업체·현장 일괄 화면 폐지. 북마크·POST 는 신규 메뉴로 안내."""
    if request.method == "POST":
        flash("업체·현장 관리는 «업체 리스트»·«현장 리스트»에서 이용해 주세요.", "error")
    return redirect(url_for("organization_list"))


@legacy_bp.route("/sites/<int:site_id>/loggers", methods=["GET", "POST"])
@login_required
def site_loggers(site_id: int):
    """구형 로거 목록 화면 폐지. 북마크는 현장 센서설정으로 연결."""
    if not db.get_site(site_id):
        abort(404)
    _require_site(site_id)
    if request.method == "POST":
        flash("로거·센서 설정은 현장 «센서설정»에서 이용해 주세요.", "error")
    return redirect(url_for("site_workspace_sensor_settings", site_id=site_id))


@legacy_bp.route("/loggers/<int:logger_id>/settings", methods=["GET", "POST"])
@login_required
def logger_settings(logger_id: int):
    lg = db.get_logger(logger_id)
    if not lg:
        abort(404)
    _require_site(int(lg["site_id"]))
    if request.method == "POST":
        _require_site_edit(int(lg["site_id"]))
        path = (request.form.get("folder_path") or "").strip() or None
        tc = request.form.get("time_column_index", type=int)
        fdc = request.form.get("first_data_column_index", type=int)
        kind = (request.form.get("logger_kind") or lg["logger_kind"]).strip()
        if kind not in ("manual", "ftp", "other"):
            kind = lg["logger_kind"]
        serial = (request.form.get("serial_number") or "").strip() or None
        memo = (request.form.get("memo") or "").strip() or None
        db.update_logger(
            logger_id,
            folder_path=path,
            time_column_index=tc,
            first_data_column_index=fdc,
            logger_kind=kind,
            serial_number=serial,
            memo=memo,
        )
        flash("로거 설정을 저장했습니다.")
        return redirect(url_for(".logger_settings", logger_id=logger_id))

    site_row = db.get_site(int(lg["site_id"]))
    if not site_row:
        abort(404)
    return render_template(
        "logger_settings.html",
        username=_username(),
        nav_active="site_workspace",
        header_breadcrumb=f"로거 설정 · {lg['name']}",
        logger=lg,
        site_list_url=url_for(
            "site_list", org_id=int(site_row["organization_id"])
        ),
    )


@legacy_bp.route("/loggers/<int:logger_id>/sensors", methods=["GET", "POST"])
@login_required
def logger_sensors(logger_id: int):
    lg = db.get_logger(logger_id)
    if not lg:
        abort(404)
    _require_site(int(lg["site_id"]))
    if request.method == "POST":
        _require_site_edit(int(lg["site_id"]))
        label = (request.form.get("label") or "").strip()
        ch_idx = request.form.get("channel_index", type=int)
        if not label or ch_idx is None:
            flash("라벨과 칼럼 번호는 필수입니다.", "error")
        elif ch_idx < 0:
            flash("칼럼 번호는 0 이상이어야 합니다.", "error")
        else:
            sk = (request.form.get("sensor_kind") or "").strip() or None
            unit = (request.form.get("unit") or "").strip() or None
            sk_f = request.form.get("scale_k", type=float)
            sb_f = request.form.get("scale_b", type=float)
            mg_id = request.form.get("measurement_group_id", type=int)
            try:
                db.create_sensor_channel(
                    logger_id,
                    ch_idx,
                    label,
                    sensor_kind=sk,
                    unit=unit,
                    scale_k=sk_f if sk_f is not None else 1.0,
                    scale_b=sb_f if sb_f is not None else 0.0,
                    measurement_group_id=mg_id if mg_id else None,
                    is_active=1,
                )
                flash("센서 채널이 추가되었습니다.")
            except db.SensorCodeDuplicateError:
                flash(
                    "이 현장에 동일한 센서코드가 이미 있습니다. 라벨(코드)을 바꿔 주세요.",
                    "error",
                )
            except sqlite3.IntegrityError:
                flash("이 로거에 같은 칼럼 번호(channel_index)가 이미 있습니다.", "error")
        return redirect(url_for(".logger_sensors", logger_id=logger_id))

    groups = db.list_measurement_groups(lg["site_id"])
    kinds = sensor_catalog.kinds_for_api()
    site_row = db.get_site(int(lg["site_id"]))
    if not site_row:
        abort(404)
    return render_template(
        "logger_sensors.html",
        username=_username(),
        nav_active="site_workspace",
        header_breadcrumb=f"센서 채널 · {lg['name']}",
        logger=lg,
        channels=db.list_sensor_channels(logger_id),
        groups=groups,
        kinds=kinds,
        site_list_url=url_for(
            "site_list", org_id=int(site_row["organization_id"])
        ),
    )


@legacy_bp.route("/channels/<int:channel_id>/chart")
@login_required
def channel_chart(channel_id: int):
    ch = db.get_sensor_channel(channel_id)
    if not ch:
        abort(404)
    _require_site(int(ch["site_id"]))
    _uid, lvl = _session_uid_level()
    sk = (ch.get("sensor_kind") or "").strip()
    ch_tilt_chart = sensor_catalog.sensor_kind_supports_tilt_derived_table(sk)
    ch_inclinometer_chart = (
        sensor_catalog.sensor_kind_supports_inclinometer_derived_table(sk)
    )
    ch_crack_chart = sensor_catalog.sensor_kind_supports_crack_derived_table(sk)
    ch_flow_chart = sensor_catalog.sensor_kind_supports_flow_derived_table(sk)
    ch_groundwater_chart = sensor_catalog.sensor_kind_supports_groundwater_derived_table(sk)
    kd_v = sensor_catalog.kind_by_id(sk)
    ch_vibration_3axis = (kd_v or {}).get("id") == "vibration_3axis"
    ch_vibration_scalar_pvs = (kd_v or {}).get("id") == "vibration"
    cy_min, cy_max = sensor_catalog.effective_chart_y_bounds_for_kind(
        sk,
        ch.get("chart_y_min"),
        ch.get("chart_y_max"),
    )
    site_row = db.get_site(int(ch["site_id"]))
    if not site_row:
        abort(404)
    mx = db.latest_observed_at_by_channel([channel_id])
    channel_latest_observed = mx.get(channel_id)
    return render_template(
        "channel_chart.html",
        username=_username(),
        nav_active="site_workspace",
        header_breadcrumb=f"그래프 · {sensor_catalog.channel_auto_label(dict(ch))}",
        channel=ch,
        channel_latest_observed=channel_latest_observed,
        site_list_url=url_for(
            "site_list", org_id=int(site_row["organization_id"])
        ),
        account_url=_account_url(),
        channel_can_purge=db.user_can_edit_site(int(lvl)),
        channel_tilt_chart=ch_tilt_chart,
        channel_inclinometer_chart=ch_inclinometer_chart,
        channel_crack_chart=ch_crack_chart,
        channel_flow_chart=ch_flow_chart,
        channel_groundwater_chart=ch_groundwater_chart,
        channel_vibration_3axis=ch_vibration_3axis,
        channel_vibration_scalar_pvs=ch_vibration_scalar_pvs,
        channel_chart_y_min_eff=cy_min,
        channel_chart_y_max_eff=cy_max,
        channel_mgmt_levels=sensor_catalog.mgmt_levels_for_chart(dict(ch)),
    )


@legacy_bp.route("/admin/users")
@login_required
@admin_required
def admin_users_list():
    """계정설정: 왼쪽 목록 + 오른쪽 상세. 계정이 있으면 첫 계정(아이디순) 선택."""
    users = db.list_portal_users()
    if not users:
        return redirect(url_for(".admin_user_new"))
    return redirect(url_for(".admin_user_edit", user_id=users[0]["id"]))


@legacy_bp.route("/admin/users/new", methods=["GET", "POST"])
@login_required
@admin_required
def admin_user_new():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        display_name = (request.form.get("display_name") or "").strip() or None
        raw_lv = request.form.get("access_level")
        try:
            level = int(raw_lv) if raw_lv not in (None, "") else 4
        except (TypeError, ValueError):
            level = 4
        if level not in (1, 3, 4):
            level = 4
        memo = (request.form.get("memo") or "").strip() or None
        site_ids = request.form.getlist("site_ids", type=int)
        if not username or not password:
            flash("아이디와 비밀번호는 필수입니다.", "error")
        else:
            try:
                uid = db.create_portal_user(
                    username,
                    password,
                    display_name=display_name,
                    access_level=level,
                    role=_level_to_role(level),
                    memo=memo,
                )
                if level != 1:
                    db.replace_portal_user_sites(uid, site_ids)
                flash("계정을 추가했습니다.")
                return redirect(url_for(".admin_user_edit", user_id=uid))
            except sqlite3.IntegrityError:
                flash("이미 있는 아이디입니다.", "error")
        return redirect(url_for(".admin_user_new"))

    return render_template(
        "admin_user_form.html",
        username=_username(),
        client_ip=_client_ip(),
        nav_active="admin",
        header_breadcrumb="계정설정",
        user_row=None,
        site_ids=[],
        all_sites=db.list_sites(),
        all_users=db.list_portal_users(),
        selected_user_id=None,
        is_new=True,
    )


@legacy_bp.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_user_edit(user_id: int):
    row = db.get_portal_user(user_id)
    if not row:
        abort(404)
    if request.method == "POST":
        if request.form.get("action") == "delete":
            if user_id == session.get("survey_user_id"):
                flash("본인 계정은 삭제할 수 없습니다.", "error")
            else:
                db.delete_portal_user(user_id)
                flash("계정을 삭제했습니다.")
                return redirect(url_for(".admin_users_list"))
            return redirect(url_for(".admin_user_edit", user_id=user_id))

        display_name = (request.form.get("display_name") or "").strip() or None
        raw_lv = request.form.get("access_level")
        try:
            level = int(raw_lv) if raw_lv not in (None, "") else int(row["access_level"])
        except (TypeError, ValueError):
            level = int(row["access_level"])
        if level not in (1, 3, 4):
            level = int(row["access_level"])
        memo = (request.form.get("memo") or "").strip() or None
        is_active = 1 if request.form.get("is_active") == "1" else 0
        site_ids = request.form.getlist("site_ids", type=int)
        pwd = request.form.get("password") or ""
        db.update_portal_user_fields(
            user_id,
            display_name=display_name,
            access_level=level,
            role=_level_to_role(level),
            memo=memo,
            is_active=is_active,
        )
        if pwd:
            db.set_portal_user_password(user_id, pwd)
        if level == 1:
            db.replace_portal_user_sites(user_id, [])
        else:
            db.replace_portal_user_sites(user_id, site_ids)
        flash("저장했습니다.")
        return redirect(url_for(".admin_user_edit", user_id=user_id))

    site_ids = db.get_portal_user_site_ids(user_id)
    return render_template(
        "admin_user_form.html",
        username=_username(),
        client_ip=_client_ip(),
        nav_active="admin",
        header_breadcrumb="계정설정",
        user_row=row,
        site_ids=site_ids,
        all_sites=db.list_sites(),
        all_users=db.list_portal_users(),
        selected_user_id=user_id,
        is_new=False,
    )


@legacy_bp.route("/api/db/summary")
@login_required
def api_db_summary():
    uid, lvl = _session_uid_level()
    return jsonify(db.get_dashboard_stats(user_id=uid, access_level=lvl))


@legacy_bp.route("/api/sensor-kinds")
@login_required
def api_sensor_kinds():
    """센서 추가 화면 드롭다운용 — DB sensor_kind 에 넣는 id 와 동일."""
    return jsonify({"kinds": sensor_catalog.kinds_for_api()})


@legacy_bp.route("/api/measurements/series")
@login_required
def api_measurement_series():
    """그래프용 시계열 (sensor_channel_id, 선택 구간, limit)."""
    ch = request.args.get("sensor_channel_id", type=int)
    if not ch:
        return jsonify({"error": "sensor_channel_id 가 필요합니다."}), 400
    meta = db.get_sensor_channel(ch)
    if not meta:
        return jsonify({"error": "센서 채널을 찾을 수 없습니다."}), 404
    uid, lvl = _session_uid_level()
    if not db.user_can_access_site(uid, lvl, int(meta["site_id"])):
        return jsonify({"error": "접근 권한이 없습니다."}), 403
    t_from = (request.args.get("from") or "").strip() or None
    t_to = (request.args.get("to") or "").strip() or None
    limit = request.args.get("limit", type=int) or 5000
    rows = db.get_measurement_series(ch, t_from, t_to, limit=limit)
    sk = (meta.get("sensor_kind") or "").strip()
    crack_table = sensor_catalog.sensor_kind_supports_crack_derived_table(sk)
    tilt_table = sensor_catalog.sensor_kind_supports_tilt_derived_table(sk)
    inclinometer_table = sensor_catalog.sensor_kind_supports_inclinometer_derived_table(
        sk
    )
    flow_table = sensor_catalog.sensor_kind_supports_flow_derived_table(sk)
    load_cell_table = sensor_catalog.sensor_kind_supports_load_cell_derived_table(sk)
    surface_settlement_table = sensor_catalog.sensor_kind_supports_surface_settlement_derived_table(sk)
    groundwater_table = sensor_catalog.sensor_kind_supports_groundwater_derived_table(sk)
    if crack_table and rows:
        rows = sensor_catalog.enrich_crack_measurement_rows(rows)
    elif groundwater_table and rows:
        rows = sensor_catalog.enrich_groundwater_measurement_rows(rows)
    elif load_cell_table and rows:
        rows = sensor_catalog.enrich_load_cell_measurement_rows(rows)
    elif surface_settlement_table and rows:
        rows = sensor_catalog.enrich_surface_settlement_measurement_rows(rows)
    elif flow_table and rows:
        rows = sensor_catalog.enrich_flow_meter_measurement_rows(rows)
    elif tilt_table and rows:
        rows = sensor_catalog.enrich_tilt_measurement_rows(rows)
    elif inclinometer_table and rows:
        rows = sensor_catalog.enrich_inclinometer_measurement_rows(rows)
    return jsonify(
        {
            "sensor_channel_id": ch,
            "sensor_kind": sk or None,
            "crack_table": crack_table,
            "tilt_table": tilt_table,
            "inclinometer_table": inclinometer_table,
            "flow_table": flow_table,
            "load_cell_table": load_cell_table,
            "surface_settlement_table": surface_settlement_table,
            "groundwater_table": groundwater_table,
            "points": rows,
            "count": len(rows),
        }
    )


def _series_payload_for_channel_row(
    ch_id: int,
    meta: dict,
    t_from: str | None,
    t_to: str | None,
    limit: int,
) -> dict:
    rows = db.get_measurement_series(ch_id, t_from, t_to, limit=limit)
    sk = (meta.get("sensor_kind") or "").strip()
    crack_table = sensor_catalog.sensor_kind_supports_crack_derived_table(sk)
    tilt_table = sensor_catalog.sensor_kind_supports_tilt_derived_table(sk)
    inclinometer_table = sensor_catalog.sensor_kind_supports_inclinometer_derived_table(
        sk
    )
    flow_table = sensor_catalog.sensor_kind_supports_flow_derived_table(sk)
    load_cell_table = sensor_catalog.sensor_kind_supports_load_cell_derived_table(sk)
    surface_settlement_table = sensor_catalog.sensor_kind_supports_surface_settlement_derived_table(sk)
    groundwater_table = sensor_catalog.sensor_kind_supports_groundwater_derived_table(sk)
    if crack_table and rows:
        rows = sensor_catalog.enrich_crack_measurement_rows(rows)
    elif groundwater_table and rows:
        rows = sensor_catalog.enrich_groundwater_measurement_rows(rows)
    elif load_cell_table and rows:
        rows = sensor_catalog.enrich_load_cell_measurement_rows(rows)
    elif surface_settlement_table and rows:
        rows = sensor_catalog.enrich_surface_settlement_measurement_rows(rows)
    elif flow_table and rows:
        rows = sensor_catalog.enrich_flow_meter_measurement_rows(rows)
    elif tilt_table and rows:
        rows = sensor_catalog.enrich_tilt_measurement_rows(rows)
    elif inclinometer_table and rows:
        rows = sensor_catalog.enrich_inclinometer_measurement_rows(rows)
    code = (meta.get("sensor_code") or "").strip() or f"CH{ch_id}"
    dp = meta.get("decimal_places")
    try:
        dp_i = int(dp) if dp is not None else 2
    except (TypeError, ValueError):
        dp_i = 2
    return {
        "sensor_channel_id": ch_id,
        "sensor_code": code,
        "unit": (meta.get("unit") or "") or None,
        "decimal_places": dp_i,
        "sensor_kind": sk or None,
        "crack_table": crack_table,
        "tilt_table": tilt_table,
        "inclinometer_table": inclinometer_table,
        "flow_table": flow_table,
        "load_cell_table": load_cell_table,
        "surface_settlement_table": surface_settlement_table,
        "groundwater_table": groundwater_table,
        "points": rows,
        "count": len(rows),
    }


@legacy_bp.route("/api/measurements/series-bundle")
@login_required
def api_measurement_series_bundle():
    """대표 센서 + 연결센서코드에 묶인 채널들의 시계열(같은 구간)."""
    ch = request.args.get("sensor_channel_id", type=int)
    if not ch:
        return jsonify({"error": "sensor_channel_id 가 필요합니다."}), 400
    primary = db.get_sensor_channel(ch)
    if not primary:
        return jsonify({"error": "센서 채널을 찾을 수 없습니다."}), 404
    uid, lvl = _session_uid_level()
    site_id = int(primary["site_id"])
    if not db.user_can_access_site(uid, lvl, site_id):
        return jsonify({"error": "접근 권한이 없습니다."}), 403
    t_from = (request.args.get("from") or "").strip() or None
    t_to = (request.args.get("to") or "").strip() or None
    limit = request.args.get("limit", type=int) or 5000
    bundle_rows, missing = db.resolve_measurement_bundle_channels(dict(primary))
    channels_out: list[dict] = []
    for meta in bundle_rows:
        cid = int(meta["id"])
        if not db.user_can_access_site(uid, lvl, int(meta["site_id"])):
            return jsonify({"error": "연결된 센서에 대한 접근 권한이 없습니다."}), 403
        channels_out.append(
            _series_payload_for_channel_row(cid, meta, t_from, t_to, limit)
        )
    vb = sensor_catalog.vibration_3axis_bundle_block(channels_out)
    resp: dict = {
        "primary_sensor_channel_id": ch,
        "missing_linked_codes": missing,
        "channels": channels_out,
    }
    if vb is not None:
        resp["vibration_3axis"] = vb
    return jsonify(resp)


@legacy_bp.route("/api/measurements/purge", methods=["POST"])
@login_required
def api_measurements_purge():
    """구간 내 측정행 삭제 + measurement_purge_log 기록."""
    body = request.get_json(force=True, silent=True) or {}
    t_from = (body.get("time_from") or "").strip()
    t_to = (body.get("time_to") or "").strip()
    note = body.get("note")
    if isinstance(note, str):
        note = note.strip() or None
    else:
        note = None
    if not t_from or not t_to:
        return jsonify({"error": "time_from, time_to 가 필요합니다."}), 400

    if not db.user_can_edit_site(int(session.get("access_level") or 4)):
        return jsonify({"error": "삭제 권한이 없습니다."}), 403

    sid = body.get("sensor_channel_id")
    lid = body.get("logger_device_id")
    if sid is not None and lid is not None:
        return jsonify(
            {"error": "sensor_channel_id 와 logger_device_id 는 동시에 쓸 수 없습니다."}
        ), 400
    if sid is None and lid is None:
        return jsonify(
            {"error": "sensor_channel_id 또는 logger_device_id 가 필요합니다."}
        ), 400

    conn = db.connect()
    try:
        if sid is not None:
            try:
                ch_id = int(sid)
            except (TypeError, ValueError):
                return jsonify({"error": "sensor_channel_id 가 올바르지 않습니다."}), 400
            meta = db.get_sensor_channel(ch_id)
            if not meta:
                return jsonify({"error": "센서를 찾을 수 없습니다."}), 404
            if not db.user_can_access_site(
                *_session_uid_level(), int(meta["site_id"])
            ):
                return jsonify({"error": "접근 권한이 없습니다."}), 403
            deleted = db.purge_measurements_by_sensor(
                conn, ch_id, t_from, t_to, note=note
            )
        else:
            try:
                log_id = int(lid)
            except (TypeError, ValueError):
                return jsonify({"error": "logger_device_id 가 올바르지 않습니다."}), 400
            lg = db.get_logger(log_id)
            if not lg:
                return jsonify({"error": "로거를 찾을 수 없습니다."}), 404
            if not db.user_can_access_site(
                *_session_uid_level(), int(lg["site_id"])
            ):
                return jsonify({"error": "접근 권한이 없습니다."}), 403
            deleted = db.purge_measurements_by_logger(
                conn, log_id, t_from, t_to, note=note
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"deleted": deleted, "time_from": t_from, "time_to": t_to})


app.register_blueprint(legacy_bp)


# 예전 북마크·링크 호환: 루트 URL → /legacy 동일 경로
@app.route("/dashboard")
def _redirect_root_dashboard():
    return redirect(url_for("organization_list"), 302)


@app.route("/account")
def _redirect_root_account():
    return redirect(url_for("legacy.account_settings"), 302)


@app.route("/sites", methods=["GET", "POST", "HEAD", "OPTIONS"])
def _redirect_root_sites():
    return redirect(url_for("organization_list"), 307)


@app.route("/sites/<int:site_id>/loggers", methods=["GET", "POST", "HEAD", "OPTIONS"])
def _redirect_root_site_loggers(site_id: int):
    return redirect(url_for("site_workspace_sensor_settings", site_id=site_id), 307)


@app.route("/loggers/<int:logger_id>/settings", methods=["GET", "POST", "HEAD", "OPTIONS"])
def _redirect_root_logger_settings(logger_id: int):
    return redirect(url_for("legacy.logger_settings", logger_id=logger_id), 307)


@app.route("/loggers/<int:logger_id>/sensors", methods=["GET", "POST", "HEAD", "OPTIONS"])
def _redirect_root_logger_sensors(logger_id: int):
    return redirect(url_for("legacy.logger_sensors", logger_id=logger_id), 307)


@app.route("/channels/<int:channel_id>/chart", methods=["GET", "HEAD", "OPTIONS"])
def _redirect_root_channel_chart(channel_id: int):
    return redirect(url_for("legacy.channel_chart", channel_id=channel_id), 302)


@app.route("/admin/users")
def _redirect_root_admin_users():
    return redirect(url_for("legacy.admin_users_list"), 302)


@app.route("/admin/users/new", methods=["GET", "POST", "HEAD", "OPTIONS"])
def _redirect_root_admin_users_new():
    return redirect(url_for("legacy.admin_user_new"), 307)


@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST", "HEAD", "OPTIONS"])
def _redirect_root_admin_user_edit(user_id: int):
    return redirect(url_for("legacy.admin_user_edit", user_id=user_id), 307)


@app.route("/api/db/summary", methods=["GET", "HEAD", "OPTIONS"])
def _redirect_api_summary():
    return redirect(url_for("legacy.api_db_summary"), 302)


@app.route("/api/sensor-kinds", methods=["GET", "HEAD", "OPTIONS"])
def _redirect_api_kinds():
    return redirect(url_for("legacy.api_sensor_kinds"), 302)


@app.route("/api/measurements/series", methods=["GET", "HEAD", "OPTIONS"])
def _redirect_api_series():
    return redirect(
        url_for("legacy.api_measurement_series", **request.args.to_dict()),
        302,
    )


@app.route("/api/measurements/purge", methods=["POST", "OPTIONS"])
def _redirect_api_purge():
    return redirect(url_for("legacy.api_measurements_purge"), 307)


def _print_lan_access_hints(port: int, host: str) -> None:
    """0.0.0.0 등 전체 바인드 시 로컬·LAN 접속 주소 안내."""
    if host not in ("0.0.0.0", "::"):
        return
    print(
        f"[안내] 이 PC 브라우저: http://127.0.0.1:{port}/",
        flush=True,
    )
    candidates: list[str] = []
    try:
        import socket

        hn = socket.gethostname()
        for ai in socket.getaddrinfo(hn, None, socket.AF_INET):
            ip = ai[4][0]
            if ip and not ip.startswith("127."):
                candidates.append(ip)
    except Exception:
        pass
    candidates = sorted(set(candidates))
    if candidates:
        for ip in candidates[:8]:
            print(f"[안내] 같은 네트워크 다른 PC: http://{ip}:{port}/", flush=True)
    else:
        print(
            f"[안내] 다른 PC에서는 이 컴퓨터 LAN IPv4 로 접속 (예: http://192.168.0.x:{port}/)",
            flush=True,
        )
    print(
        "[안내] 방화벽에서 위 포트 인바운드 허용 필요할 수 있습니다.",
        flush=True,
    )


def main():
    port = 8765
    host = "127.0.0.1"
    print(
        f"[계측관리 포털] 로컬 서버 시작 중...",
        flush=True,
    )
    print(
        f"[안내] 브라우저로 접속: http://{host}:{port}/",
        flush=True,
    )
    print(
        f"[버전] {portal_version.VERSION_LABEL}",
        flush=True,
    )
    print(f"[앱 경로] {_APP_DIR}", flush=True)
    print(f"[DB] {db.get_db_path()}", flush=True)
    app.run(
        host=host,
        port=port,
        debug=True,
        use_reloader=True,
    )


if __name__ == "__main__":
    main()
