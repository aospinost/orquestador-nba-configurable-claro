from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.ui import components as ui
from app.ui import state
from app.ui.theme import GRAY, GRAY_MID, RED, fmt_num, highlight_colors
from engine import impact, insights
from engine.rules import SYSTEM_RULES

CHART = {"displayModeBar": False}
run = state.last_run()
ui.hero("Explicabilidad", "Por qué este cliente, esta campaña y este canal; y qué reglas y cupos pesan más en el "
        "conjunto.", eyebrow="Resultado")
if run is None:
    st.info("Aún no hay corrida. Pulsa **Ejecutar orquestador** en la barra lateral.", icon=":material/play_circle:")
    st.stop()

out = run["output"]
inp, res, m = out.inp, out.result, run["metrics"]
cfg = state.applied()
df = state.clients(cfg)
info = inp.exclusion_reasons.get("info", {})
tab_c, tab_g = st.tabs([":material/person_search: Ficha de cliente", ":material/insights: Explicación global"])


def check_line(ch: dict) -> str:
    state_ = "pass" if ch["ok"] else "hit"
    if ch.get("blanda"):
        state_ = "on"
    return (f'<div style="display:flex;gap:.6rem;align-items:flex-start;margin:.25rem 0">'
            f'{ui.rule_chip_html(ch["id"], state_)}<div><b>{escape(ch["nombre"])}</b>'
            f'<div class="claro-meta">{escape(ch["detalle"])}</div></div></div>')


def render_card(i: int) -> None:
    d = insights.client_detail(inp, res, df, i, cfg)

    with st.container(border=True):
        h1, h2, h3 = st.columns([1.4, 2.2, 1.2], vertical_alignment="center")
        h1.html(f'<div class="claro-meta">Cliente</div><div style="font-size:1.9rem;font-weight:800">{d["id"]}</div>'
                f'{ui.status_badge_html(d["estado"])}')
        camps = " + ".join(d["campanas"]) or "—"
        h2.html(f'<div class="claro-meta">Canal · campañas</div><div style="font-size:1.35rem;font-weight:700">'
                f'{escape(d["canal"] + " · " + camps) if d["canal"] else "Sin contacto en esta corrida"}</div>')
        h3.html(f'<div class="claro-meta">Valor esperado</div><div style="font-size:1.9rem;font-weight:800;'
                f'color:{RED}">{fmt_num(d["valor"], 3)}</div>')
        ui.banner("Guion: " + d["guion"], "record_voice_over")
        st.markdown(f"**Razón en la parrilla:** {d['razon']}")

    if d["reglas_cliente"]:
        ui.section_label("Reglas a nivel de cliente")
        st.html("".join(check_line(ch) for ch in d["reglas_cliente"]))

    l, r = st.columns(2)
    with l:
        ui.section_label("Por campaña")
        for pid, item in d["por_campana"].items():
            icon = ":material/check_circle:" if item["elegible"] else ":material/block:"
            with st.expander(f"{pid} · {item['nombre']} — {'elegible' if item['elegible'] else 'excluida'}",
                             icon=icon, expanded=not item["elegible"]):
                st.html("".join(check_line(ch) for ch in item["checks"]) or "Sin reglas aplicables.")
    with r:
        ui.section_label("Por canal")
        for chid, item in d["por_canal"].items():
            icon = ":material/check_circle:" if item["habilitado"] else ":material/block:"
            with st.expander(f"{chid} · {item['nombre']} — {'habilitado' if item['habilitado'] else 'bloqueado'}",
                             icon=icon, expanded=not item["habilitado"]):
                st.html("".join(check_line(ch) for ch in item["checks"]) or "Sin reglas aplicables.")

    ui.section_label("Valor esperado de cada opción (campaña × canal)")
    mt = pd.DataFrame(d["matriz"])
    head = "".join(f'<th style="padding:.5rem .8rem;text-align:center">{escape(c)}</th>' for c in inp.channels)
    rows = []
    for p in inp.campaigns:
        cells = []
        for c in inp.channels:
            x = mt[(mt["campana"] == p) & (mt["canal"] == c)].iloc[0]
            if x["estado"] == "elegido":
                style, note = f"background:{RED};color:#FDFDFD;font-weight:800", "elegida"
            elif x["estado"] == "factible":
                style, note = "background:#FDFDFD;border:1.5px solid #332F2E", "factible"
            else:
                style, note = f"background:#F2F3F0;color:#5E5A58", ", ".join(x["bloqueo"][:3]) + (
                    "…" if len(x["bloqueo"]) > 3 else "")
            cells.append(f'<td style="padding:.55rem .8rem;text-align:center;border-radius:10px;{style}">'
                         f'<div style="font-size:1.1rem">{fmt_num(x["valor"], 3)}</div>'
                         f'<div style="font-size:15px">{escape(note)}</div></td>')
        rows.append(f'<tr><th style="padding:.5rem .8rem;text-align:left">{escape(p)}</th>{"".join(cells)}</tr>')
    st.html(f'<table style="border-collapse:separate;border-spacing:6px;width:100%"><tr><th></th>{head}</tr>'
            f'{"".join(rows)}</table>')
    st.caption("Valor = score de producto × score de canal × valor de negocio. En rojo la opción elegida; con borde, "
               "las opciones posibles; en gris, las bloqueadas con el ID de la regla que lo impide.")

    with st.expander("Perfil completo del cliente", icon=":material/badge:"):
        st.dataframe(pd.DataFrame({"Columna": list(d["perfil"]), "Valor": list(d["perfil"].values())}),
                     hide_index=True, width="stretch", height=420)


# ---------------------------------------------------------------- client card
with tab_c:
    a = res.assignment

    def _picks() -> list[str]:
        out_ = []
        for estado in ("asignado", "sin_accion"):
            ids = a.loc[a["estado"] == estado, "id_cliente"]
            out_ += ids.iloc[:: max(1, len(ids) // 3)].head(3).tolist()
        return out_

    picks = state.memo(run, "picks", _picks)
    if "ficha_input" not in st.session_state and picks:
        st.session_state["ficha_input"] = picks[0]

    def _pick() -> None:
        if st.session_state.get("ficha_pick"):
            st.session_state["ficha_input"] = st.session_state["ficha_pick"]

    estados = dict(zip(a["id_cliente"], a["estado"]))
    c1, c2 = st.columns([1.2, 2], vertical_alignment="bottom")
    cid = c1.text_input("ID del cliente", key="ficha_input")
    c2.selectbox("…o elige un ejemplo", picks, index=None, key="ficha_pick", on_change=_pick,
                 placeholder="Tres con acción y tres sin acción",
                 format_func=lambda x: f"{x} · {'con acción' if estados.get(x) == 'asignado' else 'sin acción'}")
    i = insights.client_index(inp, cid)
    if i is None:
        st.warning(f"No encuentro el cliente '{cid}'.", icon=":material/search_off:")
    else:
        render_card(i)

# ---------------------------------------------------------------- global explanation
with tab_g:
    ui.section_label("Qué reglas excluyen más clientes")
    counts = pd.Series(run.get("impacto", {}).get("por_regla", {}), dtype=float).sort_values()
    if len(counts):
        names = {k: info.get(k, {}).get("nombre", SYSTEM_RULES.get(k, k)) for k in counts.index}
        fig = go.Figure(go.Bar(x=counts.values, y=counts.index, orientation="h",
                               marker_color=highlight_colors(len(counts), len(counts) - 1),
                               customdata=[names[k] for k in counts.index], text=[fmt_num(v) for v in counts.values],
                               textposition="outside",
                               hovertemplate="<b>%{y}</b> · %{customdata}<br>%{x:,.0f} clientes<extra></extra>"))
        fig.update_layout(height=60 + 30 * len(counts), xaxis_title="Clientes afectados (en al menos una campaña o canal)")
        st.plotly_chart(fig, use_container_width=True, config=CHART)

    ui.section_label("Cuánto valor cuesta cada regla")
    st.caption("Valor potencial = lo que sumaría cada cliente con su mejor contacto si no hubiera cupos. Se calcula "
               "apagando una regla a la vez sobre la configuración aplicada.")
    key = f"costs_{run['hash']}"
    if st.button("Calcular costo de cada regla", icon=":material/calculate:", key="btn_costs"):
        with st.spinner("Re-evaluando las reglas…"):
            st.session_state[key] = impact.rule_costs(df, cfg)
    costs = st.session_state.get(key)
    if costs is not None and len(costs):
        top = costs.head(10).iloc[::-1]
        fig = go.Figure(go.Bar(x=top["costo"], y=top["id"], orientation="h",
                               marker_color=highlight_colors(len(top), len(top) - 1), customdata=top["nombre"],
                               text=[f"+{fmt_num(v, 1)}" for v in top["costo"]], textposition="outside",
                               hovertemplate="<b>%{y}</b> · %{customdata}<br>+%{x:,.1f} de valor potencial<extra></extra>"))
        fig.update_layout(height=60 + 34 * len(top), xaxis_title="Valor potencial que se liberaría al apagarla")
        st.plotly_chart(fig, use_container_width=True, config=CHART)
        r0 = costs.iloc[0]
        st.markdown(f"Si apagaras **{r0['id']}** ({r0['nombre']}) el valor potencial elegible subiría "
                    f"**{fmt_num(r0['costo'], 1)}**. Las reglas obligatorias del reto no se pueden apagar en la "
                    "parrilla oficial; el dato sirve para saber dónde negociar umbrales y topes.")

    ui.section_label("Precio de los cupos")
    duals = (res.duals or {}).get("capacity")
    opp = state.memo(run, "opp", lambda: insights.capacity_opportunity(inp, res))
    if not duals:
        st.caption("La línea base no calcula duales: el precio es una **estimación** = cuánto valor aportaría el mejor "
                   "cliente rechazado si hubiera un cupo más. El optimizador MILP lo reemplazará por el precio sombra exacto.")
    cols = st.columns(len(opp))
    for col, o in zip(cols, opp):
        price = duals.get(o["canal"], 0.0) if duals else o["precio_estimado"]
        label = "Precio sombra" if duals else "Precio estimado"
        lines = [f"{fmt_num(o['usado'])} / {fmt_num(o['cupo'])} usados"]
        if o["ultimo_admitido"]:
            lines.append(f"último admitido {o['ultimo_admitido']['id']} ({fmt_num(o['ultimo_admitido']['valor'], 3)})")
        if o["primer_rechazado"]:
            lines.append(f"primer rechazado {o['primer_rechazado']['id']} (+{fmt_num(o['primer_rechazado']['valor'], 3)})")
        with col:
            st.html(ui.kpi_card_html(f"{label} · {o['canal']}", fmt_num(price, 3), icon_name="sell",
                                     emphasis=o["lleno"], delta_text="cupo lleno" if o["lleno"] else "con cupo libre",
                                     delta_vs_baseline=0.0) +
                    f'<div class="claro-meta" style="margin-top:.4rem">{"<br>".join(map(escape, lines))}</div>')
    full = [o for o in opp if o["lleno"] and (duals or o["precio_estimado"] > 0)]
    if full:
        best = max(full, key=lambda o: duals.get(o["canal"], 0) if duals else o["precio_estimado"])
        st.markdown(f"Un cupo adicional de **{best['canal']}** vale ≈ **{fmt_num(duals[best['canal']] if duals else best['precio_estimado'], 3)}** "
                    f"de valor esperado{' (estimado)' if not duals else ''}.")
