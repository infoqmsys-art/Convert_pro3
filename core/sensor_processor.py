"""
SensorProcessor (Convert Pro 3) - Column-based Engine

=====================================================================
센서 모드 분류
=====================================================================
■ 원본참조 (REF) — 실측값을 읽어서 변환
  PASS        원본 그대로
  OFFSET      원본 + base
  EL          원본 + base (경사/변위 아날로그)
  EL_LOW      원본 + base (저노이즈)    ← 가라 노이즈 포함
  SET         base + (원본-base) × scale
  ANSAN_WM    (원본×4) - base + offset
  ANSAN_WM_GA 전값+하드코딩 랜덤증분+평균회귀(시작값 주변 밴드, JSON 불필요)
  COPY        다른 컬럼 복사
  NZADD       참조열 base(인덱스); 0→0, 비0→값+랜덤(rand_min~rand_max)
  VIBROMETER  원본 init 9값(스케일 1~9) → 출력 CH 복사
  SM_TAEAM    원본 유지, 진동값 base 이상만 (base-5)~base 랜덤 보정 (base 비어 있으면 75)

■ 원본미참조 (NON_REF) — 원본 무시, 자체 생성
  V / BASE_RAND / NM / DO_VM   base ± 랜덤 (DO_VM: 용존산소형, scale 기본 ~0.0045)
  DO_CR             BASE ± 균등떨림(scale) + 행마다 ±cr_step 누적(기본 0.0001)
  TS                   base ± 확률분포
  CHANG_V   CSV 8번 열(0-based 인덱스 8) × scale
  CHANG_SM   시간대별 분포
  CHANG_SM2  0-based 8번 행·채널 열 셀 × base(배율) → 열 전체 동일값
  EL_TAEAM / EL_STATION / EL_TUNNEL  base + 노이즈
  CR / CR_TAEAM        BASE에 미세 노이즈만 살짝 쌓인 것처럼(균열계 가라)
  FM                   유량 누적 (carry 이어감)
  RA                   침하 누적

=====================================================================
누락보충(fill) 정책
=====================================================================
- 원본참조 / 원본미참조 모두 fill된 행은 이전 행 값 그대로 유지
- "측정 없음 = 변화 없음" 원칙. 재계산 없음.

✅ 확장 방식:
- 새 모드 추가 시: def generate_HJ(self, df, cfg): ... 만 추가하면 자동 적용됨
"""

# NOTE:
# - SensorProcessor는 decimal/round를 절대 적용하지 않는다.
# - 모든 소수점 처리는 FileProcessor.apply_decimal()에서 일괄 처리한다.

import random  # legacy import (일부 모드에서 scale="VW" 분포 호환 목적)
import numpy as np
import pandas as pd

from core.cumulative_drift import (
    accumulate_from_increments,
    bernoulli_signed_steps,
    cumsum_drift,
    header_key_for_col,
    incremental_output_offset,
    read_carry_float,
    resolve_start_scalar,
)


MODE_META = {
    # ── 원본참조 ──────────────────────────────────────────────────
    "PASS":       {"use_base": False, "use_scale": False, "ref": True,  "desc": "원값 유지"},
    "OFFSET":     {"use_base": True,  "use_scale": False, "ref": True,  "desc": "원값 + base"},
    "EL":         {"use_base": True,  "use_scale": False, "ref": True,  "desc": "경사/변위 아날로그 센서 (원값 + base)"},
    "SET":        {"use_base": True,  "use_scale": True,  "ref": True,  "desc": "base 기준 변위를 scale 배율로 보정"},
    "ANSAN_WM":   {"use_base": True,  "use_scale": True,  "ref": True,  "desc": "지하수위계: (원값×4) - 파이프길이 + 보정"},
    "ANSAN_WM_GA":{"use_base": True,  "use_scale": True,  "ref": False, "desc": "안산 WM 가라: 전값+랜덤+밴드(코드 고정, scale만 선택)"},
    "COPY":       {"use_base": False, "use_scale": False, "ref": True,  "desc": "다른 컬럼 복사"},
    "NZADD":      {"use_base": True,  "use_scale": False, "ref": True,  "desc": "참조열 인덱스 base; 0→0 출력, 비0면 +uniform(rand_min,rand_max)"},
    # ── 원본미참조 ────────────────────────────────────────────────
    "V":          {"use_base": True,  "use_scale": True,  "ref": False, "desc": "전압형 가라 (base ± 랜덤)"},
    "BASE_RAND":  {"use_base": True,  "use_scale": True,  "ref": False, "desc": "참조컬럼 + scale 랜덤"},
    "NM":         {"use_base": True,  "use_scale": True,  "ref": False, "desc": "노이즈 가라 (base ± uniform)"},
    "DO_VM":      {"use_base": True,  "use_scale": True,  "ref": False, "desc": "용존산소형 가라 (BASE ± 균등, scale 기본 0.0045)"},
    "DO_CR":      {"use_base": True,  "use_scale": True,  "ref": False, "desc": "균열형: BASE ± 균등 + ±cr_step 누적 (scale 기본 0.0004)"},
    "TS":         {"use_base": True,  "use_scale": False, "ref": False, "desc": "TS 가라 (base ± 확률분포)"},
    "VIBROMETER": {"use_base": False, "use_scale": True,  "ref": True,  "desc": "진동계: 스케일 1~9 = X/Y/Z 각 최대·최소·평균 순, base 불필요"},
    "SM_TAEAM":   {"use_base": True,  "use_scale": False, "ref": True,  "desc": "TAEAM 진동: 원본 유지, base 이상은 (base-5)~base 랜덤 보정"},
    "CHANG_V":    {"use_base": False, "use_scale": True,  "ref": True,  "desc": "CHANG_V: 8번 열(0-based=8) 값 × scale"},
    "CHANG_SM":   {"use_base": True,  "use_scale": True,  "ref": False, "desc": "소음계 가라"},
    "CHANG_SM2":  {"use_base": True,  "use_scale": False, "ref": True,  "desc": "CHANG_SM2: 8번 행(인덱스8)·채널열 × base"},
    "EL_TAEAM":   {"use_base": True,  "use_scale": True,  "ref": False, "desc": "EL_TAEAM 가라 (base + 정규분포)"},
    "EL_LOW":     {"use_base": True,  "use_scale": True,  "ref": False, "desc": "저노이즈 경사 가라 (scale=노이즈 배율, 기본 1=과거 고정 진폭과 동일)"},
    "EL_STATION": {"use_base": True,  "use_scale": False, "ref": False, "desc": "정거장 경사 가라 (base + noise + drift)"},
    "EL_TUNNEL":  {"use_base": True,  "use_scale": False, "ref": False, "desc": "터널 경사 가라 (EL_STATION과 동일)"},
    "CR":         {"use_base": True,  "use_scale": False, "ref": False, "desc": "균열계 가라 (BASE 주변 미세 노이즈가 살짝 누적)"},
    "CR_TAEAM":   {"use_base": True,  "use_scale": False, "ref": False, "desc": "CR_TAEAM 가라 (저확률 미세 노이즈 누적)"},
    "FM":         {"use_base": True,  "use_scale": False, "ref": False, "desc": "유량계 가라 (carry 이어감, 월~토 06~18시)"},
    "RA":         {"use_base": True,  "use_scale": True,  "ref": False, "desc": "레일변위 가라 (미세 떨림 위주, 하락·침하 경향 최소)"},
    "L-QM":       {"use_base": True,  "use_scale": True,  "ref": False, "desc": "하중계 가라 (base 기준 점진적 감소 + 소수점 2자리 랜덤 노이즈)"},
    "L-KoreaHY":  {"use_base": True,  "use_scale": True,  "ref": False, "desc": "하중계 가라 KoreaHY형 (base 주변 랜덤 진동, 추세 없음)"},
    "ST":         {"use_base": True,  "use_scale": True,  "ref": False, "desc": "변형률계 가라 (base 주변 떨림, 추세 없음)"},
}

# 원본미참조 모드 집합 (원본 센서값 무시, 자체 생성)
NON_REF_MODES = frozenset(k for k, v in MODE_META.items() if not v["ref"])

# 대소문자 무관 모드 조회용 (upper → 원본 키)
_MODE_UPPER_MAP = {k.upper(): k for k in MODE_META}

# CHANG_V 입력 열: 채널설명과 동일 0=A → "8번 열" = 0-based 인덱스 8
CHANG_V_SOURCE_COL = 8
# CHANG_SM2: 0-based 8번 행 = 인덱스 8(9번째 행)
CHANG_SM2_SOURCE_ROW = 8

# ANSAN_WM_GA: 매 행 전값에 더하는 랜덤폭(균등 ±) + 앵커(첫 행)로 당겨 샘플처럼 좁은 밴드 유지.
WM_GA_STEP_HALF = 0.0035
WM_GA_MEAN_REVERT = 0.035


def _fm_increment_between_rows(prev_ts, curr_ts, step_per_hour: float) -> float:
    """
    FM 한 구간(prev→curr) 증가량. generate_FM 루프와 동일 규칙(결정론적):
    curr 시각이 월~토 06~18(18시 미포함)일 때만 (curr−prev) × 시간당 증가.
    배치 N행 / 증분 1행×N회가 같은 시각열이면 동일한 누적이 되도록 이 식만 사용한다.
    """
    try:
        if pd.isna(curr_ts) or pd.isna(prev_ts):
            return 0.0
        weekday = curr_ts.weekday()
        hour = curr_ts.hour
        is_work_time = (weekday < 6) and (6 <= hour < 18)
        if not is_work_time:
            return 0.0
        delta_hours = (curr_ts - prev_ts).total_seconds() / 3600.0
        if delta_hours > 0:
            return float(step_per_hour) * float(delta_hours)
    except Exception:
        pass
    return 0.0


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
        vib_block = file_cfg.get("__vib_init__")
        for _ch, cfg in channels.items():
            cfg["__vib_init__"] = vib_block

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

            method = getattr(self, f"generate_{mode.replace('-', '_')}", None)
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

    def process_gara_only(self, df: pd.DataFrame, file_cfg: dict) -> pd.DataFrame:
        """
        [Deprecated] 누락보충 정책 변경으로 사용하지 않음.
        fill된 행은 원본참조/원본미참조 구분 없이 이전 행 값 그대로 유지.
        ("측정 없음 = 변화 없음" 원칙)
        """
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

            # offset(구 config) → mode 호환 (config에 mode가 없으면 offset 사용)
            # 대소문자 무관 매칭: L-KoreaHY 처럼 mixed-case 모드명도 정상 인식
            raw_mode = (raw.get("mode") or raw.get("offset") or "PASS").strip()
            mode = _MODE_UPPER_MAP.get(raw_mode.upper(), "PASS")

            meta = MODE_META.get(mode, MODE_META["PASS"])

            cfg = {
                "mode": mode,
                "col_idx": 16 + ch,
                "base": None,
                "scale": None,
                # base를 컬럼 참조로 강제하고 싶을 때 config에서 base_ref: true 사용
                "base_ref": bool(raw.get("base_ref", False)),
            }
            # FM 등 변환본 마지막 값 이어가기용 (file_processor에서 설정)
            if "__last_converted_row__" in file_cfg:
                cfg["__last_converted_row__"] = file_cfg["__last_converted_row__"]

            # base
            if meta["use_base"]:
                cfg["base"] = self._parse_number_or_none(raw.get("base", None))

            # scale
            if meta["use_scale"]:
                cfg["scale"] = self._parse_scale(raw.get("scale", None))

            if mode == "RA":
                cfg["ra_settle"] = self._parse_number_or_none(raw.get("ra_settle", None))
                rrm = self._parse_number_or_none(raw.get("ra_rows_per_month", None))
                if rrm is not None and float(rrm) > 0:
                    cfg["ra_rows_per_month"] = float(rrm)
                rdd = self._parse_number_or_none(raw.get("ra_down_prob", None))
                if rdd is not None:
                    cfg["ra_down_prob"] = float(rdd)

            if mode == "DO_CR":
                cfg["cr_step"] = self._parse_number_or_none(raw.get("cr_step"))
                cfg["cr_step_prob"] = self._parse_number_or_none(raw.get("cr_step_prob"))

            if mode == "NZADD":
                cfg["rand_min"] = self._parse_number_or_none(raw.get("rand_min"))
                cfg["rand_max"] = self._parse_number_or_none(raw.get("rand_max"))

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
        - "0,0015" 등 쉼표 소수점 허용
        """
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.strip().replace(",", ".")
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
        default_colref = mode in ("COPY", "BASE_RAND", "NZADD")

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
        base = self._resolve_base(df, cfg)
        return x + base

    # EL = 원본 + base (OFFSET과 동일, 경사/변위 아날로그 센서용 명시적 별칭)
    generate_EL = generate_OFFSET

    def generate_SM_TAEAM(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        TAEAM 진동 보정: 원본 컬럼 값을 쓰되, base(리미트) 이상인 셀만 (base-5)~base 구간
        균등 랜덤으로 치환. base가 비어 있거나 숫자가 아니면 리미트 75, 구간 70~75(기본).
        NaN·비유한값은 그대로 둔다.
        """
        col_idx = cfg["col_idx"]
        x = pd.to_numeric(df.iloc[:, col_idx], errors="coerce").astype(float)
        arr = x.to_numpy(dtype=float, copy=True)
        rng = np.random.default_rng()
        default_limit = 75.0
        band = 5.0
        raw = cfg.get("base", None)
        s = "" if raw is None else str(raw).strip()
        if not s:
            limit = default_limit
        else:
            try:
                limit = float(s)
            except (TypeError, ValueError):
                limit = default_limit
        lo = limit - band
        hi = np.isfinite(arr) & (arr >= float(limit))
        if hi.any():
            k = int(hi.sum())
            arr[hi] = lo + rng.random(k) * (limit - lo)
        return pd.Series(arr, index=df.index)

    def generate_RA(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        RA (레일변위계·각도):
        - 완전 가라값: 원본 센서값을 사용하지 않는다.
        - 시작값: 변환본 마지막 값(carry) 우선 → 없으면 base → 없으면 0.0
        - 행동 모델(기본): 명시적 하락 스텝은 행당 ~0.002% — 사실상 미세 떨림(hold)만 보이게
        - 노이즈는 초기치 주변에서 매우 좁게 진동 (행마다 독립, 누적 안 됨)
        - 선형 침하(ra_settle) 기본 0 — 장기 하향 드리프트 없음(필요 시 음수로 지정)

        config 파라미터 (CH 설정에서 지정 가능):
          scale       : 행별 잡음 진폭 한계 (기본 0.015 상당)
          ra_settle   : 월간 선형 침하량(음수, 기본 0.0=없음). 음수면 월간 그만큼 점진 하향
          ra_rows_per_month: 그 월간 침하를 나눌 데이터 행 수(기본 7200).
              샘플이 촘촘할수록 크게(예: 2분 간격×30일≈21600). 예전 기본 720은 행 많을 때 과도 누적
          ra_down_prob: 명시적 하락 스텝 비율 (기본 2e-5 ≈ 행당 0.002%, 0이면 하락 스텝 없음)
          ra_up_prob  : 명시적 상승 스텝 비율 (기본 0.001 = 0.1%)
          ra_spike_prob: 스파이크 발생 확률 (기본 0.003)
        """
        col_idx = cfg["col_idx"]
        n = len(df)
        rng = np.random.default_rng()

        # ── 노이즈 진폭 (행마다 독립, 누적 안 됨 → 이게 실제 "떨림")
        raw_scale = cfg.get("scale")
        if raw_scale is None or (isinstance(raw_scale, str) and raw_scale.strip().upper() in ("", "VW")):
            scale_v = 0.015          # 기본: ±0.015 (원래 노이즈 유지)
        else:
            try:
                scale_v = float(raw_scale)
            except (TypeError, ValueError):
                scale_v = 0.015

        # ── 확률: 하락은 별도(기본 2e-5)로 두어 1%도 아니고 사실상 거의 없게
        def _ra_float(key, default):
            v = cfg.get(key, None)
            if v is None or (isinstance(v, str) and str(v).strip() == ""):
                return default
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        down_prob = min(max(_ra_float("ra_down_prob", 2e-5), 0.0), 0.01)
        up_prob = min(max(_ra_float("ra_up_prob", 1e-3), 0.0), 0.05)
        if down_prob + up_prob > 0.999:
            s = down_prob + up_prob
            down_prob, up_prob = down_prob / s * 0.999, up_prob / s * 0.999
        hold_prob = 1.0 - down_prob - up_prob

        # ── drift 스텝 크기 (누적값 → 극소량으로 설정)
        # 노이즈(±0.015)에 비해 1/1000 수준 → 월간 drift는 거의 보이지 않음
        down_mag    = float(cfg.get("ra_down_mag", 1e-5) or 1e-5)
        up_mag      = float(cfg.get("ra_up_mag",   6e-6) or 6e-6)
        hold_jitter = 1e-6   # 유지 시 미세 떨림 (실질적으로 0)

        # ra_settle: 월간 선형 침하량(음수). 기본 0 (장기 하향 없음)
        _rs = cfg.get("ra_settle", None)
        if _rs is None or (isinstance(_rs, str) and str(_rs).strip() == ""):
            monthly_settle = 0.0
        else:
            try:
                monthly_settle = float(_rs)
            except (TypeError, ValueError):
                monthly_settle = 0.0
        rpm = float(cfg.get("ra_rows_per_month", 7200) or 7200)
        rpm = max(72.0, min(rpm, 1_000_000.0))
        settle_per_row = monthly_settle / rpm

        # ── 중앙값(center): 순수 선형 drift, 누적 없는 결정론적 이동
        #    center[t] = start + settle_per_row * t
        #    → 랜덤값은 이 center 주변에서 독립적으로 진동 (누적 안 됨)
        t_arr = np.arange(n, dtype=float)

        # ── 행별 독립 진동 (누적 없음, hold + 드문 up/down)
        mode_r = rng.random(n)
        oscillation = np.zeros(n, dtype=float)

        m_down = mode_r < down_prob
        m_hold = (mode_r >= down_prob) & (mode_r < down_prob + hold_prob)
        m_up   = ~(m_down | m_hold)

        # down: center 아래 — 드문 경우에만, 진폭도 상대적으로 작게
        if m_down.any():
            k = int(m_down.sum())
            oscillation[m_down] = -rng.uniform(scale_v * 0.08, scale_v * 0.45, size=k)
        # hold: center 근방 미세 떨림
        if m_hold.any():
            oscillation[m_hold] = rng.normal(0.0, scale_v * 0.15, size=int(m_hold.sum()))
        # up: center 위 영역 (scale_v의 10%~60%)
        if m_up.any():
            oscillation[m_up] = rng.uniform(scale_v * 0.1, scale_v * 0.6, size=int(m_up.sum()))

        oscillation = np.clip(oscillation, -scale_v, scale_v)
        oscillation[0] = 0.0   # 첫 행은 시작값 그대로

        # ── 드문 스파이크 (독립, 누적 없음)
        spike_prob = float(cfg.get("ra_spike_prob", 0.003) or 0.003)
        spike_prob = min(max(spike_prob, 0.0), 0.05)
        spike_amp  = scale_v * 1.2
        spike_mask = rng.random(n) < spike_prob
        spike_mask[0] = False
        if spike_mask.any():
            nsp = int(spike_mask.sum())
            # 스파이크도 음·양 대칭이면 체감상 자주 "내려감" — 위쪽이 다소 많도록 편향
            spike_dir = np.where(rng.random(nsp) < 0.05, -1.0, 1.0)
            oscillation[spike_mask] = spike_dir * rng.uniform(scale_v * 0.8, spike_amp, size=nsp)

        # ── 최종 출력: center (선형 drift) + 독립 진동
        hk = header_key_for_col(col_idx)
        try:
            base_val = float(cfg.get("base") or 0.0)
        except (TypeError, ValueError):
            base_val = 0.0
        start = resolve_start_scalar(read_carry_float(cfg, hk), base_val)
        center = start + settle_per_row * t_arr
        out = center + oscillation
        return pd.Series(out, index=df.index, dtype=float)

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

    def generate_ANSAN_WM(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        ANSAN_WM (지하수위계):
        - 원본값(V) * 4 = WL (하부에서 물까지의 높이)
        - GL = WL - 파이프길이 + offset = (V * 4) - BASE + offset
        - BASE는 파이프 전체 길이 (양수)
        - offset은 보정값 (선택, config의 offset_add 또는 scale 사용)
        - 결과는 파이프 상단에서 물까지의 거리 (음수 = 아래)
        """
        col_idx = cfg["col_idx"]
        x = pd.to_numeric(df.iloc[:, col_idx], errors="coerce")

        base = self._resolve_base(df, cfg)

        # base를 Series 또는 스칼라 모두 지원
        if isinstance(base, pd.Series):
            base_s = pd.to_numeric(base, errors="coerce")
        else:
            try:
                base_val = float(base)
            except Exception:
                base_val = 0.0
            base_s = pd.Series(base_val, index=df.index)

        # offset 보정값 (offset_add 또는 scale 컬럼 사용)
        offset_val = 0.0
        for key in ("offset_add", "offset", "scale"):
            v = cfg.get(key)
            if v is not None and str(v).strip() != "":
                try:
                    offset_val = float(v)
                    break
                except (ValueError, TypeError):
                    pass

        # GL = (V * 4) - 파이프길이 + offset
        values = (x * 4.0) - base_s + offset_val
        return pd.to_numeric(values, errors="coerce")

    def generate_ANSAN_WM_GA(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        ANSAN_WM_GA — 안산 WM용 **가라** (원본 열 무시):

        매 행: **다음 = 전값 + 균등랜덤(±step_half) + mean_revert×(첫값−전값)**  
        `step_half`·`mean_revert`는 코드 상수(`WM_GA_STEP_HALF`, `WM_GA_MEAN_REVERT`).  
        **scale** 비우면 위 step_half, 넣으면 그 값을 반폭으로 사용(선택).

        base = 첫 행( carry 우선 ). JSON `wm_ga_*` 없음.
        """
        n = len(df)
        if n == 0:
            return pd.Series(dtype=float)
        rng = np.random.default_rng()
        col_idx = cfg["col_idx"]
        hk = header_key_for_col(col_idx)
        _raw_b = cfg.get("base")
        if _raw_b is None or (isinstance(_raw_b, str) and _raw_b.strip() == ""):
            base_val = 0.0
        else:
            try:
                base_val = float(_raw_b)
            except (TypeError, ValueError):
                base_val = 0.0
        start = resolve_start_scalar(read_carry_float(cfg, hk), base_val)

        raw_sc = cfg.get("scale")
        if raw_sc is None or (isinstance(raw_sc, str) and raw_sc.strip() == ""):
            step_half = WM_GA_STEP_HALF
        else:
            try:
                if isinstance(raw_sc, str):
                    raw_sc = raw_sc.strip().replace(",", ".")
                step_half = max(0.0, float(raw_sc))
            except (TypeError, ValueError):
                step_half = WM_GA_STEP_HALF

        kappa = WM_GA_MEAN_REVERT
        anchor = float(start)
        out = np.empty(n, dtype=float)
        out[0] = anchor
        for i in range(1, n):
            delta = rng.uniform(-step_half, step_half)
            pull = kappa * (anchor - out[i - 1])
            out[i] = out[i - 1] + delta + pull

        return pd.Series(out, index=df.index, dtype=float)

    def generate_FM(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        FM (유량계):
        - m³ 단위 누적값
        - 무조건 변환본 마지막 값 기준으로 이어감 (원본/BASE fallback 없음)
        - 데이터 없으면 0.0 → 사용자가 변환본에 수동 입력 후 사용
        - 월~토 오전 6시 ~ 오후 6시(18시 미포함)에 해당하는 행 시각에서만 구간 증가
        - 일요일은 증가 안 함 (weekday >= 6)
        - FM은 확률 없음: 동일 시각열이면 N행 한 번 처리 ≡ 1행씩 N번(증분)과 같은 누적
        """
        col_idx = cfg["col_idx"]
        ch_name = f"CH{col_idx - 16}"  # CH0~CH7 매핑
        
        if self.logger:
            self.logger.log(f"[INFO] FM 센서 시작: {ch_name} (col_idx={col_idx})", level="INFO")
        
        # 변환본 마지막 값만 사용 (무조건 변환본 전 데이터 기준)
        header_key = header_key_for_col(col_idx)
        carry = read_carry_float(cfg, header_key)
        initial_value = resolve_start_scalar(carry, 0.0)
        if carry is None and self.logger:
            self.logger.log(
                f"[INFO] FM {ch_name}: 변환본 마지막 값 없음 → 0.0 사용 (변환본에 수동 입력 시 이어감)",
                level="INFO"
            )
        
        # --------------------------------------------------
        # 선형 증가량 설정 (실제 시간 간격 기반)
        # --------------------------------------------------
        # 기본: 한 달(target_monthly) 동안 work_days * work_hours 만큼만 작동한다고 가정
        #   예) 26일 * 12시간 = 312시간 → 6.5 / 312 ≈ 0.021 m³/시간
        target_monthly = float(cfg.get("FM_TARGET_MONTHLY", 6.5))
        work_days_per_month = float(cfg.get("FM_WORK_DAYS_PER_MONTH", 26))
        work_hours_per_day = float(cfg.get("FM_WORK_HOURS_PER_DAY", 12))
        try:
            hours_per_month = max(work_days_per_month * work_hours_per_day, 1.0)
        except Exception:
            hours_per_month = 312.0
        step_per_hour = target_monthly / hours_per_month  # 작업 시간 1시간당 증가량

        # 시간 컬럼을 한 번만 파싱 (성능 최적화, format='mixed'로 혼합 형식 대응)
        try:
            time_series = pd.to_datetime(df.iloc[:, 0], errors="coerce", format="mixed")
        except TypeError:
            time_series = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        n = len(df)
        increments = np.zeros(n, dtype=float)

        # 각 행의 증가분(increment)만 계산하고 마지막에 공통 누적기로 합친다.
        for idx in range(1, n):
            try:
                timestamp = time_series.iloc[idx]
                prev_ts = time_series.iloc[idx - 1]
                inc = _fm_increment_between_rows(prev_ts, timestamp, step_per_hour)
                if inc != 0.0:
                    increments[idx] = inc
            except Exception:
                # 시간 파싱 실패 시 증가하지 않음
                continue

        values = accumulate_from_increments(initial_value, increments)
        # 증분 변환: 배치에 행이 1개만 있어도, 변환본 마지막 시각 ~ 첫 새 행 사이
        # 구간은 루프(range(1,n))에 포함되지 않아 증가분이 0이 된다. 동일 규칙으로 보정.
        gap_before_batch = 0.0
        if carry is not None and n > 0:
            last_dict = cfg.get("__last_converted_row__")
            if isinstance(last_dict, dict):
                raw_prev = last_dict.get("timestamp")
                if raw_prev is not None and str(raw_prev).strip() != "":
                    try:
                        prev_end = pd.to_datetime(raw_prev, errors="coerce", format="mixed")
                    except TypeError:
                        prev_end = pd.to_datetime(raw_prev, errors="coerce")
                    first_ts = time_series.iloc[0]
                    if pd.notna(prev_end) and pd.notna(first_ts) and first_ts > prev_end:
                        gap_before_batch = _fm_increment_between_rows(
                            prev_end, first_ts, step_per_hour
                        )
        if gap_before_batch != 0.0:
            values = np.asarray(values, dtype=float) + gap_before_batch

        return pd.Series(values, index=df.index, dtype=float)

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

    def generate_CR_TAEAM(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        CR_TAEAM: CR과 같은 맥락(BASE 주변 미세 노이즈 누적), 행당 5% 확률로 ±0.0001 스텝
        """
        base = self._resolve_base(df, cfg)
        n = len(df)
        rng = np.random.default_rng()
        drift_step = bernoulli_signed_steps(
            n, rng, 0.05, (-0.0001, 0.0001), skip_first_row=False
        )
        drift = cumsum_drift(drift_step)
        hk = header_key_for_col(cfg["col_idx"])
        base_s = base if isinstance(base, pd.Series) else pd.Series(base, index=df.index)
        base_num = pd.to_numeric(base_s, errors="coerce")
        drift_s = pd.Series(drift, index=df.index, dtype=float)
        if isinstance(base, pd.Series):
            first_out = float(base_num.iloc[0]) + float(drift[0])
            off = incremental_output_offset(cfg, hk, first_out)
            return base_num + drift_s + off
        b0 = float(base_num.iloc[0]) if pd.notna(base_num.iloc[0]) else 0.0
        start = resolve_start_scalar(read_carry_float(cfg, hk), b0)
        return pd.Series(start + drift, index=df.index, dtype=float)

    def generate_EL_TAEAM(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        EL_TAEAM 모드: BASE 기준 정규 분포 노이즈로 움직임
        - scale 기본값 0.001 (scale을 표준편차로 사용, 대부분 작은 변동)
        - 정규 분포를 사용하여 자연스러운 노이즈 생성
        """
        base = self._resolve_base(df, cfg)
        scale = self._resolve_scale(cfg, default=0.001)
        
        try:
            scale_v = float(scale) if not isinstance(scale, str) else 0.001
        except Exception:
            scale_v = 0.001
        
        n = len(df)
        rng = np.random.default_rng()
        # 정규 분포 사용 (평균 0, 표준편차 scale_v)
        # 대부분의 값이 ±2*scale_v 범위 내에 분포하고, 드물게 큰 값도 나타남
        noise = rng.normal(0.0, scale_v, size=n)
        base_s = base if isinstance(base, pd.Series) else pd.Series(base, index=df.index)
        return pd.to_numeric(base_s, errors="coerce") + noise

    def generate_CHANG_V(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        CHANG_V: 8번 열(0-based 인덱스 8) 값 × scale
        - scale: 배율(예: 0.2 → 0.2배, 2 → 2배). 생략 시 1.0
        - 해당 열이 없으면 NaN
        """
        n = len(df)
        if df.shape[1] <= CHANG_V_SOURCE_COL:
            return pd.Series([np.nan] * n, index=df.index, dtype=float)
        x = pd.to_numeric(df.iloc[:, CHANG_V_SOURCE_COL], errors="coerce")
        scale = self._resolve_scale(cfg, default=1.0)
        if isinstance(scale, str) and str(scale).strip().upper() == "VW":
            scale_v = 1.0
        else:
            try:
                scale_v = float(scale)
            except (TypeError, ValueError):
                scale_v = 1.0
        return (x * scale_v).astype(float)

    def generate_CHANG_SM2(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        CHANG_SM2: 0-based 8번 행(=CHANG_SM2_SOURCE_ROW) × 현재 채널 열(col_idx) 한 셀에 base(배율)을 곱한 값을
        열 전체에 동일하게 채움. base 0.98 → 0.98배, 비어 있으면 1.0. scale 필드 미사용.
        행 수가 8 이하이거나 셀을 읽을 수 없으면 NaN.
        """
        n = len(df)
        col_idx = int(cfg.get("col_idx", 0))
        if n <= CHANG_SM2_SOURCE_ROW or df.shape[1] <= col_idx:
            return pd.Series([np.nan] * n, index=df.index, dtype=float)
        v = df.iloc[CHANG_SM2_SOURCE_ROW, col_idx]
        if isinstance(v, pd.Series):
            v = v.iloc[0] if len(v) else np.nan
        v = pd.to_numeric(v, errors="coerce")
        b = self._parse_number_or_none(cfg.get("base"))
        mult = 1.0 if b is None else float(b)
        if pd.isna(v):
            return pd.Series([np.nan] * n, index=df.index, dtype=float)
        out = float(v) * mult
        return pd.Series([out] * n, index=df.index, dtype=float)

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
                try:
                    timestamps = pd.to_datetime(df.iloc[:, 0], errors='coerce', format='mixed')
                except TypeError:
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
                try:
                    ts_night = pd.to_datetime(df.iloc[:, 0], errors='coerce', format='mixed')
                except TypeError:
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
        CR (균열계 가라, 컬럼 기반)

        해석: BASE에서 노이즈만 조금 생긴 것처럼 보이게 할 때 사용 (실측 원본 미사용).
        - 시작 레벨은 carry 또는 base
        - 행마다 낮은 확률로 ±STEP 스파이크가 나면 그걸 시간 방향으로 누적
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
        # 1️⃣ 저확률 스파이크 스텝 → 공통 누적
        # -----------------------------
        spike_step = bernoulli_signed_steps(
            n, rng, P_SPIKE, (-STEP, STEP), skip_first_row=True
        )
        drift = cumsum_drift(spike_step)
        hk = header_key_for_col(cfg["col_idx"])
        start = resolve_start_scalar(read_carry_float(cfg, hk), base)

        # -----------------------------
        # 2️⃣ 최종 값
        # -----------------------------
        return pd.Series(start + drift, index=df.index)

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

    def generate_NZADD(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        NZADD — 참조 열(0-based base 인덱스) 각 행:
        - 0 ~ 0.005 범위(양 끝 포함)의 유한값 → 원값 그대로 유지
        - 0.005 초과·유한 → 참조값 + uniform(rand_min, rand_max)
          기본 rand_min=0.015, rand_max=0.035
        - NaN/inf 참조값은 원값 유지(NaN/inf 출력)
        """
        col_idx = cfg["col_idx"]
        ref = self._resolve_base(df, cfg)
        if not isinstance(ref, pd.Series):
            return pd.to_numeric(df.iloc[:, col_idx], errors="coerce")

        r = pd.to_numeric(ref, errors="coerce").to_numpy(dtype=float, copy=True)
        lo = cfg.get("rand_min")
        hi = cfg.get("rand_max")
        lo_f = float(lo) if lo is not None else 0.015
        hi_f = float(hi) if hi is not None else 0.035
        if lo_f > hi_f:
            lo_f, hi_f = hi_f, lo_f

        n = len(r)
        rng = np.random.default_rng()
        u = rng.uniform(lo_f, hi_f, size=n)
        out = r.copy()
        fin = np.isfinite(r)
        nz = fin & (r > 0.005)
        out[nz] = r[nz] + u[nz]
        out[~fin] = r[~fin]
        return pd.Series(out, index=df.index, dtype=float)

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

    def generate_TS(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        TS:
        - BASE 기준으로 ±0.0005 범위에서 확률 분포 기반 변동
        - 대부분 작은 변동, 드물게 최대 0.0005~0.0006까지 변동
        """
        col_idx = cfg["col_idx"]
        base = self._resolve_base(df, cfg)
        
        if not isinstance(base, pd.Series):
            # 상수 base인 경우
            base = float(base) if base is not None else 0.0
            base = pd.Series(base, index=df.index)
        else:
            base = pd.to_numeric(base, errors="coerce")
        
        n = len(df)
        rng = np.random.default_rng()
        
        # 확률 분포 기반 변동
        r = rng.random(n)  # 0~1 사이 랜덤
        sign = rng.choice([-1, 1], size=n)  # 음수/양수 방향
        
        d = np.zeros(n, dtype=float)
        
        # 확률 분포:
        # 70%: 매우 작은 변동 (±0.00005)
        # 20%: 작은 변동 (±0.0002)
        # 8%: 중간 변동 (±0.0004)
        # 2%: 최대 변동 (±0.0005~0.0006)
        
        mask_very_small = r < 0.70
        mask_small = (r >= 0.70) & (r < 0.90)
        mask_medium = (r >= 0.90) & (r < 0.98)
        mask_max = r >= 0.98
        
        d[mask_very_small] = sign[mask_very_small] * rng.uniform(0.00002, 0.00005, size=np.sum(mask_very_small))
        d[mask_small] = sign[mask_small] * rng.uniform(0.00015, 0.0002, size=np.sum(mask_small))
        d[mask_medium] = sign[mask_medium] * rng.uniform(0.00035, 0.0004, size=np.sum(mask_medium))
        d[mask_max] = sign[mask_max] * rng.uniform(0.0005, 0.0006, size=np.sum(mask_max))
        
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

    def generate_DO_VM(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        DO_VM (용존산소·VM형 BASE ± 균등):
        - 원본 무시, base + uniform(-scale, +scale)
        - scale 미지정 시 0.0045 → BASE≈0.048일 때 대략 0.043~0.053 밴드(샘플 열과 유사)
        - base_ref: True면 다른 컬럼을 BASE로 사용 (NM과 동일)
        """
        base = self._resolve_base(df, cfg)
        scale = self._resolve_scale(cfg, default=0.0045)
        try:
            scale_v = float(scale) if not isinstance(scale, str) else 0.0
        except Exception:
            scale_v = 0.0045

        n = len(df)
        rng = np.random.default_rng()
        noise = rng.uniform(-scale_v, scale_v, size=n) if scale_v != 0.0 else np.zeros(n, dtype=float)

        base_s = base if isinstance(base, pd.Series) else pd.Series(base, index=df.index)
        return pd.to_numeric(base_s, errors="coerce") + noise

    def generate_DO_CR(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        DO_CR (균열형 · BASE + 행별 떨림 + 미세 누적):
        - 시작 레벨 = 변환본 carry 우선, 없으면 config base (generate_CR와 동일)
        - 각 행: uniform(-scale, +scale) 랜덤 떨림 — 기본 scale 0.0004는 제공 샘플(std≈0.00039)에 근접
        - 누적: 행 1부터 매 행 확률 cr_step_prob(기본 1.0)로 ±cr_step(기본 0.0001) 한 칸씩 합산
        """
        col_idx = cfg["col_idx"]
        hk = header_key_for_col(col_idx)
        base = self._resolve_base(df, cfg)
        if isinstance(base, pd.Series):
            b0 = float(pd.to_numeric(base.iloc[0], errors="coerce"))
            if not np.isfinite(b0):
                b0 = 0.0
        else:
            try:
                b0 = float(base)
            except (TypeError, ValueError):
                b0 = 0.0

        scale = self._resolve_scale(cfg, default=0.0004)
        try:
            scale_v = float(scale) if not isinstance(scale, str) else 0.0004
        except Exception:
            scale_v = 0.0004

        raw_step = cfg.get("cr_step")
        STEP = float(raw_step) if raw_step is not None else 0.0001

        raw_prob = cfg.get("cr_step_prob")
        prob = float(raw_prob) if raw_prob is not None else 1.0
        prob = max(0.0, min(1.0, prob))

        n = len(df)
        rng = np.random.default_rng()
        jitter = rng.uniform(-scale_v, scale_v, size=n) if scale_v != 0.0 else np.zeros(n, dtype=float)

        drift_step = bernoulli_signed_steps(
            n, rng, prob, (-STEP, STEP), skip_first_row=True
        )
        drift = cumsum_drift(drift_step)

        start = resolve_start_scalar(read_carry_float(cfg, hk), b0)
        return pd.Series(start + jitter + drift, index=df.index, dtype=float)

    def generate_EL_LOW(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        EL_LOW: BASE + (메인 균등 노이즈 + 가끔 큰 튀김 + 저확률 ±스텝 누적)
        - scale: 노이즈 스케일(배율). 과거 고정 진폭에 곱함. 생략·1 → 예전과 동일.
          예: 2 → 진폭 2배, 0.5 → 절반.
        """
        base = self._resolve_base(df, cfg)
        if isinstance(base, pd.Series):
            base = float(base.iloc[0])
        else:
            base = float(base)

        # 기준 진폭(과거 고정값); scale은 여기에 곱하는 노이즈 배율
        REF_MAIN = 0.0003
        REF_SPIKE = 0.001
        REF_DRIFT = 0.0001

        noise_scale = self._resolve_scale(cfg, default=1.0)
        try:
            ns = float(noise_scale) if not isinstance(noise_scale, str) else 1.0
        except Exception:
            ns = 1.0
        if not np.isfinite(ns) or ns < 0.0:
            ns = 1.0

        amp_main = REF_MAIN * ns
        amp_spike = REF_SPIKE * ns
        amp_drift_step = REF_DRIFT * ns

        n = len(df)
        rng = np.random.default_rng()

        r = rng.random(n)
        noise = np.zeros(n, dtype=float)

        # -------------------------
        # 1️⃣ 기본 노이즈 (약 98.5%)
        # -------------------------
        m_base = r >= 0.015
        noise[m_base] = rng.uniform(
            -amp_main, amp_main,
            size=m_base.sum()
        )

        # -------------------------
        # 2️⃣ 튀는 값 (약 1.5%)
        # -------------------------
        m_spike = r < 0.015
        noise[m_spike] = rng.uniform(
            -amp_spike, amp_spike,
            size=m_spike.sum()
        )

        # -------------------------
        # 3️⃣ 아주 느린 누적 드리프트 (0.2% 확률 × 작은 스텝)
        # -------------------------
        drift_step = bernoulli_signed_steps(
            n, rng, 0.002, (-amp_drift_step, amp_drift_step), skip_first_row=False
        )
        drift = cumsum_drift(drift_step)
        drift[0] = 0.0

        # -------------------------
        # 4️⃣ 최종 값: base + 노이즈 + 누적 drift
        # incremental_output_offset 사용 안 함:
        # 배치마다 offset을 더하면 증분 변환 시 오프셋이 잘못 쌓여 위로 기어올라가는 버그 발생
        # -------------------------
        return pd.Series(base + noise + drift, index=df.index, dtype=float)

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
        # 2️⃣ 아주 낮은 확률 drift (0.1% × ±0.0001 → 공통 누적)
        # -----------------------------
        drift_step = bernoulli_signed_steps(
            n, rng, 0.001, (-0.0001, 0.0001), skip_first_row=False
        )
        drift = cumsum_drift(drift_step)

        # -----------------------------
        # 3️⃣ base + noise + drift (+ 증분 시 첫 행 레벨 맞춤)
        # -----------------------------
        base_s = base if isinstance(base, pd.Series) else pd.Series(base, index=df.index)
        base_num = pd.to_numeric(base_s, errors="coerce")
        hk = header_key_for_col(cfg["col_idx"])
        first_out = float(base_num.iloc[0]) + float(noise[0]) + float(drift[0])
        off = incremental_output_offset(cfg, hk, first_out)

        return base_num + noise + pd.Series(drift, index=df.index, dtype=float) + off


    def generate_EL_TUNNEL(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        return self.generate_EL_STATION(df, cfg)

    def generate_VIBROMETER(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        진동계: 원본 init 9열(24~32열) 중 스케일로 고른 값을 해당 CH에 복사.
        스케일 1~9 → 순서: X최대, X최소, X평균, Y최대, Y최소, Y평균, Z최대, Z최소, Z평균
        (원본 헤더: initDegreeX, initDegreeY, initDegreeZ, initCrack, initCH1~initCH5)
        """
        sc = cfg.get("scale")
        if sc is None:
            return pd.Series(0.0, index=df.index)
        try:
            idx = int(float(sc)) - 1
        except (TypeError, ValueError):
            return pd.Series(0.0, index=df.index)
        if idx < 0 or idx > 8:
            return pd.Series(0.0, index=df.index)

        block = cfg.get("__vib_init__")
        if block is None or getattr(block, "shape", (0,))[1] <= idx:
            return pd.Series(0.0, index=df.index)

        col = pd.to_numeric(block.iloc[:, idx], errors="coerce").astype(float)
        return pd.Series(col.values, index=df.index)

    def generate_L_QM(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        L-QM (하중계 가라값):
        - base = 시작 하중값 (예: 2281). carry 값 우선 사용.
        - scale = 행별 노이즈 폭 (기본 1.0). 소수점 2자리 수준 랜덤.
        - lqm_daily_drift: 하루당 감소량 (기본 -0.5, 음수 = 감소)
        - lqm_rows_per_day: 하루 행 수 (기본 144 = 10분 간격)

        동작:
          center[t] = start + (daily_drift / rows_per_day) × t   ← 선형 내림 추세
          noise[t]  = uniform(-scale, +scale)                      ← 행별 독립 노이즈
          output[t] = center[t] + noise[t]

        소수점 처리는 FileProcessor.apply_decimal()에서 수행.
        """
        n = len(df)
        rng = np.random.default_rng()

        # ── scale (노이즈 폭)
        raw_scale = cfg.get("scale")
        if raw_scale is None or (isinstance(raw_scale, str) and raw_scale.strip() == ""):
            scale_v = 1.0
        else:
            try:
                scale_v = float(raw_scale)
            except (TypeError, ValueError):
                scale_v = 1.0

        # ── drift 파라미터 (노이즈 폭의 약 1/10 수준 → 장기적으로만 감지됨)
        daily_drift   = float(cfg.get("lqm_daily_drift",   -0.01) or -0.01)
        rows_per_day  = float(cfg.get("lqm_rows_per_day",   144)   or 144)
        rows_per_day  = max(1.0, rows_per_day)
        drift_per_row = daily_drift / rows_per_day   # 행당 감소량

        # ── 시작값: carry → base → 0
        hk = header_key_for_col(cfg["col_idx"])
        try:
            base_val = float(cfg.get("base") or 0.0)
        except (TypeError, ValueError):
            base_val = 0.0
        start = resolve_start_scalar(read_carry_float(cfg, hk), base_val)

        # ── 선형 내림 추세 (center)
        t_arr  = np.arange(n, dtype=float)
        center = start + drift_per_row * t_arr

        # ── 행별 독립 노이즈 (소수점 2자리 수준)
        noise = rng.uniform(-scale_v, scale_v, size=n)
        # 소수점 2자리로 반올림하여 자연스러운 2자리 수준 노이즈 생성
        noise = np.round(noise, 2)

        out = center + noise
        return pd.Series(out, index=df.index, dtype=float)

    def generate_ST(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        ST (변형률계 가라값):
        - base 주변에서 추세 없이 떨림
        - scale = 노이즈 최대 폭 (기본 1.0)
        - 출력 = base + uniform(-scale, scale)

        소수점 처리는 FileProcessor.apply_decimal()에서 수행.
        """
        n = len(df)
        rng = np.random.default_rng()

        # ── scale
        raw_scale = cfg.get("scale")
        if raw_scale is None or (isinstance(raw_scale, str) and raw_scale.strip() == ""):
            scale_v = 1.0
        else:
            try:
                scale_v = float(raw_scale)
            except (TypeError, ValueError):
                scale_v = 1.0

        # ── base
        try:
            base_val = float(cfg.get("base") or 0.0)
        except (TypeError, ValueError):
            base_val = 0.0

        noise = rng.uniform(-scale_v, scale_v, size=n)
        out   = base_val + noise
        return pd.Series(out, index=df.index, dtype=float)

    def generate_L_KoreaHY(self, df: pd.DataFrame, cfg: dict) -> pd.Series:
        """
        L-KoreaHY (하중계 가라값 — KoreaHY형):
        - base 주변 랜덤 진동 + 미세한 선형 감소 추세
        - scale = 노이즈 최대 폭 (기본 10.0)
        - lqm_daily_drift   : 하루 감소량 (기본 -1.0, 음수=감소)
        - lqm_rows_per_day  : 하루 행 수  (기본 144 = 10분 간격)

        확률 분포:
          60%: ±(scale×0.3) 이내  — 미세 변화
          30%: ±(scale×0.7) 이내  — 중간 변화
          10%: ±scale 이내         — 큰 변화

        출력 = (base + 미세 선형 감소) + 가중 랜덤 진동
        소수점 처리는 FileProcessor.apply_decimal()에서 수행.
        """
        n = len(df)
        rng = np.random.default_rng()

        # ── scale (노이즈 최대 폭, 기본 10)
        raw_scale = cfg.get("scale")
        if raw_scale is None or (isinstance(raw_scale, str) and raw_scale.strip() == ""):
            scale_v = 10.0
        else:
            try:
                scale_v = float(raw_scale)
            except (TypeError, ValueError):
                scale_v = 10.0

        # ── drift 파라미터 (노이즈 폭의 약 1/10 수준 → 장기적으로만 감지됨)
        daily_drift  = float(cfg.get("lqm_daily_drift",  -0.1) or -0.1)
        rows_per_day = float(cfg.get("lqm_rows_per_day",  144) or 144)
        rows_per_day = max(1.0, rows_per_day)
        drift_per_row = daily_drift / rows_per_day   # 행당 미세 감소

        # ── base 값 (carry 우선)
        hk = header_key_for_col(cfg["col_idx"])
        try:
            base_val = float(cfg.get("base") or 0.0)
        except (TypeError, ValueError):
            base_val = 0.0
        start = resolve_start_scalar(read_carry_float(cfg, hk), base_val)

        # ── 미세 선형 감소 중심선
        t_arr  = np.arange(n, dtype=float)
        center = start + drift_per_row * t_arr

        # ── 가중 랜덤 진동 (작은 변화가 더 자주)
        r    = rng.random(n)
        sign = rng.choice([-1.0, 1.0], size=n)
        noise = np.zeros(n, dtype=float)

        m_small  = r < 0.60
        m_medium = (r >= 0.60) & (r < 0.90)
        m_large  = r >= 0.90

        if m_small.any():
            noise[m_small]  = sign[m_small]  * rng.uniform(0.0,           scale_v * 0.3, size=m_small.sum())
        if m_medium.any():
            noise[m_medium] = sign[m_medium] * rng.uniform(scale_v * 0.3, scale_v * 0.7, size=m_medium.sum())
        if m_large.any():
            noise[m_large]  = sign[m_large]  * rng.uniform(scale_v * 0.7, scale_v,       size=m_large.sum())

        out = center + noise
        return pd.Series(out, index=df.index, dtype=float)
