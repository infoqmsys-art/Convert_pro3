"""
SensorProcessor (Convert Pro 3) - Column-based Engine (generate_XXX 확장 구조 유지)

✅ Convert Pro 3 전제:
- 전면 컬럼 기반 처리 (iterrows/apply_row/state 제거)
- CH0~CH7은 DataFrame 컬럼 인덱스 16~23 고정
- SensorProcessor만 수정 대상 (FileProcessor/파이프라인/UI 변경 없음)
- 누적은 shift/cumsum 등 컬럼 연산만 사용
- 상태(state) 기반 누적/이벤트 분기 누적은 현 단계 제외
- process(df, file_cfg) -> df 인터페이스 유지

✅ 확장 방식:
- 새 모드 추가 시: def generate_HJ(self, df, cfg): ... 만 추가하면 자동 적용됨
"""

# NOTE:
# - SensorProcessor는 decimal/round를 절대 적용하지 않는다.
# - 모든 소수점 처리는 FileProcessor.apply_decimal()에서 일괄 처리한다.

import random  # legacy import (일부 모드에서 scale="VW" 분포 호환 목적)
import numpy as np
import pandas as pd


MODE_META = {
    "PASS": {"use_base": False, "use_scale": False, "desc": "원값 유지"},
    "OFFSET": {"use_base": True, "use_scale": False, "desc": "원값 + base"},
    "EL": {"use_base": True, "use_scale": False, "desc": "경사/변위 아날로그 센서"},
    "EL_LOW": {"use_base": True, "use_scale": False, "desc": "저노이즈 경사/변위 센서"},
    "CR": {"use_base": True, "use_scale": False, "desc": "균열계 (누적)"},
    "V": {"use_base": True, "use_scale": True, "desc": "전압형 아날로그 센서"},
    "NM": {"use_base": True, "use_scale": True, "desc": "노이즈 전용 센서 (테스트)"},
    "SET": {"use_base": True, "use_scale": True, "desc": "기준값(base) 기준 변위를 scale 배율로 보정"},
    "BASE_RAND": {"use_base": True, "use_scale": True, "desc": "base ± scale 랜덤"},
    "COPY": {"use_base": False, "use_scale": False, "desc": "원값 복사 (명시적 PASS)"},
    "EL_STATION": {"use_base": True, "use_scale": False, "desc": "경사계 - 정거장 환경"},
    "EL_TUNNEL": {"use_base": True, "use_scale": False, "desc": "경사계 - 터널 내부"},
    "CHANG_SM": {"use_base": True, "use_scale": True, "desc": "소음계 데이터"},
}


class SensorProcessor:
    def __init__(self, logger=None):
        self.logger = logger

    # ======================================================
    # Public API (fixed)
    # ======================================================
    def process(self, df: pd.DataFrame, file_cfg: dict) -> pd.DataFrame:
        """
        Column-based processing entry.

        - file_cfg를 기반으로 채널 설정을 로드
        - CH0~CH7(16~23) 컬럼을 모드별 generate_XXX로 처리
        - row loop 없음 (iterrows/apply_row 제거)
        """
        if df is None or df.empty:
            return df

        # CH0~CH7 컬럼 인덱스 16~23 고정 전제 체크
        if df.shape[1] < 24:
            if self.logger:
                self.logger.log(
                    f"[SensorProcessor] df 컬럼 수 부족: {df.shape[1]} (CH0~CH7은 16~23 필요)",
                    level="ERROR",
                )
            return df

        channels = self._load_channels(file_cfg)

        if self.logger:
            self.logger.log(
                "센서 설정 로드 완료 (컬럼 기반)",
                level="DEBUG"
            )
            
        sensor_cols = [cfg["col_idx"] for cfg in channels.values()]

        # 각 센서 컬럼을 개별 레이블 기반으로 안전하게 numeric->float로 변환하여 할당
        try:
            converted = (
                df.iloc[:, sensor_cols]
                .apply(pd.to_numeric, errors="coerce")
                .astype(float)
            )
            for i, col_idx in enumerate(sensor_cols):
                col_name = df.columns[col_idx]
                df[col_name] = converted.iloc[:, i]
        except Exception:
            # 실패 시 기존 방식으로 시도
            df.iloc[:, sensor_cols] = (
                df.iloc[:, sensor_cols]
                .apply(pd.to_numeric, errors="coerce")
                .astype(float)
            )

        for ch, cfg in channels.items():
            mode = cfg["mode"]
            if mode == "PASS":
                continue

            method = getattr(self, f"generate_{mode}", None)
            if not method:
                # 미구현 모드는 PASS로 처리
                continue

            try:
                # generate_XXX는 반드시 (df, cfg) -> Series 반환
                out = method(df, cfg)
                if out is not None:
                    # 안전한 할당: out을 Series로 변환하고 numeric으로 강제한 뒤 float로 캐스팅
                    try:
                        if not isinstance(out, pd.Series):
                            out = pd.Series(out, index=df.index)
                        out = pd.to_numeric(out, errors="coerce").astype(float)
                    except Exception:
                        # 변환 실패 시, 객체 형태로 그대로 할당하여 원래 동작 유지
                        out = pd.Series(out, index=df.index)

                    # 대상 컬럼을 float로 미리 캐스팅하여 dtype 불일치 경고 방지
                    try:
                        col_name = df.columns[cfg["col_idx"]]
                        df[col_name] = df[col_name].astype(float)
                    except Exception:
                        pass

                    # 레이블 기반으로 안전하게 할당
                    try:
                        df[df.columns[cfg["col_idx"]]] = out
                    except Exception:
                        df.iloc[:, cfg["col_idx"]] = out
            except Exception as e:
                if self.logger:
                    self.logger.log(
                        f"[SensorProcessor] 채널 처리 실패 (CH{ch}, mode={mode}): {e}",
                        level="ERROR",
                    )

        if self.logger:
            self.logger.log(
                "센서 컬럼 처리 완료",
                level="DEBUG"
            )

        return df

    # ======================================================
    # Config loader (NO df access here)
    # ======================================================
    def _load_channels(self, file_cfg: dict) -> dict:
        """
        file_cfg를 해석해 채널 설정만 구성한다. (df 접근/연산 금지)

        cfg 구조:
        - mode: str
        - col_idx: int (16+ch)
        - base: 상수(float/int) 또는 컬럼 인덱스(int) 또는 None
        - scale: float 또는 문자열("VW") 또는 None
        - base_ref: bool (옵션) -> True면 base를 컬럼 참조로 강제
        """
        result = {}

        if not isinstance(file_cfg, dict):
            file_cfg = {}

        for ch in range(8):
            ch_key = f"CH{ch}"
            raw = file_cfg.get(ch_key, {}) if isinstance(file_cfg.get(ch_key, {}), dict) else {}

            mode = (raw.get("mode") or "PASS").upper()
            if mode not in MODE_META:
                mode = "PASS"

            meta = MODE_META.get(mode, MODE_META["PASS"])

            cfg = {
                "mode": mode,
                "col_idx": 16 + ch,
                "base": None,
                "scale": None,
                # base를 컬럼 참조로 강제하고 싶을 때 config에서 base_ref: true 사용
                "base_ref": bool(raw.get("base_ref", False)),
            }

            # base
            if meta["use_base"]:
                cfg["base"] = self._parse_number_or_none(raw.get("base", None))

            # scale
            if meta["use_scale"]:
                cfg["scale"] = self._parse_scale(raw.get("scale", None))

            result[ch] = cfg

        return result

    def _parse_number_or_none(self, v):
        """
        base 파싱:
        - None/"" -> None
        - int/float -> 그대로
        - "16" -> int 16
        - "0.12" -> float 0.12
        """
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return None
            # 정수 문자열
            if s.lstrip("-").isdigit():
                try:
                    return int(s)
                except Exception:
                    return None
            # 실수 문자열
            try:
                return float(s)
            except Exception:
                return None
        # 기타 타입은 파싱 불가
        return None

    def _parse_scale(self, v):
        """
        scale 파싱:
        - None/"" -> None
        - "VW" -> "VW" 유지 (BASE_RAND의 특수 분포)
        - 숫자 -> float
        """
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return None
            if s.upper() == "VW":
                return "VW"
            try:
                return float(s)
            except Exception:
                return None
        return None

    # ======================================================
    # Resolver (df access allowed)
    # ======================================================
    def _resolve_base(self, df: pd.DataFrame, cfg: dict):
        """
        base resolver:
        - COPY / BASE_RAND: base는 컬럼 참조(인덱스)로 해석 (기본)
        - 그 외 모드: base는 상수로 해석 (기본)
          단, cfg["base_ref"]=True 이면 컬럼 참조로 강제

        반환:
        - 상수(float) 또는 Series
        """
        base = cfg.get("base", None)
        if base is None:
            return 0.0

        mode = cfg.get("mode", "PASS")

        # 기본 컬럼 참조 모드
        default_colref = mode in ("COPY", "BASE_RAND")

        # 강제 컬럼 참조
        if cfg.get("base_ref", False) or default_colref:
            if isinstance(base, int) and 0 <= base < df.shape[1]:
                return df.iloc[:, base]
            # 컬럼 참조 실패 시 0 처리
            return 0.0

        # 상수 base
        try:
            return float(base)
        except Exception:
            return 0.0

    def _resolve_scale(self, cfg: dict, default: float = 1.0):
        s = cfg.get("scale", None)
        if s is None:
            return default
        return s

    # ======================================================
    # generate_XXX (Column-based)
    # - 반드시 (df, cfg) -> Series 반환
    # ======================================================
    def generate_OFFSET(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        col_idx = cfg["col_idx"]
        x = pd.to_numeric(df.iloc[:, col_idx], errors="coerce")
        base = self._resolve_base(df, cfg)  # 상수(float) 기본
        return x + base

    def generate_SET(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        col_idx = cfg["col_idx"]
        x = pd.to_numeric(df.iloc[:, col_idx], errors="coerce")
        base = self._resolve_base(df, cfg)  # 상수(float) 기본, base_ref=True면 Series 가능
        scale = self._resolve_scale(cfg, default=1.0)
        try:
            scale_v = float(scale) if not isinstance(scale, str) else 1.0
        except Exception:
            scale_v = 1.0
        return base + (x - base) * scale_v

    def generate_V(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        V (전압형 가라 데이터, 컬럼 기반)

        - 기본은 base 그대로
        - ±0.0001 : 7%
        - ±0.0002 ~ ±0.0003 : 2.8%
        - +0.0005 : 0.2%
        - 음수 방지
        """

        base = self._resolve_base(df, cfg)
        if isinstance(base, pd.Series):
            base = float(base.iloc[0])
        else:
            base = float(base)

        n = len(df)
        rng = np.random.default_rng()

        r = rng.random(n)
        noise = np.zeros(n, dtype=float)

        # -------------------------
        # 1️⃣ +0.0005 (0.2%)
        # -------------------------
        m_big = r < 0.002
        noise[m_big] = 0.0005

        # -------------------------
        # 2️⃣ ±0.0002 ~ ±0.0003 (2.8%)
        # -------------------------
        m_mid = (r >= 0.002) & (r < 0.03)
        mid_choices = [-0.0003, -0.0002, 0.0002, 0.0003]
        noise[m_mid] = rng.choice(
            mid_choices,
            size=m_mid.sum()
        )

        # -------------------------
        # 3️⃣ ±0.0001 (7%)
        # -------------------------
        m_small = (r >= 0.03) & (r < 0.10)
        noise[m_small] = rng.choice(
            [-0.0001, 0.0001],
            size=m_small.sum()
        )

        # -------------------------
        # 4️⃣ 최종 값 (음수 방지)
        # -------------------------
        values = base + noise
        values = np.maximum(values, 0.0)

        return pd.Series(values, index=df.index)

    def generate_CHANG_V(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        CHANG_V:
        - 새벽(01~05시): 95%→0, 5%→0.001 고정 스파이크
        - 그 외: 0~0.001(80%), 0.002~0.003(10%), 0.003~0.004(8%), 0.004~0.005(2%)
        - scale는 진폭 배율(기본 1.0), base 오프셋 후 음수 방지
        """

        # 기준값(base)은 상수 또는 참조 컬럼
        raw_base = self._resolve_base(df, cfg)
        base_series = raw_base if isinstance(raw_base, pd.Series) else pd.Series(raw_base, index=df.index)
        base_series = pd.to_numeric(base_series, errors="coerce").fillna(0.0)

        n = len(df)
        rng = np.random.default_rng()

        # 시간대 분리용 hour 추출 (파싱 실패 시 주간으로 처리)
        hours = pd.to_datetime(df.iloc[:, 0], errors="coerce").dt.hour
        night_mask = (hours >= 1) & (hours <= 5)
        day_mask = ~night_mask

        noise = np.zeros(n, dtype=float)

        # 새벽: 95% 0, 5% 0.001 고정
        if night_mask.any():
            r_night = rng.random(night_mask.sum())
            night_noise = np.zeros(night_mask.sum(), dtype=float)
            hit_night = r_night < 0.05
            if hit_night.any():
                night_noise[hit_night] = 0.001
            noise[night_mask.to_numpy()] = night_noise

        # 그 외 시간: 주어진 확률 분포
        if day_mask.any():
            r_day = rng.random(day_mask.sum())
            day_noise = np.zeros(day_mask.sum(), dtype=float)

            mask_80 = r_day < 0.80
            mask_10 = (r_day >= 0.80) & (r_day < 0.90)
            mask_08 = (r_day >= 0.90) & (r_day < 0.98)
            mask_02 = r_day >= 0.98

            if mask_80.any():
                day_noise[mask_80] = rng.uniform(0.0, 0.001, size=mask_80.sum())
            if mask_10.any():
                day_noise[mask_10] = rng.uniform(0.002, 0.003, size=mask_10.sum())
            if mask_08.any():
                day_noise[mask_08] = rng.uniform(0.003, 0.004, size=mask_08.sum())
            if mask_02.any():
                day_noise[mask_02] = rng.uniform(0.004, 0.005, size=mask_02.sum())

            noise[day_mask.to_numpy()] = day_noise

        # 진폭 배율 (기본 1.0)
        scale = self._resolve_scale(cfg, default=1.0)
        try:
            scale_v = float(scale) if not isinstance(scale, str) else 1.0
        except Exception:
            scale_v = 1.0

        values = base_series + noise * scale_v
        values = np.maximum(values, 0.0)

        return pd.Series(values, index=df.index)

    def generate_CHANG_SM(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        Chang_SM (소음계 데이터, 10분 간격 측정 특성 반영)
        
        📊 실제 데이터 2개 종합 분석 (10분 단위):
        
        데이터1 (999개): 평균 55.69, 표준편차 5.79, 변화량 평균 1.93
        데이터2 (2997개): 평균 54.78, 표준편차 6.33, 변화량 평균 2.65
        
        ✅ 종합 특성:
        - 평균: 55.2 dB, 표준편차: 6.1 dB
        - 10분간 변화량: 중앙값 1.5, 평균 2.3, 최대 15+
        - 변화량 분포: 60% ≤ 2dB, 30% 2-5dB, 10% 5+dB
        - 시간대: 야간(1-5시) 최저, 출근(7-10시) & 저녁(19-22시) 피크
        
        설정:
        - base: 평균 기준값 (권장: 55.2)
        - scale: 표준편차 (권장: 6.1)
        """
        base = self._resolve_base(df, cfg)
        scale = self._resolve_scale(cfg, default=6.1)
        
        try:
            scale_v = float(scale) if not isinstance(scale, str) else 6.1
        except Exception:
            scale_v = 6.1
        
        if isinstance(base, pd.Series):
            base_val = float(base.iloc[0])
        else:
            base_val = float(base)
        
        n = len(df)
        rng = np.random.default_rng()
        
        # ========================================
        # 1️⃣ 시간대별 기준값 조정 (두 데이터 종합)
        # ========================================
        time_offset = np.zeros(n, dtype=float)
        
        if df.shape[1] > 0:
            try:
                timestamps = pd.to_datetime(df.iloc[:, 0], errors='coerce')
                if not timestamps.isna().all():
                    hours = timestamps.dt.hour.values
                    
                    # 두 데이터 평균 패턴
                    time_offset[(hours >= 0) & (hours < 1)] = -4.0     # 자정
                    time_offset[(hours >= 1) & (hours < 6)] = -10.5    # 깊은 야간 (최저, 45dB 근처)
                    time_offset[(hours >= 6) & (hours < 7)] = -1.0     # 이른 아침
                    time_offset[(hours >= 7) & (hours < 11)] = 4.5     # 출근 피크
                    time_offset[(hours >= 11) & (hours < 12)] = -0.5   # 점심 전
                    time_offset[(hours >= 12) & (hours < 17)] = 0.5    # 오후
                    time_offset[(hours >= 17) & (hours < 19)] = 1.5    # 퇴근 시작
                    time_offset[(hours >= 19) & (hours < 23)] = 4.0    # 저녁 피크
                    time_offset[(hours >= 23)] = -1.0                  # 늦은 밤
            except Exception:
                pass
        
        # ========================================
        # 2️⃣ 10분 간격 변화량 생성 (두 데이터 종합 분포)
        # ========================================
        r = rng.random(n)
        step = np.zeros(n, dtype=float)

        # 70%: 작은 변화 (< ~1.8 dB)
        m_small = r < 0.70
        step[m_small] = rng.normal(0, 0.6, size=m_small.sum())
        step[m_small] = np.clip(step[m_small], -1.8, 1.8)

        # 25%: 중간 변화 (2~4 dB)
        m_medium = (r >= 0.70) & (r < 0.95)
        medium_vals = rng.uniform(-4.0, 4.0, size=m_medium.sum())
        step[m_medium] = np.where(
            np.abs(medium_vals) < 2.0,
            np.sign(medium_vals) * rng.uniform(2.0, 4.0, size=m_medium.sum()),
            medium_vals
        )

        # 5%: 큰 변화 (4~7 dB)
        m_large = r >= 0.95
        large_vals = rng.uniform(-7.0, 7.0, size=m_large.sum())
        step[m_large] = np.where(
            np.abs(large_vals) < 4.0,
            np.sign(large_vals) * rng.uniform(4.0, 7.0, size=m_large.sum()),
            large_vals
        )
        
        # 첫 행은 변화 없음
        step[0] = 0.0
        
        # ========================================
        # 3️⃣ 평균 회귀 (10분 단위, 두 데이터 특성 반영)
        # ========================================
        # 더 완만한 변화감을 위해 감쇠율을 높임
        alpha = 0.93  # 10분당 7% 감쇠
        
        cumulative = np.zeros(n, dtype=float)
        for i in range(1, n):
            cumulative[i] = alpha * cumulative[i-1] + step[i]
        
        # 누적값 제한 (실제 범위 44~68 dB 반영)
        cumulative = np.clip(cumulative, -scale_v*1.6, scale_v*1.6)
        
        # ========================================
        # 4️⃣ 최종 값 계산
        # ========================================
        values = base_val + time_offset + cumulative

        # 소음계 특성: 최소 44 dB (실제 데이터 패턴 반영)
        values = np.maximum(values, 44.0)
        
        # 야간(1~5시) 구간은 45 ± 0.25 dB로 고정 (실제 데이터 패턴)
        if df.shape[1] > 0:
            try:
                ts_night = pd.to_datetime(df.iloc[:, 0], errors='coerce')
                if not ts_night.isna().all():
                    hours_night = ts_night.dt.hour.values
                    night_mask = (hours_night >= 1) & (hours_night < 5)
                    if night_mask.any():
                        jitter = rng.normal(0, 0.08, size=night_mask.sum())
                        jitter = np.clip(jitter, -0.25, 0.25)
                        values[night_mask] = 45.0 + jitter
            except Exception:
                pass
        
        # 정수값 방지: 모든 값에 미세 노이즈 추가
        micro_noise = rng.uniform(0.001, 0.05, size=n)
        values = values + micro_noise
        
        return pd.Series(values, index=df.index)

    def generate_CR(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        CR (완전 가라값 생성, 컬럼 기반)

        - 원본 컬럼 값 사용 ❌
        - 첫 값은 base에서 시작
        - 아주 낮은 확률(p=0.05%)로 ±0.0001 스파이크가 누적됨
        - state / row loop / 캐시 ❌
        """

        # -----------------------------
        # 파라미터
        # -----------------------------
        P_SPIKE = 0.01     # 1%
        STEP = 0.0001

        # -----------------------------
        # 기준값(base)
        # -----------------------------
        base = self._resolve_base(df, cfg)
        if isinstance(base, pd.Series):
            base = float(base.iloc[0])
        else:
            base = float(base)

        n = len(df)
        rng = np.random.default_rng()

        # -----------------------------
        # 1️⃣ 저확률 스파이크 스텝 생성
        # -----------------------------
        spike_step = np.zeros(n, dtype=float)

        # 첫 행은 기준값이므로 스파이크 제외
        spike_mask = rng.random(n - 1) < P_SPIKE
        spike_step[1:][spike_mask] = rng.choice(
            [-STEP, STEP],
            size=spike_mask.sum()
        )

        # -----------------------------
        # 2️⃣ 누적 드리프트
        # -----------------------------
        drift = spike_step.cumsum()

        # -----------------------------
        # 3️⃣ 최종 값
        # -----------------------------
        return pd.Series(base + drift, index=df.index)

    def generate_COPY(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        COPY:
        - base는 '참조 컬럼 인덱스'로 사용 (기본 colref)
        - 예: base=16이면 df.iloc[:,16]을 현재 채널로 복사
        """
        col_idx = cfg["col_idx"]
        ref = self._resolve_base(df, cfg)
        if isinstance(ref, pd.Series):
            return pd.to_numeric(ref, errors="coerce")
        # 참조 실패 시 원본 유지
        return df.iloc[:, col_idx]

    def generate_BASE_RAND(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        BASE_RAND:
        - base(참조 컬럼, 같은 행 기준) + 랜덤
        - scale == "VW": VW 분포
        - else: uniform(-scale, scale)
        - ❗ decimal 처리는 FileProcessor.apply_decimal 에서 수행
        """
        col_idx = cfg["col_idx"]

        # base는 반드시 컬럼 참조
        ref = self._resolve_base(df, cfg)
        if not isinstance(ref, pd.Series):
            # 참조 실패 시 PASS
            return df.iloc[:, col_idx]

        base = pd.to_numeric(ref, errors="coerce")
        scale = self._resolve_scale(cfg, default=0.0)

        n = len(df)
        rng = np.random.default_rng()

        # -------------------------------
        # VW 분포
        # -------------------------------
        if isinstance(scale, str) and scale.upper() == "VW":
            r = rng.random(n)
            d = np.zeros(n, dtype=float)

            d[(r >= 0.85) & (r < 0.97)] = 0.001
            d[(r >= 0.97) & (r < 0.995)] = 0.002
            d[(r >= 0.995) & (r < 0.999)] = 0.003
            d[r >= 0.999] = 0.004

            return base + d

        # -------------------------------
        # 일반 ±scale 랜덤
        # -------------------------------
        try:
            scale_v = float(scale)
        except Exception:
            scale_v = 0.0

        if scale_v == 0.0:
            return base

        d = rng.uniform(-scale_v, scale_v, size=n)
        return base + d

    def generate_NM(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        NM(노이즈 전용):
        - base + uniform(-scale, scale)
        """
        col_idx = cfg["col_idx"]
        base = self._resolve_base(df, cfg)  # 상수 or Series(base_ref=True)
        scale = self._resolve_scale(cfg, default=0.0)

        try:
            scale_v = float(scale) if not isinstance(scale, str) else 0.0
        except Exception:
            scale_v = 0.0

        n = len(df)
        rng = np.random.default_rng()
        noise = rng.uniform(-scale_v, scale_v, size=n) if scale_v != 0.0 else np.zeros(n, dtype=float)

        # base가 Series일 수도 있으니 Series로 맞춘다
        base_s = base if isinstance(base, pd.Series) else pd.Series(base, index=df.index)
        return pd.to_numeric(base_s, errors="coerce") + noise

    def generate_EL_LOW(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        base = self._resolve_base(df, cfg)
        if isinstance(base, pd.Series):
            base = float(base.iloc[0])
        else:
            base = float(base)

        n = len(df)
        rng = np.random.default_rng()

        r = rng.random(n)
        noise = np.zeros(n, dtype=float)

        # -------------------------
        # 1️⃣ 기본 노이즈 (약 98.5%)
        # ±0.0003
        # -------------------------
        m_base = r >= 0.015
        noise[m_base] = rng.uniform(
            -0.0003, 0.0003,
            size=m_base.sum()
        )

        # -------------------------
        # 2️⃣ 튀는 값 (약 1.5%)
        # ±0.001
        # -------------------------
        m_spike = r < 0.015
        noise[m_spike] = rng.uniform(
            -0.001, 0.001,
            size=m_spike.sum()
        )

        # -------------------------
        # 3️⃣ 아주 미세한 드리프트
        # step = ±0.0001
        # 발생 확률 0.2%
        # -------------------------
        drift_step = np.zeros(n, dtype=float)
        m_drift = rng.random(n) < 0.002
        drift_step[m_drift] = rng.choice(
            [-0.0001, 0.0001],
            size=m_drift.sum()
        )

        drift = drift_step.cumsum()
        drift[0] = 0.0

        # -------------------------
        # 4️⃣ 최종 값
        # -------------------------
        values = base + drift + noise

        return pd.Series(values, index=df.index)

    def generate_EL_STATION(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        EL_STATION (컬럼 기반)
        - base + noise
        - 아주 낮은 확률로 ±0.0001 drift가 누적됨
        """

        base = self._resolve_base(df, cfg)  # 상수 or Series
        n = len(df)
        rng = np.random.default_rng()

        # -----------------------------
        # 1️⃣ 일반 노이즈 (기존 유지)
        # -----------------------------
        r = rng.random(n)
        noise = np.zeros(n, dtype=float)

        # 60%: 미세 노이즈
        m1 = r < 0.60
        noise[m1] = rng.uniform(-0.0001, 0.0001, size=m1.sum())

        # 30%: 0 (0.60 ~ 0.90)

        # 10%: 작은 스파이크
        m3 = r >= 0.90
        choices = np.array(
            [0.0, 0.0001, 0.0002, 0.0003, -0.0001, -0.0002, -0.0003],
            dtype=float
        )
        noise[m3] = rng.choice(choices, size=m3.sum())

        # -----------------------------
        # 2️⃣ 아주 낮은 확률 drift (핵심)
        # -----------------------------
        drift_event = rng.random(n)

        drift_step = np.zeros(n, dtype=float)

        # 예: 0.1% 확률로만 drift 발생
        drift_mask = drift_event < 0.001

        drift_step[drift_mask] = rng.choice(
            [-0.0001, 0.0001],
            size=drift_mask.sum()
        )

        # 🔑 누적 drift
        drift = drift_step.cumsum()

        # -----------------------------
        # 3️⃣ base + noise + drift
        # -----------------------------
        base_s = base if isinstance(base, pd.Series) else pd.Series(base, index=df.index)

        return pd.to_numeric(base_s, errors="coerce") + noise + drift


    def generate_EL_TUNNEL(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        return self.generate_EL_STATION(df, cfg)
