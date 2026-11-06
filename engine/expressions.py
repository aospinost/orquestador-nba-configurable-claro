"""Vectorised evaluator of conditions, shared by derived constants, rules and segments.

A condition is ``atributo operador valor``. ``atributo`` is a data column or the ID of a
derived constant; ``valor`` may be a pipe list and may contain ``$producto``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine.config_store import OPERATORS, PRODUCT_PLACEHOLDER, Condition, split_list

ORDER_OPS = {"<", "<=", ">", ">="}


class ExpressionError(ValueError):
    """Raised with a Spanish, business-readable message."""


@dataclass
class EvalContext:
    df: pd.DataFrame
    constants: dict[str, np.ndarray] = field(default_factory=dict)  # (n,) or (n, P)
    campaign_index: int | None = None
    product: str | None = None

    @property
    def n(self) -> int:
        return len(self.df)


def needs_campaign(cond: Condition, per_campaign_constants: set[str]) -> bool:
    return PRODUCT_PLACEHOLDER in (cond.valor or "") or cond.atributo in per_campaign_constants


def check_condition(cond: Condition, columns: set[str] | None, numeric_columns: set[str] | None,
                    constant_ids: list[str]) -> list[str]:
    """Static checks (no data evaluation). Returns Spanish error messages."""
    e = []
    if cond.operador not in OPERATORS:
        e.append(f"operador '{cond.operador}' desconocido (use {', '.join(OPERATORS)}).")
        return e
    is_const = cond.atributo in constant_ids
    if not cond.atributo:
        e.append("falta el atributo de la condición.")
    elif columns is not None and cond.atributo not in columns and not is_const:
        e.append(f"'{cond.atributo}' no es una columna de la base ni una constante derivada.")
    vals = split_list(cond.valor)
    if cond.operador in ORDER_OPS:
        if len(vals) != 1:
            e.append(f"el operador '{cond.operador}' necesita exactamente un valor.")
        elif PRODUCT_PLACEHOLDER not in vals[0]:
            try:
                float(vals[0].replace(",", "."))
            except ValueError:
                e.append(f"el operador '{cond.operador}' necesita un valor numérico y recibió '{vals[0]}'.")
        if (numeric_columns is not None and columns is not None and cond.atributo in columns
                and cond.atributo not in numeric_columns):
            e.append(f"la columna '{cond.atributo}' no es numérica; no admite '{cond.operador}'.")
    if cond.operador in ("==", "!=") and len(vals) > 1:
        e.append(f"el operador '{cond.operador}' admite un solo valor; para listas use 'en' o 'no_en'.")
    if cond.operador in ("en", "no_en", "contiene") and not vals:
        e.append(f"el operador '{cond.operador}' necesita al menos un valor.")
    return e


def _values(cond: Condition, ctx: EvalContext) -> list[str]:
    raw = cond.valor or ""
    if PRODUCT_PLACEHOLDER in raw:
        if ctx.product is None:
            raise ExpressionError(f"'{PRODUCT_PLACEHOLDER}' solo puede usarse en reglas que se evalúan por campaña.")
        raw = raw.replace(PRODUCT_PLACEHOLDER, ctx.product)
    return split_list(raw)


def _to_numbers(vals: list[str], attr: str) -> list[float]:
    out = []
    for v in vals:
        s = v.strip().lower()
        if s in ("si", "sí", "true"):
            out.append(1.0)
        elif s in ("no", "false"):
            out.append(0.0)
        else:
            try:
                out.append(float(v.replace(",", ".")))
            except ValueError:
                raise ExpressionError(f"'{attr}' es numérica y el valor '{v}' no es un número.") from None
    return out


def _series(attr: str, ctx: EvalContext):
    if attr in ctx.constants:
        arr = ctx.constants[attr]
        if arr.ndim == 2:
            if ctx.campaign_index is None:
                raise ExpressionError(f"la constante '{attr}' es por campaña y aquí no hay campaña.")
            arr = arr[:, ctx.campaign_index]
        return pd.Series(arr.astype(float), index=ctx.df.index)
    if attr not in ctx.df.columns:
        raise ExpressionError(f"'{attr}' no es una columna de la base ni una constante derivada.")
    return ctx.df[attr]


def _is_list_column(s: pd.Series) -> bool:
    return s.dtype == object and len(s) > 0 and isinstance(s.iloc[0], frozenset)


def evaluate(cond: Condition, ctx: EvalContext) -> np.ndarray:
    """Boolean mask (n,) where the condition holds."""
    op, attr = cond.operador, cond.atributo
    if op not in OPERATORS:
        raise ExpressionError(f"operador '{op}' desconocido.")
    s = _series(attr, ctx)
    vals = _values(cond, ctx)

    if _is_list_column(s):
        vs = frozenset(vals)
        if op == "contiene" or op == "en":
            out = s.map(lambda x: not x.isdisjoint(vs))
        elif op == "no_en":
            out = s.map(lambda x: x.isdisjoint(vs))
        elif op == "==":
            out = s.map(lambda x: x == vs)
        elif op == "!=":
            out = s.map(lambda x: x != vs)
        else:
            raise ExpressionError(f"'{attr}' es una lista; no admite el operador '{op}'.")
        return out.to_numpy(dtype=bool)

    if pd.api.types.is_numeric_dtype(s):
        if op == "contiene":
            raise ExpressionError(f"'{attr}' es numérica; use 'en' en lugar de 'contiene'.")
        nums = _to_numbers(vals, attr)
        x = s.to_numpy(dtype=float)
        if op in ("en", "no_en"):
            m = np.isin(x, nums)
            return m if op == "en" else ~m
        if len(nums) != 1:
            raise ExpressionError(f"el operador '{op}' necesita exactamente un valor.")
        v = nums[0]
        return {"==": x == v, "!=": x != v, "<": x < v, "<=": x <= v, ">": x > v, ">=": x >= v}[op]

    x = s.astype(str).str.strip()
    if op in ("en", "no_en"):
        m = x.isin(vals).to_numpy()
        return m if op == "en" else ~m
    if op == "contiene":
        m = np.zeros(len(x), dtype=bool)
        for v in vals:
            m |= x.str.contains(v, regex=False).to_numpy()
        return m
    if op in ORDER_OPS:
        raise ExpressionError(f"'{attr}' no es numérica; no admite el operador '{op}'.")
    if len(vals) > 1:
        raise ExpressionError(f"el operador '{op}' admite un solo valor; use 'en' o 'no_en'.")
    v = vals[0] if vals else ""
    return (x == v).to_numpy() if op == "==" else (x != v).to_numpy()


def evaluate_all(conds: list[Condition], ctx: EvalContext) -> np.ndarray:
    """Combine conditions with Y/O. Y binds tighter than O: a Y b O c Y d = (a Y b) O (c Y d).

    The connector of a row joins it with the PREVIOUS row (the first row's connector is ignored).
    """
    if not conds:
        return np.zeros(ctx.n, dtype=bool)
    result = np.zeros(ctx.n, dtype=bool)
    group = evaluate(conds[0], ctx)
    for c in conds[1:]:
        m = evaluate(c, ctx)
        if c.conector == "O":
            result |= group
            group = m
        else:
            group = group & m
    return result | group
