"""Official metrics (CLAUDE.md §8) and business-constraint status."""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.config_store import ALL, BusinessConstraint
from engine.optimizers.base import SolveInput, SolveResult, pair_values

BASELINE = {"valor_esperado": 10241.5, "clientes_con_accion": 55393, "productos_asignados": 70443,
            "indicador_jerarquia": 99.7, "violaciones": 0}


def _filter_pairs(b: BusinessConstraint, inp: SolveInput, pairs: pd.DataFrame,
                  campaigns: bool = True) -> pd.DataFrame:
    m = np.ones(len(pairs), bool)
    if campaigns and ALL not in b.campanas:
        idx = [inp.campaigns.index(c) for c in b.campanas if c in inp.campaigns]
        m &= pairs["campaign_idx"].isin(idx).to_numpy()
    if ALL not in b.canales:
        idx = [inp.channels.index(c) for c in b.canales if c in inp.channels]
        m &= pairs["channel_idx"].isin(idx).to_numpy()
    if b.segmento:
        seg = inp.constants.get(b.segmento)
        if seg is not None:
            i = pairs["client_idx"].to_numpy(int)
            vals = seg[i, pairs["campaign_idx"].to_numpy(int)] if seg.ndim == 2 else seg[i]
            m &= vals.astype(bool)
    return pairs[m]


def _measure(metric: str, inp: SolveInput, pairs: pd.DataFrame) -> float:
    if metric == "contactos":
        return float(len(pairs.drop_duplicates(["client_idx", "channel_idx"])))
    if metric == "productos":
        return float(len(pairs))
    return float(pair_values(inp, pairs).sum()) if len(pairs) else 0.0


def business_constraint_status(inp: SolveInput, pairs: pd.DataFrame) -> list[dict]:
    out = []
    for b in inp.business_constraints:
        val = _measure(b.metrica, inp, _filter_pairs(b, inp, pairs))
        if b.unidad == "pct_total":
            base = _measure(b.metrica, inp, pairs)
            val = 100 * val / base if base else 0.0
        elif b.unidad == "pct_canal":
            base = _measure(b.metrica, inp, _filter_pairs(b, inp, pairs, campaigns=False))
            val = 100 * val / base if base else 0.0
        ok = val <= b.valor + 1e-9 if b.sentido == "<=" else val >= b.valor - 1e-9
        out.append({"id": b.id, "nombre": b.nombre, "valor_actual": val, "sentido": b.sentido,
                    "limite": b.valor, "unidad": b.unidad, "cumple": bool(ok)})
    return out


def top_hierarchy_mask(inp: SolveInput) -> np.ndarray:
    """(n, P) True for each client's eligible campaign(s) with the best hierarchy rank."""
    rank = np.where(inp.eligible, inp.hierarchy_rank[None, :], np.inf)
    best = rank.min(axis=1, keepdims=True)
    return inp.eligible & (rank == best)


def compute(inp: SolveInput, result: SolveResult) -> dict:
    pairs = result.pairs if result.pairs is not None else pd.DataFrame(
        columns=["client_idx", "channel_idx", "campaign_idx"])
    n, P, C = inp.n, len(inp.campaigns), len(inp.channels)
    pv = pair_values(inp, pairs) if len(pairs) else np.zeros(0)
    ci = pairs["client_idx"].to_numpy(int)
    cc = pairs["channel_idx"].to_numpy(int)
    cp = pairs["campaign_idx"].to_numpy(int)
    with_action = np.bincount(ci, minlength=n) > 0

    got = np.zeros((n, P), bool)
    got[ci, cp] = True
    top = top_hierarchy_mask(inp)
    hit = (got & top).any(axis=1)
    has_elig = inp.eligible.any(axis=1) & inp.client_active

    contacts = pairs.drop_duplicates(["client_idx", "channel_idx"])["channel_idx"].to_numpy(int)
    used = np.bincount(contacts, minlength=C)
    soft = float(inp.soft_bonus[ci, cp, cc].sum()) if len(pairs) else 0.0
    return {
        "valor_esperado": float(pv.sum()),
        "bono_reglas_blandas": soft,
        "clientes_con_accion": int(with_action.sum()),
        "productos_asignados": int(len(pairs)),
        "indicador_jerarquia": float(100 * hit[with_action].mean()) if with_action.any() else 0.0,
        "indicador_jerarquia_elegibles": float(100 * hit[has_elig].mean()) if has_elig.any() else 0.0,
        "clientes_elegibles": int(has_elig.sum()),
        "uso_capacidad": {inp.channels[c]: {"usado": int(used[c]), "cupo": int(inp.capacity[c])} for c in range(C)},
        "valor_por_canal": {inp.channels[c]: float(pv[cc == c].sum()) for c in range(C)},
        "valor_por_campana": {inp.campaigns[p]: float(pv[cp == p].sum()) for p in range(P)},
        "productos_por_campana": {inp.campaigns[p]: int((cp == p).sum()) for p in range(P)},
        "restricciones_negocio": business_constraint_status(inp, pairs),
        "segundos_optimizador": result.solve_seconds,
        "optimizador": result.optimizer,
    }
