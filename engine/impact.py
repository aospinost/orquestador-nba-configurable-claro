"""Fast "what changes if…" figures computed from rules only (no optimization).

Used by the console's impact preview, live counters and threshold histograms.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import constants as constants_mod
from engine.config_store import Config, Rule, upsert_row
from engine.data_loader import list_columns
from engine.expressions import ExpressionError
from engine.rules import _scores, campaign_threshold, channel_threshold, evaluate_rules

ERRORS = (ExpressionError, KeyError, ValueError)


def _outcome(df: pd.DataFrame, cfg: Config):
    camps, chans = cfg.active_campaigns, cfg.active_channels
    consts = constants_mod.build(df, cfg, camps)
    return evaluate_rules(df, cfg, camps, chans, consts), consts


def summarize(df: pd.DataFrame, cfg: Config) -> dict:
    """Eligible pairs and per-rule reach. On an invalid rule returns {'error': message}."""
    try:
        out, consts = _outcome(df, cfg)
    except ERRORS as exc:
        return {"error": str(exc)}
    act = out.client_active
    per_rule = {}
    for rid, m in {**out.by_campaign, **out.by_channel}.items():
        per_rule[rid] = int(m.any(axis=1).sum())
    for rid, m in out.by_client.items():
        per_rule[rid] = int(m.sum())
    for rid, m in out.soft_hits.items():
        per_rule[rid] = int(np.asarray(m).any(axis=(1, 2)).sum())
    return {
        "pares_elegibles": int((out.eligible & act[:, None]).sum()),
        "clientes_elegibles": int((out.eligible.any(axis=1) & act).sum()),
        "pares_canal": int((out.channel_ok & act[:, None]).sum()),
        "clientes_activos": int(act.sum()),
        "por_regla": per_rule,
        "constantes": {k: float(np.mean(v)) for k, v in consts.items()},
        "error": None,
    }


def rule_reach(df: pd.DataFrame, cfg: Config, rule: Rule) -> tuple[int, str | None]:
    """Clients for whom the (possibly unsaved) rule fires in at least one campaign/channel of its scope."""
    tmp = cfg.copy()
    tmp.tables["reglas"] = tmp.tables["reglas"].iloc[0:0]
    upsert_row(tmp, "reglas", {
        "id": rule.id, "nombre": rule.nombre, "tipo": rule.tipo, "alcance_nivel": rule.alcance_nivel,
        "alcance_valores": "|".join(rule.alcance_valores), "atributo": rule.condicion.atributo,
        "operador": rule.condicion.operador, "valor": rule.condicion.valor, "accion": "excluir",
        "peso": "", "activa": "1"})
    try:
        out, _ = _outcome(df, tmp)
    except ERRORS as exc:
        return 0, str(exc)
    m = out.by_campaign.get(rule.id, out.by_channel.get(rule.id))
    return (int(m.any(axis=1).sum()) if m is not None else 0), None


def constant_values(df: pd.DataFrame, cfg: Config) -> tuple[dict[str, np.ndarray], str | None]:
    try:
        return constants_mod.build(df, cfg, cfg.active_campaigns), None
    except ERRORS as exc:
        return {}, str(exc)


def thresholds(df: pd.DataFrame, cfg: Config) -> dict:
    """Score arrays and how many clients fall below each campaign / channel threshold."""
    out = {"campanas": {}, "canales": {}}
    for kind, items, thr in (("campanas", cfg.active_campaigns, campaign_threshold),
                             ("canales", cfg.active_channels, channel_threshold)):
        for c in items:
            s = _scores(df, [c.columna_score])[:, 0] if c.columna_score in df.columns else np.full(len(df), np.nan)
            u = thr(cfg, c)
            out[kind][c.id] = {"scores": s, "umbral": u, "debajo": int((~(s >= u)).sum()),
                               "columna": c.columna_score, "nombre": c.nombre}
    return out


def column_profile(df: pd.DataFrame, max_categories: int = 40) -> pd.DataFrame:
    """columna, tipo (numerica | categoria | lista | texto), valores (for categories / lists), min, max."""
    rows = []
    lists = set(list_columns(df))
    for c in df.columns:
        s = df[c]
        if c in lists:
            vals = sorted(set().union(*s.tolist())) if len(s) else []
            rows.append({"columna": c, "tipo": "lista", "valores": vals, "min": None, "max": None})
        elif pd.api.types.is_numeric_dtype(s):
            u = s.dropna().unique()
            rows.append({"columna": c, "tipo": "numerica", "valores": sorted(u.tolist()) if len(u) <= 12 else [],
                         "min": float(s.min()) if len(s) else None, "max": float(s.max()) if len(s) else None})
        else:
            u = s.astype(str).unique()
            kind = "categoria" if len(u) <= max_categories else "texto"
            rows.append({"columna": c, "tipo": kind, "valores": sorted(u.tolist()) if kind == "categoria" else [],
                         "min": None, "max": None})
    return pd.DataFrame(rows)


def potential_value(df: pd.DataFrame, cfg: Config) -> float:
    """Upper bound of expected value ignoring capacities: each eligible client takes its best single
    contact (best channel, top M_c feasible campaigns). Used to price what each rule costs."""
    out, _ = _outcome(df, cfg)
    camps, chans = cfg.active_campaigns, cfg.active_channels
    if not camps or not chans:
        return 0.0
    sp = np.nan_to_num(_scores(df, [c.columna_score for c in camps]))
    sc = np.nan_to_num(_scores(df, [c.columna_score for c in chans]))
    vn = np.array([c.valor_negocio for c in camps])
    best = np.zeros(len(df))
    for k, ch in enumerate(chans):
        allowed = np.array([ch.id in c.canales_permitidos for c in camps])
        feas = out.eligible & allowed[None, :] & out.channel_ok[:, k, None] & out.client_active[:, None]
        v = np.where(feas, sp * sc[:, k, None] * vn[None, :], 0.0)
        best = np.maximum(best, -np.sort(-v, axis=1)[:, :ch.max_productos].sum(axis=1))
    return float(best.sum())


def rule_costs(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """For each active exclusion rule: potential value if it were switched off, and the difference."""
    base = potential_value(df, cfg)
    rows = []
    for r in cfg.rules:
        if not r.activa or r.accion != "excluir":
            continue
        tmp = cfg.copy()
        t = tmp.tables["reglas"]
        t.loc[t["id"] == r.id, "activa"] = "0"
        try:
            without = potential_value(df, tmp)
        except ERRORS:
            continue
        rows.append({"id": r.id, "nombre": r.nombre, "potencial_sin_regla": without, "costo": without - base})
    return pd.DataFrame(rows, columns=["id", "nombre", "potencial_sin_regla", "costo"]).sort_values(
        "costo", ascending=False, ignore_index=True)
