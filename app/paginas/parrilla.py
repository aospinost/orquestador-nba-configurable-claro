import numpy as np
import pandas as pd
import streamlit as st

from app.ui import components as ui
from app.ui import state
from app.ui.theme import fmt_num
from engine.pipeline import to_parrilla

run = state.last_run()
ui.hero("Parrilla", "La decisión cliente por cliente: canal, campañas y la razón en lenguaje de negocio.",
        eyebrow="Resultado")
if run is None:
    st.info("Aún no hay corrida. Pulsa **Ejecutar orquestador** en la barra lateral.", icon=":material/play_circle:")
    st.stop()

out = run["output"]
inp, res = out.inp, out.result
cfg = state.applied()
df = state.clients(cfg)
a = res.assignment
camp_cols = [c for c in a.columns if c.startswith("campana_")]

# ---------------------------------------------------------------- downloads
ui.section_label("Descargas")


def _organizer_csv() -> bytes:
    return to_parrilla(a).to_csv(index=False).encode("utf-8")


def _extended_csv() -> bytes:
    ext = a.copy()
    for p, cid in enumerate(inp.campaigns):
        ext[f"score_{cid}"] = inp.product_score[:, p]
    for c, ch in enumerate(inp.channels):
        ext[f"score_canal_{ch}"] = inp.channel_score[:, c]
    if res.pairs is not None and len(res.pairs):
        pv = inp.product_score[res.pairs["client_idx"], res.pairs["campaign_idx"]] * \
             inp.channel_score[res.pairs["client_idx"], res.pairs["channel_idx"]] * inp.business_value[res.pairs["campaign_idx"]]
        for p, cid in enumerate(inp.campaigns):
            sel = res.pairs["campaign_idx"].to_numpy() == p
            col = np.zeros(inp.n)
            col[res.pairs["client_idx"].to_numpy()[sel]] = pv[sel]
            ext[f"valor_{cid}"] = col
    return ext.to_csv(index=False).encode("utf-8")


d1, d2, _ = st.columns([1.6, 1.6, 2])
d1.download_button("Parrilla (formato organizadores)", state.memo(run, "csv_org", _organizer_csv),
                   file_name=f"parrilla_{run['optimizer']}_{run['hash']}.csv", mime="text/csv",
                   icon=":material/download:", type="primary", width="stretch")
d2.download_button("Parrilla extendida (valores y scores)", state.memo(run, "csv_ext", _extended_csv),
                   file_name=f"parrilla_extendida_{run['optimizer']}_{run['hash']}.csv", mime="text/csv",
                   icon=":material/dataset:", width="stretch")

# ---------------------------------------------------------------- filters
ui.section_label("Filtros")
f1, f2, f3 = st.columns(3)
estados = f1.multiselect("Estado", ["asignado", "sin_accion"], placeholder="Todos",
                         format_func={"asignado": "Asignado", "sin_accion": "Sin acción"}.get)
canales = f2.multiselect("Canal", inp.channels, placeholder="Todos")
campanas = f3.multiselect("Campaña", inp.campaigns, placeholder="Todas")
prof = state.column_profile(cfg)
id_col = cfg.param("datos.columna_id")
filterable = prof[(prof["tipo"].isin(["categoria", "numerica", "lista"])) & (prof["valores"].map(len) > 0)
                  & (prof["columna"] != id_col)]["columna"].tolist()
g1, g2, g3 = st.columns([1, 2, 1.4])
col = g1.selectbox("Filtrar por columna de la base", [""] + filterable, format_func=lambda c: c or "Ninguna")
vals = []
if col:
    options = prof.set_index("columna").loc[col, "valores"]
    vals = g2.multiselect("Valores", [str(v) for v in options], placeholder="Todos")
search = g3.text_input("Buscar cliente", placeholder="ID del cliente")

mask = np.ones(len(a), bool)
if estados:
    mask &= a["estado"].isin(estados).to_numpy()
if canales:
    mask &= a["canal"].str.split("|").map(lambda xs: bool(set(xs) & set(canales))).to_numpy()
if campanas:
    mask &= a[camp_cols].isin(campanas).any(axis=1).to_numpy()
if col and vals:
    s = df[col]
    if s.dtype == object and len(s) and isinstance(s.iloc[0], frozenset):
        mask &= s.map(lambda x: bool({str(v) for v in x} & set(vals))).to_numpy()
    else:
        mask &= s.map(lambda v: (str(int(v)) if isinstance(v, float) and float(v).is_integer() else str(v))
                      ).isin(vals).to_numpy()
if search.strip():
    mask &= a["id_cliente"].str.contains(search.strip(), case=False, regex=False).to_numpy()

view = a[mask]
ui.section_label(f"{fmt_num(len(view))} clientes")
size = 100
pages = max(1, int(np.ceil(len(view) / size)))
p1, p2 = st.columns([1, 5], vertical_alignment="center")
page = p1.number_input("Página", 1, pages, 1)
p2.caption(f"de {fmt_num(pages)} · {size} filas por página (la consola nunca dibuja las {fmt_num(inp.n)} a la vez).")
chunk = view.iloc[(page - 1) * size: page * size]
show = chunk[["id_cliente", "estado", "canal", *camp_cols, "valor_esperado", "razon"]]
st.dataframe(show, hide_index=True, width="stretch", height=560, column_config={
    "id_cliente": st.column_config.TextColumn("Cliente"),
    "estado": st.column_config.TextColumn("Estado"),
    "canal": st.column_config.TextColumn("Canal"),
    **{c: st.column_config.TextColumn(c.replace("campana_", "Campaña ")) for c in camp_cols},
    "valor_esperado": st.column_config.NumberColumn("Valor", format="%.3f"),
    "razon": st.column_config.TextColumn("Razón", width="large"),
})
