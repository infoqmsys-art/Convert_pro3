"""
웹 「센서 타입」 드롭다운과 DB sensor_channel.sensor_kind 저장값 매핑.

DB에는 id(영문 스네이크)만 넣고, 화면에는 label_ko 를 씁니다.
목록 순서는 레거시 계측관리 통합시스템 UI와 맞춥니다.
"""
from __future__ import annotations

import math
from typing import Any, TypedDict


class SensorKindDef(TypedDict):
    id: str
    label_ko: str
    kind_group: str
    default_unit: str


# 스크린 순서 유지 (첫 항목 "-" 는 템플릿에서 빈 option 으로 처리)
SENSOR_KINDS: list[SensorKindDef] = [
    {"id": "structure_tilt", "label_ko": "구조물경사계", "kind_group": "경사", "default_unit": "°"},
    {"id": "crack_meter", "label_ko": "균열측정계", "kind_group": "균열", "default_unit": "mm"},
    {"id": "flow_meter", "label_ko": "유량계", "kind_group": "유체", "default_unit": "m³"},
    {"id": "inclinometer", "label_ko": "지중경사계", "kind_group": "경사", "default_unit": "°"},
    {"id": "surface_settlement", "label_ko": "지표침하계", "kind_group": "침하", "default_unit": "mm"},
    {"id": "internal_displacement", "label_ko": "내공변위계", "kind_group": "변위", "default_unit": "mm"},
    {"id": "rail_displacement", "label_ko": "레일변위계", "kind_group": "변위", "default_unit": "mm"},
    {"id": "groundwater", "label_ko": "지하수위계", "kind_group": "수위", "default_unit": "GL.m"},
    {"id": "vibration", "label_ko": "진동계", "kind_group": "진동", "default_unit": "kine"},
    {"id": "vibration_3axis", "label_ko": "진동계(3축)", "kind_group": "진동", "default_unit": "kine"},
    {"id": "load_cell", "label_ko": "하중계", "kind_group": "하중", "default_unit": "Ton"},
    # 구 DB·임의 코드 호환
    {"id": "other", "label_ko": "기타", "kind_group": "기타", "default_unit": ""},
]

# 예전 catalog id → 현재 id (표시·드롭다운 매칭용). 목록에서 제거된 종류는 기타로 표시.
_LEGACY_SENSOR_KIND_IDS: dict[str, str] = {
    "tilt": "structure_tilt",
    "building_tilt": "structure_tilt",
    "optical_target": "other",
    "embedded_strain": "other",
    "strain": "other",
    "auto_inclinometer": "other",
    "auto_surface_settlement": "other",
}


def kind_by_id(kind_id: str) -> SensorKindDef | None:
    if not kind_id:
        return None
    for k in SENSOR_KINDS:
        if k["id"] == kind_id:
            return k
    mapped = _LEGACY_SENSOR_KIND_IDS.get(kind_id)
    if mapped:
        return kind_by_id(mapped)
    return None


def kinds_for_api() -> list[dict]:
    """JSON API 용 단순 목록."""
    return [
        {"id": k["id"], "label": k["label_ko"], "group": k["kind_group"], "unit": k["default_unit"]}
        for k in SENSOR_KINDS
    ]


def kind_label_ko(kind_id: str | None) -> str:
    """sensor_kind(DB id) → 카탈로그 한글명."""
    if not kind_id or not str(kind_id).strip():
        return ""
    kid = str(kind_id).strip()
    kd = kind_by_id(kid)
    if kd:
        return (kd.get("label_ko") or "").strip()
    return kid


def channel_tree_caption(row: dict) -> str:
    """트리·좌측 목록: 센서코드 우선."""
    code = (row.get("sensor_code") or "").strip()
    if code:
        return code
    return (row.get("label") or "").strip() or "—"


def channel_auto_label(
    row: dict | None = None,
    *,
    sensor_code: str | None = None,
    sensor_kind: str | None = None,
) -> str:
    """DB label / 화면 ‘센서명’: 「센서코드 + 공백 + 센서종류(한글)」."""
    row = row or {}
    code = sensor_code if sensor_code is not None else (row.get("sensor_code") or "")
    code = str(code).strip()
    sk = sensor_kind if sensor_kind is not None else (row.get("sensor_kind") or "")
    sk = str(sk).strip()
    kko = kind_label_ko(sk)
    parts: list[str] = []
    if code:
        parts.append(code)
    if kko:
        parts.append(kko)
    if parts:
        return " ".join(parts)
    return (row.get("label") or "").strip() or "—"


def channel_kind_title(row: dict | None) -> str:
    """대제목용: 센서 종류 한글 (없으면 —)."""
    row = row or {}
    kko = kind_label_ko((row.get("sensor_kind") or "").strip())
    return kko or "—"


# 구조물경사계만(레거시 DB의 building_tilt·tilt 는 _LEGACY_SENSOR_KIND_IDS 로 동일 처리)
_TILT_DERIVED_TABLE_KIND_IDS: frozenset[str] = frozenset({"structure_tilt"})
# 지중경사·내공변위(세그먼트): 적재 후 value_real 은 mm(각→L*tan 등). 표·그래프는 조회 구간 첫 유효값을 0 기준 상대변위.
_INCLINOMETER_DERIVED_TABLE_KIND_IDS: frozenset[str] = frozenset(
    {"inclinometer", "internal_displacement", "rail_displacement"}
)

# 균열측정계: 원시 V×10=mm 파생 표시용 (0~50mm 계열 센서 가정)
_CRACK_DERIVED_TABLE_KIND_IDS: frozenset[str] = frozenset({"crack_meter"})

# 유량계: 순간 유량(m³)·전회대비·초기대비 표·단일 시간축 차트용
_FLOW_DERIVED_TABLE_KIND_IDS: frozenset[str] = frozenset({"flow_meter"})

# 하중계: 톤(Ton) 환산값·전회대비·초기대비 표/차트용
_LOAD_CELL_DERIVED_KIND_IDS: frozenset[str] = frozenset({"load_cell"})

# 지표침하계: mm 환산값·변위·전회대비·초기대비 표/차트용
_SURFACE_SETTLEMENT_DERIVED_KIND_IDS: frozenset[str] = frozenset({"surface_settlement"})

# 진동계(3축): 연결 번들 X·Y·Z 채널 3개 합성 PVS(√(x²+y²+z²))
_VIBRATION_3AXIS_IDS: frozenset[str] = frozenset({"vibration_3axis"})
# 진동계·진동계(3축): 관리기준은 1차(주)만 권장, 차트 세로축 기본 범위(저장값 없을 때 적용).
_VIBRATION_CHART_KIND_IDS: frozenset[str] = frozenset({"vibration", "vibration_3axis"})
VIBRATION_MANAGEMENT_PRIMARY_DEFAULT: float = 0.3
VIBRATION_CHART_Y_MIN_DEFAULT: float = 0.0
VIBRATION_CHART_Y_MAX_DEFAULT: float = 0.5

# 유량계: 시간 유량(m³)·차트 Y 기본 고정 범위(관리기준 없음).
FLOW_CALC_FORMULA_1_DEFAULT: str = "m"
FLOW_CHART_Y_MIN_DEFAULT: float = 0.0
FLOW_CHART_Y_MAX_DEFAULT: float = 100.0

# 하중계: m = 스케일 후 계측값. 기본 1번식에서 gf(게이지팩터) 적용해 Ton 산출.
LOAD_CELL_CALC_FORMULA_1_DEFAULT: str = "m*gf"
LOAD_CELL_CHART_Y_MIN_DEFAULT: float = 0.0
LOAD_CELL_CHART_Y_MAX_DEFAULT: float = 150.0

# 지표침하계(1000mm 센서): mm = m*200
SURFACE_SETTLEMENT_CALC_FORMULA_1_DEFAULT: str = "m*200"
SURFACE_SETTLEMENT_CHART_Y_MIN_DEFAULT: float = -26.0
SURFACE_SETTLEMENT_CHART_Y_MAX_DEFAULT: float = 26.0
SURFACE_SETTLEMENT_MANAGEMENT_DEFAULTS_MM: dict[str, float] = {
    "level1_primary": 15.0,
    "level1_secondary": -15.0,
    "level2_primary": 20.0,
    "level2_secondary": -20.0,
    "level3_primary": 25.0,
    "level3_secondary": -25.0,
}

# 지하수위계(25 m급): m = 스케일 후 측정값(V), 계산식 예) m*5-pipe → GL.m, pipe = 파이프심도(m)
GROUNDWATER_CALC_FORMULA_1_DEFAULT: str = "m*5-pipe"
GROUNDWATER_CHART_Y_MIN_DEFAULT: float = -10.0
GROUNDWATER_CHART_Y_MAX_DEFAULT: float = 0.5
_GROUNDWATER_DERIVED_KIND_IDS: frozenset[str] = frozenset({"groundwater"})

# 지중경사계: 원시(스케일 후 m)=경사각(°) 가정 → 수평변위(mm) = L(mm)*tan(r1*pi/180)
INCLINOMETER_SENSOR_LENGTH_MM_DEFAULT: float = 1000.0
INCLINOMETER_CHART_Y_MIN_DEFAULT: float = -100.0
INCLINOMETER_CHART_Y_MAX_DEFAULT: float = 100.0
INCLINOMETER_CALC_FORMULA_1_DEFAULT: str = "m"
INCLINOMETER_CALC_FORMULA_2_DEFAULT: str = "L*tan(r1*pi/180)"

# 구조물경사계 센서설정 「관리기준」 권장 기본값 (변위량 mm, 조회 구간 초기 대비와 동일 스케일)
TILT_MANAGEMENT_DEFAULTS_MM: dict[str, float] = {
    "level1_primary": 0.5,
    "level1_secondary": -0.5,
    "level2_primary": 0.59,
    "level2_secondary": -0.59,
    "level3_primary": 1.0,
    "level3_secondary": -1.0,
}
TILT_CHART_Y_MIN_DEFAULT: float = -0.6
TILT_CHART_Y_MAX_DEFAULT: float = 0.6

# 균열측정계 관리기준 권장 기본값(mm). 차트 기본 세로축은 조회 구간 개폭(mm)과 맞춤.
CRACK_MANAGEMENT_DEFAULTS_MM: dict[str, float] = {
    "level1_primary": 0.2,
    "level1_secondary": -0.2,
    "level2_primary": 0.38,
    "level2_secondary": -0.38,
    "level3_primary": 0.5,
    "level3_secondary": -0.5,
}
CRACK_CHART_Y_MIN_DEFAULT: float = -0.4
CRACK_CHART_Y_MAX_DEFAULT: float = 0.4
# 적재 시 m = scale_k×원시+b ; 균열 0~50mm 계열은 V를 mm로: value_real 에 저장됨.
CRACK_CALC_FORMULA_1_DEFAULT: str = "m*10"

_LEVEL_KEYS: tuple[str, ...] = (
    "level1_primary",
    "level1_secondary",
    "level2_primary",
    "level2_secondary",
    "level3_primary",
    "level3_secondary",
)
_CALC_KEYS: tuple[str, ...] = tuple(f"calc_formula_{i}" for i in range(1, 7))


def _empty_level_dict() -> dict[str, None]:
    return {k: None for k in _LEVEL_KEYS}


def _empty_calc_dict() -> dict[str, None]:
    return {k: None for k in _CALC_KEYS}


def channel_template_defaults(kind_id: str | None) -> dict[str, Any]:
    """
    센서종류별 기본 세팅(단위·분해능·스케일·관리기준·차트 Y·계산식).
    신규 센서 추가·종류 변경 시 DB·폼에 동일하게 쓴다.
    """
    kid_in = (kind_id or "").strip()
    kd = kind_by_id(kid_in)
    canon = (kd["id"] if kd else kid_in) or ""

    unit: str | None = None
    if kd and (kd.get("default_unit") or "").strip():
        unit = kd["default_unit"].strip()

    out: dict[str, Any] = {
        "unit": unit if unit else None,
        "decimal_places": 2,
        "scale_k": 1.0,
        "scale_b": 0.0,
        **_empty_level_dict(),
        "chart_y_min": None,
        "chart_y_max": None,
        **_empty_calc_dict(),
    }

    if sensor_kind_supports_tilt_derived_table(canon):
        out["decimal_places"] = 4
        out.update({k: float(v) for k, v in tilt_management_defaults_mm().items()})
        out["chart_y_min"] = TILT_CHART_Y_MIN_DEFAULT
        out["chart_y_max"] = TILT_CHART_Y_MAX_DEFAULT
        out["calc_formula_1"] = "m"
        out["calc_formula_2"] = "r1*6"
    elif sensor_kind_supports_crack_derived_table(canon):
        out["decimal_places"] = 4
        out.update({k: float(v) for k, v in crack_management_defaults_mm().items()})
        out["chart_y_min"] = CRACK_CHART_Y_MIN_DEFAULT
        out["chart_y_max"] = CRACK_CHART_Y_MAX_DEFAULT
        out["calc_formula_1"] = CRACK_CALC_FORMULA_1_DEFAULT
    elif sensor_kind_supports_flow_derived_table(canon):
        out["decimal_places"] = 2
        out["unit"] = "m³"
        out["chart_y_min"] = FLOW_CHART_Y_MIN_DEFAULT
        out["chart_y_max"] = FLOW_CHART_Y_MAX_DEFAULT
        out["calc_formula_1"] = FLOW_CALC_FORMULA_1_DEFAULT
    elif sensor_kind_supports_load_cell_derived_table(canon):
        out["decimal_places"] = 2
        out["unit"] = "Ton"
        out["chart_y_min"] = LOAD_CELL_CHART_Y_MIN_DEFAULT
        out["chart_y_max"] = LOAD_CELL_CHART_Y_MAX_DEFAULT
        out["calc_formula_1"] = LOAD_CELL_CALC_FORMULA_1_DEFAULT
        out["gauge_factor"] = 1.0
    elif sensor_kind_supports_surface_settlement_derived_table(canon):
        out["decimal_places"] = 4
        out["unit"] = "mm"
        out.update({k: float(v) for k, v in SURFACE_SETTLEMENT_MANAGEMENT_DEFAULTS_MM.items()})
        out["chart_y_min"] = SURFACE_SETTLEMENT_CHART_Y_MIN_DEFAULT
        out["chart_y_max"] = SURFACE_SETTLEMENT_CHART_Y_MAX_DEFAULT
        out["calc_formula_1"] = SURFACE_SETTLEMENT_CALC_FORMULA_1_DEFAULT
    elif sensor_kind_supports_groundwater_derived_table(canon):
        out["decimal_places"] = 4
        out["unit"] = "GL.m"
        out["chart_y_min"] = GROUNDWATER_CHART_Y_MIN_DEFAULT
        out["chart_y_max"] = GROUNDWATER_CHART_Y_MAX_DEFAULT
        out["calc_formula_1"] = "m"
        out["calc_formula_2"] = "r1*5-pipe"
        out["scale_k"] = 1.0
        out["scale_b"] = 0.0
        out["pipe_depth_m"] = None
    elif canon == "inclinometer":
        out["decimal_places"] = 3
        out["unit"] = "mm"
        out.update({k: float(v) for k, v in tilt_management_defaults_mm().items()})
        out["calc_formula_1"] = INCLINOMETER_CALC_FORMULA_1_DEFAULT
        out["calc_formula_2"] = INCLINOMETER_CALC_FORMULA_2_DEFAULT
        out["sensor_length_mm"] = INCLINOMETER_SENSOR_LENGTH_MM_DEFAULT
    elif canon == "internal_displacement":
        out["decimal_places"] = 3
        out["unit"] = "mm"
        out.update({k: float(v) for k, v in tilt_management_defaults_mm().items()})
        out["calc_formula_1"] = INCLINOMETER_CALC_FORMULA_1_DEFAULT
        out["calc_formula_2"] = INCLINOMETER_CALC_FORMULA_2_DEFAULT
        out["sensor_length_mm"] = INCLINOMETER_SENSOR_LENGTH_MM_DEFAULT
    elif canon == "rail_displacement":
        out["decimal_places"] = 3
        out["unit"] = "mm"
        out.update({k: float(v) for k, v in tilt_management_defaults_mm().items()})
        out["chart_y_min"] = INCLINOMETER_CHART_Y_MIN_DEFAULT
        out["chart_y_max"] = INCLINOMETER_CHART_Y_MAX_DEFAULT
        out["calc_formula_1"] = "m"
    elif canon in _VIBRATION_CHART_KIND_IDS:
        out["decimal_places"] = 3
        out["level1_primary"] = VIBRATION_MANAGEMENT_PRIMARY_DEFAULT
        out["chart_y_min"] = VIBRATION_CHART_Y_MIN_DEFAULT
        out["chart_y_max"] = VIBRATION_CHART_Y_MAX_DEFAULT

    return out


def vibration_sensor_form_defaults() -> dict[str, Any]:
    """센서설정 폼 기본 표시값(저장값 없을 때 진동종류 선택용). 관리기준은 1차(주)만 채움."""
    base = dict(_empty_level_dict())
    base["level1_primary"] = VIBRATION_MANAGEMENT_PRIMARY_DEFAULT
    return {
        "management": base,
        "chart_y_min": VIBRATION_CHART_Y_MIN_DEFAULT,
        "chart_y_max": VIBRATION_CHART_Y_MAX_DEFAULT,
        "decimal_places": 3,
    }


def kind_template_defaults_map_for_json() -> dict[str, dict[str, Any]]:
    """브라우저 폼 채우기용: 카탈로그에 등록된 종류 id → channel_template_defaults."""
    return {k["id"]: channel_template_defaults(k["id"]) for k in SENSOR_KINDS}


def tilt_management_defaults_mm() -> dict[str, float]:
    """관리기준 1~3차 주·보조 기본값(복사본)."""
    return dict(TILT_MANAGEMENT_DEFAULTS_MM)


def crack_management_defaults_mm() -> dict[str, float]:
    """균열측정계 관리기준 1~3차 주·보조 기본값(복사본)."""
    return dict(CRACK_MANAGEMENT_DEFAULTS_MM)


def surface_settlement_management_defaults_mm() -> dict[str, float]:
    """지표침하계 관리기준 1~3차 주·보조 기본값(mm)."""
    return dict(SURFACE_SETTLEMENT_MANAGEMENT_DEFAULTS_MM)


MGMT_CHART_LEVEL_KEYS: tuple[str, ...] = (
    "level1_primary",
    "level1_secondary",
    "level2_primary",
    "level2_secondary",
    "level3_primary",
    "level3_secondary",
)


def mgmt_levels_for_chart(meta: dict | None) -> dict[str, float | None]:
    """센서설정 1~3차 관리기준 주·보조. 그래프 기준선용."""
    empty: dict[str, float | None] = {k: None for k in MGMT_CHART_LEVEL_KEYS}
    if not meta:
        return empty
    out = dict(empty)
    for key in MGMT_CHART_LEVEL_KEYS:
        raw = meta.get(key)
        if raw is None:
            continue
        try:
            out[key] = float(raw)
        except (TypeError, ValueError):
            continue
    return out


def mgmt_primary_levels_for_chart(meta: dict | None) -> dict[str, float | None]:
    """하위 호환: 주값만 (API·기타용)."""
    full = mgmt_levels_for_chart(meta)
    return {
        "level1_primary": full["level1_primary"],
        "level2_primary": full["level2_primary"],
        "level3_primary": full["level3_primary"],
    }


def crack_chart_axis_defaults() -> dict[str, float]:
    """균열측정계 차트 Y축 권장 최소·최대(mm)."""
    return {"min": CRACK_CHART_Y_MIN_DEFAULT, "max": CRACK_CHART_Y_MAX_DEFAULT}


def effective_chart_y_bounds_for_kind(
    kind_id: str | None,
    chart_y_min: float | None,
    chart_y_max: float | None,
) -> tuple[float | None, float | None]:
    """차트 Y 고정. DB값이 없을 때 유량계 0~100(m³), 진동계·진동계(3축) 0~0.5(kine) 등."""
    ymin: float | None
    ymax: float | None
    if isinstance(chart_y_min, (int, float)):
        ymin = float(chart_y_min)
    else:
        ymin = None
    if isinstance(chart_y_max, (int, float)):
        ymax = float(chart_y_max)
    else:
        ymax = None
    if ymin is None and ymax is None and sensor_kind_supports_flow_derived_table(kind_id):
        return (FLOW_CHART_Y_MIN_DEFAULT, FLOW_CHART_Y_MAX_DEFAULT)
    if ymin is None and ymax is None and sensor_kind_supports_load_cell_derived_table(kind_id):
        return (LOAD_CELL_CHART_Y_MIN_DEFAULT, LOAD_CELL_CHART_Y_MAX_DEFAULT)
    if ymin is None and ymax is None and sensor_kind_supports_surface_settlement_derived_table(kind_id):
        return (
            SURFACE_SETTLEMENT_CHART_Y_MIN_DEFAULT,
            SURFACE_SETTLEMENT_CHART_Y_MAX_DEFAULT,
        )
    if ymin is None and ymax is None:
        kd = kind_by_id(kind_id or "")
        kid = kd["id"] if kd else (kind_id or "").strip()
        if kid in _VIBRATION_CHART_KIND_IDS:
            return (
                VIBRATION_CHART_Y_MIN_DEFAULT,
                VIBRATION_CHART_Y_MAX_DEFAULT,
            )
        if kid in _GROUNDWATER_DERIVED_KIND_IDS:
            return (
                GROUNDWATER_CHART_Y_MIN_DEFAULT,
                GROUNDWATER_CHART_Y_MAX_DEFAULT,
            )
    return (ymin, ymax)


def sensor_kind_supports_tilt_derived_table(kind_id: str | None) -> bool:
    """구조물경사계(및 레거시 building_tilt)·조회 구간 첫 측정치 기준 파생 열 표시."""
    kd = kind_by_id(kind_id or "")
    if kd:
        return kd["id"] in _TILT_DERIVED_TABLE_KIND_IDS
    return (kind_id or "").strip() in _TILT_DERIVED_TABLE_KIND_IDS


def sensor_kind_supports_inclinometer_derived_table(kind_id: str | None) -> bool:
    """지중경사계·내공변위계(세그먼트 각→mm)·조회 구간 첫 유효 mm 대비 상대 누적변위 표·그래프."""
    kd = kind_by_id(kind_id or "")
    if kd:
        return kd["id"] in _INCLINOMETER_DERIVED_TABLE_KIND_IDS
    return (kind_id or "").strip() in _INCLINOMETER_DERIVED_TABLE_KIND_IDS


def sensor_kind_supports_flow_derived_table(kind_id: str | None) -> bool:
    """유량계 → 시간 유량(m³)·전회·초기대비 표 및 단일 차트."""
    kd = kind_by_id(kind_id or "")
    if kd:
        return kd["id"] in _FLOW_DERIVED_TABLE_KIND_IDS
    return (kind_id or "").strip() in _FLOW_DERIVED_TABLE_KIND_IDS


def sensor_kind_supports_load_cell_derived_table(kind_id: str | None) -> bool:
    """하중계 → Ton·전회·초기대비 표 및 단일 차트."""
    kd = kind_by_id(kind_id or "")
    if kd:
        return kd["id"] in _LOAD_CELL_DERIVED_KIND_IDS
    return (kind_id or "").strip() in _LOAD_CELL_DERIVED_KIND_IDS


def sensor_kind_supports_surface_settlement_derived_table(kind_id: str | None) -> bool:
    """지표침하계 → 측정치(V·mm)·변위·전회·초기대비 표 및 단일 차트."""
    kd = kind_by_id(kind_id or "")
    if kd:
        return kd["id"] in _SURFACE_SETTLEMENT_DERIVED_KIND_IDS
    return (kind_id or "").strip() in _SURFACE_SETTLEMENT_DERIVED_KIND_IDS


def sensor_kind_supports_crack_derived_table(kind_id: str | None) -> bool:
    """균열측정계 → mm 환산·전회대비·누적(구간 첫 유효 행 대비) 표시."""
    kd = kind_by_id(kind_id or "")
    if kd:
        return kd["id"] in _CRACK_DERIVED_TABLE_KIND_IDS
    return (kind_id or "").strip() in _CRACK_DERIVED_TABLE_KIND_IDS


def sensor_kind_supports_groundwater_derived_table(kind_id: str | None) -> bool:
    """지하수위계 → 측정값(V)·GL.m·변화량·전회·초기 표."""
    kd = kind_by_id(kind_id or "")
    if kd:
        return kd["id"] in _GROUNDWATER_DERIVED_KIND_IDS
    return (kind_id or "").strip() in _GROUNDWATER_DERIVED_KIND_IDS


def _float_finite_or_none(x) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def enrich_crack_measurement_rows(rows: list[dict]) -> list[dict]:
    """
    균열측정계: 수치 저장이 원시 V일 때 mm = V×10.
    value_raw 가 유효하면 그 값×10, 없으면 value_real 을 이미 mm 로 간주.
    시간순(호출 전 ORDER BY observed_at ASC 가정).
    - crack_read_mm
    - crack_delta_prev_mm (구간 내 직전 유효 행 대비, 첫 유효 행은 None)
    - crack_cumulative_mm (구간 첫 유효 행 대비 누적)
    """
    first_mm: float | None = None
    prev_mm: float | None = None
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        raw_v = _float_finite_or_none(row.get("value_raw"))
        mm: float | None = None
        if raw_v is not None:
            mm = raw_v * 10.0
        else:
            mm = _float_finite_or_none(row.get("value_real"))
        if mm is None:
            row["crack_read_mm"] = None
            row["crack_delta_prev_mm"] = None
            row["crack_cumulative_mm"] = None
        else:
            row["crack_read_mm"] = mm
            if first_mm is None:
                first_mm = mm
            row["crack_delta_prev_mm"] = None if prev_mm is None else (mm - prev_mm)
            row["crack_cumulative_mm"] = mm - first_mm
            prev_mm = mm
        out.append(row)
    return out


def enrich_tilt_measurement_rows(rows: list[dict]) -> list[dict]:
    """
    구조물경사계 표용. 시계열 첫 행(시간순, value_real 유효)을 초기값 v0로 두고:
    - delta_deg = value_real - v0
    - disp_mm = 1000 * delta_deg * (π/180)  (도→라디안 후 m→mm 스케일; 기존 계산식 체인과 동 형태)
    - angular_gradient: |Δrad|의 역수 기반 1/N 표기(매우 작은 각도용)
    """
    v0: float | None = None
    for r in rows:
        vr = r.get("value_real")
        if vr is None:
            continue
        try:
            v0 = float(vr)
            break
        except (TypeError, ValueError):
            continue
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        if v0 is None:
            row["delta_deg"] = None
            row["disp_mm"] = None
            row["angular_gradient"] = None
            out.append(row)
            continue
        vr = row.get("value_real")
        if vr is None:
            row["delta_deg"] = None
            row["disp_mm"] = None
            row["angular_gradient"] = None
        else:
            try:
                fv = float(vr)
            except (TypeError, ValueError):
                row["delta_deg"] = None
                row["disp_mm"] = None
                row["angular_gradient"] = None
            else:
                d = fv - v0
                row["delta_deg"] = d
                row["disp_mm"] = 1000.0 * d * (math.pi / 180.0)
                rad = d * math.pi / 180.0
                if abs(rad) > 1e-14:
                    n = max(1, int(round(1.0 / abs(rad))))
                    row["angular_gradient"] = f"1/{n}"
                else:
                    row["angular_gradient"] = "—"
        out.append(row)
    return out


def enrich_inclinometer_measurement_rows(rows: list[dict]) -> list[dict]:
    """
    지중경사계·내공변위계(세그먼트): value_real 은 적재 계산 결과(mm, 절대값).
    조회 구간에서 시간순 첫 유효 value_real 을 초기치 v0로 두고:
    - disp_mm = value_real - v0  (그래프·「누적」열용 상대변위, 초기 시점=0)
    - delta_deg / angular_gradient 는 사용하지 않음(None)
    """
    v0: float | None = None
    for r in rows:
        vr = r.get("value_real")
        if vr is None:
            continue
        try:
            v0 = float(vr)
            break
        except (TypeError, ValueError):
            continue
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        if v0 is None:
            row["delta_deg"] = None
            row["disp_mm"] = None
            row["angular_gradient"] = None
            out.append(row)
            continue
        vr = row.get("value_real")
        if vr is None:
            row["delta_deg"] = None
            row["disp_mm"] = None
            row["angular_gradient"] = None
        else:
            try:
                fv = float(vr)
            except (TypeError, ValueError):
                row["delta_deg"] = None
                row["disp_mm"] = None
                row["angular_gradient"] = None
            else:
                row["delta_deg"] = None
                row["disp_mm"] = fv - v0
                row["angular_gradient"] = None
        out.append(row)
    return out


def enrich_flow_meter_measurement_rows(rows: list[dict]) -> list[dict]:
    """
    유량계: value_real 을 순간 유량(m³)로 간주(적재 시 1번 식·m).
    시간순(AS C) 가정.
    - flow_qty_m3
    - flow_delta_prev_m3 (직전 유효 행 대비 증분, 첫 유효 행은 None)
    - flow_delta_initial_m3 (구간 첫 유효 행 대비, 초기대비)
    """
    first_q: float | None = None
    prev_q: float | None = None
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        q = _float_finite_or_none(row.get("value_real"))
        if q is None:
            row["flow_qty_m3"] = None
            row["flow_delta_prev_m3"] = None
            row["flow_delta_initial_m3"] = None
        else:
            row["flow_qty_m3"] = q
            if first_q is None:
                first_q = q
            row["flow_delta_prev_m3"] = None if prev_q is None else (q - prev_q)
            row["flow_delta_initial_m3"] = q - first_q
            prev_q = q
        out.append(row)
    return out


def enrich_groundwater_measurement_rows(rows: list[dict]) -> list[dict]:
    """
    지하수위계: value_raw = 측정값(V), value_real = 적재 계산 결과 GL.m.
    - gw_read_v: 표시용 V
    - gw_gl_m: 지하수위 GL.m (= value_real)
    - gw_change_mag_m: 직전 행 대비 변화량(절댓값, m)
    - gw_delta_prev_m: 전회대비(직전 유효 행과의 차이, 부호 유지)
    - gw_delta_initial_m: 초기대비(구간 첫 유효 GL 대비, 첫 행은 0)
    """
    first_gl: float | None = None
    prev_gl: float | None = None
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        v_raw = _float_finite_or_none(row.get("value_raw"))
        gl_m = _float_finite_or_none(row.get("value_real"))
        row["gw_read_v"] = v_raw
        row["gw_gl_m"] = gl_m
        if gl_m is None:
            row["gw_change_mag_m"] = None
            row["gw_delta_prev_m"] = None
            row["gw_delta_initial_m"] = None
        else:
            dp = None if prev_gl is None else (gl_m - prev_gl)
            row["gw_delta_prev_m"] = dp
            row["gw_change_mag_m"] = None if dp is None else abs(dp)
            if first_gl is None:
                first_gl = gl_m
                row["gw_delta_initial_m"] = 0.0
            else:
                row["gw_delta_initial_m"] = gl_m - first_gl
            prev_gl = gl_m
        out.append(row)
    return out


def enrich_load_cell_measurement_rows(rows: list[dict]) -> list[dict]:
    """
    하중계: value_real 을 Ton 으로 간주(적재 시 1번 식·gf 반영).
    - load_ton
    - load_delta_prev_ton (직전 유효 행 대비 증분, 첫 유효 행은 None)
    - load_delta_initial_ton (구간 첫 유효 행 대비)
    """
    first_q: float | None = None
    prev_q: float | None = None
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        q = _float_finite_or_none(row.get("value_real"))
        if q is None:
            row["load_ton"] = None
            row["load_delta_prev_ton"] = None
            row["load_delta_initial_ton"] = None
        else:
            row["load_ton"] = q
            if first_q is None:
                first_q = q
            row["load_delta_prev_ton"] = None if prev_q is None else (q - prev_q)
            row["load_delta_initial_ton"] = q - first_q
            prev_q = q
        out.append(row)
    return out


def enrich_surface_settlement_measurement_rows(rows: list[dict]) -> list[dict]:
    """
    지표침하계: value_raw = 측정치(V), value_real = 환산(mm, 기본 m*200).
    - ss_read_v / ss_read_mm
    - ss_displacement_mm: 구간 첫 유효 mm 대비 변위
    - ss_delta_prev_mm: 전회대비
    - ss_delta_initial_mm: 초기대비
    """
    first_mm: float | None = None
    prev_mm: float | None = None
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        v_raw = _float_finite_or_none(row.get("value_raw"))
        mm = _float_finite_or_none(row.get("value_real"))
        row["ss_read_v"] = v_raw
        row["ss_read_mm"] = mm
        if mm is None:
            row["ss_displacement_mm"] = None
            row["ss_delta_prev_mm"] = None
            row["ss_delta_initial_mm"] = None
        else:
            if first_mm is None:
                first_mm = mm
            row["ss_displacement_mm"] = mm - first_mm
            row["ss_delta_prev_mm"] = None if prev_mm is None else (mm - prev_mm)
            row["ss_delta_initial_mm"] = mm - first_mm
            prev_mm = mm
        out.append(row)
    return out


def bundle_is_three_channel_vibration_3axis(channels_payload: list[dict]) -> bool:
    """연결 번들이 X·Y·Z용 진동계(3축) 채널 3개인지."""
    if len(channels_payload) != 3:
        return False
    for c in channels_payload:
        sk = (c.get("sensor_kind") or "").strip()
        kd = kind_by_id(sk)
        canon = kd["id"] if kd else sk
        if canon not in _VIBRATION_3AXIS_IDS:
            return False
    return True


def merge_vibration_3axis_bundle_points(channels_payload: list[dict]) -> list[dict]:
    """
    번들 순서 channels_payload[0..2] → X, Y, Z 축 값(value_real).
    세 채널 모두 존재하는 observed_at 교집합만 사용.
    PVS(kine) = √(x²+y²+z²) — 응답 필드 vib_*_gal 은 역사적 키 이름.
    """
    if len(channels_payload) != 3:
        return []
    maps: list[dict[str, dict]] = []
    for c in channels_payload:
        mm: dict[str, dict] = {}
        for p in c.get("points") or []:
            raw = p.get("observed_at")
            if raw is None:
                continue
            k = str(raw).replace("T", " ").replace("Z", "").strip()[:19]
            if not k:
                continue
            mm[k] = p
        maps.append(mm)
    if len(maps) != 3 or not maps[0] or not maps[1] or not maps[2]:
        return []
    common = sorted(set(maps[0].keys()) & set(maps[1].keys()) & set(maps[2].keys()))
    out: list[dict] = []
    for ck in common:
        x = _float_finite_or_none(maps[0][ck].get("value_real"))
        y = _float_finite_or_none(maps[1][ck].get("value_real"))
        z = _float_finite_or_none(maps[2][ck].get("value_real"))
        if x is None or y is None or z is None:
            continue
        pvs = math.sqrt(x * x + y * y + z * z)
        observed = maps[0][ck].get("observed_at")
        out.append(
            {
                "observed_at": observed,
                "vib_x_gal": x,
                "vib_y_gal": y,
                "vib_z_gal": z,
                "vib_pvs_gal": pvs,
            }
        )
    return out


def vibration_3axis_bundle_block(channels_payload: list[dict]) -> dict[str, Any] | None:
    """시리즈 번들용: 3채널 진동계(3축)일 때 병합 점 목록 및 축 순서 정보."""
    if not bundle_is_three_channel_vibration_3axis(channels_payload):
        return None
    pts = merge_vibration_3axis_bundle_points(channels_payload)
    codes: list[str] = []
    for c in channels_payload:
        cid = c.get("sensor_channel_id")
        scode = (c.get("sensor_code") or "").strip()
        codes.append(scode if scode else f"CH{cid}")
    return {
        "points": pts,
        "axis_sensor_codes": codes,
        "axis_order_xyz": ["X", "Y", "Z"],
    }
