import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.ui import components as ui
from app.ui import state
from app.ui.theme import fmt_delta, fmt_num, highlight_colors
from engine import config_store as cs
from engine import insights, scenarios
from engine.config_store import ConfigError
from engine.expressions import ExpressionError

CHART = {"displayModeBar": False}
APPLIED = "aplicada"
ss = st.session_state

ui.hero("Simulador ¿Qué pasa si?", "Compara hasta tres escenarios antes de decidir: cada uno es una configuración "
        "completa que se optimiza con las mismas 16 restricciones.", eyebrow="Decisión")

optimizer = ss.get("optimizer", "greedy")
if not state.optimizers().get(optimizer, {}).get("available"):
    optimizer = next(n for n, o in state.optimizers().items() if o["available"])
demos = scenarios.demo_scenarios()
saved = {s["id"]: s for s in scenarios.list_saved()}

options = {APPLIED: "Configuración aplicada"}
options |= {f"demo:{k}": f"{v['nombre']} (demo)" for k, v in demos.items()}
options |= {f"saved:{k}": f"{v['nombre']} (guardado)" for k, v in saved.items()}


def scenario_config(key: str) -> cs.Config:
    if key == APPLIED:
        return state.applied().copy()
    kind, sid = key.split(":", 1)
    if kind == "demo":
        return scenarios.apply_ops(state.applied(), demos[sid]["ops"])
    return scenarios.load(sid)[0]


ui.section_label("Escenarios")
pick = st.multiselect("Elige hasta 3", list(options), default=[APPLIED], max_selections=3,
                      format_func=options.get, placeholder="Elige escenarios")
for k in pick:
    if k.startswith("demo:"):
        st.caption(f"**{demos[k[5:]]['nombre']}:** {demos[k[5:]]['descripcion']}")
st.caption(f"Se optimiza con **{state.optimizers()[optimizer]['label']}**. La primera corrida de cada escenario "
           "tarda unos segundos; luego queda en caché.")

if st.button("Comparar escenarios", type="primary", icon=":material/compare_arrows:", disabled=not pick):
    results = {}
    with st.status("Optimizando escenarios…", expanded=True) as status:
        for k in pick:
            st.write(f"{options[k]}…")
            try:
                cfg = scenario_config(k)
                errs = cs.validate(cfg, state.columns(cfg))
                if errs:
                    raise ConfigError(errs)
                results[k] = {"cfg": cfg, "out": state.run_config(cfg, optimizer)}
            except (ConfigError, ExpressionError, ValueError) as exc:
                errs = exc.errors if isinstance(exc, ConfigError) else [str(exc)]
                st.error(f"{options[k]}: " + "; ".join(errs))
        status.update(label="Escenarios listos", state="complete", expanded=False)
    ss["sim"] = {"keys": [k for k in pick if k in results], "results": results, "optimizer": optimizer}

sim = ss.get("sim")
if sim and sim["results"]:
    ui.section_label("Resultado")
    named = {options.get(k, k): sim["results"][k]["out"].metrics for k in sim["keys"]}
    table = insights.compare_metrics(named)
    st.dataframe(table.style.format({c: lambda v: fmt_num(v, 1) if isinstance(v, float) else fmt_num(v)
                                     for c in table.columns if c != "Indicador"}), hide_index=True, width="stretch")
    vals = pd.Series({n: mm["valor_esperado"] for n, mm in named.items()})
    best = int(vals.values.argmax())
    base = vals.iloc[0]
    fig = go.Figure(go.Bar(x=vals.index, y=vals.values, marker_color=highlight_colors(len(vals), best),
                           text=[fmt_num(v, 1) + ("" if k == 0 else f" ({fmt_delta(v - base, 1)})")
                                 for k, v in enumerate(vals.values)], textposition="outside"))
    fig.update_layout(height=360, yaxis_title="Valor esperado", title="Valor esperado por escenario")
    st.plotly_chart(fig, use_container_width=True, config=CHART)

    ui.section_label("Qué cambia en la configuración")
    ref = state.applied()
    for k in sim["keys"]:
        if k == APPLIED:
            continue
        d = cs.diff(ref, sim["results"][k]["cfg"])
        with st.expander(f"{options.get(k, k)} · {len(d)} cambio{'s' if len(d) != 1 else ''} frente a la aplicada",
                         icon=":material/difference:"):
            st.dataframe(pd.DataFrame(d).rename(columns={"tabla": "Tabla", "clave": "Elemento", "campo": "Campo",
                                                         "antes": "Antes", "despues": "Después"}),
                         hide_index=True, width="stretch")
            if st.button("Cargar en el borrador", key=f"load_{k}", icon=":material/edit_note:",
                         help="Lleva este escenario a la configuración en edición para aplicarlo desde allí."):
                state.replace_draft(sim["results"][k]["cfg"].copy())
                st.rerun()

# ---------------------------------------------------------------- save / manage
ui.section_label("Guardar el escenario actual")
c1, c2 = st.columns([3, 1.3], vertical_alignment="bottom")
name = c1.text_input("Nombre del escenario", placeholder="Navidad con más cupo",
                     help="Guarda la configuración en edición (borrador) y el optimizador elegido.")
if c2.button("Guardar escenario actual", icon=":material/bookmark_add:", disabled=not name.strip(), width="stretch"):
    sid = scenarios.save(state.draft(), name.strip(), optimizer)
    st.toast(f"Escenario guardado: {name.strip()}", icon=":material/bookmark:")
    st.rerun()
if saved:
    for sid, meta in saved.items():
        r1, r2 = st.columns([5, 1], vertical_alignment="center")
        r1.html(f'<b>{meta["nombre"]}</b> <span class="claro-meta">· {meta["creado"].replace("T", " ")} · '
                f'{meta["optimizador"]} · configuración {meta["hash"]}</span>')
        if r2.button("", icon=":material/delete:", key=f"del_{sid}", help="Eliminar escenario"):
            scenarios.delete(sid)
            st.rerun()
