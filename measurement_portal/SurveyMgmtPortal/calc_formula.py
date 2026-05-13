"""
센서 1~6번 계산식 안전 평가.

- 변수: m(원시값에 스케일 적용 후), r1~r6(이전 단계 결과), extra_env 로 주입된 이름(예: pipe = 파이프심도 m, gf = 게이지팩터, L = 센서길이 mm)
- 1번 식이 비어 있으면 r1 = m
- k번 식이 비어 있으면 r{k} = r{k-1} (유지)
- 최종 표시값: 「비어 있지 않은 식」 중 **가장 마지막** 단계 결과 (식이 모두 비어 있으면 m)

지원: 사칙연산, 괄호, 단항 +/-, abs/min/max/round/pow, sqrt/sin/cos/tan, pi
함수명은 대소문자 무관 (ABS → abs).
"""
from __future__ import annotations

import ast
import math
import operator
import re
from collections.abc import Mapping, Sequence

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}

_FUNCS = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "pow": pow,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
}


def _normalize_expr(expr: str) -> str:
    s = (expr or "").strip()
    if not s:
        return ""
    s = re.sub(r"\bABS\s*\(", "abs(", s, flags=re.IGNORECASE)
    return s


def _safe_eval_node(node: ast.AST, env: dict[str, float]) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError("지원하지 않는 상수입니다.")
    if isinstance(node, ast.BinOp):
        op = type(node.op)
        if op not in _BINOPS:
            raise ValueError("허용되지 않은 연산자입니다.")
        return float(_BINOPS[op](_safe_eval_node(node.left, env), _safe_eval_node(node.right, env)))
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.UAdd):
            return float(+_safe_eval_node(node.operand, env))
        if isinstance(node.op, ast.USub):
            return float(-_safe_eval_node(node.operand, env))
        raise ValueError("허용되지 않은 단항 연산입니다.")
    if isinstance(node, ast.Name):
        if node.id == "pi":
            return float(math.pi)
        if node.id in env:
            return float(env[node.id])
        raise ValueError(f"알 수 없는 이름: {node.id}")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("함수 호출 형식이 올바르지 않습니다.")
        fn = node.func.id.lower()
        if fn not in _FUNCS:
            raise ValueError(f"허용되지 않은 함수: {node.func.id}")
        args = [_safe_eval_node(a, env) for a in node.args]
        return float(_FUNCS[fn](*args))
    raise ValueError("지원하지 않는 식입니다.")


def safe_eval_formula(expr: str, env: dict[str, float]) -> float:
    raw = _normalize_expr(expr)
    if not raw:
        raise ValueError("빈 계산식입니다.")
    tree = ast.parse(raw, mode="eval")
    if not isinstance(tree.body, ast.AST):
        raise ValueError("식 파싱 오류")
    return _safe_eval_node(tree.body, env)


def evaluate_formula_chain(
    m: float,
    formulas: Sequence[str | None],
    *,
    extra_env: Mapping[str, float] | None = None,
) -> tuple[tuple[float | None, float | None, float | None, float | None, float | None, float | None], float]:
    """
    formulas: 길이 6. 각 요소는 1~6번 계산식 문자열.
    반환: (value_step_1..6), value_real(최종)
    """
    if len(formulas) != 6:
        raise ValueError("계산식은 6개여야 합니다.")
    m = float(m)
    env: dict[str, float] = {"m": m}
    if extra_env:
        for kk, vv in extra_env.items():
            env[str(kk)] = float(vv)
    steps: list[float | None] = [None, None, None, None, None, None]
    last_explicit = m
    prev = m

    for i in range(6):
        raw = (formulas[i] or "").strip()
        if raw:
            ri = safe_eval_formula(raw, env)
            env[f"r{i + 1}"] = ri
            steps[i] = ri
            prev = ri
            last_explicit = ri
        else:
            if i == 0:
                steps[0] = m
                env["r1"] = m
                prev = m
            else:
                steps[i] = prev
                env[f"r{i + 1}"] = prev

    return (
        (steps[0], steps[1], steps[2], steps[3], steps[4], steps[5]),
        last_explicit,
    )
