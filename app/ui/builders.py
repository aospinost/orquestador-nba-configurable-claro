"""No-code editors: rules, derived constants and business constraints.

Each builder only edits the draft config through config_store helpers; evaluation happens in engine/.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.ui import components as ui
from app.ui import state
from app.ui.theme import fmt_num, fmt_pct
from engine import config_store as cs
from engine.config_store import Condition, Rule
from engine.explain import OPERATOR_WORDS, rule_sentence

ACTIONS = {"excluir": "Excluir", "bonificar": "Bonificar", "penalizar": "Penalizar"}
SCOPES = {  # option -> (tipo, alcance_nivel, label)
    "todas_campanas": ("elegibilidad", "global", "todas las campañas"),
    "campana": ("elegibilidad", "campana", "las campañas…"),
    "producto": ("elegibilidad", "producto", "los productos…"),
    "objetivo": ("elegibilidad", "objetivo", "los objetivos…"),
    "todos_canales": ("canal", "global", "todos los canales"),
    "canal": ("canal", "canal", "los canales…"),
}
OPS_BY_KIND = {
    "numerica": ["==", "!=", "<", "<=", ">", ">=", "en", "no_en"],
    "categoria": ["en", "no_en", "==", "!=", "contiene"],
    "lista": ["contiene", "no_en", "en", "=="],
    "texto": ["==", "!=", "contiene", "en", "no_en"],
    "constante": ["==", "!=", "<", "<=", ">", ">="],
}


def _num_str(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def _scope_option(r: Rule | None) -> str:
    if r is None:
        return "campana"
    if r.alcance_nivel == "global":
        return "todos_canales" if r.tipo == "canal" else "todas_campanas"
    return r.alcance_nivel


def _attributes(cfg: cs.Config) -> tuple[list[str], dict[str, str]]:
    """Attribute options (data columns + derived constants) and their kind."""
    prof = state.column_profile(cfg)
    id_col = cfg.param("datos.columna_id")
    kinds = {r["columna"]: r["tipo"] for r in prof.to_dict("records") if r["columna"] != id_col}
    for k in cfg.constants:
        kinds[k.id] = "constante"
    return list(kinds), kinds


def _value_widget(cfg: cs.Config, attr: str, kind: str, op: str, current: str, key: str,
                  per_campaign: bool) -> str:
    """Input that adapts to the attribute's type. Returns the config ``valor`` string."""
    prof = state.column_profile(cfg).set_index("columna")
    cur = cs.split_list(current)
    multi = op in ("en", "no_en") or (kind == "lista" and op == "contiene")
    if kind == "lista":
        opts = list(prof.loc[attr, "valores"]) + ([cs.PRODUCT_PLACEHOLDER] if per_campaign else [])
        opts += [v for v in cur if v not in opts]
        sel = st.multiselect("Valor", opts, default=[v for v in cur if v in opts], key=key, placeholder="Elige uno o varios",
                             format_func=lambda v: "$producto (el de la campaña)" if v == cs.PRODUCT_PLACEHOLDER else v,
                             help="$producto toma el producto de la campaña evaluada.")
        return "|".join(sel)
    if kind == "categoria":
        opts = list(prof.loc[attr, "valores"])
        opts += [v for v in cur if v not in opts]
        if multi:
            return "|".join(st.multiselect("Valores", opts, default=[v for v in cur if v in opts], key=key, placeholder="Elige uno o varios"))
        if op == "contiene":
            return st.text_input("Texto", value=current, key=key)
        idx = opts.index(cur[0]) if cur and cur[0] in opts else 0
        return st.selectbox("Valor", opts, index=idx, key=key)
    if kind in ("numerica", "constante"):
        few = list(prof.loc[attr, "valores"]) if kind == "numerica" else [0, 1]
        if multi:
            if few:
                opts = [_num_str(v) for v in few]
                return "|".join(st.multiselect("Valores", opts, default=[v for v in cur if v in opts], key=key, placeholder="Elige uno o varios"))
            return st.text_input("Valores separados por |", value=current, key=key)
        if few and len(few) <= 2:
            opts = [_num_str(v) for v in few]
            idx = opts.index(cur[0]) if cur and cur[0] in opts else len(opts) - 1
            return st.selectbox("Valor", opts, index=idx, key=key)
        try:
            v0 = float(cur[0].replace(",", ".")) if cur else 0.0
        except ValueError:
            v0 = 0.0
        is_int = kind == "numerica" and all(float(x).is_integer() for x in
                                            [prof.loc[attr, "min"] or 0, prof.loc[attr, "max"] or 0, v0])
        if is_int:
            return _num_str(st.number_input("Valor", value=int(v0), step=1, key=key))
        return _num_str(st.number_input("Valor", value=float(v0), step=0.01, format="%.4g", key=key))
    return st.text_input("Valor (para listas use |)", value=current, key=key)


@st.cache_data(show_spinner=False, max_entries=64)
def _reach(cfg_hash: str, rule_key: tuple, _cfg: cs.Config, _rule: Rule) -> tuple[int, str | None]:
    from engine import impact
    return impact.rule_reach(state.clients(_cfg), _cfg, _rule)


# ---------------------------------------------------------------- rules
def rule_builder(cfg: cs.Config, editing: Rule | None) -> dict | None:
    """Sentence-like editor. Returns the row to save when the user clicks the save button."""
    k = f"rb_{editing.id if editing else 'nueva'}_{state.rev()}"
    camps, chans = cfg.campaigns, cfg.channels
    c1, c2, c3 = st.columns([1.1, 1.5, 2.4], vertical_alignment="bottom")
    action = c1.selectbox("Acción", list(ACTIONS), format_func=ACTIONS.get, key=f"{k}_acc",
                          index=list(ACTIONS).index(editing.accion) if editing and editing.accion in ACTIONS else 0)
    sc = _scope_option(editing)
    scope = c2.selectbox("A", list(SCOPES), format_func=lambda s: SCOPES[s][2], key=f"{k}_sc",
                         index=list(SCOPES).index(sc) if sc in SCOPES else 1)
    tipo, nivel, _ = SCOPES[scope]
    options = {"campana": [c.id for c in camps], "producto": sorted({c.producto for c in camps}),
               "objetivo": sorted({c.objetivo for c in camps}), "canal": [c.id for c in chans]}.get(nivel)
    values: list[str] = []
    if options is not None:
        cur = [v for v in (editing.alcance_valores if editing and _scope_option(editing) == scope else []) if v in options]
        names = {c.id: f"{c.id} · {c.nombre}" for c in camps + chans}
        values = c3.multiselect("Cuáles", options, default=cur, key=f"{k}_vals", format_func=lambda v: names.get(v, v),
                                placeholder="Elige una o varias")
    else:
        c3.markdown("&nbsp;")

    attrs, kinds = _attributes(cfg)
    d1, d2, d3 = st.columns([2, 1.3, 2.2], vertical_alignment="bottom")
    a0 = editing.condicion.atributo if editing and editing.condicion.atributo in attrs else attrs[0]
    attr = d1.selectbox("Cuando", attrs, index=attrs.index(a0), key=f"{k}_attr",
                        format_func=lambda a: f"{a} (constante)" if kinds[a] == "constante" else a)
    ops = OPS_BY_KIND[kinds[attr]]
    o0 = editing.condicion.operador if editing and editing.condicion.operador in ops else ops[0]
    op = d2.selectbox("Operador", ops, index=ops.index(o0), key=f"{k}_op", format_func=lambda o: OPERATOR_WORDS[o])
    with d3:
        valor = _value_widget(cfg, attr, kinds[attr], op, editing.condicion.valor if editing else "",
                              f"{k}_val_{attr}_{op}", per_campaign=tipo == "elegibilidad")

    peso = 0.0
    e1, e2, e3 = st.columns([1.2, 3.2, 1], vertical_alignment="bottom")
    if action != "excluir":
        peso = e1.number_input("Peso en el objetivo", 0.0, 10.0, float(editing.peso if editing else 0.05), 0.01,
                               key=f"{k}_peso", help="Se suma (bonificar) o resta (penalizar) al puntaje; "
                                                     "no cambia la métrica oficial de valor.")
    rid = editing.id if editing else cs.next_id([r.id for r in cfg.rules], "R")
    draft_rule = Rule(rid, "", tipo, nivel, values, Condition(attr, op, valor), action, peso, True)
    sentence = rule_sentence(draft_rule)
    name = e2.text_input("Nombre para negocio", value=editing.nombre if editing else "", key=f"{k}_name",
                         placeholder=sentence)
    active = e3.toggle("Activa", value=editing.activa if editing else True, key=f"{k}_on")

    reach, err = _reach(cs.config_hash(cfg), (tipo, nivel, tuple(values), attr, op, valor), cfg, draft_rule)
    n = len(state.clients(cfg))
    if err:
        st.error(err, icon=":material/error:")
    elif options is not None and not values:
        st.info("Elige a qué " + {"campana": "campañas", "producto": "productos", "objetivo": "objetivos",
                                  "canal": "canales"}[nivel] + " aplica la regla.", icon=":material/info:")
    else:
        st.html(f'<div class="claro-banner" style="background:#FDFDFD;border-color:#BDC3B8">'
                f'{ui.icon("groups")}<span><b>{rid}</b> · {sentence}. Esta regla afecta a '
                f'<b>{fmt_num(reach)} clientes</b> ({fmt_pct(100 * reach / n if n else 0)}).</span></div>')

    label = "Guardar cambios" if editing else "Agregar regla"
    disabled = bool(err) or (options is not None and not values) or (not valor and op != "==")
    if st.button(label, type="primary", icon=":material/save:", key=f"{k}_save", disabled=disabled):
        return {"id": rid, "nombre": name or sentence, "tipo": tipo, "alcance_nivel": nivel,
                "alcance_valores": "|".join(values), "atributo": attr, "operador": op, "valor": valor,
                "accion": action, "peso": _num_str(peso) if action != "excluir" else "", "activa": "1" if active else "0"}
    return None


# ---------------------------------------------------------------- derived constants
def constant_sentence(k: cs.DerivedConstant) -> str:
    if k.tipo == "numerica":
        return " + ".join(f"{fmt_num(cs.to_float(c.valor, 1.0), 2)} × {c.atributo}" for c in k.condiciones)
    parts = []
    for i, c in enumerate(k.condiciones):
        txt = f"{c.atributo} {OPERATOR_WORDS.get(c.operador, c.operador)} " + (
            "el producto de la campaña" if c.valor == cs.PRODUCT_PLACEHOLDER else ", ".join(cs.split_list(c.valor)))
        parts.append(txt if i == 0 else f"{c.conector} {txt}")
    return "1 si " + " ".join(parts)


def constant_builder(cfg: cs.Config, editing: cs.DerivedConstant | None) -> list[dict] | None:
    k = f"kb_{editing.id if editing else 'nueva'}_{state.rev()}"
    c1, c2, c3, c4 = st.columns([1, 2.2, 1.2, 1.8])
    cid = c1.text_input("Símbolo", value=editing.id if editing else "", key=f"{k}_id", placeholder="TER_i",
                        help="Identificador que usan las reglas, p. ej. TER_i.")
    nombre = c2.text_input("Nombre para negocio", value=editing.nombre if editing else "", key=f"{k}_nom")
    tipo = c3.selectbox("Tipo", cs.CONSTANT_TYPES, key=f"{k}_tipo",
                        index=cs.CONSTANT_TYPES.index(editing.tipo) if editing and editing.tipo in cs.CONSTANT_TYPES else 0,
                        format_func={"binaria": "Binaria (0/1)", "numerica": "Numérica (suma ponderada)"}.get)
    per = c4.selectbox("Nivel", ["cliente", "cliente_campana"], key=f"{k}_niv",
                       index=1 if editing and (editing.por_campana or editing.nivel == "cliente_campana") else 0,
                       format_func={"cliente": "Por cliente", "cliente_campana": "Por cliente y campaña ($producto)"}.get)
    attrs, kinds = _attributes(cfg)
    attrs = [a for a in attrs if a != (editing.id if editing else None)]
    rows = [{"atributo": c.atributo, "operador": c.operador, "valor": c.valor, "conector": c.conector}
            for c in (editing.condiciones if editing else [])] or [
        {"atributo": attrs[0], "operador": "==", "valor": "", "conector": "Y"}]
    if tipo == "numerica":
        st.caption("Cada fila suma **peso × atributo**. Ejemplo: 1 × columna_a + 1 × columna_b cuenta cuántas valen 1.")
        cfg_cols = {"atributo": st.column_config.SelectboxColumn("Atributo", options=attrs, required=True),
                    "valor": st.column_config.TextColumn("Peso", default="1")}
        order = ["atributo", "valor"]
    else:
        st.caption("Condiciones unidas con **Y** / **O** (Y se evalúa primero). El conector de una fila la une con "
                   "la anterior. En el valor, varias opciones se separan con | y **$producto** es el de la campaña.")
        cfg_cols = {"atributo": st.column_config.SelectboxColumn("Atributo", options=attrs, required=True),
                    "operador": st.column_config.SelectboxColumn("Operador", options=cs.OPERATORS, required=True,
                                                                 default="=="),
                    "valor": st.column_config.TextColumn("Valor"),
                    "conector": st.column_config.SelectboxColumn("Conector", options=cs.CONNECTORS, default="Y")}
        order = ["conector", "atributo", "operador", "valor"]
    edited = st.data_editor(pd.DataFrame(rows), column_config=cfg_cols, column_order=order, num_rows="dynamic",
                            hide_index=True, width="stretch", key=f"{k}_rows_{tipo}")
    active = st.toggle("Activa", value=editing.activa if editing else True, key=f"{k}_on")
    edited = edited.dropna(subset=["atributo"]).fillna("")
    out = [{"id": cid.strip(), "nombre": nombre or cid, "tipo": tipo, "nivel": per,
            "por_campana": "1" if per == "cliente_campana" else "0", "orden": str(i + 1), "atributo": r["atributo"],
            "operador": r.get("operador", "") if tipo == "binaria" else "", "valor": r.get("valor", ""),
            "conector": r.get("conector", "Y") or "Y", "activa": "1" if active else "0"}
           for i, r in enumerate(edited.to_dict("records"))]
    taken = {x.id for x in cfg.constants} - ({editing.id} if editing else set())
    problem = ("Escribe el símbolo." if not cid.strip() else
               "Ese símbolo ya existe." if cid.strip() in taken else
               "Ese símbolo es una columna de la base." if cid.strip() in state.columns(cfg) else
               "Agrega al menos una condición." if not out else "")
    if problem:
        st.caption(f":red[{problem}]")
    if st.button("Guardar constante" if editing else "Agregar constante", type="primary", icon=":material/save:",
                 key=f"{k}_save", disabled=bool(problem)):
        return out
    return None


# ---------------------------------------------------------------- business constraints
METRIC_WORDS = {"contactos": "contactos", "productos": "productos ofrecidos", "valor": "valor esperado"}
UNIT_WORDS = {"absoluto": "", "pct_total": "% del total", "pct_canal": "% de los canales indicados"}


def constraint_sentence(b: cs.BusinessConstraint) -> str:
    camps = "todas las campañas" if cs.ALL in b.campanas else ", ".join(b.campanas)
    chans = "todos los canales" if cs.ALL in b.canales else ", ".join(b.canales)
    lim = fmt_num(b.valor, 0 if b.unidad == "absoluto" and b.metrica != "valor" else 1)
    unit = UNIT_WORDS.get(b.unidad, b.unidad)
    seg = f" (solo clientes con {b.segmento} = 1)" if b.segmento else ""
    return (f"{'Como máximo' if b.sentido == '<=' else 'Como mínimo'} {lim}{(' ' + unit) if unit else ''} "
            f"de {METRIC_WORDS.get(b.metrica, b.metrica)} para {camps} por {chans}{seg}")


def constraint_builder(cfg: cs.Config, editing: cs.BusinessConstraint | None) -> dict | None:
    k = f"cb_{editing.id if editing else 'nueva'}_{state.rev()}"
    nombre = st.text_input("Nombre para negocio", value=editing.nombre if editing else "", key=f"{k}_nom",
                           placeholder="Al menos 5.000 renovaciones de terminal")
    c1, c2, c3 = st.columns([1.2, 1, 1.2])
    sentido = c1.selectbox("Sentido", cs.SENSES, key=f"{k}_sen", format_func={"<=": "Como máximo", ">=": "Como mínimo"}.get,
                           index=cs.SENSES.index(editing.sentido) if editing and editing.sentido in cs.SENSES else 1)
    valor = c2.number_input("Valor", min_value=0.0, value=float(editing.valor if editing else 0), step=1.0,
                            key=f"{k}_val")
    unidad = c3.selectbox("Unidad", cs.UNITS, key=f"{k}_uni",
                          index=cs.UNITS.index(editing.unidad) if editing and editing.unidad in cs.UNITS else 0,
                          format_func={"absoluto": "Absoluto", "pct_total": "% del total",
                                       "pct_canal": "% del canal"}.get)
    d1, d2, d3, d4 = st.columns([1.2, 1.5, 1.5, 1.3])
    metrica = d1.selectbox("Métrica", cs.METRICS, key=f"{k}_met", format_func=METRIC_WORDS.get,
                           index=cs.METRICS.index(editing.metrica) if editing and editing.metrica in cs.METRICS else 0)
    camp_ids = [c.id for c in cfg.campaigns]
    ch_ids = [c.id for c in cfg.channels]
    camps = d2.multiselect("Campañas (vacío = todas)", camp_ids, key=f"{k}_camps", placeholder="Todas",
                           default=[c for c in (editing.campanas if editing else []) if c in camp_ids])
    chans = d3.multiselect("Canales (vacío = todos)", ch_ids, key=f"{k}_chans", placeholder="Todos",
                           default=[c for c in (editing.canales if editing else []) if c in ch_ids])
    binaries = [""] + [x.id for x in cfg.constants if x.tipo == "binaria"]
    seg = d4.selectbox("Segmento", binaries, key=f"{k}_seg", format_func=lambda s: s or "Todos los clientes",
                       index=binaries.index(editing.segmento) if editing and editing.segmento in binaries else 0)
    active = st.toggle("Activa", value=editing.activa if editing else True, key=f"{k}_on")
    bid = editing.id if editing else cs.next_id([b.id for b in cfg.business_constraints], "N")
    preview = cs.BusinessConstraint(bid, nombre, camps or [cs.ALL], chans or [cs.ALL], seg, metrica, sentido, valor,
                                    unidad, active)
    st.caption(f"**{bid}** · {constraint_sentence(preview)}.")
    if st.button("Guardar restricción" if editing else "Agregar restricción", type="primary", icon=":material/save:",
                 key=f"{k}_save"):
        return {"id": bid, "nombre": nombre or constraint_sentence(preview), "campanas": "|".join(camps) or cs.ALL,
                "canales": "|".join(chans) or cs.ALL, "segmento": seg, "metrica": metrica, "sentido": sentido,
                "valor": _num_str(valor), "unidad": unidad, "activa": "1" if active else "0"}
    return None
