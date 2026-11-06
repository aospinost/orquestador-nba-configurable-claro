import streamlit as st

from app.ui import builders, panels, state
from app.ui import components as ui
from app.ui.theme import fmt_num
from engine import config_store as cs
from engine.explain import rule_sentence, scope_words
from engine import rules as R
from engine.rules import SYSTEM_RULES

cfg = state.draft()
ss = st.session_state

ui.hero("Reglas", "Quién puede recibir qué y por dónde. Cada regla se lee como una frase y se aplica sin tocar "
        "el código.", eyebrow="Configuración")
panels.validation(("Regla", "Constante", "Restricción"))

draft_summary = state.impact_summary(cfg)
last = state.last_run()
counts = (last or {}).get("impacto", {}).get("por_regla") if last else None
counts_label = "en la última corrida" if counts is not None else "estimado con la configuración en edición"
counts = counts if counts is not None else draft_summary.get("por_regla", {})

tab_r, tab_k, tab_b, tab_s = st.tabs([":material/rule: Reglas", ":material/function: Constantes derivadas",
                                       ":material/balance: Restricciones de negocio",
                                       ":material/settings: Reglas del sistema"])

# ---------------------------------------------------------------- rules
with tab_r:
    rules = {r.id: r for r in cfg.rules}
    editing_id = ss.get("rule_edit")
    editing = rules.get(editing_id)
    with st.container(border=True):
        ui.section_label(f"Editando {editing.id}" if editing else "Nueva regla")
        row = builders.rule_builder(cfg, editing)
        if editing and st.button("Cancelar edición", icon=":material/close:", key="rule_cancel"):
            ss.pop("rule_edit", None)
            st.rerun()
        if row:
            cs.upsert_row(cfg, "reglas", row)
            ss.pop("rule_edit", None)
            state.touch()
            st.toast(f"Regla {row['id']} {'actualizada' if editing else 'agregada'} (sin aplicar)",
                     icon=":material/rule:")
            st.rerun()

    ui.section_label(f"Reglas configuradas · {len(rules)}")
    st.caption(f"El número de clientes afectados es {counts_label}.")

    def _toggle(rid: str, key: str) -> None:
        t = cfg.tables["reglas"]
        t.loc[t["id"] == rid, "activa"] = "1" if ss[key] else "0"

    for r in rules.values():
        with st.container(border=True):
            c0, c1, c2, c3 = st.columns([0.7, 5.2, 1.4, 2.1], vertical_alignment="center")
            key = f"rule_on_{r.id}_{state.rev()}"
            c0.toggle(r.id, value=r.activa, key=key, on_change=_toggle, args=(r.id, key), label_visibility="collapsed")
            chip = ui.rule_chip_html(r.id, "on" if r.activa else "off")
            action = {"excluir": "Exclusión", "bonificar": "Bonificación", "penalizar": "Penalización"}.get(r.accion)
            c1.html(f'<div>{chip}<b>{r.nombre}</b></div><div class="claro-meta">{rule_sentence(r)} · '
                    f'{action} · alcance: {scope_words(r)}</div>')
            n = counts.get(r.id)
            c2.html(f'<div style="text-align:right"><div style="font-size:1.5rem;font-weight:800">'
                    f'{fmt_num(n) if n is not None and r.activa else "—"}</div><div class="claro-meta">clientes</div></div>')
            b1, b2, b3 = c3.columns(3)
            if b1.button("", icon=":material/edit:", key=f"ed_{r.id}", help="Editar"):
                ss["rule_edit"] = r.id
                st.rerun()
            if b2.button("", icon=":material/content_copy:", key=f"dup_{r.id}", help="Duplicar (queda apagada)"):
                new_id = cs.next_id(list(rules), "R")
                cs.upsert_row(cfg, "reglas", {**cfg.tables["reglas"].set_index("id").loc[r.id].to_dict(),
                                              "id": new_id, "nombre": r.nombre + " (copia)", "activa": "0"})
                ss["rule_edit"] = new_id
                state.touch()
                st.rerun()
            with b3.popover("", icon=":material/delete:", help="Eliminar"):
                st.write(f"¿Eliminar **{r.id}**? Para dejar de aplicarla sin perderla, apágala.")
                if st.button("Eliminar", type="primary", key=f"del_{r.id}"):
                    cs.delete_row(cfg, "reglas", r.id)
                    ss.pop("rule_edit", None)
                    state.touch()
                    st.rerun()

# ---------------------------------------------------------------- derived constants
with tab_k:
    st.markdown("Las **constantes derivadas** son los indicadores del modelo (p. ej. *TER_i = 1 si la calificación "
                "es E, A o B*). Se definen con condiciones y luego cualquier regla o restricción puede usarlas.")
    consts = {k.id: k for k in cfg.constants}
    editing = consts.get(ss.get("const_edit"))
    with st.container(border=True):
        ui.section_label(f"Editando {editing.id}" if editing else "Nueva constante")
        rows = builders.constant_builder(cfg, editing)
        if editing and st.button("Cancelar edición", icon=":material/close:", key="const_cancel"):
            ss.pop("const_edit", None)
            st.rerun()
        if rows:
            cs.replace_constant(cfg, rows[0]["id"], rows, old_id=editing.id if editing else None)
            ss.pop("const_edit", None)
            state.touch()
            st.rerun()
    shares = draft_summary.get("constantes", {})
    if not consts:
        st.caption("Aún no hay constantes derivadas. La configuración inicial de los organizadores no las usa.")
    used_by = {}
    for r in cfg.rules:
        used_by.setdefault(r.condicion.atributo, []).append(r.id)
    for k in consts.values():
        with st.container(border=True):
            c1, c2, c3 = st.columns([6, 1.6, 1.4], vertical_alignment="center")
            share = shares.get(k.id)
            share_txt = ("" if share is None else
                         f" · vale 1 en el {fmt_num(100 * share, 1)} % de los casos" if k.tipo == "binaria" else
                         f" · promedio {fmt_num(share, 2)}")
            refs = used_by.get(k.id, [])
            c1.html(f'<div>{ui.rule_chip_html(k.id, "on" if k.activa else "off")}<b>{k.nombre}</b></div>'
                    f'<div class="claro-meta">{builders.constant_sentence(k)}{share_txt}'
                    f'{" · usada por " + ", ".join(refs) if refs else ""}</div>')
            if c2.button("Editar", icon=":material/edit:", key=f"ked_{k.id}"):
                ss["const_edit"] = k.id
                st.rerun()
            with c3.popover("", icon=":material/delete:", help="Eliminar"):
                if refs:
                    st.warning(f"La usan las reglas {', '.join(refs)}. Cámbialas antes de eliminarla.")
                elif st.button("Eliminar", type="primary", key=f"kdel_{k.id}"):
                    cs.delete_row(cfg, "constantes", k.id)
                    state.touch()
                    st.rerun()

# ---------------------------------------------------------------- business constraints
with tab_b:
    st.markdown("Cuotas sobre la parrilla completa, por ejemplo *como mínimo 5.000 contactos de una campaña* o "
                "*como máximo 30 % de un canal para cierta campaña*. **Las aplica el optimizador MILP**; la línea base las ignora "
                "y solo reporta si se cumplen.")
    bcs = {b.id: b for b in cfg.business_constraints}
    editing = bcs.get(ss.get("bc_edit"))
    with st.container(border=True):
        ui.section_label(f"Editando {editing.id}" if editing else "Nueva restricción")
        row = builders.constraint_builder(cfg, editing)
        if row:
            cs.upsert_row(cfg, "restricciones", row)
            ss.pop("bc_edit", None)
            state.touch()
            st.rerun()
    status = {b["id"]: b for b in ((last or {}).get("metrics", {}).get("restricciones_negocio", []))}
    for b in bcs.values():
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([5.2, 1.8, 1.2, 1.2], vertical_alignment="center")
            c1.html(f'<div>{ui.rule_chip_html(b.id, "on" if b.activa else "off")}<b>{b.nombre}</b></div>'
                    f'<div class="claro-meta">{builders.constraint_sentence(b)}</div>')
            s = status.get(b.id)
            if s:
                c2.html(ui.rule_chip_html("Cumple" if s["cumple"] else "No cumple", "pass" if s["cumple"] else "hit",
                                          fmt_num(s["valor_actual"], 1)))
            else:
                c2.caption("Sin corrida")
            if c3.button("Editar", icon=":material/edit:", key=f"bed_{b.id}"):
                ss["bc_edit"] = b.id
                st.rerun()
            if c4.button("", icon=":material/delete:", key=f"bdel_{b.id}", help="Eliminar"):
                cs.delete_row(cfg, "restricciones", b.id)
                state.touch()
                st.rerun()

# ---------------------------------------------------------------- system rules
with tab_s:
    st.markdown("Estas reglas salen de los **parámetros** y la estructura de campañas y canales; se editan en "
                "*Prioridad y canales* y *Política de contacto*. Tienen ID propio para citarlas en cada razón.")
    where = {R.SYS_PRODUCT_THRESHOLD: "Prioridad y canales → umbral de producto",
             R.SYS_CHANNEL_THRESHOLD: "Prioridad y canales → umbral de canal",
             R.SYS_WEEKLY_CAP: "Política de contacto → tope semanal",
             R.SYS_ALLOWED_CHANNEL: "Campañas → canales permitidos",
             R.SYS_AUTHORIZATION: "Prioridad y canales → columna de autorización del canal",
             R.SYS_CHANNELS_PER_CLIENT: "Política de contacto → canales por cliente",
             R.SYS_MAX_PRODUCTS: "Prioridad y canales → productos por contacto",
             R.SYS_CAPACITY: "Prioridad y canales → cupo"}
    for rid, name in SYSTEM_RULES.items():
        n = counts.get(rid)
        c1, c2 = st.columns([6, 1.5], vertical_alignment="center")
        c1.html(f'<div>{ui.rule_chip_html(rid, "on")}<b>{name}</b></div><div class="claro-meta">'
                f'Se edita en: {where.get(rid, "")}</div>')
        c2.html(f'<div style="text-align:right;font-weight:800;font-size:1.3rem">{fmt_num(n) if n is not None else ""}'
                f'</div>')

panels.impact_preview()
