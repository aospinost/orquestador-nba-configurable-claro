"""Optimizer contract (CLAUDE.md §6) and registry."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

from engine.config_store import BusinessConstraint

# Status codes per client, turned into Spanish text by explain.py.
ST_ASSIGNED = "asignado"
ST_INACTIVE = "cliente_inactivo"        # removed before solving (e.g. weekly cap)
ST_NO_CAMPAIGN = "sin_campana"          # no eligible campaign
ST_NO_CHANNEL = "sin_canal"             # eligible campaigns but no usable channel for them
ST_NO_CAPACITY = "sin_cupo"             # usable channels exist but they were full
ST_NOT_SELECTED = "no_seleccionado"     # optimizer chose not to contact (e.g. MILP / constraints)

# Config features an optimizer may or may not honour (shown in the UI).
FEATURES = {
    "reglas_duras": "Reglas de exclusión y umbrales",
    "reglas_blandas": "Bonificaciones / penalizaciones (reglas blandas)",
    "restricciones_negocio": "Restricciones de negocio (cuotas)",
    "multicanal": "Más de un canal por cliente",
    "precios_sombra": "Precios sombra (duales) de cupos y cuotas",
    "jerarquia_estricta": "Modo de jerarquía estricta",
}


@dataclass
class SolveInput:
    client_ids: np.ndarray            # (n,)
    campaigns: list[str]
    channels: list[str]
    product_score: np.ndarray         # (n, P)  SP
    channel_score: np.ndarray         # (n, C)  SC
    business_value: np.ndarray        # (P,)    VN
    hierarchy_rank: np.ndarray        # (P,)    1 = most preferred
    eligible: np.ndarray              # (n, P) bool after hard rules + U_p
    channel_ok: np.ndarray            # (n, C) bool after hard rules + U_c
    allowed: np.ndarray               # (P, C) bool
    soft_bonus: np.ndarray            # (n, P, C)
    capacity: np.ndarray              # (C,)
    max_products: np.ndarray          # (C,)
    channels_per_client: int
    client_active: np.ndarray         # (n,) bool
    business_constraints: list[BusinessConstraint]
    exclusion_reasons: dict
    params: dict
    registry: object = None           # engine.model_registry.ModelRegistry
    campaign_products: list[str] = field(default_factory=list)
    channel_preference: np.ndarray | None = None   # (C,) orden_preferencia
    weekly_room: np.ndarray | None = None          # (n,) contacts still allowed this week
    constants: dict = field(default_factory=dict)
    config_hash: str = ""

    @property
    def n(self) -> int:
        return len(self.client_ids)


@dataclass
class SolveResult:
    assignment: pd.DataFrame          # organizer format + extended cols (razon filled by explain)
    objective: float
    status: str
    solve_seconds: float
    duals: dict | None
    per_client_value: pd.Series
    unsupported: list[str]
    log: list[str]
    pairs: pd.DataFrame | None = None         # long format: client_idx, channel_idx, campaign_idx, orden
    client_status: np.ndarray | None = None   # (n,) status code per client
    optimizer: str = ""


class Optimizer(Protocol):
    name: str
    label: str
    available: bool
    supports: set[str]

    def solve(self, inp: SolveInput) -> SolveResult: ...


REGISTRY: dict[str, type] = {}


def register(cls):
    REGISTRY[cls.name] = cls
    return cls


def get_optimizer(name: str):
    if name not in REGISTRY:
        raise KeyError(f"Optimizador '{name}' no registrado. Disponibles: {', '.join(REGISTRY)}")
    return REGISTRY[name]()


def unsupported_features(opt, inp: SolveInput) -> list[str]:
    """Config features in use that this optimizer ignores."""
    used = set()
    if np.any(inp.soft_bonus != 0):
        used.add("reglas_blandas")
    if inp.business_constraints:
        used.add("restricciones_negocio")
    if inp.channels_per_client > 1:
        used.add("multicanal")
    if inp.params.get("priorizacion.modo") == "jerarquia_estricta":
        used.add("jerarquia_estricta")
    return [FEATURES[f] for f in sorted(used - set(opt.supports))]


def pair_values(inp: SolveInput, pairs: pd.DataFrame) -> np.ndarray:
    """Official expected value per assigned (client, channel, campaign): SP × SC × VN."""
    i, c, p = (pairs[k].to_numpy(int) for k in ("client_idx", "channel_idx", "campaign_idx"))
    return inp.product_score[i, p] * inp.channel_score[i, c] * inp.business_value[p]


def assemble_assignment(inp: SolveInput, pairs: pd.DataFrame, status: np.ndarray) -> pd.DataFrame:
    """Organizer format (one row per client) + extended columns. ``razon`` is filled by explain.py.

    With more than one channel per client, ``canal`` holds the channels joined by '|' and the
    campaign columns follow channel order.
    """
    n_cols = max(2, int(inp.max_products.max()) * max(1, inp.channels_per_client)) if len(inp.max_products) else 2
    n = inp.n
    canal = np.full(n, "", dtype=object)
    camps = [np.full(n, "", dtype=object) for _ in range(n_cols)]
    value = np.zeros(n)
    nprod = np.zeros(n, int)
    if len(pairs):
        pairs = pairs.sort_values(["client_idx", "canal_orden", "orden"], kind="stable")
        ci = pairs["client_idx"].to_numpy(int)
        value = np.bincount(ci, weights=pair_values(inp, pairs), minlength=n)
        nprod = np.bincount(ci, minlength=n)
        pos = pairs.groupby("client_idx").cumcount().to_numpy()
        camp_names = np.array(inp.campaigns, dtype=object)[pairs["campaign_idx"].to_numpy(int)]
        for k in range(n_cols):
            sel = pos == k
            camps[k][ci[sel]] = camp_names[sel]
        first = pairs.drop_duplicates(["client_idx", "channel_idx"])
        names = np.array(inp.channels, dtype=object)[first["channel_idx"].to_numpy(int)]
        joined = pd.Series(names, index=first["client_idx"].to_numpy(int)).groupby(level=0).agg("|".join)
        canal[joined.index.to_numpy()] = joined.to_numpy()
    out = pd.DataFrame({"id_cliente": inp.client_ids,
                        "estado": np.where(nprod > 0, "asignado", "sin_accion"),
                        "canal": canal})
    for k in range(n_cols):
        out[f"campana_{k + 1}"] = camps[k]
    out["razon"] = ""
    out["valor_esperado"] = value
    out["n_productos"] = nprod
    out["codigo_estado"] = status
    return out
