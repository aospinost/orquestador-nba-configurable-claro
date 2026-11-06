"""Entrypoint: streamlit run app/Inicio.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.ui import components as ui  # noqa: E402
from app.ui import panels  # noqa: E402
from app.ui import state  # noqa: E402
from app.ui.theme import fmt_num, inject_css  # noqa: E402
from engine import config_store  # noqa: E402
from engine.config_store import ConfigError  # noqa: E402
from engine.expressions import ExpressionError  # noqa: E402

st.set_page_config(page_title="Orquestador NBA · Claro", page_icon=":material/hub:", layout="wide",
                   initial_sidebar_state="expanded")
inject_css()
state.init()

P = "paginas/"  # relative to this entrypoint; not "pages/", which Streamlit would auto-load as legacy pages
SECTIONS = {
    "Resultado": [
        st.Page(P + "resumen.py", title="Resumen ejecutivo", icon=":material/space_dashboard:", default=True),
        st.Page(P + "parrilla.py", title="Parrilla", icon=":material/table_rows:"),
        st.Page(P + "explicabilidad.py", title="Explicabilidad", icon=":material/psychology_alt:"),
    ],
    "Configuración": [
        st.Page(P + "datos.py", title="Datos", icon=":material/database:"),
        st.Page(P + "campanas.py", title="Campañas", icon=":material/campaign:"),
        st.Page(P + "reglas.py", title="Reglas", icon=":material/rule:"),
        st.Page(P + "prioridad_canales.py", title="Prioridad y canales", icon=":material/alt_route:"),
        st.Page(P + "politica_contacto.py", title="Política de contacto", icon=":material/contact_phone:"),
    ],
    "Decisión": [
        st.Page(P + "simulador.py", title="Simulador ¿Qué pasa si?", icon=":material/science:"),
        st.Page(P + "validador.py", title="Validador", icon=":material/verified:"),
        st.Page(P + "metodologia.py", title="Metodología", icon=":material/function:"),
    ],
}
STYLE_PAGE = st.Page(P + "_estilo.py", title="Guía de estilo", icon=":material/palette:", url_path="estilo")

# Hidden native menu: the sidebar below draws its own (and leaves the style page out of it).
current = st.navigation([p for ps in SECTIONS.values() for p in ps] + [STYLE_PAGE], position="hidden")

with st.sidebar:
    st.html('<div style="display:flex;align-items:center;gap:.6rem;margin:-.4rem 0 .4rem">'
            f'{ui.icon("hub")}<div style="line-height:1.1"><div style="font-weight:800;font-size:1.25rem">'
            'Orquestador NBA</div><div class="claro-meta">Claro Colombia · Hackatón</div></div></div>')
    for section, pages in SECTIONS.items():
        ui.section_label(section)
        for page in pages:
            st.page_link(page)

    ui.section_label("Corrida")
    cfg = state.draft()
    opts = state.optimizers()
    names = list(opts)
    choice = st.selectbox(
        "Optimizador", names, index=names.index(st.session_state["optimizer"]) if st.session_state["optimizer"]
        in names else 0, format_func=lambda n: opts[n]["label"] + ("" if opts[n]["available"] else " · en construcción"),
        help="Los optimizadores en construcción aparecen deshabilitados para ejecutar.")
    st.session_state["optimizer"] = choice
    available = opts[choice]["available"]
    if st.button("Ejecutar orquestador", type="primary", icon=":material/play_arrow:", width="stretch",
                 disabled=not available, help=None if available else "En construcción"):
        try:
            with st.status("Ejecutando orquestador…", expanded=False) as status:
                st.write("Cargando datos y evaluando reglas…")
                run = state.apply_and_run(choice) if state.pending_changes() else state.execute(choice)
                status.update(label="Corrida lista", state="complete")
            st.toast(f"Corrida lista · valor esperado {fmt_num(run['metrics']['valor_esperado'], 1)}",
                     icon=":material/check_circle:")
        except (ConfigError, ExpressionError) as exc:
            errs = exc.errors if isinstance(exc, ConfigError) else [str(exc)]
            st.error("La configuración tiene errores:\n\n" + "\n".join(f"- {e}" for e in errs))

    last = state.last_run()
    st.html(
        '<div class="claro-meta">'
        f'Configuración: <b>{state.config_version(cfg)}</b><br>'
        f'Huella: <code>{state.draft_hash()}</code><br>'
        + (f'Última corrida: <b>{last["timestamp"]:%d/%m/%Y %H:%M:%S}</b> · {last["optimizer"]}'
           if last else "Sin corridas todavía")
        + "</div>")

    with st.expander("Configuración", icon=":material/settings_backup_restore:"):
        st.download_button("Exportar configuración (.zip)", config_store.export_bundle(cfg),
                           file_name=f"configuracion_{state.draft_hash()}.zip", mime="application/zip",
                           icon=":material/download:", width="stretch")
        bundle = st.file_uploader("Importar configuración (.zip)", type=["zip"], key=f"import_{state.rev()}")
        if bundle is not None:
            try:
                state.replace_draft(config_store.import_bundle(bundle.getvalue()))
                st.rerun()
            except Exception as exc:  # malformed bundle
                st.error(f"No se pudo importar: {exc}")
        if st.button("Restaurar configuración inicial", icon=":material/restart_alt:", width="stretch",
                     help="Carga la configuración de los organizadores en el borrador; se aplica con "
                          "\"Aplicar y re-optimizar\"."):
            state.restore_initial()
            st.rerun()



@st.dialog("Cambios sin aplicar", width="large")
def impact_dialog() -> None:
    panels.impact_preview(key="banner")


changes = state.pending_changes()
if changes:
    c1, c2 = st.columns([4.2, 1.3], vertical_alignment="center")
    with c1:
        ui.banner(f"Tienes {len(changes)} cambio{'s' if len(changes) != 1 else ''} sin aplicar")
    if c2.button("Ver impacto", icon=":material/insights:", width="stretch", key="banner_impact"):
        impact_dialog()

current.run()
