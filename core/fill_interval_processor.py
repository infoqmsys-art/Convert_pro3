# core/fill_interval_processor.py
"""
누락된 데이터 처리 (interval 기준, 예: 60분 = 시간당 1행)

1. map_slots: 각 슬롯마다 원본에서 가장 가까운 행 1개 선택 → 시간당 1행
2. fill_gaps: 매핑된 행들 사이 빈 슬롯만 이전 행 복사로 채움 (원본 기준)
3. fill_from_last_to_now: 원본 0행일 때 base_time~현재 주기 채움
"""

import pandas as pd
from datetime import datetime, timedelta

TIME_COL = 0
FMT = "%Y-%m-%d %H:%M:%S"


def _slot_key(ts, interval_min: int) -> str:
    """시각을 interval 슬롯 문자열로 (예: 10:05, 60 → '2026-03-15 10:00')"""
    if pd.isna(ts):
        return ""
    ts = pd.Timestamp(ts)
    total_m = ts.hour * 60 + ts.minute
    slot_m = (total_m // interval_min) * interval_min
    slot_ts = ts.floor("D") + pd.Timedelta(minutes=slot_m)
    return slot_ts.strftime(FMT)


def _slot_ts(ts, interval_min: int):
    """시각을 슬롯 시각으로 변환 (Timestamp 반환)"""
    if pd.isna(ts):
        return None
    ts = pd.Timestamp(ts)
    total_m = ts.hour * 60 + ts.minute
    slot_m = (total_m // interval_min) * interval_min
    return ts.floor("D") + pd.Timedelta(minutes=slot_m)


class FillIntervalProcessor:
    """누락 처리: map_slots → fill_gaps (원본 기준), fill_from_last_to_now (원본 0행 시)"""

    TIME_COL_INDEX = TIME_COL
    TIME_FORMAT = FMT

    def __init__(self, logger=None):
        self.logger = logger
        self.last_added = 0

    # ─────────────────────────────────────────────────────────
    # 1) 슬롯 매핑: 각 슬롯마다 원본에서 가장 가까운 행 1개
    # ─────────────────────────────────────────────────────────
    def map_slots(self, df: pd.DataFrame, interval_min: int) -> pd.DataFrame:
        if df is None or df.empty or not interval_min:
            return df if df is not None else pd.DataFrame()

        try:
            times = pd.to_datetime(df.iloc[:, TIME_COL], errors="coerce", format="mixed")
        except TypeError:
            times = pd.to_datetime(df.iloc[:, TIME_COL], errors="coerce")
        valid = times.notna()
        if not valid.any():
            return pd.DataFrame(columns=df.columns)

        rows = []
        for idx in df.index[valid]:
            ts = times.loc[idx]
            slot_str = _slot_key(ts, interval_min)
            if not slot_str:
                continue
            # 원본 timestamp는 그대로 두고, 슬롯 기준 선택만 위해 slot_str을 사용
            row = df.loc[idx].copy()
            dist = abs((ts - pd.to_datetime(slot_str)).total_seconds())
            rows.append((slot_str, dist, row))

        if not rows:
            return pd.DataFrame(columns=df.columns)

        # 슬롯별로 거리 최소 행 1개만
        by_slot = {}
        for slot_str, dist, row in rows:
            if slot_str not in by_slot or dist < by_slot[slot_str][0]:
                by_slot[slot_str] = (dist, row)

        result = pd.DataFrame([r[1] for r in by_slot.values()], columns=df.columns)
        try:
            result = result.sort_values(
                by=df.columns[TIME_COL],
                key=lambda s: pd.to_datetime(s, format="mixed", errors="coerce")
            ).reset_index(drop=True)
        except Exception:
            result = result.sort_values(
                by=df.columns[TIME_COL],
                key=lambda s: pd.to_datetime(s, errors="coerce")
            ).reset_index(drop=True)
        return result

    # ─────────────────────────────────────────────────────────
    # 2) 누락 보충: 원본 행 사이 빈 슬롯만 이전 행 복사로 채움
    #    - 채운 행은 __filled__=True, 원본 행은 __filled__=False
    #    - 채운 행의 timestamp는 슬롯 경계(정각)로 스냅
    # ─────────────────────────────────────────────────────────
    def fill_gaps(
        self, df: pd.DataFrame, interval_min: int, max_time=None
    ) -> pd.DataFrame:
        if df is None or df.empty or not interval_min:
            return df if df is not None else pd.DataFrame()

        try:
            times = pd.to_datetime(df.iloc[:, TIME_COL], errors="coerce", format="mixed")
        except TypeError:
            times = pd.to_datetime(df.iloc[:, TIME_COL], errors="coerce")
        if times.isna().all():
            return df

        # 동일 슬롯 중복 제거 (마지막 행 유지) — prepend된 last_row보다 실측 데이터 우선
        # keep="last": prepend(이전 변환본 마지막 행)와 실제 측정값이 같은 슬롯에 있을 때
        #              실측 행(나중에 등장)을 유지하고 prepend 행을 삭제
        slot_keys = times.apply(lambda t: _slot_key(t, interval_min))
        df = df.loc[~slot_keys.duplicated(keep="last")].copy().reset_index(drop=True)
        try:
            times = pd.to_datetime(df.iloc[:, TIME_COL], errors="coerce", format="mixed")
        except TypeError:
            times = pd.to_datetime(df.iloc[:, TIME_COL], errors="coerce")

        out = []
        filled_flags = []
        for i in range(len(df)):
            out.append(df.iloc[i].copy())
            filled_flags.append(False)
            if i >= len(df) - 1:
                break

            t_curr = times.iloc[i]
            t_next = times.iloc[i + 1]
            if pd.isna(t_curr) or pd.isna(t_next):
                continue

            slot = _slot_ts(t_curr, interval_min)
            slot_next = _slot_ts(t_next, interval_min)
            if slot is None or slot_next is None:
                continue

            # 슬롯 경계 기준으로 빈 슬롯 수 계산
            # (t_curr/t_next 오프셋 무관하게 슬롯 차이로 정확히 계산)
            n = max(0, int(round((slot_next - slot).total_seconds() / 60 / interval_min)) - 1)

            for _ in range(n):
                slot = slot + timedelta(minutes=interval_min)
                # 채움 행이 다음 실측 슬롯과 겹치면 중단 (이중 안전장치)
                if slot >= slot_next:
                    break
                if max_time is not None and slot > max_time:
                    break
                src = df.iloc[i]
                row = src.copy()
                row.iloc[TIME_COL] = slot.strftime(FMT)
                # deviceId/STX 빈 값이면 다음 행에서 가져옴
                try:
                    if (
                        (pd.isna(src.iloc[1]) or str(src.iloc[1]).strip() in ("", "0"))
                        or (pd.isna(src.iloc[2]) or str(src.iloc[2]).strip() in ("", "0"))
                    ):
                        next_row = df.iloc[i + 1]
                        row.iloc[1] = next_row.iloc[1]
                        row.iloc[2] = next_row.iloc[2]
                except Exception:
                    pass
                out.append(row)
                filled_flags.append(True)

        self.last_added = sum(filled_flags)
        result = pd.DataFrame(out, columns=df.columns)
        result["__filled__"] = filled_flags
        try:
            result = result.sort_values(
                by=df.columns[TIME_COL],
                key=lambda s: pd.to_datetime(s, format="mixed", errors="coerce")
            ).reset_index(drop=True)
        except Exception:
            result = result.sort_values(
                by=df.columns[TIME_COL],
                key=lambda s: pd.to_datetime(s, errors="coerce")
            ).reset_index(drop=True)
        return result

    # ─────────────────────────────────────────────────────────
    # 2-b) 누락 보충(슬롯 스냅 없음): N분 단위로 "빈 구간만" 행 추가
    # - 기존 실측 timestamp는 절대 변경하지 않음
    # - 추가 행은 직전 행 복사 + timestamp만 t_curr + k*N 으로 설정
    # ─────────────────────────────────────────────────────────
    def fill_missing_by_step(
        self, df: pd.DataFrame, interval_min: int, current_time_limit=None
    ) -> pd.DataFrame:
        """
        interval_min 간격으로, 인접한 두 실측 시각 사이의 "빈 구간"만 채운다.

        예) interval=60, 12:10과 15:00이 있으면
            13:10, 14:10을 추가한다. (정각 스냅/슬롯 통일 없음)

        Args:
            df: TIME_COL(0열)에 timestamp 문자열/값이 있는 DataFrame
            interval_min: 간격(분)
            current_time_limit: (옵션) 생성되는 timestamp 상한
        """
        self.last_added = 0
        if df is None or df.empty or not interval_min:
            return df if df is not None else pd.DataFrame()

        # 시간 파싱/정렬 (format='mixed': '2026-01-22 15:00' vs '2026-01-22 16:00:00' 혼재 대응)
        try:
            times = pd.to_datetime(df.iloc[:, TIME_COL], errors="coerce", format="mixed")
        except TypeError:
            times = pd.to_datetime(df.iloc[:, TIME_COL], errors="coerce")
        valid = times.notna()
        if not valid.any():
            return df

        df2 = df.loc[valid].copy()
        try:
            times2 = pd.to_datetime(df2.iloc[:, TIME_COL], errors="coerce", format="mixed")
        except TypeError:
            times2 = pd.to_datetime(df2.iloc[:, TIME_COL], errors="coerce")
        df2 = df2.iloc[times2.argsort(kind="mergesort")].reset_index(drop=True)
        try:
            times2 = pd.to_datetime(df2.iloc[:, TIME_COL], errors="coerce", format="mixed")
        except TypeError:
            times2 = pd.to_datetime(df2.iloc[:, TIME_COL], errors="coerce")

        max_time = None
        if current_time_limit is not None:
            try:
                max_time = pd.Timestamp(current_time_limit)
            except Exception:
                max_time = None

        out = []
        filled_flags = []
        for i in range(len(df2)):
            out.append(df2.iloc[i].copy())
            filled_flags.append(False)
            if i >= len(df2) - 1:
                break

            t_curr = times2.iloc[i]
            t_next = times2.iloc[i + 1]
            if pd.isna(t_curr) or pd.isna(t_next):
                continue

            step = timedelta(minutes=int(interval_min))
            t = pd.Timestamp(t_curr) + step
            # 다음 실측 전까지만(=빈 구간만) 채움. 한 구간당 최대 48행(60분주기 2일치) 제한
            gap_max = 48
            gap_count = 0
            while t < pd.Timestamp(t_next):
                if max_time is not None and t > max_time:
                    break
                if gap_count >= gap_max:
                    break
                src = df2.iloc[i]
                row = src.copy()
                row.iloc[TIME_COL] = t.strftime(FMT)

                # deviceId/STX(1,2열) 빈 값이면 다음 행에서 가져오기 (기존 fill_gaps와 동일한 안전장치)
                try:
                    if (
                        (pd.isna(src.iloc[1]) or str(src.iloc[1]).strip() in ("", "0"))
                        or (pd.isna(src.iloc[2]) or str(src.iloc[2]).strip() in ("", "0"))
                    ):
                        next_row = df2.iloc[i + 1]
                        row.iloc[1] = next_row.iloc[1]
                        row.iloc[2] = next_row.iloc[2]
                except Exception:
                    pass

                out.append(row)
                filled_flags.append(True)
                t = t + step
                gap_count += 1

        self.last_added = len(out) - len(df2)
        result = pd.DataFrame(out, columns=df2.columns)
        result["__filled__"] = filled_flags
        # 결과는 시간순으로 유지
        try:
            try:
                ts_out = pd.to_datetime(result.iloc[:, TIME_COL], errors="coerce", format="mixed")
            except TypeError:
                ts_out = pd.to_datetime(result.iloc[:, TIME_COL], errors="coerce")
            result = result.iloc[ts_out.argsort(kind="mergesort")].reset_index(drop=True)
        except Exception:
            pass
        return result

    # ─────────────────────────────────────────────────────────
    # 3) 주기 채움: 원본 0행일 때 base_time ~ 현재
    # ─────────────────────────────────────────────────────────
    def fill_from_last_to_now(
        self,
        last_row_df: pd.DataFrame,
        base_time,
        interval_min: int,
        current_time_limit=None,
        max_rows: int = 24,
    ) -> pd.DataFrame:
        """
        마지막 실측 시각 ~ 현재 구간을 주기로 채움.
        max_rows: 최대 추가 행 수 (기본 24 = 60분 주기 시 1일치. 무제한 채움 방지)
        """
        self.last_added = 0
        if not interval_min or last_row_df is None or last_row_df.empty or base_time is None:
            return pd.DataFrame(columns=last_row_df.columns if last_row_df is not None else [])

        now = current_time_limit or datetime.now()
        total_m = now.hour * 60 + now.minute
        slot_end_m = ((total_m // interval_min) + 1) * interval_min
        max_time = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=slot_end_m)

        bt = base_time
        if hasattr(bt, "to_pydatetime"):
            bt = bt.to_pydatetime()
        bt = bt.replace(second=0, microsecond=0)
        if bt >= max_time:
            return pd.DataFrame(columns=last_row_df.columns)

        rows = []
        t = bt + timedelta(minutes=interval_min)
        while t <= max_time and len(rows) < max_rows:
            row = last_row_df.iloc[0].copy()
            row.iloc[TIME_COL] = t.strftime(FMT)
            rows.append(row)
            t += timedelta(minutes=interval_min)

        self.last_added = len(rows)
        result = pd.DataFrame(rows, columns=last_row_df.columns).reset_index(drop=True) if rows else pd.DataFrame(columns=last_row_df.columns)
        if not result.empty:
            result["__filled__"] = True
        return result

    # ─── file_processor 호환용 별칭 ───
    def _filter_on_interval(self, df: pd.DataFrame, interval_min: int) -> pd.DataFrame:
        return self.map_slots(df, interval_min)

    def _fill_missing_intervals(
        self, df: pd.DataFrame, interval_min: int, current_time_limit=None
    ) -> pd.DataFrame:
        max_time = None
        if current_time_limit and isinstance(current_time_limit, datetime):
            total_m = current_time_limit.hour * 60 + current_time_limit.minute
            slot_m = (total_m // interval_min) * interval_min
            max_time = current_time_limit.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=slot_m + interval_min)
        return self.fill_gaps(df, interval_min, max_time)
