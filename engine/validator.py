"""Independent validator of a parrilla against raw data + configuration.

Deliberately does NOT use rules.py / expressions.py / the optimizer's masks: it re-checks every
assigned client row by row with its own small evaluator, so a bug in the engine cannot hide
itself. Results are grouped by the challenge's 16 constraints through
``config/trazabilidad_reto.csv``; checks not mapped there (rules added by business, format,
inactive campaigns) are reported on their own rows.
"""
from __future__ import annotations

import math
import numbers
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from engine import rules as sysrules
from engine.config_store import (PRODUCT_PLACEHOLDER, Config, DerivedConstant, load_traceability, split_list,
                                 to_bool, to_float)
from engine.data_loader import id_column

SRC_FORMAT = "sistema:FORMATO"
SRC_CAMPAIGN = "sistema:P-CAMPANA-ACTIVA"
SRC_CHANNEL = "sistema:P-CANAL-ACTIVO"


@dataclass
class ValidationReport:
    summary: pd.DataFrame      # id, nombre, fuentes, violaciones (distinct clients)
    details: pd.DataFrame      # id_cliente, fuente, detalle

    @property
    def total(self) -> int:
        return int(self.summary["violaciones"].sum())

    def offending(self, id_: str) -> list[str]:
        srcs = set(self.summary.loc[self.summary["id"] == id_, "fuentes"].iloc[0].split("|"))
        return sorted(set(self.details.loc[self.details["fuente"].isin(srcs), "id_cliente"]))


# ---------------------------------------------------------------- row-wise evaluator
def _num(v) -> float | None:
    s = str(v).strip().lower()
    if s in ("si", "sí", "true"):
        return 1.0
    if s in ("no", "false"):
        return 0.0
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def holds(value, op: str, raw: str, product: str | None) -> bool:
    """Does ``value op raw`` hold? ``value`` is a scalar, a frozenset (list column) or NaN."""
    raw = raw or ""
    if PRODUCT_PLACEHOLDER in raw:
        raw = raw.replace(PRODUCT_PLACEHOLDER, product or "")
    vals = split_list(raw)
    if isinstance(value, (set, frozenset)):
        hit = any(v in value for v in vals)
        return {"en": hit, "contiene": hit, "no_en": not hit, "==": set(vals) == set(value),
                "!=": set(vals) != set(value)}.get(op, False)
    if isinstance(value, numbers.Number) and not isinstance(value, bool):
        if math.isnan(value):
            return False
        nums = [_num(v) for v in vals]
        if op == "en":
            return any(value == x for x in nums)
        if op == "no_en":
            return all(value != x for x in nums)
        x = nums[0] if nums else None
        if x is None:
            return False
        return {"==": value == x, "!=": value != x, "<": value < x, "<=": value <= x,
                ">": value > x, ">=": value >= x}.get(op, False)
    s = str(value).strip()
    if op == "en":
        return s in vals
    if op == "no_en":
        return s not in vals
    if op == "contiene":
        return any(v in s for v in vals)
    if op == "==":
        return s == (vals[0] if vals else "")
    if op == "!=":
        return s != (vals[0] if vals else "")
    return False


class _RowContext:
    def __init__(self, row: dict, consts: dict[str, DerivedConstant]):
        self.row, self.consts = row, consts

    def value(self, attr: str, product: str | None):
        if attr in self.consts:
            return self.constant(self.consts[attr], product)
        return self.row.get(attr)

    def constant(self, k: DerivedConstant, product: str | None) -> float:
        if k.tipo != "binaria":
            total = 0.0
            for c in k.condiciones:
                v = _num(self.value(c.atributo, product))
                total += (to_float(c.valor, 1.0) or 0.0) * (v or 0.0)
            return total
        result, group = False, None
        for c in k.condiciones:
            m = holds(self.value(c.atributo, product), c.operador, c.valor, product)
            if group is None:
                group = m
            elif c.conector == "O":
                result, group = result or group, m
            else:
                group = group and m
        return float(result or bool(group))


# ---------------------------------------------------------------- validation
def validate(parrilla: pd.DataFrame, df: pd.DataFrame, cfg: Config) -> ValidationReport:
    trace = load_traceability()
    camps = {c.id: c for c in cfg.campaigns}
    in_force = {c.id for c in cfg.active_campaigns}
    chans = {c.id: c for c in cfg.channels}
    active_ch = {c.id for c in cfg.active_channels}
    consts = {k.id: k for k in cfg.constants if k.activa}
    rules = [r for r in cfg.rules if r.activa and r.accion == "excluir"]
    u_prod = cfg.param_float("priorizacion.umbral_score_producto", 0.0)
    u_chan = cfg.param_float("canal.umbral_score_canal", 0.0)
    k_max = cfg.param_int("politica_contacto.canales_por_cliente", 1)
    week_col = cfg.param("politica_contacto.columna_contactos_semana", "")
    week_max = cfg.param_int("politica_contacto.max_contactos_semana")

    viol: list[tuple[str, str, str]] = []
    add = lambda cid, src, msg: viol.append((cid, src, msg))  # noqa: E731

    id_col = id_column(cfg)
    records = dict(zip(df[id_col].astype(str), df.to_dict("records")))
    camp_cols = [c for c in parrilla.columns if c.startswith("campana_")]
    p = parrilla.fillna("").astype(str)

    # Format: one row per client, every client present.
    dup = p["id_cliente"][p["id_cliente"].duplicated()]
    for cid in dup.unique():
        add(cid, SRC_FORMAT, "cliente repetido en la parrilla")
    missing = set(records) - set(p["id_cliente"])
    for cid in sorted(missing):
        add(cid, SRC_FORMAT, "cliente ausente en la parrilla")

    used = defaultdict(list)
    for r in p.to_dict("records"):
        cid = r["id_cliente"]
        channels = split_list(r.get("canal", ""))
        campaigns = [r[c].strip() for c in camp_cols if r[c].strip()]
        if r["estado"] not in ("asignado", "sin_accion"):
            add(cid, SRC_FORMAT, f"estado '{r['estado']}' no válido")
            continue
        if r["estado"] == "sin_accion":
            if channels or campaigns:
                add(cid, SRC_FORMAT, "sin_accion con canal o campañas")
            continue
        if cid not in records:
            add(cid, SRC_FORMAT, "cliente desconocido")
            continue
        if not channels or not campaigns:
            add(cid, SRC_FORMAT, "asignado sin canal o sin campañas")
            continue
        if len(set(campaigns)) != len(campaigns):
            add(cid, SRC_FORMAT, "campaña repetida")
        row = records[cid]
        ctx = _RowContext(row, consts)
        for ch in channels:
            used[ch].append(cid)

        # Channel-level checks.
        for ch in channels:
            c = chans.get(ch)
            if c is None or ch not in active_ch:
                add(cid, SRC_CHANNEL, f"canal '{ch}' inexistente o inactivo")
                continue
            sc = _num(row.get(c.columna_score))
            thr = c.umbral_score if c.umbral_score is not None else u_chan
            if sc is None or sc < thr:
                add(cid, "sistema:" + sysrules.SYS_CHANNEL_THRESHOLD, f"{ch}: score {sc} < {thr}")
            if c.columna_autorizacion and not to_bool(row.get(c.columna_autorizacion)):
                add(cid, "sistema:" + sysrules.SYS_AUTHORIZATION, f"{ch}: sin autorización")
            for rule in rules:
                if rule.tipo != "canal":
                    continue
                if rule.alcance_nivel == "canal" and ch not in rule.alcance_valores:
                    continue
                cond = rule.condicion
                if holds(ctx.value(cond.atributo, None), cond.operador, cond.valor, None):
                    add(cid, "regla:" + rule.id, f"{ch}: {cond.atributo} {cond.operador} {cond.valor}")

        # Campaign-level checks.
        for cp in campaigns:
            camp = camps.get(cp)
            if camp is None or cp not in in_force:
                add(cid, SRC_CAMPAIGN, f"campaña '{cp}' inexistente, pausada o fuera de vigencia")
                continue
            sp = _num(row.get(camp.columna_score))
            thr = camp.umbral_score if camp.umbral_score is not None else u_prod
            if sp is None or sp < thr:
                add(cid, "sistema:" + sysrules.SYS_PRODUCT_THRESHOLD, f"{cp}: score {sp} < {thr}")
            if not any(ch in camp.canales_permitidos for ch in channels) or (
                    len(channels) == 1 and channels[0] not in camp.canales_permitidos):
                add(cid, "sistema:" + sysrules.SYS_ALLOWED_CHANNEL, f"{cp} no permitida por {'|'.join(channels)}")
            for rule in rules:
                if rule.tipo != "elegibilidad":
                    continue
                lvl, vals = rule.alcance_nivel, rule.alcance_valores
                if (lvl == "campana" and cp not in vals) or (lvl == "producto" and camp.producto not in vals) or (
                        lvl == "objetivo" and camp.objetivo not in vals):
                    continue
                cond = rule.condicion
                if holds(ctx.value(cond.atributo, camp.producto), cond.operador, cond.valor, camp.producto):
                    add(cid, "regla:" + rule.id, f"{cp}: {cond.atributo} {cond.operador} {cond.valor}")

        # Contact policy.
        if len(channels) > k_max:
            add(cid, "sistema:" + sysrules.SYS_CHANNELS_PER_CLIENT, f"{len(channels)} canales > {k_max}")
        cap_products = sum(chans[ch].max_productos for ch in channels if ch in chans)
        if len(campaigns) > cap_products:
            add(cid, "sistema:" + sysrules.SYS_MAX_PRODUCTS, f"{len(campaigns)} productos > {cap_products}")
        if week_col and week_max is not None:
            received = _num(row.get(week_col)) or 0
            if received + len(channels) > week_max:
                add(cid, "sistema:" + sysrules.SYS_WEEKLY_CAP,
                    f"{week_col} = {received:g} + {len(channels)} > {week_max}")

    for ch, ids in used.items():
        cap = chans[ch].capacidad if ch in chans else 0
        for cid in ids[cap:]:
            add(cid, "sistema:" + sysrules.SYS_CAPACITY, f"{ch}: {len(ids)} contactos > cupo {cap}")

    details = pd.DataFrame(viol, columns=["id_cliente", "fuente", "detalle"])
    rows, mapped = [], set()
    for t in trace.to_dict("records"):
        srcs = split_list(t["fuentes"])
        mapped.update(srcs)
        n = details.loc[details["fuente"].isin(srcs), "id_cliente"].nunique()
        rows.append({"id": t["id_reto"], "nombre": t["nombre"], "fuentes": t["fuentes"], "violaciones": int(n)})
    extra = [r.id for r in rules if "regla:" + r.id not in mapped]
    names = {r.id: r.nombre for r in cfg.rules}
    for rid in extra:
        n = details.loc[details["fuente"] == "regla:" + rid, "id_cliente"].nunique()
        rows.append({"id": rid, "nombre": f"Regla adicional: {names[rid]}", "fuentes": "regla:" + rid,
                     "violaciones": int(n)})
    for src, name in ((SRC_CAMPAIGN, "Campaña activa y vigente"), (SRC_CHANNEL, "Canal existente y activo"),
                      (SRC_FORMAT, "Formato de la parrilla")):
        n = details.loc[details["fuente"] == src, "id_cliente"].nunique()
        rows.append({"id": src.split(":", 1)[1], "nombre": name, "fuentes": src, "violaciones": int(n)})
    return ValidationReport(pd.DataFrame(rows), details)
