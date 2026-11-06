"""Derived constants (the model's "dummies") built from config_constantes.

- binaria: conditions combined with Y/O -> 0/1.
- numerica: weighted sum of attributes, one row per term: Σ valor × atributo (valor blank = 1).
- nivel cliente_campana (or por_campana = 1): evaluated once per active campaign, so a single
  definition with ``$producto`` yields the (n, P) matrix, e.g. OF_i^p.
Constants are evaluated in file order; a constant may use the ones defined before it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.config_store import Campaign, Config, DerivedConstant, to_float
from engine.expressions import EvalContext, ExpressionError, _series, evaluate_all


def is_per_campaign(k: DerivedConstant) -> bool:
    return k.por_campana or k.nivel == "cliente_campana"


def _numeric(k: DerivedConstant, ctx: EvalContext) -> np.ndarray:
    total = np.zeros(ctx.n)
    for c in k.condiciones:
        w = to_float(c.valor, 1.0)
        total += w * pd.to_numeric(_series(c.atributo, ctx), errors="coerce").fillna(0).to_numpy(float)
    return total


def build(df: pd.DataFrame, cfg: Config, campaigns: list[Campaign]) -> dict[str, np.ndarray]:
    """Evaluate every active constant. Raises ExpressionError with the constant ID in the message."""
    out: dict[str, np.ndarray] = {}
    for k in cfg.constants:
        if not k.activa:
            continue
        try:
            if is_per_campaign(k):
                cols = []
                for p, camp in enumerate(campaigns):
                    ctx = EvalContext(df, out, p, camp.producto)
                    cols.append(evaluate_all(k.condiciones, ctx) if k.tipo == "binaria" else _numeric(k, ctx))
                arr = np.column_stack(cols) if cols else np.zeros((len(df), 0))
            else:
                ctx = EvalContext(df, out)
                arr = evaluate_all(k.condiciones, ctx) if k.tipo == "binaria" else _numeric(k, ctx)
        except ExpressionError as exc:
            raise ExpressionError(f"Constante '{k.id}': {exc}") from None
        out[k.id] = arr.astype(float)
    return out
