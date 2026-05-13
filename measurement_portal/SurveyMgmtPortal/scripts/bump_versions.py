"""
계측관리 통합시스템 — 웹(`portal_version.py`) / 데이터수집(`collector_version.py`) patch 버전 올리기.

실행 위치: `SurveyMgmtPortal` 폴더(또는 그 상위에서 경로만 맞으면 됨).

  python scripts/bump_versions.py auto       # git 변경 파일 기준으로 해당 쪽만 +1
  python scripts/bump_versions.py portal     # 웹 포털만
  python scripts/bump_versions.py collector    # 수집 프로그램만
  python scripts/bump_versions.py both        # 둘 다 +1

auto 는 `git diff --name-only HEAD` 를 씁니다. 커밋 전 변경분도 포함하려면 스테이징 여부와 관계없이
working tree 기준으로 하려면 아래처럼 할 수 있습니다(미구현이면 `portal`/`collector` 수동 권장).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # SurveyMgmtPortal
_PORTAL_VER = _ROOT / "portal_version.py"
_COLLECTOR_VER = _ROOT / "scripts" / "collector_version.py"

PATCH_RE = re.compile(r"^(VERSION_PATCH)\s*=\s*(\d+)\s*$", re.MULTILINE)


def _bump_patch_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = PATCH_RE.search(text)
    if not m:
        raise SystemExit(f"VERSION_PATCH 를 찾을 수 없습니다: {path}")
    old = int(m.group(2))
    new = old + 1
    text2 = PATCH_RE.sub(rf"\1 = {new}", text, count=1)
    path.write_text(text2, encoding="utf-8")
    return f"{path.name}: {old} → {new}"


def _git_changed_paths(git_root: Path) -> list[str]:
    r = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=str(git_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if r.returncode != 0:
        return []
    return [ln.strip().replace("\\", "/") for ln in r.stdout.splitlines() if ln.strip()]


def _find_git_root() -> Path | None:
    for d in [_ROOT, *_ROOT.parents]:
        if (d / ".git").exists():
            return d
    return None


def _classify_auto(paths: list[str]) -> tuple[bool, bool]:
    bump_portal = False
    bump_collector = False
    portal_needles = (
        "SurveyMgmtPortal/app.py",
        "SurveyMgmtPortal/wsgi.py",
        "SurveyMgmtPortal/db.py",
        "SurveyMgmtPortal/portal_version.py",
        "SurveyMgmtPortal/sensor_catalog.py",
        "SurveyMgmtPortal/schema.sql",
        "SurveyMgmtPortal/templates/",
        "SurveyMgmtPortal/static/",
    )
    collector_needles = (
        "SurveyMgmtPortal/scripts/measurement_ingest",
        "SurveyMgmtPortal/scripts/collector_version.py",
        "SurveyMgmtPortal/auto_db_upload_gui.bat",
    )
    for p in paths:
        p = p.replace("\\", "/")
        if any(n in p for n in portal_needles):
            bump_portal = True
        if any(n in p for n in collector_needles):
            bump_collector = True
    return bump_portal, bump_collector


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    mode = sys.argv[1].strip().lower()
    do_portal = False
    do_collector = False
    if mode == "portal":
        do_portal = True
    elif mode in ("collector", "ingest", "data"):
        do_collector = True
    elif mode in ("both", "all"):
        do_portal = do_collector = True
    elif mode == "auto":
        git_root = _find_git_root()
        if not git_root:
            print("git 저장소를 찾지 못했습니다. `portal` / `collector` / `both` 를 지정하세요.", file=sys.stderr)
            raise SystemExit(1)
        paths = _git_changed_paths(git_root)
        do_portal, do_collector = _classify_auto(paths)
        if not do_portal and not do_collector:
            print(
                "변경된 파일에서 포털/수집 구분이 없습니다. "
                "커밋 전이면 `both` 또는 수정한 쪽을 명시하세요.\n"
                f"(git diff --name-only HEAD 줄 수: {len(paths)})"
            )
            raise SystemExit(1)
        print(f"[auto] 감지: portal={do_portal}, collector={do_collector}")
    else:
        print(__doc__)
        raise SystemExit(2)

    out = []
    if do_portal:
        out.append(_bump_patch_file(_PORTAL_VER))
    if do_collector:
        out.append(_bump_patch_file(_COLLECTOR_VER))
    for line in out:
        print(line)


if __name__ == "__main__":
    main()
