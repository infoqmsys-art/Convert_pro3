"""Fill hourly CSV F-4/F-5 columns from a daily flowmeter PDF report.

고척 기본값:
  F-4 -> CSV index 18 (AmountCH2)
  F-5 -> CSV index 19 (AmountCH3)

Usage:
  python tools/flowmeter_pdf_fill.py --pdf <report.pdf> --csv <1220262001.csv>
  python tools/flowmeter_pdf_fill.py --pdf <report.pdf> --csv <file.csv> --dry-run
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pdfplumber

DATE_RE = re.compile(r"^(20\d{2}-\d{2}-\d{2})$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
METER_RE = re.compile(r"F-\d+")

# Dual-meter table headers (누적 F-3 / 누적 F-4) from 고척 Flowmeter Report.
F4_CUMUL_X = 242.2
Y_GROUP_TOL = 3.0
DATE_VALUE_Y_MAX = 8.0
TABLE_X_MIN = 180.0
X_ASSIGN_MAX = 30.0

DEFAULT_COLUMNS = {"F-4": 18, "F-5": 19}
HOLD_UNTIL_HOUR = 16


def _fnum(text: str) -> float:
    return float(text)


def _parse_ts(raw: str) -> datetime:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return datetime.strptime(raw, "%Y-%m-%d %H:%M")


def _format_value(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text


def _group_words_by_y(words: list[dict], tol: float = Y_GROUP_TOL) -> list[tuple[float, list[dict]]]:
    items = sorted(words, key=lambda w: (w["top"], w["x0"]))
    groups: list[tuple[float, list[dict]]] = []
    for word in items:
        y = word["top"]
        if groups and abs(y - groups[-1][0]) <= tol:
            groups[-1][1].append(word)
        else:
            groups.append((y, [word]))
    return groups


def _page_meters(words: list[dict]) -> list[str]:
    """Read meter ids from the top header, not from the data-table column labels."""
    top = [w for w in words if w["top"] < 140]
    text = " ".join(w["text"] for w in sorted(top, key=lambda w: (w["top"], w["x0"])))
    seen: list[str] = []
    for meter in METER_RE.findall(text):
        if meter not in seen:
            seen.append(meter)
    if seen:
        return seen
    seen = []
    for meter in METER_RE.findall(" ".join(w["text"] for w in words[:80])):
        if meter not in seen:
            seen.append(meter)
    return seen


def _nearest_date(dates: list[tuple[float, str]], value_y: float) -> str | None:
    best = None
    best_gap = DATE_VALUE_Y_MAX
    for y, date in dates:
        gap = value_y - y
        if -1.0 <= gap <= DATE_VALUE_Y_MAX and gap <= best_gap:
            best = date
            best_gap = gap
    return best


def parse_flowmeter_pdf(pdf_path: Path) -> dict[str, dict[str, float]]:
    """Return {meter_id: {YYYY-MM-DD: cumulative_m3}}."""
    series: dict[str, dict[str, float]] = defaultdict(dict)
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False) or []
            if not words:
                continue
            meters = _page_meters(words)
            groups = _group_words_by_y(words)
            dates: list[tuple[float, str]] = []
            for y, row in groups:
                texts = [w["text"] for w in sorted(row, key=lambda w: w["x0"])]
                joined = " ".join(texts)
                m = re.search(r"(20\d{2}-\d{2}-\d{2})", joined)
                if m:
                    dates.append((y, m.group(1)))

            for y, row in groups:
                nums = [
                    w
                    for w in row
                    if NUM_RE.match(w["text"]) and w["x0"] >= TABLE_X_MIN
                ]
                if not nums:
                    continue
                date = _nearest_date(dates, y)
                if not date:
                    continue

                if len(meters) == 1:
                    leftmost = min(nums, key=lambda w: w["x0"])
                    series[meters[0]][date] = _fnum(leftmost["text"])
                    continue

                if "F-4" in meters:
                    f4 = min(
                        nums,
                        key=lambda w: abs(((w["x0"] + w["x1"]) / 2) - F4_CUMUL_X),
                    )
                    center = (f4["x0"] + f4["x1"]) / 2
                    if abs(center - F4_CUMUL_X) <= X_ASSIGN_MAX:
                        series["F-4"][date] = _fnum(f4["text"])
    return {k: dict(v) for k, v in series.items()}


def detect_cutoff(
    rows: list[list[str]],
    pdf_f4: dict[str, float],
    pdf_f5: dict[str, float],
    col_f4: int,
    col_f5: int,
    hold_until_hour: int = HOLD_UNTIL_HOUR,
) -> datetime | None:
    """Last already-filled timestamp.

    Last calendar date whose CSV F-4/F-5 match that day's PDF, then hold
    those values through the next day at hold_until_hour (고척: 16:00).
    """
    last_match_date = None
    for row in rows:
        if len(row) <= max(col_f4, col_f5):
            continue
        try:
            ts = _parse_ts(row[0])
            f4 = float(row[col_f4])
            f5 = float(row[col_f5])
        except (ValueError, TypeError):
            continue
        day = ts.strftime("%Y-%m-%d")
        if day in pdf_f4 and day in pdf_f5:
            if abs(f4 - pdf_f4[day]) < 0.051 and abs(f5 - pdf_f5[day]) < 0.051:
                last_match_date = day
    if not last_match_date:
        return None
    d = datetime.strptime(last_match_date, "%Y-%m-%d")
    return d + timedelta(days=1, hours=hold_until_hour)


def lookup_pdf(series: dict[str, float], day: str) -> float | None:
    if day in series:
        return series[day]
    earlier = [k for k in series if k < day]
    if not earlier:
        return None
    return series[max(earlier)]


def fill_csv(
    csv_path: Path,
    pdf_series: dict[str, dict[str, float]],
    columns: dict[str, int],
    after: datetime | None,
    inplace: bool,
    dry_run: bool,
) -> tuple[Path | None, dict]:
    pdf_f4 = pdf_series.get("F-4", {})
    pdf_f5 = pdf_series.get("F-5", {})
    if not pdf_f4 or not pdf_f5:
        missing = [m for m in ("F-4", "F-5") if m not in pdf_series]
        raise SystemExit(f"PDF에서 {', '.join(missing)} 누적유량을 찾지 못했습니다.")

    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    col_f4 = columns["F-4"]
    col_f5 = columns["F-5"]
    cutoff = after or detect_cutoff(rows, pdf_f4, pdf_f5, col_f4, col_f5)
    if cutoff is None:
        raise SystemExit("이미 맞춰진 마지막 시각을 찾지 못했습니다. --after 로 지정하세요.")

    changed = 0
    samples: list[tuple[str, str, str, str, str]] = []
    first_change = None
    last_change = None
    for row in rows:
        if len(row) <= max(col_f4, col_f5):
            continue
        try:
            ts = _parse_ts(row[0])
        except ValueError:
            continue
        if ts <= cutoff:
            continue
        day = ts.strftime("%Y-%m-%d")
        new_f4 = lookup_pdf(pdf_f4, day)
        new_f5 = lookup_pdf(pdf_f5, day)
        if new_f4 is None or new_f5 is None:
            continue
        old_f4, old_f5 = row[col_f4], row[col_f5]
        row[col_f4] = _format_value(new_f4)
        row[col_f5] = _format_value(new_f5)
        if old_f4 != row[col_f4] or old_f5 != row[col_f5]:
            changed += 1
            if first_change is None:
                first_change = ts
            last_change = ts
            if len(samples) < 12:
                samples.append((row[0], old_f4, row[col_f4], old_f5, row[col_f5]))

    summary = {
        "cutoff": cutoff.strftime("%Y-%m-%d %H:%M"),
        "changed": changed,
        "pdf_f4_last": max(pdf_f4) if pdf_f4 else None,
        "pdf_f5_last": max(pdf_f5) if pdf_f5 else None,
        "pdf_f4_last_value": pdf_f4.get(max(pdf_f4)) if pdf_f4 else None,
        "pdf_f5_last_value": pdf_f5.get(max(pdf_f5)) if pdf_f5 else None,
        "first_change": first_change.strftime("%Y-%m-%d %H:%M") if first_change else None,
        "last_change": last_change.strftime("%Y-%m-%d %H:%M") if last_change else None,
        "samples": samples,
    }

    if dry_run:
        return None, summary

    out_path = csv_path if inplace else csv_path.with_name(csv_path.stem + "_filled.csv")
    if inplace:
        bak = csv_path.with_suffix(csv_path.suffix + ".bak")
        shutil.copy2(csv_path, bak)
        summary["backup"] = str(bak)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    summary["output"] = str(out_path)
    return out_path, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="유량계 PDF 일일 누적을 CSV F-4/F-5에 채웁니다.")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--f4-col", type=int, default=DEFAULT_COLUMNS["F-4"])
    parser.add_argument("--f5-col", type=int, default=DEFAULT_COLUMNS["F-5"])
    parser.add_argument("--after", default=None, help="이 시각 이후만 갱신 (예: 2026-08-28 16:00)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-inplace", action="store_true", help="원본 대신 *_filled.csv 로 저장")
    args = parser.parse_args()

    if not args.pdf.exists():
        raise SystemExit(f"PDF 없음: {args.pdf}")
    if not args.csv.exists():
        raise SystemExit(f"CSV 없음: {args.csv}")

    series = parse_flowmeter_pdf(args.pdf)
    print("PDF meters:", {k: f"{min(v)} ~ {max(v)} ({len(v)}일)" for k, v in series.items()})
    for meter in ("F-4", "F-5"):
        days = series.get(meter, {})
        late = {d: days[d] for d in sorted(days) if d >= "2026-08-27"}
        print(f"  {meter} late:", late)

    after = _parse_ts(args.after) if args.after else None
    _, summary = fill_csv(
        args.csv,
        series,
        {"F-4": args.f4_col, "F-5": args.f5_col},
        after=after,
        inplace=not args.no_inplace,
        dry_run=args.dry_run,
    )
    print("cutoff:", summary["cutoff"])
    print("changed rows:", summary["changed"])
    print("range:", summary["first_change"], "->", summary["last_change"])
    print("pdf last F-4", summary["pdf_f4_last"], summary["pdf_f4_last_value"])
    print("pdf last F-5", summary["pdf_f5_last"], summary["pdf_f5_last_value"])
    print("samples (ts, oldF4, newF4, oldF5, newF5):")
    for sample in summary["samples"]:
        print(" ", sample)
    if summary.get("output"):
        print("wrote:", summary["output"])
    if summary.get("backup"):
        print("backup:", summary["backup"])


if __name__ == "__main__":
    main()
