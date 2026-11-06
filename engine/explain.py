"""Builds the ``razon`` column: a Spanish sentence per client citing rule / constant IDs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.optimizers.base import (ST_ASSIGNED, ST_INACTIVE, ST_NO_CAMPAIGN, ST_NO_CAPACITY, ST_NO_CHANNEL,
                                    ST_NOT_SELECTED, SolveInput, SolveResult)
from engine.rules import SYS_ALLOWED_CHANNEL, SYS_CHANNEL_THRESHOLD, SYS_PRODUCT_THRESHOLD, SYS_WEEKLY_CAP


def fmt(x, decimals: int = 2) -> str:
    """Colombian number format: 1.234,56."""
    if isinstance(x, (int, np.integer)) or (isinstance(x, float) and float(x).is_integer() and decimals == 0):
        return f"{int(x):,}".replace(",", ".")
    s = f"{float(x):,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _value_str(v) -> str:
    if isinstance(v, (set, frozenset)):
        return "{" + ", ".join(sorted(v)) + "}" if v else "vacío"
    if isinstance(v, (float, np.floating)):
        return fmt(v, 0) if float(v).is_integer() else fmt(v, 2)
    return str(v)


class _Describer:
    """Short Spanish detail for '<rule> (<why>)' tokens."""

    def __init__(self, inp: SolveInput, df: pd.DataFrame):
        self.inp, self.df = inp, df
        self.info = inp.exclusion_reasons.get("info", {})
        self.consts = inp.constants

    def _attr_value(self, attr: str, i: int, p: int | None):
        if attr in self.consts:
            arr = self.consts[attr]
            return arr[i, p] if arr.ndim == 2 and p is not None else (arr[i] if arr.ndim == 1 else "")
        if attr in self.df.columns:
            return self.df[attr].iat[i]
        return ""

    def campaign(self, rid: str, i: int, p: int) -> str:
        if rid == SYS_PRODUCT_THRESHOLD:
            u = self.info[rid]["umbral"][self.inp.campaigns[p]]
            return f"{rid} (score {fmt(self.inp.product_score[i, p])} < {fmt(u)})"
        inf = self.info.get(rid, {})
        if "atributo" in inf:
            v = self._attr_value(inf["atributo"], i, p)
            return f"{rid} ({inf['atributo']} = {_value_str(v)})"
        return rid

    def channel(self, rid: str, i: int, c: int) -> str:
        if rid == SYS_CHANNEL_THRESHOLD:
            u = self.info[rid]["umbral"][self.inp.channels[c]]
            return f"{rid} (score {fmt(self.inp.channel_score[i, c])} < {fmt(u)})"
        inf = self.info.get(rid, {})
        if "atributo" in inf:
            v = self._attr_value(inf["atributo"], i, None)
            return f"{rid} ({inf['atributo']} = {_value_str(v)})"
        return rid


def _hits_per_cell(masks: dict[str, np.ndarray], shape: tuple[int, int]) -> np.ndarray:
    """Object (n, k) array with the list of rule IDs hitting each cell."""
    out = np.empty(shape, dtype=object)  # filled with None
    for rid, m in masks.items():
        for i, j in zip(*np.nonzero(m)):
            if out[i, j] is None:
                out[i, j] = [rid]
            else:
                out[i, j].append(rid)
    return out


def build_reasons(inp: SolveInput, result: SolveResult, df: pd.DataFrame) -> pd.Series:
    n, P, C = inp.n, len(inp.campaigns), len(inp.channels)
    reasons = inp.exclusion_reasons
    d = _Describer(inp, df)
    camp_hits = _hits_per_cell(reasons.get("campana", {}), (n, P))
    chan_hits = _hits_per_cell(reasons.get("canal", {}), (n, C))
    client_hits = reasons.get("cliente", {})
    criterion = inp.params.get("canal.criterio", "")
    why_channel = ("primer canal habilitado con cupo según el orden de preferencia"
                   if criterion == "orden_preferencia" else "mejor canal habilitado con cupo")

    pairs = result.pairs
    by_client: dict[int, list[tuple[int, int]]] = {}
    if pairs is not None and len(pairs):
        srt = pairs.sort_values(["client_idx", "canal_orden", "orden"], kind="stable")
        for i, c, p in zip(srt["client_idx"].tolist(), srt["channel_idx"].tolist(), srt["campaign_idx"].tolist()):
            by_client.setdefault(i, []).append((c, p))
    status = result.client_status
    used = np.zeros(C, int)
    if pairs is not None and len(pairs):
        used = np.bincount(pairs.drop_duplicates(["client_idx", "channel_idx"])["channel_idx"], minlength=C)
    full = used >= inp.capacity

    def blocked_campaigns(i: int, skip: set[int]) -> str:
        parts = []
        for p in range(P):
            if p in skip or camp_hits[i, p] is None:
                continue
            parts.append(f"{inp.campaigns[p]} por " + ", ".join(d.campaign(r, i, p) for r in camp_hits[i, p]))
        return "; ".join(parts)

    def blocked_channels(i: int) -> str:
        parts = []
        for c in range(C):
            if chan_hits[i, c] is not None:
                parts.append(f"{inp.channels[c]} por " + ", ".join(d.channel(r, i, c) for r in chan_hits[i, c]))
        return "; ".join(parts)

    out = []
    for i in range(n):
        st = status[i] if status is not None else (ST_ASSIGNED if i in by_client else ST_NO_CAMPAIGN)
        if st == ST_ASSIGNED and i in by_client:
            items = by_client[i]
            chans = list(dict.fromkeys(c for c, _ in items))
            ch_txt = " y ".join(f"{inp.channels[c]} (score {fmt(inp.channel_score[i, c])})" for c in chans)
            prods = " + ".join(
                f"{inp.campaigns[p]} (valor {fmt(inp.product_score[i, p] * inp.channel_score[i, c] * inp.business_value[p], 3)})"
                for c, p in items)
            txt = f"Asignado por {ch_txt}: {why_channel}. {prods}."
            got = {p for _, p in items}
            notes = []
            # Eligible campaigns left out: channel not allowed or no room in the contact.
            for p in range(P):
                if p in got or not inp.eligible[i, p]:
                    continue
                if not any(inp.allowed[p, c] for c in chans):
                    notes.append(f"{inp.campaigns[p]} no va por {'/'.join(inp.channels[c] for c in chans)} "
                                 f"({SYS_ALLOWED_CHANNEL})")
                else:
                    notes.append(f"{inp.campaigns[p]} no cabe (tope de "
                                 f"{int(sum(inp.max_products[c] for c in chans))} producto(s) por contacto)")
            better_full = [inp.channels[c] for c in range(C)
                           if c not in chans and inp.channel_ok[i, c] and full[c]
                           and inp.channel_score[i, c] > min(inp.channel_score[i, k] for k in chans)
                           and any(inp.eligible[i, p] and inp.allowed[p, c] for p in range(P))]
            if better_full:
                notes.append("sin cupo en " + ", ".join(better_full))
            excl = blocked_campaigns(i, got)
            if excl:
                notes.append("excluidas: " + excl)
            if notes:
                joined = "; ".join(notes)
                txt += " " + joined[0].upper() + joined[1:] + "."
        elif st == ST_INACTIVE:
            rids = [r for r, m in client_hits.items() if m[i]]
            parts = []
            for r in rids:
                inf = reasons["info"].get(r, {})
                if r == SYS_WEEKLY_CAP:
                    v = df[inf["atributo"]].iat[i]
                    parts.append(f"tope semanal de contactos alcanzado ({r}: {inf['atributo']} = "
                                 f"{_value_str(v)}, máximo {inf['maximo']})")
                else:
                    parts.append(f"{inf.get('nombre', r)} ({r})")
            txt = "Sin acción: " + "; ".join(parts) + "." if parts else "Sin acción: cliente inactivo."
        elif st == ST_NO_CAMPAIGN:
            txt = "Sin acción: ninguna campaña elegible. " + (blocked_campaigns(i, set()) or "") + "."
        elif st == ST_NO_CHANNEL:
            el = [inp.campaigns[p] for p in range(P) if inp.eligible[i, p]]
            ch = blocked_channels(i)
            txt = (f"Sin acción: no hay canal habilitado para {', '.join(el)}. "
                   + (ch + "." if ch else f"Ningún canal habilitado está permitido para esas campañas "
                                          f"({SYS_ALLOWED_CHANNEL})."))
        elif st == ST_NO_CAPACITY:
            cands = [inp.channels[c] for c in range(C) if inp.channel_ok[i, c]
                     and any(inp.eligible[i, p] and inp.allowed[p, c] for p in range(P))]
            txt = f"Sin acción: cupo agotado en los canales habilitados ({', '.join(cands)})."
        elif st == ST_NOT_SELECTED:
            txt = "Sin acción: el optimizador no lo seleccionó porque el cupo rinde más valor en otros clientes."
        else:
            txt = "Sin acción."
        out.append(txt)
    return pd.Series(out, index=range(n), name="razon")


OPERATOR_WORDS = {"==": "es", "!=": "no es", "<": "es menor que", "<=": "es menor o igual a", ">": "es mayor que",
                  ">=": "es mayor o igual a", "en": "está en", "no_en": "no está en", "contiene": "contiene"}
ACTION_WORDS = {"excluir": "Excluir", "bonificar": "Bonificar", "penalizar": "Penalizar"}


def value_words(raw: str) -> str:
    from engine.config_store import PRODUCT_PLACEHOLDER, split_list
    vals = ["el producto de la campaña" if v == PRODUCT_PLACEHOLDER else v for v in split_list(raw)]
    return ", ".join(vals) if vals else "(vacío)"


def scope_words(rule) -> str:
    vals = ", ".join(rule.alcance_valores)
    many = len(rule.alcance_valores) > 1
    if rule.alcance_nivel == "global":
        return "todos los canales" if rule.tipo == "canal" else "todas las campañas"
    return {"campana": f"las campañas {vals}" if many else f"la campaña {vals}",
            "producto": f"los productos {vals}" if many else f"el producto {vals}",
            "objetivo": f"los objetivos {vals}" if many else f"el objetivo {vals}",
            "canal": f"los canales {vals}" if many else f"el canal {vals}"}.get(rule.alcance_nivel, vals)


def rule_sentence(rule) -> str:
    """Business sentence, e.g. 'Excluir la campaña C-TER cuando calificacion_riesgo está en C, P'."""
    c = rule.condicion
    s = (f"{ACTION_WORDS.get(rule.accion, rule.accion)} {scope_words(rule)} cuando {c.atributo} "
         f"{OPERATOR_WORDS.get(c.operador, c.operador)} {value_words(c.valor)}")
    if rule.accion != "excluir":
        s += f" (peso {fmt(rule.peso, 2)})"
    return s
