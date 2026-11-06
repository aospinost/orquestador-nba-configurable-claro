import datetime as dt
import re

import pandas as pd
import streamlit as st

from app.ui import components as ui
from app.ui import panels, state
from app.ui.theme import fmt_num
from engine import data_loader
from engine.config_store import ROOT, load_dictionary

UPLOAD_DIR = ROOT / "data" / "in" / "cargas"

cfg = state.draft()
ss = st.session_state

ui.hero("Datos", "La base de clientes que alimenta las reglas y el modelo. Cualquier columna nueva queda "
        "disponible de inmediato en el constructor de reglas.", eyebrow="Configuración")
panels.validation(("Datos", "Política"))

ui.section_label("Fuente")
c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
c1.html(f'<div class="claro-meta">Base en uso</div><div style="font-weight:700;font-size:1.1rem">'
        f'{cfg.param("datos.ruta")}</div>')
up = c2.file_uploader("Cargar otra base (CSV)", type=["csv"], key=f"upload_{state.rev()}",
                      help="Debe tener una fila por cliente; las columnas de lista van separadas por |.")
if up is not None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w.-]+", "_", up.name)
    dest = UPLOAD_DIR / f"{dt.datetime.now():%Y%m%d-%H%M%S}_{name}"
    dest.write_bytes(up.getvalue())
    cfg.set_param("datos.ruta", dest.relative_to(ROOT).as_posix())
    state.touch()
    st.toast(f"Base cargada: {up.name} (sin aplicar)", icon=":material/upload_file:")
    st.rerun()

try:
    df = state.clients(cfg)
except Exception as exc:  # unreadable upload: say so in Spanish, keep the console alive
    st.error(f"No se pudo leer la base: {exc}", icon=":material/error:")
    panels.impact_preview()
    st.stop()

dictionary = load_dictionary()
report = data_loader.quality_report(df, dictionary)
prof = state.column_profile(cfg)
new_cols = report.loc[report["problema"].str.startswith("columna nueva"), "columna"].tolist()
issues = report[~report["problema"].str.startswith("columna nueva")]

ui.kpi_row([
    {"label": "Clientes", "value": fmt_num(len(df)), "icon_name": "groups"},
    {"label": "Columnas", "value": fmt_num(df.shape[1]), "icon_name": "view_column"},
    {"label": "Columnas de lista", "value": fmt_num(len(data_loader.list_columns(df))), "icon_name": "list"},
    {"label": "Alertas de calidad", "value": fmt_num(len(issues)), "icon_name": "rule_settings",
     "emphasis": len(issues) > 0},
])

if new_cols:
    st.success("**Columnas nuevas detectadas:** " + ", ".join(f"`{c}`" for c in new_cols)
               + ". Ya están disponibles en el constructor de *Reglas*, *Constantes* y como columnas de score de "
                 "campañas o canales.", icon=":material/new_releases:")

ui.section_label("Calidad de datos")
if issues.empty:
    st.html(ui.rule_chip_html("Sin alertas", "pass", "todas las columnas del diccionario están presentes y en rango"))
else:
    st.dataframe(issues.rename(columns={"columna": "Columna", "problema": "Problema", "filas": "Filas",
                                        "ejemplo": "Ejemplo"}), hide_index=True, width="stretch")

ui.section_label("Columnas")
desc = dictionary.set_index("columna")["descripcion"].to_dict()
kind_words = {"numerica": "Numérica", "categoria": "Categoría", "lista": "Lista", "texto": "Texto"}
cols = prof.assign(
    descripcion=prof["columna"].map(desc).fillna("Columna nueva"),
    tipo=prof["tipo"].map(kind_words),
    rango=[(f"{fmt_num(a, 2 if a % 1 else 0)} a {fmt_num(b, 2 if b % 1 else 0)}" if pd.notna(a) and t == "numerica"
            else ", ".join(map(str, v[:12])) + (" …" if len(v) > 12 else ""))
           for a, b, v, t in zip(prof["min"], prof["max"], prof["valores"], state.column_profile(cfg)["tipo"])],
)[["columna", "tipo", "rango", "descripcion"]]
st.dataframe(cols.rename(columns={"columna": "Columna", "tipo": "Tipo", "rango": "Valores", "descripcion": "Descripción"}),
             hide_index=True, width="stretch", height=420)

ui.section_label("Muestra")
st.caption("Primeras 50 filas (la consola nunca dibuja las 100.000 a la vez).")
sample = df.head(50).copy()
for c in data_loader.list_columns(df):
    sample[c] = sample[c].map(lambda s: "|".join(sorted(s)))
st.dataframe(sample, hide_index=True, width="stretch", height=300)

panels.impact_preview()
