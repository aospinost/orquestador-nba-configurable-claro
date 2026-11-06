import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.ui import components as ui
from app.ui import panels, state
from app.ui.theme import BLACK, GRAY, GRAY_MID, RED, fmt_num, fmt_pct
from engine import config_store as cs
from engine import impact

cfg = state.draft()
ss = st.session_state
rev = state.rev()
WEIGHT_PREFIX = "priorizacion.pesos."
WEIGHT_NAMES = {"score_producto": "Modelo (score de producto)", "valor_negocio": "Valor de negocio",
                "jerarquia": "Jerarquía"}
MODE_HELP = {"ponderado": "Combina modelo, valor y jerarquía con los pesos de abajo. La jerarquía es una "
                          "preferencia que puede ceder ante más valor.",
             "jerarquia_estricta": "Siempre ofrece primero la campaña de mayor jerarquía elegible; el puntaje solo "
                                   "desempata."}
CRITERIA_HELP = {"score_canal": "El canal habilitado con mayor probabilidad de respuesta que aún tenga cupo.",
                 "orden_preferencia": "El primer canal habilitado con cupo según el orden fijo de la tabla."}

ui.hero("Prioridad y canales", "Cómo se ordenan las campañas, cuánto pesa el modelo frente al valor y la "
        "jerarquía, desde qué score se compite y cuánto cupo tiene cada canal.", eyebrow="Configuración")
panels.validation(("Prioridad", "Canal", "Parámetro"))

# ---------------------------------------------------------------- hierarchy
ui.step_header(1, "Jerarquía de campañas", "Preferencia de negocio")
camps = sorted(cfg.campaigns, key=lambda c: (c.rango_jerarquia, c.id))


def _move(i: int, j: int) -> None:
    order = [c.id for c in camps]
    order[i], order[j] = order[j], order[i]
    t = cfg.tables["campanas"]
    for rank, cid in enumerate(order, start=1):
        t.loc[t["id"] == cid, "rango_jerarquia"] = str(rank)
    state.touch()


for i, c in enumerate(camps):
    c0, c1, c2, c3 = st.columns([0.6, 6, 0.6, 0.6], vertical_alignment="center")
    c0.html(f'<div style="font-size:2rem;font-weight:800;color:{RED};text-align:center">{i + 1}</div>')
    paused = "" if cfg.campaign_in_force(c) else " · <i>pausada o fuera de vigencia</i>"
    c1.html(f'<b>{c.nombre}</b> <span class="claro-meta">{c.id} · valor {fmt_num(c.valor_negocio, 2)}{paused}</span>')
    c2.button("", icon=":material/arrow_upward:", key=f"up_{c.id}_{rev}", disabled=i == 0,
              on_click=_move, args=(i, i - 1), help="Subir")
    c3.button("", icon=":material/arrow_downward:", key=f"dn_{c.id}_{rev}", disabled=i == len(camps) - 1,
              on_click=_move, args=(i, i + 1), help="Bajar")

modes = cfg.param_list(cs.PRIORITY_MODES_KEY) or [cfg.param("priorizacion.modo")]
mode = st.radio("Modo de priorización", modes, index=modes.index(cfg.param("priorizacion.modo"))
                if cfg.param("priorizacion.modo") in modes else 0, horizontal=True, key=f"mode_{rev}",
                format_func=lambda m: {"ponderado": "Ponderado", "jerarquia_estricta": "Jerarquía estricta"}.get(m, m))
st.caption(MODE_HELP.get(mode, ""))
if mode != cfg.param("priorizacion.modo"):
    cfg.set_param("priorizacion.modo", mode)
    st.rerun()

# ---------------------------------------------------------------- weights
ui.step_header(2, "Pesos del puntaje", "Modelo vs. valor vs. jerarquía")
wkeys = [k for k in cfg.params if k.startswith(WEIGHT_PREFIX)]
weights = {k: cfg.param_float(k, 0.0) for k in wkeys}


def _rebalance(changed: str, key: str) -> None:
    """Keep the weights summing 1: the others absorb the change in proportion to their current values."""
    v = round(float(ss[key]), 2)
    others = [k for k in wkeys if k != changed]
    rest = 1.0 - v
    base = sum(weights[k] for k in others)
    new = {changed: v}
    for k in others:
        new[k] = rest * (weights[k] / base if base > 0 else 1 / len(others))
    rounded = {k: round(x, 2) for k, x in new.items()}
    if others:
        rounded[others[-1]] = round(1.0 - sum(x for k, x in rounded.items() if k != others[-1]), 2)
    for k, x in rounded.items():
        cfg.set_param(k, f"{max(x, 0.0):g}")
    state.touch()


wc = st.columns(len(wkeys) or 1)
for col, k in zip(wc, wkeys):
    name = k[len(WEIGHT_PREFIX):]
    key = f"w_{name}_{rev}"
    col.slider(WEIGHT_NAMES.get(name, name), 0.0, 1.0, weights[k], 0.05, key=key, on_change=_rebalance, args=(k, key))
if wkeys:
    fig = go.Figure()
    colors = [RED, BLACK, GRAY_MID, GRAY]
    for i, k in enumerate(wkeys):
        name = k[len(WEIGHT_PREFIX):]
        fig.add_bar(y=["Puntaje"], x=[weights[k]], orientation="h", name=WEIGHT_NAMES.get(name, name),
                    marker_color=colors[i % len(colors)], text=[fmt_pct(100 * weights[k], 0)],
                    textposition="inside", insidetextfont=dict(color="#FDFDFD", size=16),
                    hovertemplate=f"{WEIGHT_NAMES.get(name, name)}: %{{x:.2f}}<extra></extra>")
    fig.update_layout(barmode="stack", height=130, margin=dict(l=0, r=0, t=30, b=0), xaxis=dict(range=[0, 1],
                      visible=False), yaxis=dict(visible=False))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
tie_opts = [k[len(WEIGHT_PREFIX):] for k in wkeys]
tie = st.multiselect("Desempate (en orden)", tie_opts, default=[t for t in cfg.param_list("priorizacion.desempate")
                                                               if t in tie_opts],
                     format_func=lambda n: WEIGHT_NAMES.get(n, n), key=f"tie_{rev}", placeholder="Elige uno o varios",
                     help="Si dos campañas o clientes empatan en puntaje, gana el de mayor valor en estos criterios.")
if "|".join(tie) != cfg.param("priorizacion.desempate"):
    cfg.set_param("priorizacion.desempate", "|".join(tie))
    st.rerun()

# ---------------------------------------------------------------- thresholds
ui.step_header(3, "Umbrales de score", "Desde qué score se compite")
df = state.clients(cfg)
thr = impact.thresholds(df, cfg)


def _hist(scores: np.ndarray, u: float, title: str, below: int) -> go.Figure:
    s = scores[~np.isnan(scores)]
    bins = np.linspace(0, 1, 41)
    counts, edges = np.histogram(s, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    fig = go.Figure(go.Bar(x=centers, y=counts, width=edges[1] - edges[0],
                           marker_color=[GRAY if x < u else BLACK for x in centers],
                           hovertemplate="score %{x:.2f}: %{y:,.0f} clientes<extra></extra>"))
    fig.add_vline(x=u, line_color=RED, line_width=4)
    fig.add_annotation(x=u, y=1, yref="paper", text=f"<b>{fmt_num(below)}</b> clientes por debajo "
                       f"({fmt_pct(100 * below / max(len(scores), 1))})", showarrow=False, xanchor="left",
                       xshift=8, font=dict(color=RED, size=15), bgcolor="rgba(253,253,253,.9)")
    fig.update_layout(title=title, height=300, bargap=0.05, xaxis_title="Score", yaxis_title="Clientes",
                      xaxis=dict(range=[0, 1]))
    return fig


g1, g2 = st.columns(2)
with g1:
    up = cfg.param_float("priorizacion.umbral_score_producto", 0.0)
    v = st.slider("Score mínimo de producto (global)", 0.0, 1.0, up, 0.01, key=f"up_{rev}")
    if v != up:
        cfg.set_param("priorizacion.umbral_score_producto", f"{v:g}")
        st.rerun()
    if thr["campanas"]:
        pick = st.selectbox("Ver distribución de", list(thr["campanas"]), key="hist_camp",
                            format_func=lambda c: f"{c} · {thr['campanas'][c]['nombre']}")
        h = thr["campanas"][pick]
        st.plotly_chart(_hist(h["scores"], h["umbral"], f"{h['columna']}", h["debajo"]), use_container_width=True,
                        config={"displayModeBar": False})
        if h["umbral"] != v:
            st.caption(f"{pick} usa un umbral propio de {fmt_num(h['umbral'], 2)} (se cambia en Campañas).")
with g2:
    uc = cfg.param_float("canal.umbral_score_canal", 0.0)
    v = st.slider("Score mínimo de canal (global)", 0.0, 1.0, uc, 0.01, key=f"uc_{rev}")
    if v != uc:
        cfg.set_param("canal.umbral_score_canal", f"{v:g}")
        st.rerun()
    if thr["canales"]:
        pick = st.selectbox("Ver distribución de", list(thr["canales"]), key="hist_chan",
                            format_func=lambda c: thr["canales"][c]["nombre"])
        h = thr["canales"][pick]
        st.plotly_chart(_hist(h["scores"], h["umbral"], f"{h['columna']}", h["debajo"]), use_container_width=True,
                        config={"displayModeBar": False})
        if h["umbral"] != v:
            st.caption(f"{pick} usa un umbral propio de {fmt_num(h['umbral'], 2)} (columna 'Umbral propio' abajo).")

# ---------------------------------------------------------------- channels
ui.step_header(4, "Canales y cupos", "Por dónde y cuánto")
crits = cfg.param_list(cs.CHANNEL_CRITERIA_KEY) or [cfg.param("canal.criterio")]
crit = st.radio("Cómo se elige el canal", crits, horizontal=True, key=f"crit_{rev}",
                index=crits.index(cfg.param("canal.criterio")) if cfg.param("canal.criterio") in crits else 0,
                format_func=lambda c: {"score_canal": "Mayor score de canal",
                                       "orden_preferencia": "Orden de preferencia fijo"}.get(c, c))
st.caption(CRITERIA_HELP.get(crit, ""))
if crit != cfg.param("canal.criterio"):
    cfg.set_param("canal.criterio", crit)
    st.rerun()

prof = state.column_profile(cfg)
numeric_cols = prof.query("tipo == 'numerica'")["columna"].tolist()
all_cols = [""] + prof["columna"].tolist()
t = cfg.tables["canales"]
view = pd.DataFrame({
    "id": t["id"], "nombre": t["nombre"], "columna_score": t["columna_score"],
    "capacidad": pd.to_numeric(t["capacidad"], errors="coerce").astype("Int64"),
    "max_productos": pd.to_numeric(t["max_productos"], errors="coerce").astype("Int64"),
    "umbral_score": pd.to_numeric(t["umbral_score"].replace("", None), errors="coerce"),
    "columna_autorizacion": t["columna_autorizacion"],
    "orden_preferencia": pd.to_numeric(t["orden_preferencia"], errors="coerce").astype("Int64"),
    "activo": t["activo"].map(cs.to_bool),
})
edited = st.data_editor(view, hide_index=True, width="stretch", key=f"chan_editor_{rev}", disabled=["id"],
                        column_config={
                            "id": "ID", "nombre": st.column_config.TextColumn("Nombre", required=True),
                            "columna_score": st.column_config.SelectboxColumn("Columna de score (SC)",
                                                                              options=numeric_cols, required=True),
                            "capacidad": st.column_config.NumberColumn("Cupo por corrida", min_value=0, step=100,
                                                                       format="localized"),
                            "max_productos": st.column_config.NumberColumn("Productos por contacto", min_value=1,
                                                                           max_value=10, step=1),
                            "umbral_score": st.column_config.NumberColumn("Umbral propio", min_value=0.0,
                                                                          max_value=1.0, step=0.01, format="%.2f",
                                                                          help="Vacío = umbral global"),
                            "columna_autorizacion": st.column_config.SelectboxColumn(
                                "Columna de autorización", options=all_cols,
                                help="Opcional: si se indica, el canal exige valor 1 en esa columna (P-AUTORIZACION)."),
                            "orden_preferencia": st.column_config.NumberColumn("Orden", min_value=1, step=1),
                            "activo": st.column_config.CheckboxColumn("Activo"),
                        })


def _s(v) -> str:
    if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, (bool, np.bool_)):
        return "1" if v else "0"
    if isinstance(v, (float, np.floating)):
        return f"{float(v):g}"
    return str(v)


changed = False
for col in view.columns:
    for i, (a, b) in enumerate(zip(view[col], edited[col])):
        if _s(a) != _s(b):
            t.iat[i, t.columns.get_loc(col)] = _s(b)
            changed = True
if changed:
    state.touch()
    st.rerun()


with st.expander("Agregar canal", icon=":material/add_circle:"):
    with st.form(f"new_channel_{rev}", border=False):
        c1, c2 = st.columns(2)
        cid = c1.text_input("ID del canal", placeholder="app", help="Una palabra, sin espacios.")
        nombre = c2.text_input("Nombre visible", placeholder="App Mi Claro")
        score = st.selectbox("Columna con la probabilidad de respuesta (SC)", numeric_cols)
        c3, c4 = st.columns(2)
        cap = c3.number_input("Cupo por corrida", min_value=0, value=1000, step=100)
        mp = c4.number_input("Productos por contacto", min_value=1, max_value=10, value=1)
        auth = st.selectbox("Columna de autorización (opcional)", all_cols, format_func=lambda c: c or "No exige")
        allow = st.multiselect("Campañas que pueden ir por este canal", [c.id for c in cfg.campaigns],
                               placeholder="Elige una o varias")
        submitted = st.form_submit_button("Agregar canal", type="primary", icon=":material/add:")
    if submitted:
        cid = cid.strip().lower()
        problem = ("Escribe el ID y el nombre." if not (cid and nombre.strip()) else
                   "El ID no puede tener espacios." if " " in cid else
                   "Ya existe un canal con ese ID." if cid in [c.id for c in cfg.channels] else "")
        if problem:
            st.error(problem, icon=":material/error:")
        else:
            order = max([c.orden_preferencia for c in cfg.channels] or [0]) + 1
            cs.upsert_row(cfg, "canales", {"id": cid, "nombre": nombre.strip(), "columna_score": score,
                                           "capacidad": int(cap), "max_productos": int(mp), "umbral_score": "",
                                           "columna_autorizacion": auth, "orden_preferencia": order, "activo": "1"})
            tc = cfg.tables["campanas"]
            for camp in allow:
                m = tc["id"] == camp
                cur = cs.split_list(tc.loc[m, "canales_permitidos"].iloc[0])
                tc.loc[m, "canales_permitidos"] = "|".join(cur + [cid])
            state.touch()
            st.toast(f"Canal {cid} agregado (sin aplicar)", icon=":material/alt_route:")
            st.rerun()

panels.impact_preview()
