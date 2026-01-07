# core/fill_interval_processor.py

import pandas as pd
from datetime import timedelta


class FillIntervalProcessor:
    """
    Convert Pro 3 – Fill Interval Processor (증분 방식)

    규칙:
    - 변환 대상 DataFrame 내부에서 연속된 행들 사이의 시간 간격 체크
    - 간격이 설정된 interval_min보다 크면 중간 시간대 데이터 생성
    - 이전 행의 모든 값을 복사하고 시간만 변경
    - 증분 변환(append) 방식에 최적화됨
    """

    TIME_COL_INDEX = 0
    TIME_FORMAT = "%Y-%m-%d %H:%M"

    def __init__(self, logger=None):
        self.logger = logger
        self.last_added = 0

    def process(self, df: pd.DataFrame, interval_min: int) -> pd.DataFrame:
        """
        DataFrame의 연속된 행들 사이 시간 간격을 체크하여 누락된 시간대를 생성
        
        Args:
            df: 변환 대상 DataFrame
            interval_min: 간격 설정값(분 단위), 0 이하면 처리 안 함
            
        Returns:
            누락된 시간대가 채워진 DataFrame
        """
        self.last_added = 0

        if interval_min is None or interval_min <= 0:
            return df
        if df is None or df.empty:
            return df

        df = df.copy()
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔧 STEP 1: 정각 데이터만 필터링 (중간 데이터 제거)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        df = self._filter_on_interval(df, interval_min)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 🔧 STEP 2: 누락된 시간대 채우기
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        result_rows = []

        # 각 행을 순회하면서 다음 행과의 시간 간격 체크
        for i in range(len(df)):
            # 현재 행 추가
            result_rows.append(df.iloc[i])

            # 다음 행이 있으면 시간 간격 체크
            if i < len(df) - 1:
                current_time = self._parse_time(df.iloc[i, self.TIME_COL_INDEX])
                next_time = self._parse_time(df.iloc[i + 1, self.TIME_COL_INDEX])

                if current_time and next_time:
                    # 시간 차이 계산 (분 단위)
                    time_diff_minutes = (next_time - current_time).total_seconds() / 60

                    # 간격이 interval_min보다 크면 중간 시간대 생성
                    if time_diff_minutes > interval_min:
                        # 필요한 중간 시간대 개수 계산
                        num_gaps = int(time_diff_minutes / interval_min)
                        
                        # 정확히 나누어떨어지면 1개 줄임 (다음 행이 이미 존재하므로)
                        if time_diff_minutes % interval_min == 0:
                            num_gaps -= 1

                        if num_gaps > 0:
                            # 중간 시간대 생성
                            gap_time = current_time + timedelta(minutes=interval_min)

                            for _ in range(num_gaps):
                                # 현재 행 데이터 복사 후 시간 업데이트
                                gap_values = df.iloc[i].values.copy()
                                gap_time_str = gap_time.strftime(self.TIME_FORMAT)
                                gap_values[self.TIME_COL_INDEX] = gap_time_str
                                gap_row = pd.Series(gap_values, index=df.columns)
                                result_rows.append(gap_row)

                                if self.logger:
                                    self.logger.log(
                                        f"FillInterval 생성: {gap_time_str}",
                                        level="DEBUG"
                                    )

                                gap_time += timedelta(minutes=interval_min)

        self.last_added = len(result_rows) - len(df)
        
        if self.last_added > 0 and self.logger:
            self.logger.log(
                f"FillInterval: {self.last_added}개 행 생성",
                level="DEBUG"
            )

        return pd.DataFrame(result_rows, columns=df.columns).reset_index(drop=True)

    # ==========================================================
    # helpers
    # ==========================================================
    def _filter_on_interval(self, df: pd.DataFrame, interval_min: int) -> pd.DataFrame:
        """
        정각에 가장 가까운 데이터만 남기고 중간 데이터 제거
        
        예: interval_min=60 이면 각 시간대(10시, 11시 등)에서 정각에 가장 가까운 데이터 1개만 유지
            10:00:05, 10:00:30, 10:15:00 → 10:00:05만 남김 (10시에 가장 가까움)
            
        Args:
            df: 원본 DataFrame
            interval_min: 간격 설정값(분 단위)
            
        Returns:
            정각 데이터만 필터링된 DataFrame
        """
        if df is None or df.empty:
            return df
        
        # 각 행의 시간과 목표 정각(rounded time)을 계산
        time_groups = {}  # {rounded_time: [(index, actual_time, distance)]}
        
        for i in range(len(df)):
            time_str = df.iloc[i, self.TIME_COL_INDEX]
            parsed_time = self._parse_time(time_str)
            
            if parsed_time is None:
                # 시간 파싱 실패한 행은 별도로 처리
                if 'invalid' not in time_groups:
                    time_groups['invalid'] = []
                time_groups['invalid'].append((i, None, 0))
                continue
            
            # 목표 정각 시간 계산 (가장 가까운 interval_min의 배수로 반올림)
            total_minutes = parsed_time.hour * 60 + parsed_time.minute
            rounded_minutes = round(total_minutes / interval_min) * interval_min
            
            # 목표 시간 생성 (같은 날짜, 반올림된 시간)
            rounded_time = parsed_time.replace(hour=0, minute=0, second=0, microsecond=0)
            rounded_time = rounded_time + timedelta(minutes=rounded_minutes)
            
            # 목표 정각과의 시간 차이 계산 (초 단위)
            distance = abs((parsed_time - rounded_time).total_seconds())
            
            # 같은 목표 정각끼리 그룹핑
            key = rounded_time.strftime(self.TIME_FORMAT)
            if key not in time_groups:
                time_groups[key] = []
            time_groups[key].append((i, parsed_time, distance))
        
        # 각 그룹에서 정각에 가장 가까운 데이터 1개만 선택
        selected_indices = set()
        removed_count = 0
        
        for group_key, group_items in time_groups.items():
            if group_key == 'invalid':
                # 파싱 실패한 행들은 모두 유지
                for idx, _, _ in group_items:
                    selected_indices.add(idx)
                continue
            
            # 거리 기준으로 정렬 (가장 가까운 것이 먼저)
            group_items.sort(key=lambda x: x[2])
            
            # 가장 가까운 것만 선택
            selected_indices.add(group_items[0][0])
            
            # 나머지는 제거
            if len(group_items) > 1:
                removed_count += len(group_items) - 1
                if self.logger:
                    for idx, actual_time, distance in group_items[1:]:
                        self.logger.log(
                            f"중간 데이터 제거: {actual_time.strftime(self.TIME_FORMAT)} "
                            f"(목표: {group_key}, 거리: {distance:.1f}초)",
                            level="DEBUG"
                        )
        
        # 선택된 인덱스로 DataFrame 재구성
        filtered_rows = [df.iloc[i] for i in sorted(selected_indices)]
        
        if removed_count > 0 and self.logger:
            self.logger.log(
                f"정각 필터링: {removed_count}개 중간 데이터 제거",
                level="DEBUG"
            )
        
        if not filtered_rows:
            return pd.DataFrame(columns=df.columns)
            
        return pd.DataFrame(filtered_rows, columns=df.columns).reset_index(drop=True)
    
    def _parse_time(self, value):
        if value is None or value == "":
            return None
        try:
            ts = pd.to_datetime(value, errors="coerce")
            if pd.isna(ts):
                return None
            return ts.to_pydatetime()
        except Exception:
            return None
