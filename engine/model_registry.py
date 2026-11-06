"""Symbol table of the mathematical model, generated from the live configuration.

The UI and the methodology page render from here, so the math shown is the math being solved.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from engine.config_store import FILES, Campaign, Channel, Config


@dataclass
class Symbol:
    simbolo: str
    latex: str
    significado: str
    fuente: str
    valor: str
    editable: bool
    grupo: str


def _fmt(x: float) -> str:
    return f"{x:,.4g}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dist(values: np.ndarray) -> str:
    v = values[~np.isnan(values)]
    if not len(v):
        return "sin datos"
    return f"min {_fmt(v.min())} · media {_fmt(v.mean())} · máx {_fmt(v.max())}"


@dataclass
class ModelRegistry:
    symbols: list[Symbol]

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(s) for s in self.symbols])


def build(cfg: Config, campaigns: list[Campaign], channels: list[Channel],
          df: pd.DataFrame | None = None, constants: dict | None = None) -> ModelRegistry:
    S: list[Symbol] = []
    fc, fk, fp = FILES["campanas"], FILES["canales"], FILES["parametros"]
    S.append(Symbol("P", r"p \in P", "Campañas activas y vigentes", f"{fc} (activa, vigencia)",
                    ", ".join(c.id for c in campaigns), True, "Conjuntos"))
    S.append(Symbol("C", r"c \in C", "Canales activos", f"{fk} (activo)",
                    ", ".join(c.id for c in channels), True, "Conjuntos"))
    for c in campaigns:
        S.append(Symbol(f"VN_{c.id}", rf"VN_{{{c.id}}}", f"Valor de negocio de {c.nombre}",
                        f"{fc}.valor_negocio", _fmt(c.valor_negocio), True, "Parámetros por campaña"))
        thr = c.umbral_score if c.umbral_score is not None else cfg.param_float("priorizacion.umbral_score_producto")
        S.append(Symbol(f"U_{c.id}", rf"U_{{{c.id}}}", f"Score mínimo de producto para {c.nombre}",
                        f"{fc}.umbral_score (vacío = {fp} priorizacion.umbral_score_producto)",
                        _fmt(thr), True, "Parámetros por campaña"))
        sp = (_dist(pd.to_numeric(df[c.columna_score], errors="coerce").to_numpy(float))
              if df is not None and c.columna_score in df.columns else "")
        S.append(Symbol(f"SP_i^{c.id}", rf"SP_i^{{{c.id}}}", f"Propensión del cliente a {c.nombre}",
                        f"columna {c.columna_score}", sp, True, "Constantes de cliente"))
    for c in channels:
        S.append(Symbol(f"K_{c.id}", rf"K_{{{c.id}}}", f"Cupo por corrida del canal {c.nombre}",
                        f"{fk}.capacidad", _fmt(c.capacidad), True, "Parámetros por canal"))
        S.append(Symbol(f"M_{c.id}", rf"M_{{{c.id}}}", f"Productos por contacto en {c.nombre}",
                        f"{fk}.max_productos", _fmt(c.max_productos), True, "Parámetros por canal"))
        thr = c.umbral_score if c.umbral_score is not None else cfg.param_float("canal.umbral_score_canal")
        S.append(Symbol(f"U_{c.id}", rf"U_{{{c.id}}}", f"Score mínimo del canal {c.nombre}",
                        f"{fk}.umbral_score (vacío = {fp} canal.umbral_score_canal)",
                        _fmt(thr), True, "Parámetros por canal"))
        sc = (_dist(pd.to_numeric(df[c.columna_score], errors="coerce").to_numpy(float))
              if df is not None and c.columna_score in df.columns else "")
        S.append(Symbol(f"SC_i^{c.id}", rf"SC_i^{{{c.id}}}", f"Probabilidad de respuesta por {c.nombre}",
                        f"columna {c.columna_score}", sc, True, "Constantes de cliente"))
    for k in cfg.constants:
        arr = (constants or {}).get(k.id)
        val = "" if arr is None else (f"{_fmt(100 * float(np.mean(arr)))} % de 1" if k.tipo == "binaria"
                                      else _dist(np.asarray(arr, float).ravel()))
        idx = "_i^p" if k.por_campana or k.nivel == "cliente_campana" else "_i"
        S.append(Symbol(k.id, k.id.replace("_i", idx, 1) if "_i" in k.id else k.id + idx, k.nombre,
                        f"{FILES['constantes']}", val if k.activa else "inactiva", True, "Constantes derivadas"))
    for key in ("politica_contacto.canales_por_cliente", "politica_contacto.max_contactos_semana",
                "priorizacion.modo", "objetivo.peso_valor", "objetivo.peso_jerarquia",
                "optimizador.tiempo_max_s", "optimizador.gap"):
        S.append(Symbol(key, r"\text{" + key.replace("_", r"\_") + "}", "Parámetro global", fp,
                        cfg.param(key, ""), True, "Parámetros globales"))
    for b in cfg.business_constraints:
        S.append(Symbol(b.id, b.id, b.nombre, FILES["restricciones"],
                        f"{b.metrica} {b.sentido} {_fmt(b.valor)} ({b.unidad})" + ("" if b.activa else " · inactiva"),
                        True, "Restricciones de negocio"))
    S.append(Symbol("Z_i^{p,c}", r"Z_i^{p,c} \in \{0,1\}", "Ofrecer la campaña p al cliente i por el canal c",
                    "variable de decisión", "", False, "Variables"))
    S.append(Symbol("Z_i^c", r"Z_i^{c} \in \{0,1\}", "Contactar al cliente i por el canal c",
                    "variable de decisión", "", False, "Variables"))
    return ModelRegistry(S)
