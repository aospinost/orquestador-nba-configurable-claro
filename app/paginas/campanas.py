import datetime as dt

import pandas as pd
import streamlit as st

from app.ui import components as ui
from app.ui import panels, state
from app.ui.theme import fmt_num
from engine import config_store as cs

cfg = state.draft()
ss = st.session_state
numeric_cols = state.column_profile(cfg).query("tipo == 'numerica'")["columna"].tolist()
channel_ids = [c.id for c in cfg.channels]

ui.hero("Campañas", "Cada campaña es un producto con su valor para la compañía, los canales por donde puede "
        "ofrecerse y su vigencia. Pausar una campaña la saca de la corrida sin borrarla.", eyebrow="Configuración",
        big_numeral=str(len(cfg.active_campaigns)), numeral_caption="activas y vigentes")
panels.validation(("Campaña", "Campañas"))


def _status(c: cs.Campaign) -> tuple[str, str]:
    d = cfg.run_date()
    if not c.activa:
        return "off", "Pausada"
    if c.vigencia_inicio and d < c.vigencia_inicio:
        return "off", f"Empieza el {c.vigencia_inicio:%d/%m/%Y}"
    if c.vigencia_fin and d > c.vigencia_fin:
        return "off", f"Terminó el {c.vigencia_fin:%d/%m/%Y}"
    return "on", "Activa y vigente"


def _toggle(cid: str, key: str) -> None:
    t = cfg.tables["campanas"]
    t.loc[t["id"] == cid, "activa"] = "1" if ss[key] else "0"
    state.touch()


ui.section_label(f"Campañas · fecha de corrida {cfg.run_date():%d/%m/%Y}")
camps = sorted(cfg.campaigns, key=lambda c: c.rango_jerarquia)
per_row = 3
for start in range(0, len(camps), per_row):
    cols = st.columns(per_row)
    for col, c in zip(cols, camps[start:start + per_row]):
        state_cls, label = _status(c)
        dim = "opacity:.5;filter:grayscale(1);" if state_cls == "off" else ""
        thr = c.umbral_score if c.umbral_score is not None else cfg.param_float("priorizacion.umbral_score_producto")
        chips = "".join(ui.chip_html(ch) for ch in c.canales_permitidos)
        with col.container(border=True):
            st.html(f'<div style="{dim}"><div style="display:flex;gap:1rem;align-items:center">'
                    f'{ui.tile_html("campaign", c.producto, small=True)}<div><div class="claro-meta">{c.id} · {c.objetivo}</div>'
                    f'<div style="font-weight:800;font-size:1.25rem;line-height:1.2">{c.nombre}</div>'
                    f'<div class="claro-meta">Valor {fmt_num(c.valor_negocio, 2)} · jerarquía '
                    f'{fmt_num(c.rango_jerarquia)} · umbral {fmt_num(thr, 2)}'
                    f'{"" if c.umbral_score is None else " (propio)"}</div></div></div>'
                    f'<div style="margin-top:.6rem">{chips}</div></div>')
            key = f"camp_on_{c.id}_{state.rev()}"
            st.toggle(f"{label}", value=c.activa, key=key, on_change=_toggle, args=(c.id, key),
                      help="Pausar sin borrar: la campaña sale de la corrida y se puede reactivar.")


with st.expander("Nueva campaña", icon=":material/add_circle:"):
    with st.form(f"new_campaign_{state.rev()}", clear_on_submit=False, border=False):
        c1, c2 = st.columns(2)
        producto = c1.text_input("Código de producto", placeholder="SEG",
                                 help="Se compara con la columna de productos ya ofertados en el mes.")
        cid = c2.text_input("ID de campaña", placeholder="C-SEG", help="Vacío = C- más el código de producto.")
        nombre = st.text_input("Nombre visible", placeholder="Seguro de equipo")
        objectives = sorted({c.objetivo for c in cfg.campaigns})
        c3, c4 = st.columns(2)
        obj = c3.selectbox("Objetivo", objectives)
        new_obj = c4.text_input("…o un objetivo nuevo", placeholder="Fidelización")
        score = st.selectbox("Columna con la propensión (SP)", numeric_cols,
                             help="Columna numérica de la base con el score del producto.")
        valor = st.slider("Valor de negocio", 0.0, 1.0, 0.5, 0.05)
        canales = st.multiselect("Canales permitidos", channel_ids, default=channel_ids, placeholder="Elige uno o varios")
        d1, d2 = st.columns(2)
        ini = d1.date_input("Vigente desde", value=cfg.run_date(), format="DD/MM/YYYY")
        fin = d2.date_input("Vigente hasta", value=cfg.run_date() + dt.timedelta(days=60), format="DD/MM/YYYY")
        e1, e2 = st.columns(2)
        own = e1.checkbox("Usar un umbral de score propio")
        umbral = e2.slider("Umbral propio", 0.0, 1.0, 0.35, 0.01)
        submitted = st.form_submit_button("Crear campaña", type="primary", icon=":material/add:")
    if submitted:
        producto = producto.strip().upper()
        cid = cid.strip() or (f"C-{producto}" if producto else "")
        problem = ("Escribe el código de producto y el nombre." if not (producto and nombre.strip()) else
                   "Ya existe una campaña con ese ID." if cid in [c.id for c in cfg.campaigns] else
                   "Elige al menos un canal." if not canales else "")
        if problem:
            st.error(problem, icon=":material/error:")
        else:
            rank = max([c.rango_jerarquia for c in cfg.campaigns if c.rango_jerarquia != float("inf")] or [0]) + 1
            cs.upsert_row(cfg, "campanas", {
                "id": cid, "nombre": nombre.strip(), "producto": producto, "objetivo": new_obj.strip() or obj,
                "columna_score": score, "valor_negocio": f"{valor:g}", "canales_permitidos": "|".join(canales),
                "vigencia_inicio": ini.isoformat(), "vigencia_fin": fin.isoformat(), "activa": "1",
                "umbral_score": f"{umbral:g}" if own else "", "rango_jerarquia": str(int(rank))})
            state.touch()
            st.toast(f"Campaña {cid} creada (sin aplicar)", icon=":material/campaign:")
            st.rerun()

ui.section_label("Edición en tabla")
st.caption("Edita varias campañas a la vez. Los cambios quedan en borrador hasta pulsar **Aplicar y re-optimizar**. "
           "La jerarquía se ordena en *Prioridad y canales*.")
t = cfg.tables["campanas"]
view = pd.DataFrame({
    "id": t["id"], "nombre": t["nombre"], "producto": t["producto"], "objetivo": t["objetivo"],
    "columna_score": t["columna_score"],
    "valor_negocio": pd.to_numeric(t["valor_negocio"], errors="coerce"),
    "canales_permitidos": t["canales_permitidos"].map(cs.split_list),
    "vigencia_inicio": pd.to_datetime(t["vigencia_inicio"], errors="coerce").dt.date,
    "vigencia_fin": pd.to_datetime(t["vigencia_fin"], errors="coerce").dt.date,
    "activa": t["activa"].map(cs.to_bool),
    "umbral_score": pd.to_numeric(t["umbral_score"].replace("", None), errors="coerce"),
})
edited = st.data_editor(
    view, hide_index=True, width="stretch", key=f"camp_editor_{state.rev()}", disabled=["id"],
    column_config={
        "id": st.column_config.TextColumn("ID"),
        "nombre": st.column_config.TextColumn("Nombre", required=True),
        "producto": st.column_config.TextColumn("Producto", required=True),
        "objetivo": st.column_config.TextColumn("Objetivo", required=True),
        "columna_score": st.column_config.SelectboxColumn("Columna de score", options=numeric_cols, required=True),
        "valor_negocio": st.column_config.NumberColumn("Valor", min_value=0.0, max_value=1.0, step=0.05, format="%.2f"),
        "canales_permitidos": st.column_config.MultiselectColumn("Canales permitidos", options=channel_ids),
        "vigencia_inicio": st.column_config.DateColumn("Desde", format="DD/MM/YYYY"),
        "vigencia_fin": st.column_config.DateColumn("Hasta", format="DD/MM/YYYY"),
        "activa": st.column_config.CheckboxColumn("Activa"),
        "umbral_score": st.column_config.NumberColumn("Umbral propio", min_value=0.0, max_value=1.0, step=0.01,
                                                      format="%.2f", help="Vacío = umbral global"),
    })


def _s(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
        return ""
    if isinstance(v, (list, tuple)):
        return "|".join(v)
    if isinstance(v, (dt.date, pd.Timestamp)):
        return v.isoformat()[:10]
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


changed = False
for col in view.columns:
    for i, (a, b) in enumerate(zip(view[col], edited[col])):
        if _s(a) != _s(b):  # only cells the user touched; untouched cells keep their original text
            t.iat[i, t.columns.get_loc(col)] = _s(b)
            changed = True
if changed:
    state.touch()
    st.rerun()

panels.impact_preview()
