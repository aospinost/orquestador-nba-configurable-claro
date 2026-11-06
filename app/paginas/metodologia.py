import streamlit as st

from app.ui import components as ui
from app.ui import state
from app.ui.theme import fmt_num, fmt_pct
from engine import impact, model_registry
from engine.config_store import ROOT

DOC = ROOT / "docs" / "metodologia.md"
WEIGHT_PREFIX = "priorizacion.pesos."
WEIGHT_NAMES = {"score_producto": "modelo", "valor_negocio": "valor de negocio", "jerarquia": "jerarquía"}

ui.hero("Metodología", "El modelo matemático que resuelve la consola, cómo se arma desde la configuración y qué "
        "balance entre jerarquía y valor está activo.", eyebrow="Decisión")

ui.section_label("De los datos a la parrilla")
ui.flow([
    {"icon_name": "database", "label": "Datos", "sub": "scores y perfil"},
    {"icon_name": "rule", "label": "Reglas", "sub": "constantes y exclusiones"},
    {"icon_name": "checklist", "label": "Elegibilidad", "sub": "máscaras con ID"},
    {"icon_name": "hub", "label": "Optimizador", "sub": "valor con cupos"},
    {"icon_name": "verified", "label": "Validador", "sub": "independiente"},
    {"icon_name": "table_rows", "label": "Parrilla", "sub": "con su razón", "state": "dark"},
])

# ---------------------------------------------------------------- hierarchy vs value
cfg = state.applied()
ui.section_label("Balance jerarquía vs. valor (configuración aplicada)")
mode = cfg.param("priorizacion.modo")
weights = {k[len(WEIGHT_PREFIX):]: cfg.param_float(k, 0.0) for k in cfg.params if k.startswith(WEIGHT_PREFIX)}
w_txt = ", ".join(f"{WEIGHT_NAMES.get(n, n)} {fmt_pct(100 * w, 0)}" for n, w in weights.items())
order = " → ".join(cfg.hierarchy())
if mode == "jerarquia_estricta":
    stance = ("**Jerarquía estricta:** a cada cliente se le ofrece primero la campaña de mayor jerarquía para la que "
              "es elegible; el modelo y el valor solo desempatan. Se gana indicador de jerarquía y se puede perder valor.")
else:
    stance = (f"**Ponderado:** el puntaje combina {w_txt}. La jerarquía es una preferencia que cede cuando otra "
              "campaña aporta bastante más.")
last = state.last_run()
hier = f" En la última corrida el indicador de jerarquía fue **{fmt_pct(last['metrics']['indicador_jerarquia'])}**." \
    if last else ""
st.markdown(f"{stance} Orden actual: **{order}**.{hier}")
st.markdown("**Cómo cambiarlo:** *Prioridad y canales* → paso 1 (orden y modo) y paso 2 (pesos). El efecto se ve en el "
            "indicador de jerarquía y en el valor del *Resumen ejecutivo*; el *Simulador* compara ambos modos.")

# ---------------------------------------------------------------- model document
ui.section_label("Modelo")
if DOC.exists():
    st.markdown(DOC.read_text(encoding="utf-8"))
else:
    st.info("Aún no hay documento de metodología (docs/metodologia.md).", icon=":material/description:")

# ---------------------------------------------------------------- symbol table
ui.section_label("Tabla de símbolos (generada desde la configuración)")
if last:
    reg = last["output"].inp.registry
    st.caption(f"Configuración de la última corrida ({last['hash']}).")
else:
    consts, _ = impact.constant_values(state.clients(cfg), cfg)
    reg = model_registry.build(cfg, cfg.active_campaigns, cfg.active_channels, state.clients(cfg), consts)
    st.caption("Configuración aplicada (aún sin corrida).")
frame = reg.frame()
for grupo, g in frame.groupby("grupo", sort=False):
    with st.expander(f"{grupo} · {fmt_num(len(g))}", icon=":material/function:", expanded=grupo == "Conjuntos"):
        for r in g.to_dict("records"):
            c1, c2 = st.columns([1.2, 3.8], vertical_alignment="center")
            c1.latex(r["latex"])
            c2.markdown(f"**{r['significado']}** · {r['valor'] or '—'}  \n"
                        f"<span class='claro-meta'>Fuente: {r['fuente']} · "
                        f"{'editable desde la consola' if r['editable'] else 'variable del modelo'}</span>",
                        unsafe_allow_html=True)
