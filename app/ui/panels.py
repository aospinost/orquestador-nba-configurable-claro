"""Panels shared by the configuration pages: inline validation and the impact preview."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.ui import components as ui
from app.ui import state
from app.ui.theme import fmt_delta, fmt_num
from engine.config_store import ConfigError
from engine.expressions import ExpressionError

TABLE_NAMES = {"campanas": "Campañas", "canales": "Canales", "parametros": "Parámetros",
               "constantes": "Constantes", "reglas": "Reglas", "restricciones": "Restricciones"}


def validation(prefixes: tuple[str, ...] | None = None) -> list[str]:
    """Show the draft's validation errors (optionally only those starting with ``prefixes``)."""
    errs = state.errors()
    shown = [e for e in errs if prefixes is None or e.startswith(prefixes)]
    if shown:
        st.error("**Hay que corregir antes de aplicar:**\n\n" + "\n".join(f"- {e}" for e in shown),
                 icon=":material/error:")
    return errs


def _kpi(label: str, new: int | None, old: int | None, icon: str) -> str:
    if new is None:
        return ui.kpi_card_html(label, "—", icon_name=icon)
    d = (new - old) if old is not None else 0
    return ui.kpi_card_html(label, fmt_num(new), d, icon, delta_text=f"{fmt_delta(d)} vs. configuración aplicada")


def impact_preview(key: str = "impacto") -> None:
    """Draft vs applied (rules only, fast) + Aplicar y re-optimizar / Descartar."""
    ui.section_label("Vista previa de impacto")
    changes = state.pending_changes()
    errs = state.errors()
    new, old = state.impact_summary(state.draft()), state.impact_summary(state.applied())
    if new.get("error"):
        st.error(f"No se puede evaluar la configuración: {new['error']}", icon=":material/error:")
        new = {}
    cols = st.columns(3)
    cards = [("Pares cliente-campaña elegibles", "pares_elegibles", "checklist"),
             ("Clientes con ≥1 campaña elegible", "clientes_elegibles", "groups"),
             ("Pares cliente-canal habilitados", "pares_canal", "alt_route")]
    for col, (label, k, icon) in zip(cols, cards):
        with col:
            st.html(_kpi(label, new.get(k), old.get(k), icon))
    if not changes:
        st.caption("Sin cambios pendientes: la configuración en edición es la misma de la última corrida.")
        return
    with st.expander("Ver el cambio sin aplicar" if len(changes) == 1 else f"Ver los {len(changes)} cambios sin aplicar",
                     icon=":material/difference:"):
        df = pd.DataFrame(changes)
        df["tabla"] = df["tabla"].map(TABLE_NAMES).fillna(df["tabla"])
        st.dataframe(df.rename(columns={"tabla": "Tabla", "clave": "Elemento", "campo": "Campo",
                                        "antes": "Antes", "despues": "Después"}),
                     hide_index=True, width="stretch")
    if errs:
        st.warning("Corrige los errores de validación para poder aplicar.", icon=":material/warning:")
    opt = st.session_state.get("optimizer", "greedy")
    available = state.optimizers().get(opt, {}).get("available", False)
    c1, c2, _ = st.columns([2, 1.8, 2.5])
    if c1.button("Aplicar y re-optimizar", type="primary", icon=":material/bolt:", key=f"{key}_apply",
                 disabled=bool(errs) or not available, width="stretch",
                 help=None if available else "El optimizador elegido está en construcción"):
        try:
            with st.status("Guardando configuración y re-optimizando…") as s:
                run = state.apply_and_run(opt)
                s.update(label="Configuración aplicada", state="complete")
            st.toast(f"Aplicado · valor esperado {fmt_num(run['metrics']['valor_esperado'], 1)}",
                     icon=":material/check_circle:")
            st.rerun()
        except (ConfigError, ExpressionError) as exc:
            errs = exc.errors if isinstance(exc, ConfigError) else [str(exc)]
            st.error("\n".join(f"- {e}" for e in errs))
    if c2.button("Descartar cambios", icon=":material/undo:", key=f"{key}_discard", width="stretch"):
        state.discard_changes()
        st.rerun()
