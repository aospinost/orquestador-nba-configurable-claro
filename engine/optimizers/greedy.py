"""Baseline greedy optimizer (organizers' "línea base"), generalised to any config.

1. Puntaje per eligible (client, campaign):
   ponderado: w_sp·SP + w_vn·VN + w_j·nivel, with nivel linear from 1 (first in the hierarchy)
   to 0 (last); jerarquia_estricta: campaigns ordered by hierarchy, puntaje only breaks ties.
   Puntajes are rounded to ``priorizacion.decimales_puntaje`` so that equal scores tie exactly,
   and ties are broken by ``priorizacion.desempate`` and then by file order.
2. Clients are sorted by the puntaje of their best campaign (descending).
3. Each client gets the best usable channel (``canal.criterio``) that still has capacity and
   carries at least one of its eligible campaigns; campaigns are loaded by puntaje up to M_c.
   Repeated up to min(canales_por_cliente, weekly room) channels.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from engine.optimizers.base import (ST_ASSIGNED, ST_INACTIVE, ST_NO_CAMPAIGN, ST_NO_CAPACITY, ST_NO_CHANNEL,
                                    SolveInput, SolveResult, assemble_assignment, pair_values, register,
                                    unsupported_features)

WEIGHT_PREFIX = "priorizacion.pesos."


def hierarchy_level(rank: np.ndarray) -> np.ndarray:
    """1 for the most preferred campaign, 0 for the least, linear in between (ties share a level)."""
    levels = np.unique(rank)
    if len(levels) <= 1:
        return np.ones(len(rank))
    pos = np.searchsorted(levels, rank)
    return 1.0 - pos / (len(levels) - 1)


def campaign_features(inp: SolveInput) -> dict[str, np.ndarray]:
    """Named per-(client, campaign) features usable in weights and tie-breaks."""
    n = inp.n
    return {
        "score_producto": inp.product_score,
        "valor_negocio": np.broadcast_to(inp.business_value, (n, len(inp.campaigns))),
        "jerarquia": np.broadcast_to(hierarchy_level(inp.hierarchy_rank), (n, len(inp.campaigns))),
    }


def puntaje(inp: SolveInput) -> np.ndarray:
    feats = campaign_features(inp)
    total = np.zeros((inp.n, len(inp.campaigns)))
    for key, val in inp.params.items():
        if key.startswith(WEIGHT_PREFIX):
            name = key[len(WEIGHT_PREFIX):]
            if name in feats:
                total = total + float(val.replace(",", ".")) * feats[name]
    return total


def campaign_order(inp: SolveInput, score: np.ndarray) -> np.ndarray:
    """(n, P) campaign indices per client, best first; ineligible campaigns last."""
    feats = campaign_features(inp)
    keys = [np.broadcast_to(np.arange(len(inp.campaigns)), score.shape)]  # file order (last resort)
    for name in reversed(inp.params.get("priorizacion.desempate", "").split("|")):
        name = name.strip()
        if name in feats:
            keys.append(-feats[name])
    keys.append(-score)
    if inp.params.get("priorizacion.modo") == "jerarquia_estricta":
        keys.append(np.broadcast_to(inp.hierarchy_rank, score.shape))
    keys.append(~inp.eligible)
    return np.lexsort(keys, axis=-1)


def channel_order(inp: SolveInput) -> np.ndarray:
    if inp.params.get("canal.criterio") == "orden_preferencia" and inp.channel_preference is not None:
        return np.broadcast_to(np.argsort(inp.channel_preference, kind="stable"), inp.channel_score.shape)
    return np.argsort(-inp.channel_score, axis=1, kind="stable")


@register
class GreedyOptimizer:
    name = "greedy"
    label = "Línea base codiciosa"
    available = True
    supports = {"reglas_duras", "reglas_blandas", "multicanal", "jerarquia_estricta"}

    def solve(self, inp: SolveInput) -> SolveResult:
        t0 = time.perf_counter()
        n, P, C = inp.n, len(inp.campaigns), len(inp.channels)
        decimals = int(float(inp.params.get("priorizacion.decimales_puntaje", "6") or 6))
        has_soft = bool(np.any(inp.soft_bonus != 0))
        base = puntaje(inp)
        best_soft = inp.soft_bonus.max(axis=2) if has_soft else 0.0
        score = np.round(base + best_soft, decimals)
        c_order = campaign_order(inp, score)

        # Client order: puntaje of the best campaign, then its tie-break features, then file order.
        best = c_order[:, 0]
        rows = np.arange(n)
        feats = campaign_features(inp)
        keys = [rows]
        for name in reversed(inp.params.get("priorizacion.desempate", "").split("|")):
            if name.strip() in feats:
                keys.append(-feats[name.strip()][rows, best])
        keys.append(-score[rows, best])
        usable = inp.client_active & inp.eligible.any(axis=1)
        order = [i for i in np.lexsort(keys).tolist() if usable[i]]

        status = np.full(n, ST_NO_CAMPAIGN, dtype=object)
        status[~inp.client_active] = ST_INACTIVE

        ch_order = channel_order(inp).tolist()
        elig, ok, allowed = inp.eligible.tolist(), inp.channel_ok.tolist(), inp.allowed.tolist()
        corder = c_order.tolist()
        room = np.minimum(inp.weekly_room if inp.weekly_room is not None else inp.channels_per_client,
                          inp.channels_per_client).tolist()
        rem = inp.capacity.astype(int).tolist()
        mp = inp.max_products.astype(int).tolist()
        soft = inp.soft_bonus if has_soft else None
        ci, cc, cp, co, cco = [], [], [], [], []

        for i in order:
            used: set[int] = set()
            had_channel = False
            n_ch = 0
            for c in ch_order[i]:
                if n_ch >= room[i]:
                    break
                if not ok[i][c]:
                    continue
                cands = [p for p in corder[i] if elig[i][p] and allowed[p][c] and p not in used]
                if not cands:
                    continue
                had_channel = True
                if rem[c] <= 0:
                    continue
                if soft is not None:
                    cands.sort(key=lambda p: -round(base[i, p] + soft[i, p, c], decimals))
                take = cands[:mp[c]]
                rem[c] -= 1
                for k, p in enumerate(take):
                    ci.append(i); cc.append(c); cp.append(p); co.append(k + 1); cco.append(n_ch + 1)
                used.update(take)
                n_ch += 1
            if n_ch:
                status[i] = ST_ASSIGNED
            else:
                status[i] = ST_NO_CAPACITY if had_channel else ST_NO_CHANNEL

        pairs = pd.DataFrame({"client_idx": ci, "channel_idx": cc, "campaign_idx": cp, "orden": co,
                              "canal_orden": cco})
        pv = pair_values(inp, pairs) if len(pairs) else np.zeros(0)
        assignment = assemble_assignment(inp, pairs, status)
        objective = float(pv.sum())
        log = [f"Clientes recorridos: {len(order):,}".replace(",", "."),
               "Cupo restante: " + ", ".join(f"{inp.channels[c]}={rem[c]}" for c in range(C))]
        return SolveResult(
            assignment=assignment, objective=objective, status="ok",
            solve_seconds=time.perf_counter() - t0, duals=None,
            per_client_value=pd.Series(assignment["valor_esperado"].to_numpy(), index=inp.client_ids),
            unsupported=unsupported_features(self, inp), log=log, pairs=pairs, client_status=status,
            optimizer=self.name,
        )
