"""Build the SolveInput from data + configuration."""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import constants as constants_mod
from engine import model_registry
from engine.config_store import Config, config_hash
from engine.data_loader import id_column
from engine.optimizers.base import SolveInput
from engine.rules import SYS_ALLOWED_CHANNEL, SYSTEM_RULES, _scores, evaluate_rules


def build_solve_input(df: pd.DataFrame, cfg: Config) -> SolveInput:
    campaigns = cfg.active_campaigns
    channels = cfg.active_channels
    consts = constants_mod.build(df, cfg, campaigns)
    outcome = evaluate_rules(df, cfg, campaigns, channels, consts)

    ch_ids = [c.id for c in channels]
    allowed = np.array([[ch in c.canales_permitidos for ch in ch_ids] for c in campaigns], bool).reshape(
        len(campaigns), len(channels))
    reasons = outcome.as_dict()
    reasons["info"][SYS_ALLOWED_CHANNEL] = {"nombre": SYSTEM_RULES[SYS_ALLOWED_CHANNEL], "sistema": True}
    reasons["permitidos"] = allowed

    sp = np.nan_to_num(_scores(df, [c.columna_score for c in campaigns]))
    sc = np.nan_to_num(_scores(df, [c.columna_score for c in channels]))
    return SolveInput(
        client_ids=df[id_column(cfg)].astype(str).to_numpy(),
        campaigns=[c.id for c in campaigns],
        channels=ch_ids,
        product_score=sp,
        channel_score=sc,
        business_value=np.array([c.valor_negocio for c in campaigns], float),
        hierarchy_rank=np.array([c.rango_jerarquia for c in campaigns], float),
        eligible=outcome.eligible,
        channel_ok=outcome.channel_ok,
        allowed=allowed,
        soft_bonus=outcome.soft_bonus,
        capacity=np.array([c.capacidad for c in channels], int),
        max_products=np.array([c.max_productos for c in channels], int),
        channels_per_client=cfg.param_int("politica_contacto.canales_por_cliente", 1),
        client_active=outcome.client_active,
        business_constraints=[b for b in cfg.business_constraints if b.activa],
        exclusion_reasons=reasons,
        params=cfg.params,
        registry=model_registry.build(cfg, campaigns, channels, df, consts),
        campaign_products=[c.producto for c in campaigns],
        channel_preference=np.array([c.orden_preferencia for c in channels], float),
        weekly_room=outcome.weekly_room,
        constants=consts,
        config_hash=config_hash(cfg),
    )


def split_clients(inp: SolveInput) -> tuple[np.ndarray, np.ndarray]:
    """Preprocessing step of the team's model (J. Reina, §5): separate clients before optimizing.

    A client is "posible" if it is active (e.g. weekly cap, R15) and has at least one
    (campaign, channel) pair that survives every hard rule: eligible campaign (R01-R08),
    usable channel (R09-R11) and channel allowed for that campaign (R12).
    Everyone else is "eliminado": the optimizer never sees them and they end as sin_accion;
    their reason is already built by explain.py from the rule masks.

    Returns the row indices of (posibles, eliminados).
    """
    # (n, P, C): True where client i could receive campaign p through channel c
    pair_ok = inp.eligible[:, :, None] & inp.channel_ok[:, None, :] & inp.allowed[None, :, :]
    posible = inp.client_active & pair_ok.any(axis=(1, 2))
    return np.flatnonzero(posible), np.flatnonzero(~posible)
