"""Hidden visual-QA page (/estilo): palette, type, every component and the chart template."""
import plotly.graph_objects as go
import streamlit as st

from app.ui import components as ui
from app.ui.theme import BLACK, BRAND_FONT, GRAY, PALETTE, RED, fmt_delta, fmt_num, fmt_pct, highlight_colors

ui.hero("Guía de estilo", "Sistema de diseño de la consola, basado en el manual de señalética de Claro.",
        big_numeral="16", eyebrow="Control visual", numeral_caption="px de radio")

ui.section_label("Paleta")
cols = st.columns(len(PALETTE))
for col, (name, hexv) in zip(cols, PALETTE.items()):
    with col:
        st.html(f'<div class="claro-swatch" style="background:{hexv}"></div>'
                f'<div class="claro-swatch-cap">{name}</div><div class="claro-swatch-hex">{hexv}</div>')
st.caption("Rojo, gris, blanco y negro son los colores del manual. El gris #BDC3B8 se usa solo para líneas y "
           "fondos (no cumple contraste AA como texto); el texto secundario usa #5E5A58.")

ui.section_label("Tipografía")
st.html(f'<div style="font-size:15px;color:#5E5A58">Familia activa: <b>{BRAND_FONT}</b> '
        '(Kamerik 105 si sus archivos están en app/static/fonts; si no, Jost)</div>')
st.markdown("# Título 1 · Orquestador NBA")
st.markdown("## Título 2 · Campañas y canales")
st.markdown("### Título 3 · Reglas de elegibilidad")
st.markdown("Texto base de 16 px. Ningún texto de la consola baja de 15 px para que se lea en un proyector.")
ui.section_label("Etiqueta de sección en mayúsculas")

ui.section_label("Números en formato colombiano")
st.markdown(f"`fmt_num(10241.5, 1)` → **{fmt_num(10241.5, 1)}** · `fmt_num(55393)` → **{fmt_num(55393)}** · "
            f"`fmt_pct(99.68)` → **{fmt_pct(99.68)}** · `fmt_delta(-1250)` → **{fmt_delta(-1250)}**")

ui.section_label("Indicadores (kpi_card)")
ui.kpi_row([
    {"label": "Valor esperado", "value": "10.987,3", "icon_name": "paid", "emphasis": True,
     "delta_vs_baseline": 745.8, "decimals": 1},
    {"label": "Clientes con acción", "value": "55.393", "icon_name": "groups", "delta_vs_baseline": 0},
    {"label": "Jerarquía", "value": "97,2 %", "icon_name": "stacked_bar_chart", "delta_vs_baseline": -2.5,
     "decimals": 1},
    {"label": "Violaciones", "value": "0", "icon_name": "verified", "delta_text": "Cumple las 16 restricciones",
     "delta_vs_baseline": 0},
])

ui.section_label("Losas de señalética (tile)")
ui.tiles([
    {"icon_name": "campaign", "label": "Campañas"},
    {"icon_name": "rule", "label": "Reglas"},
    {"icon_name": "support_agent", "label": "Asesor", "sub": "2.500 cupos"},
    {"icon_name": "chat", "label": "WhatsApp", "sub": "15.000 cupos"},
    {"icon_name": "mail", "label": "Correo", "sub": "30.000 cupos"},
    {"icon_name": "sms", "label": "SMS", "sub": "40.000 cupos"},
    {"icon_name": "check_circle", "label": "R01", "sub": "0 violaciones", "state": "ok"},
    {"icon_name": "table_rows", "label": "Parrilla", "state": "dark"},
])

ui.section_label("Flujo con flechas")
ui.flow([{"icon_name": "database", "label": "Datos"}, {"icon_name": "rule", "label": "Reglas"},
         {"icon_name": "hub", "label": "Optimizador"}, {"icon_name": "verified", "label": "Validador"},
         {"icon_name": "table_rows", "label": "Parrilla", "state": "dark"}])

ui.section_label("Encabezados de paso (step_header)")
ui.step_header(1, "El reto", "Paso")
ui.step_header(2, "Las reglas", "Paso")

ui.section_label("Chips de regla y estado")
st.html(ui.rule_chip_html("R01", "on", "Sin venta en mora") + ui.rule_chip_html("R05", "off", "Regla apagada")
        + ui.rule_chip_html("R03", "hit", "equipo de 12 meses") + ui.rule_chip_html("P-UMBRAL-PROD", "pass")
        + "&nbsp;&nbsp;" + ui.status_badge_html("asignado") + "&nbsp;" + ui.status_badge_html("sin_accion"))

ui.section_label("Aviso de cambios sin aplicar")
ui.banner("Tienes 3 cambios sin aplicar")

ui.section_label("Botones y controles")
c1, c2, c3, c4 = st.columns(4)
c1.button("Ejecutar orquestador", type="primary", icon=":material/play_arrow:", key="s1")
c2.button("Guardar escenario", icon=":material/bookmark:", key="s2")
c3.toggle("Regla activa", value=True, key="s3")
c4.selectbox("Optimizador", ["Línea base codiciosa", "Optimización MILP"], key="s4")
st.slider("Umbral de score de producto", 0.0, 1.0, 0.35, 0.01, key="s5")

ui.section_label("Plantilla de gráficos \"claro\"")
g1, g2 = st.columns(2)
with g1:
    camps = ["C-VCH", "C-TER", "C-OTT"]
    fig = go.Figure(go.Bar(x=camps, y=[4210.4, 3987.2, 2043.9], marker_color=highlight_colors(3, 0),
                           text=[fmt_num(v, 1) for v in (4210.4, 3987.2, 2043.9)], textposition="outside"))
    fig.update_layout(title="Valor por campaña", height=340, yaxis_title="Valor esperado")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
with g2:
    x = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    fig = go.Figure()
    fig.add_scatter(x=x, y=[11250, 10870, 10241.5, 9310, 8120, 6900], name="Valor", mode="lines+markers",
                    line=dict(color=RED, width=4))
    fig.add_scatter(x=x, y=[12010, 11400, 10500, 9600, 8400, 7200], name="Potencial", mode="lines",
                    line=dict(color=BLACK, width=2, dash="dot"))
    fig.add_vline(x=0.35, line_color=GRAY, line_width=2)
    fig.update_layout(title="Valor según el umbral de producto", height=340, xaxis_title="Umbral",
                      yaxis_title="Valor esperado")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
