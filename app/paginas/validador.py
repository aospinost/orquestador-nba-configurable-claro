import pandas as pd
import streamlit as st

from app.ui import components as ui
from app.ui import state
from app.ui.theme import fmt_num
from engine import validator
from engine.config_store import load_traceability

ui.hero("Validador", "Revisa la parrilla cliente por cliente contra las 16 restricciones obligatorias, con un "
        "verificador independiente del motor.", eyebrow="Decisión", big_numeral="16", numeral_caption="restricciones")

run = state.last_run()
cfg = state.applied()
source = st.radio("Parrilla a validar", ["ultima", "externa"], horizontal=True,
                  format_func={"ultima": "Última corrida", "externa": "Subir una parrilla (CSV)"}.get)

report = None
if source == "ultima":
    if run is None:
        st.info("Aún no hay corrida. Pulsa **Ejecutar orquestador** en la barra lateral.", icon=":material/play_circle:")
        st.stop()
    report = run["output"].validation
    st.caption(f"Corrida del {run['timestamp']:%d/%m/%Y %H:%M} · optimizador {run['optimizer']} · "
               f"configuración {run['hash']}")
else:
    up = st.file_uploader("Parrilla en el formato de los organizadores", type=["csv"],
                          help="Columnas: id_cliente, estado, canal, campana_1, campana_2 (…), razon.")
    if up is None:
        st.caption("Se valida contra la configuración aplicada y la base de clientes en uso.")
        st.stop()
    try:
        ext = pd.read_csv(up, dtype=str, keep_default_na=False)
    except Exception as exc:  # malformed upload: Spanish message, no crash
        st.error(f"No se pudo leer el archivo: {exc}", icon=":material/error:")
        st.stop()
    missing = {"id_cliente", "estado", "canal", "campana_1"} - set(ext.columns)
    if missing:
        st.error("Faltan columnas: " + ", ".join(sorted(missing)), icon=":material/error:")
        st.stop()
    with st.spinner("Validando cliente por cliente…"):
        report = validator.validate(ext, state.clients(cfg), cfg)

summary = report.summary
challenge = summary[summary["id"].isin(load_traceability()["id_reto"])]  # the 16 from the statement
extra = summary[~summary.index.isin(challenge.index)]
ok = int((challenge["violaciones"] == 0).sum())
total = int(report.total)

ui.kpi_row([
    {"label": "Restricciones cumplidas", "value": f"{ok} / {len(challenge)}", "icon_name": "verified",
     "emphasis": ok < len(challenge)},
    {"label": "Clientes con violaciones", "value": fmt_num(report.details["id_cliente"].nunique()),
     "icon_name": "person_alert"},
    {"label": "Violaciones registradas", "value": fmt_num(len(report.details)), "icon_name": "error",
     "delta_text": "La parrilla compite en valor" if total == 0 else "No compite en valor hasta llegar a 0",
     "delta_vs_baseline": 0.0 if total == 0 else -1.0},
])


def tiles(rows: pd.DataFrame) -> None:
    ui.tiles([{"icon_name": "check_circle" if r["violaciones"] == 0 else "cancel", "label": r["id"],
               "sub": "0 violaciones" if r["violaciones"] == 0 else f"{fmt_num(r['violaciones'])} clientes",
               "state": "ok" if r["violaciones"] == 0 else ""} for r in rows.to_dict("records")])


ui.section_label("Las 16 restricciones del reto")
tiles(challenge)
with st.expander("Qué revisa cada una", icon=":material/list_alt:"):
    st.dataframe(challenge.rename(columns={"id": "ID", "nombre": "Restricción", "fuentes": "Se verifica con",
                                           "violaciones": "Clientes"}), hide_index=True, width="stretch")
if len(extra):
    ui.section_label("Controles adicionales")
    tiles(extra)
    st.caption(" · ".join(f"**{r['id']}**: {r['nombre']}" for r in extra.to_dict("records")))

failing = summary[summary["violaciones"] > 0]
if len(failing):
    ui.section_label("Clientes infractores")
    pick = st.selectbox("Restricción", failing["id"].tolist(),
                        format_func=lambda x: f"{x} · {summary.set_index('id').loc[x, 'nombre']}")
    srcs = summary.set_index("id").loc[pick, "fuentes"].split("|")
    det = report.details[report.details["fuente"].isin(srcs)]
    st.dataframe(det.head(200), hide_index=True, width="stretch")
    st.download_button(f"Descargar los {fmt_num(det['id_cliente'].nunique())} clientes ({pick})",
                       det.to_csv(index=False).encode("utf-8"), file_name=f"infractores_{pick}.csv",
                       mime="text/csv", icon=":material/download:", type="primary")
