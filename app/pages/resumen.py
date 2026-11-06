import plotly.graph_objects as go
import streamlit as st

from app.ui import components as ui
from app.ui import state
from app.ui.theme import GRAY, RED, fmt_num, fmt_pct
from engine.metrics import BASELINE

run = state.last_run()

PIPELINE = [
    {"icon_name": "database", "label": "Datos", "sub": "100.000 clientes"},
    {"icon_name": "rule", "label": "Reglas", "sub": "exclusiones y umbrales"},
    {"icon_name": "checklist", "label": "Elegibilidad", "sub": "campaña × canal"},
    {"icon_name": "hub", "label": "Optimizador", "sub": "cupos y valor"},
    {"icon_name": "verified", "label": "Validador", "sub": "16 restricciones"},
    {"icon_name": "table_rows", "label": "Parrilla", "sub": "una fila por cliente", "state": "dark"},
]

if run is None:
    ui.hero("Orquestador NBA · Claro Colombia",
            "Qué ofrecer a cada cliente y por qué canal, con el mayor valor y sin violar ninguna regla. "
            "Negocio cambia todo desde esta consola, sin tocar código.",
            big_numeral="100.000", eyebrow="Next Best Action configurable", numeral_caption="clientes")
    ui.section_label("Cómo decide")
    ui.flow(PIPELINE)
    ui.section_label("Primer paso")
    st.info("Pulsa **Ejecutar orquestador** en la barra lateral para generar la parrilla con la "
            "configuración actual.", icon=":material/play_circle:")
    st.stop()

m = run["metrics"]
ui.hero("Orquestador NBA · Claro Colombia",
        f"Corrida del {run['timestamp']:%d/%m/%Y %H:%M} · optimizador {run['optimizer']} · "
        f"configuración {run['hash']}",
        big_numeral=fmt_num(m["valor_esperado"], 1), eyebrow="Resumen ejecutivo", numeral_caption="valor esperado")

viol = m.get("violaciones", 0)
ui.kpi_row([
    {"label": "Valor esperado", "value": fmt_num(m["valor_esperado"], 1), "icon_name": "paid", "emphasis": True,
     "delta_vs_baseline": m["valor_esperado"] - BASELINE["valor_esperado"], "decimals": 1},
    {"label": "Clientes con acción", "value": fmt_num(m["clientes_con_accion"]), "icon_name": "groups",
     "delta_vs_baseline": m["clientes_con_accion"] - BASELINE["clientes_con_accion"]},
    {"label": "Productos asignados", "value": fmt_num(m["productos_asignados"]), "icon_name": "inventory_2",
     "delta_vs_baseline": m["productos_asignados"] - BASELINE["productos_asignados"]},
    {"label": "Jerarquía", "value": fmt_pct(m["indicador_jerarquia"]), "icon_name": "stacked_bar_chart",
     "delta_vs_baseline": m["indicador_jerarquia"] - BASELINE["indicador_jerarquia"], "decimals": 1},
    {"label": "Violaciones", "value": fmt_num(viol), "icon_name": "verified" if viol == 0 else "error",
     "delta_text": "Cumple las 16 restricciones" if viol == 0 else "Revisar el validador",
     "delta_vs_baseline": 0.0 if viol == 0 else -float(viol)},
])

ui.section_label("Uso de cupo por canal")
cap = m["uso_capacidad"]
chans = list(cap)
used = [cap[c]["usado"] for c in chans]
total = [cap[c]["cupo"] for c in chans]
fig = go.Figure()
fig.add_bar(y=chans, x=total, orientation="h", name="Cupo", marker_color=GRAY, opacity=0.45,
            hovertemplate="%{y}: cupo %{x:,.0f}<extra></extra>")
fig.add_bar(y=chans, x=used, orientation="h", name="Usado",
            marker_color=[RED if u >= t else "#332F2E" for u, t in zip(used, total)],
            text=[f"{fmt_num(u)} / {fmt_num(t)}" for u, t in zip(used, total)], textposition="outside",
            hovertemplate="%{y}: usado %{x:,.0f}<extra></extra>")
fig.update_layout(barmode="overlay", height=300, xaxis_title="Contactos", yaxis=dict(autorange="reversed"))
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
st.caption("En rojo, los canales con el cupo agotado. El detalle completo del resumen llega en la fase 4.")
