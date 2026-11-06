import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.ui import components as ui
from app.ui import state
from app.ui.theme import BLACK, GRAY, GRAY_MID, RED, fmt_delta, fmt_num, fmt_pct, highlight_colors
from engine import insights
from engine.metrics import BASELINE

CHART = {"displayModeBar": False}
run = state.last_run()

PIPELINE = [
    {"icon_name": "database", "label": "Datos", "sub": "base de clientes"},
    {"icon_name": "rule", "label": "Reglas", "sub": "exclusiones y umbrales"},
    {"icon_name": "checklist", "label": "Elegibilidad", "sub": "campaña × canal"},
    {"icon_name": "hub", "label": "Optimizador", "sub": "cupos y valor"},
    {"icon_name": "verified", "label": "Validador", "sub": "16 restricciones"},
    {"icon_name": "table_rows", "label": "Parrilla", "sub": "una fila por cliente", "state": "dark"},
]

if run is None:
    n = len(state.clients())
    ui.hero("Orquestador NBA · Claro Colombia",
            "Qué ofrecer a cada cliente y por qué canal, con el mayor valor y sin violar ninguna regla. "
            "Negocio cambia todo desde esta consola, sin tocar código.",
            big_numeral=fmt_num(n), eyebrow="Next Best Action configurable", numeral_caption="clientes")
    ui.section_label("Cómo decide")
    ui.flow(PIPELINE)
    ui.section_label("Primer paso")
    st.info("Pulsa **Ejecutar orquestador** en la barra lateral para generar la parrilla con la "
            "configuración actual.", icon=":material/play_circle:")
    st.stop()

out = run["output"]
inp, res, m = out.inp, out.result, run["metrics"]
ui.hero("Orquestador NBA · Claro Colombia",
        f"Corrida del {run['timestamp']:%d/%m/%Y %H:%M} · optimizador {run['optimizer']} · "
        f"configuración {run['hash']}",
        big_numeral=fmt_num(m["valor_esperado"], 1), eyebrow="Resumen ejecutivo", numeral_caption="valor esperado")

viol = m.get("violaciones", 0)
dv = m["valor_esperado"] - BASELINE["valor_esperado"]
secs = sum(out.seconds.values())
ui.kpi_row([
    {"label": "Valor esperado", "value": fmt_num(m["valor_esperado"], 1), "icon_name": "paid", "emphasis": True,
     "delta_vs_baseline": dv, "decimals": 1,
     "delta_text": f"{fmt_delta(dv, 1)} ({fmt_delta(100 * dv / BASELINE['valor_esperado'], 1, ' %')}) vs. línea base"},
    {"label": "Clientes con acción", "value": fmt_num(m["clientes_con_accion"]), "icon_name": "groups",
     "delta_vs_baseline": m["clientes_con_accion"] - BASELINE["clientes_con_accion"]},
    {"label": "Productos", "value": fmt_num(m["productos_asignados"]), "icon_name": "inventory_2",
     "delta_vs_baseline": m["productos_asignados"] - BASELINE["productos_asignados"]},
    {"label": "Jerarquía", "value": fmt_pct(m["indicador_jerarquia"]), "icon_name": "stacked_bar_chart",
     "delta_vs_baseline": m["indicador_jerarquia"] - BASELINE["indicador_jerarquia"], "decimals": 1},
    {"label": "Violaciones", "value": fmt_num(viol), "icon_name": "verified" if viol == 0 else "error",
     "delta_text": "Cumple las 16 restricciones" if viol == 0 else "Revisar el validador",
     "delta_vs_baseline": 0.0 if viol == 0 else -float(viol)},
    {"label": "Tiempo de cómputo", "value": f"{fmt_num(secs, 1)} s", "icon_name": "timer",
     "delta_text": f"optimizador {fmt_num(out.seconds.get('optimizador', 0), 1)} s"},
], per_row=3)
if m.get("bono_reglas_blandas"):
    st.caption(f"Bono de reglas blandas: {fmt_num(m['bono_reglas_blandas'], 1)} (se muestra aparte; no suma al "
               "valor oficial).")
if res.unsupported:
    st.warning("Este optimizador no aplica: " + "; ".join(res.unsupported) + ".", icon=":material/warning:")

# ---------------------------------------------------------------- funnel
ui.section_label(f"De {fmt_num(inp.n)} clientes a la parrilla")
steps = state.memo(run, "funnel", lambda: insights.funnel(inp, res))
labels = [s["etapa"] for s in steps]
fig = go.Figure(go.Funnel(
    y=labels, x=[s["clientes"] for s in steps], textinfo="value+percent initial",
    texttemplate="%{value:,.0f} · %{percentInitial:.1%}",
    marker=dict(color=[GRAY] * (len(steps) - 1) + [RED]),
    customdata=[s["nombre"] for s in steps], connector=dict(line=dict(color=GRAY_MID, width=1)),
    hovertemplate="<b>%{y}</b><br>%{customdata}<br>%{value:,.0f} clientes<extra></extra>"))
fig.update_layout(height=60 + 46 * len(steps), margin=dict(l=8, r=8, t=8, b=8))
st.plotly_chart(fig, use_container_width=True, config=CHART)
st.caption("Cada barra con ID es una regla que deja al cliente sin ninguna campaña. Pasa el cursor para ver su nombre.")

# ---------------------------------------------------------------- flows + capacity
c1, c2 = st.columns([1.25, 1])
with c1:
    ui.section_label("Campaña → canal")
    fl = state.memo(run, "flows", lambda: insights.flows(inp, res))
    if len(fl):
        camps, chans = list(dict.fromkeys(fl["campana"])), list(dict.fromkeys(fl["canal"]))
        nodes = camps + chans
        top = fl.groupby("canal")["clientes"].sum().idxmax()
        fig = go.Figure(go.Sankey(
            arrangement="snap", textfont=dict(size=15, color=BLACK, shadow="none"),
            node=dict(label=nodes, pad=18, thickness=18, color=[BLACK] * len(camps) + [RED if c == top else GRAY_MID
                                                                                       for c in chans]),
            link=dict(source=[nodes.index(x) for x in fl["campana"]], target=[nodes.index(x) for x in fl["canal"]],
                      value=fl["clientes"], color="rgba(189,195,184,.55)",
                      customdata=fl["valor"], hovertemplate="%{source.label} → %{target.label}<br>"
                                                            "%{value:,.0f} productos · valor %{customdata:,.1f}<extra></extra>")))
        fig.update_layout(height=380, margin=dict(l=8, r=8, t=8, b=8), font=dict(size=15))
        st.plotly_chart(fig, use_container_width=True, config=CHART)
with c2:
    ui.section_label("Uso de cupo por canal")
    cap = m["uso_capacidad"]
    chs = list(cap)
    used = [cap[c]["usado"] for c in chs]
    total = [cap[c]["cupo"] for c in chs]
    fig = go.Figure()
    fig.add_bar(y=chs, x=total, orientation="h", name="Cupo", marker_color=GRAY, opacity=0.45,
                hovertemplate="%{y}: cupo %{x:,.0f}<extra></extra>")
    fig.add_bar(y=chs, x=used, orientation="h", name="Usado",
                marker_color=[RED if u >= t else BLACK for u, t in zip(used, total)],
                text=[fmt_pct(100 * u / t if t else 0, 0) for u, t in zip(used, total)], textposition="outside",
                hovertemplate="%{y}: usado %{x:,.0f}<extra></extra>")
    fig.update_layout(barmode="overlay", height=380, xaxis_title="Contactos", yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True, config=CHART)

# ---------------------------------------------------------------- value bars
c1, c2 = st.columns(2)
for col, key, title in ((c1, "valor_por_canal", "Valor por canal"), (c2, "valor_por_campana", "Valor por campaña")):
    with col:
        ui.section_label(title)
        d = pd.Series(m[key]).sort_values(ascending=False)
        fig = go.Figure(go.Bar(x=d.index, y=d.values, marker_color=highlight_colors(len(d), 0),
                               text=[fmt_num(v, 1) for v in d.values], textposition="outside",
                               hovertemplate="%{x}: %{y:,.1f}<extra></extra>"))
        fig.update_layout(height=320, yaxis_title="Valor esperado")
        st.plotly_chart(fig, use_container_width=True, config=CHART)

if m.get("restricciones_negocio"):
    ui.section_label("Restricciones de negocio")
    st.html("".join(ui.rule_chip_html(b["id"], "pass" if b["cumple"] else "hit",
                                      f"{b['nombre']}: {fmt_num(b['valor_actual'], 1)} {b['sentido']} "
                                      f"{fmt_num(b['limite'], 1)}") for b in m["restricciones_negocio"]))

# ---------------------------------------------------------------- run comparison
runs = state.runs()
if len(runs) >= 2:
    ui.section_label("Comparación de corridas")
    named = {f"#{k + 1} · {r['optimizer']} · {r['hash'][:6]}": r["metrics"] for k, r in enumerate(runs[-4:])}
    table = insights.compare_metrics(named)
    st.dataframe(table.style.format({c: lambda v: fmt_num(v, 1) if isinstance(v, float) else fmt_num(v)
                                     for c in table.columns if c != "Indicador"}),
                 hide_index=True, width="stretch")
    a, b = runs[-2], runs[-1]
    diff = state.memo(b, f"diff_{id(a)}", lambda: insights.run_diff(a["output"].result, b["output"].result,
                                                                    a["output"].inp, b["output"].inp))
    st.markdown(f"**Dónde cambia la última corrida frente a la anterior:** "
                f"{fmt_num(diff['clientes_cambiaron_canal'])} clientes cambiaron de canal (o de estado).")
    d = pd.Series(diff["valor_por_canal"]).sort_values()
    fig = go.Figure(go.Bar(x=d.values, y=d.index, orientation="h",
                           marker_color=[RED if v >= 0 else GRAY_MID for v in d.values],
                           text=[fmt_delta(v, 1) for v in d.values], textposition="outside"))
    fig.update_layout(height=60 + 48 * len(d), xaxis_title="Δ valor esperado por canal")
    st.plotly_chart(fig, use_container_width=True, config=CHART)
