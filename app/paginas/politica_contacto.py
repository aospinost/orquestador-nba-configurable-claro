import streamlit as st

from app.ui import components as ui
from app.ui import panels, state
from app.ui.theme import fmt_num, fmt_pct
from engine import config_store as cs
from engine.explain import rule_sentence
from engine.rules import SYS_WEEKLY_CAP

cfg = state.draft()
rev = state.rev()
df = state.clients(cfg)
n = len(df)
summary = state.impact_summary(cfg)
per_rule = summary.get("por_regla", {})

ui.hero("Política de contacto", "Cuántas veces y por cuántos canales se puede contactar a un cliente. Cada tope "
        "muestra a cuántos clientes afecta antes de aplicarlo.", eyebrow="Configuración")
panels.validation(("Política", "Parámetro 'politica_contacto", "Regla"))


def counter(value: int, text: str) -> None:
    st.html(f'<div class="claro-kpi" style="padding:.8rem 1rem"><div class="lbl">Clientes afectados</div>'
            f'<div class="val" style="font-size:2rem">{fmt_num(value)}</div>'
            f'<div class="claro-meta">{fmt_pct(100 * value / n if n else 0)} · {text}</div></div>')


# ---------------------------------------------------------------- weekly cap
ui.step_header(1, "Tope semanal de contactos", "Contando los ya recibidos")
week_col = cfg.param("politica_contacto.columna_contactos_semana")
c1, c2, c3 = st.columns([1.3, 1.6, 1.6], vertical_alignment="center")
cap = c1.number_input("Máximo de contactos por semana", 0, 50, cfg.param_int("politica_contacto.max_contactos_semana", 0),
                      key=f"cap_{rev}")
num_cols = state.column_profile(cfg).query("tipo == 'numerica'")["columna"].tolist()
col = c2.selectbox("Columna con los contactos de la semana", num_cols,
                   index=num_cols.index(week_col) if week_col in num_cols else 0, key=f"wcol_{rev}")
with c3:
    counter(per_rule.get(SYS_WEEKLY_CAP, 0), f"ya tienen {cap} o más contactos esta semana ({SYS_WEEKLY_CAP})")
if cap != cfg.param_int("politica_contacto.max_contactos_semana") or col != week_col:
    cfg.set_param("politica_contacto.max_contactos_semana", int(cap))
    cfg.set_param("politica_contacto.columna_contactos_semana", col)
    st.rerun()

# ---------------------------------------------------------------- channels per client
ui.step_header(2, "Canales por cliente en cada corrida")
k = cfg.param_int("politica_contacto.canales_por_cliente", 1)
c1, c2 = st.columns([1.3, 3.2], vertical_alignment="center")
newk = c1.number_input("Canales por cliente", 1, max(len(cfg.channels), 1), k, key=f"k_{rev}")
if col in df.columns:
    room = (cap - df[col].fillna(0)).clip(lower=0)
    limited = int(((room > 0) & (room < newk)).sum())
    with c2:
        counter(limited, f"no pueden recibir {newk} contactos porque el tope semanal no se lo permite")
if newk != k:
    cfg.set_param("politica_contacto.canales_por_cliente", int(newk))
    st.rerun()
if newk > 1:
    st.info("Con más de un canal por cliente la parrilla lista los canales separados por | en la columna *canal*.",
            icon=":material/info:")

# ---------------------------------------------------------------- channel caps (rules)
ui.step_header(3, "Topes por canal", "Por ejemplo, llamadas por un canal en el mes")
st.caption("Son las reglas de canal que limitan por un número (≥, >, ≤, <). Cambiar el número aquí cambia la "
           "regla; para crear un tope nuevo usa *Reglas*.")
caps = [r for r in cfg.rules if r.tipo == "canal" and r.accion == "excluir" and r.condicion.operador in ("<", "<=", ">", ">=")]
if not caps:
    st.caption("No hay reglas de canal con tope numérico.")
for r in caps:
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([3.6, 1.2, 0.9, 1.9], vertical_alignment="center")
        c1.html(f'<div>{ui.rule_chip_html(r.id, "on" if r.activa else "off")}<b>{r.nombre}</b></div>'
                f'<div class="claro-meta">{rule_sentence(r)}</div>')
        try:
            cur = float(r.condicion.valor.replace(",", "."))
        except ValueError:
            cur = 0.0
        v = c2.number_input("Tope", value=int(cur) if cur.is_integer() else cur, key=f"rv_{r.id}_{rev}")
        on = c3.toggle("Activa", value=r.activa, key=f"ron_{r.id}_{rev}")
        with c4:
            counter(per_rule.get(r.id, 0) if r.activa else 0, "quedan sin ese canal")
        new_v = f"{v:g}" if isinstance(v, float) else str(v)
        if new_v != r.condicion.valor or on != r.activa:
            t = cfg.tables["reglas"]
            t.loc[t["id"] == r.id, "valor"] = new_v
            t.loc[t["id"] == r.id, "activa"] = "1" if on else "0"
            st.rerun()

panels.impact_preview()
