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
