"""Generic rule evaluator: config rules + implicit system rules -> masks, soft terms, reasons.

No rule ID is hard-coded except the system IDs of rules implied by parameters (CLAUDE.md §9).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine.config_store import Campaign, Channel, Config, Rule, to_bool
from engine.constants import is_per_campaign
from engine.expressions import EvalContext, ExpressionError, evaluate, needs_campaign

# System rules implied by parameters / structure.
SYS_PRODUCT_THRESHOLD = "P-UMBRAL-PROD"
SYS_CHANNEL_THRESHOLD = "P-UMBRAL-CANAL"
SYS_WEEKLY_CAP = "P-TOPE-SEMANAL"
SYS_ALLOWED_CHANNEL = "P-CANAL-PERMITIDO"
SYS_AUTHORIZATION = "P-AUTORIZACION"
SYS_CHANNELS_PER_CLIENT = "P-CANALES-CLIENTE"
SYS_MAX_PRODUCTS = "P-MAX-PRODUCTOS"
SYS_CAPACITY = "P-CAPACIDAD"

SYSTEM_RULES = {
    SYS_PRODUCT_THRESHOLD: "Score de producto menor al umbral",
    SYS_CHANNEL_THRESHOLD: "Score de canal menor al umbral",
    SYS_WEEKLY_CAP: "Tope semanal de contactos",
    SYS_ALLOWED_CHANNEL: "Producto solo por sus canales permitidos",
    SYS_AUTHORIZATION: "Canal sin autorización del cliente",
    SYS_CHANNELS_PER_CLIENT: "Canales por cliente en cada corrida",
    SYS_MAX_PRODUCTS: "Productos por contacto según el canal",
    SYS_CAPACITY: "Cupo del canal",
}


@dataclass
class RuleOutcome:
    eligible: np.ndarray          # (n, P)
    channel_ok: np.ndarray        # (n, C)
    client_active: np.ndarray     # (n,)
    soft_bonus: np.ndarray        # (n, P, C)
    weekly_room: np.ndarray       # (n,)
    # Every rule that excluded something, with ALL its hits (not only the first blocking rule).
    by_campaign: dict[str, np.ndarray] = field(default_factory=dict)   # id -> (n, P)
    by_channel: dict[str, np.ndarray] = field(default_factory=dict)    # id -> (n, C)
    by_client: dict[str, np.ndarray] = field(default_factory=dict)     # id -> (n,)
    soft_hits: dict[str, np.ndarray] = field(default_factory=dict)     # id -> (n, P, C) bool
    info: dict[str, dict] = field(default_factory=dict)                # id -> description

    def as_dict(self) -> dict:
        return {"campana": self.by_campaign, "canal": self.by_channel, "cliente": self.by_client,
                "blandas": self.soft_hits, "info": self.info}


def campaign_threshold(cfg: Config, c: Campaign) -> float:
    return c.umbral_score if c.umbral_score is not None else cfg.param_float("priorizacion.umbral_score_producto", 0.0)


def channel_threshold(cfg: Config, c: Channel) -> float:
    return c.umbral_score if c.umbral_score is not None else cfg.param_float("canal.umbral_score_canal", 0.0)


def scope_campaigns(rule: Rule, campaigns: list[Campaign]) -> list[int]:
    lvl, vals = rule.alcance_nivel, set(rule.alcance_valores)
    if lvl == "global":
        return list(range(len(campaigns)))
    key = {"campana": "id", "producto": "producto", "objetivo": "objetivo"}.get(lvl)
    if key is None:
        return []
    return [p for p, c in enumerate(campaigns) if getattr(c, key) in vals]


def scope_channels(rule: Rule, channels: list[Channel]) -> list[int]:
    if rule.alcance_nivel == "global":
        return list(range(len(channels)))
    vals = set(rule.alcance_valores)
    return [k for k, c in enumerate(channels) if c.id in vals]


def _scores(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    if not cols:
        return np.zeros((len(df), 0))
    return np.column_stack([pd.to_numeric(df[c], errors="coerce").to_numpy(float) for c in cols])


def evaluate_rules(df: pd.DataFrame, cfg: Config, campaigns: list[Campaign], channels: list[Channel],
                   constants: dict[str, np.ndarray]) -> RuleOutcome:
    n, P, C = len(df), len(campaigns), len(channels)
    out = RuleOutcome(
        eligible=np.ones((n, P), bool), channel_ok=np.ones((n, C), bool), client_active=np.ones(n, bool),
        soft_bonus=np.zeros((n, P, C)), weekly_room=np.full(n, np.iinfo(np.int32).max),
    )
    per_campaign_consts = {k.id for k in cfg.constants if k.activa and is_per_campaign(k)}

    # -- configured rules
    for rule in cfg.rules:
        if not rule.activa:
            continue
        cond = rule.condicion
        out.info[rule.id] = {"nombre": rule.nombre, "tipo": rule.tipo, "atributo": cond.atributo,
                             "operador": cond.operador, "valor": cond.valor, "accion": rule.accion,
                             "peso": rule.peso, "sistema": False, "alcance": rule.alcance_nivel, "objetivos": []}
        sign = {"excluir": 0.0, "bonificar": 1.0, "penalizar": -1.0}.get(rule.accion, 0.0)
        try:
            if rule.tipo == "elegibilidad":
                targets = scope_campaigns(rule, campaigns)
                out.info[rule.id]["objetivos"] = targets
                hits = np.zeros((n, P), bool)
                if needs_campaign(cond, per_campaign_consts):
                    for p in targets:
                        hits[:, p] = evaluate(cond, EvalContext(df, constants, p, campaigns[p].producto))
                elif targets:
                    m = evaluate(cond, EvalContext(df, constants))
                    hits[:, targets] = m[:, None]
                if rule.accion == "excluir":
                    out.eligible &= ~hits
                    out.by_campaign[rule.id] = hits
                else:
                    out.soft_bonus += sign * rule.peso * hits[:, :, None]
                    out.soft_hits[rule.id] = np.broadcast_to(hits[:, :, None], (n, P, C))
            elif rule.tipo == "canal":
                targets = scope_channels(rule, channels)
                out.info[rule.id]["objetivos"] = targets
                hits = np.zeros((n, C), bool)
                if targets:
                    m = evaluate(cond, EvalContext(df, constants))
                    hits[:, targets] = m[:, None]
                if rule.accion == "excluir":
                    out.channel_ok &= ~hits
                    out.by_channel[rule.id] = hits
                else:
                    out.soft_bonus += sign * rule.peso * hits[:, None, :]
                    out.soft_hits[rule.id] = np.broadcast_to(hits[:, None, :], (n, P, C))
            else:
                raise ExpressionError(f"tipo de regla '{rule.tipo}' desconocido.")
        except ExpressionError as exc:
            raise ExpressionError(f"Regla '{rule.id}': {exc}") from None

    # -- implicit system rules
    sp = _scores(df, [c.columna_score for c in campaigns])
    u_p = np.array([campaign_threshold(cfg, c) for c in campaigns])
    below = ~(sp >= u_p[None, :])  # NaN scores count as below
    out.eligible &= ~below
    out.by_campaign[SYS_PRODUCT_THRESHOLD] = below
    out.info[SYS_PRODUCT_THRESHOLD] = {"nombre": SYSTEM_RULES[SYS_PRODUCT_THRESHOLD], "sistema": True,
                                       "umbral": dict(zip([c.id for c in campaigns], u_p.tolist()))}

    sc = _scores(df, [c.columna_score for c in channels])
    u_c = np.array([channel_threshold(cfg, c) for c in channels])
    below = ~(sc >= u_c[None, :])
    out.channel_ok &= ~below
    out.by_channel[SYS_CHANNEL_THRESHOLD] = below
    out.info[SYS_CHANNEL_THRESHOLD] = {"nombre": SYSTEM_RULES[SYS_CHANNEL_THRESHOLD], "sistema": True,
                                       "umbral": dict(zip([c.id for c in channels], u_c.tolist()))}

    auth = np.zeros((n, C), bool)
    for k, ch in enumerate(channels):
        if ch.columna_autorizacion:
            auth[:, k] = ~df[ch.columna_autorizacion].map(to_bool).to_numpy(bool)
    if auth.any():
        out.channel_ok &= ~auth
        out.by_channel[SYS_AUTHORIZATION] = auth
        out.info[SYS_AUTHORIZATION] = {"nombre": SYSTEM_RULES[SYS_AUTHORIZATION], "sistema": True}

    col = cfg.param("politica_contacto.columna_contactos_semana", "")
    cap = cfg.param_int("politica_contacto.max_contactos_semana")
    if col and cap is not None:
        received = pd.to_numeric(df[col], errors="coerce").fillna(0).to_numpy(float)
        out.weekly_room = np.maximum(cap - received, 0).astype(int)
        blocked = out.weekly_room < 1
        out.client_active &= ~blocked
        out.by_client[SYS_WEEKLY_CAP] = blocked
        out.info[SYS_WEEKLY_CAP] = {"nombre": SYSTEM_RULES[SYS_WEEKLY_CAP], "sistema": True,
                                    "atributo": col, "maximo": cap}
    return out
