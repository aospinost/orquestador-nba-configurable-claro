"""Read-only analyses of a finished run for the Resultado / Decisión pages.

Funnel, campaign→channel flows, capacity opportunity cost (greedy's stand-in for duals), the
per-client explanation card and run-to-run comparison. Nothing here changes a decision.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.config_store import Config
from engine.explain import OPERATOR_WORDS, fmt, value_words
from engine.optimizers.base import SolveInput, SolveResult, pair_values
from engine.rules import (SYS_ALLOWED_CHANNEL, SYS_CHANNEL_THRESHOLD, SYS_PRODUCT_THRESHOLD, SYSTEM_RULES)


def _pairs(result: SolveResult) -> pd.DataFrame:
    if result.pairs is None or not len(result.pairs):
        return pd.DataFrame(columns=["client_idx", "channel_idx", "campaign_idx", "orden", "canal_orden"], dtype=int)
    return result.pairs


# ---------------------------------------------------------------- funnel
def funnel(inp: SolveInput, result: SolveResult) -> list[dict]:
    """From all clients to the parrilla: client-level rules and global rules (one step each),
    clients with an eligible campaign, with a usable channel for it, and assigned."""
    reasons = inp.exclusion_reasons
    info = reasons.get("info", {})
    n = inp.n
    remaining = np.ones(n, bool)
    steps = [{"etapa": "Clientes en la base", "clientes": n, "regla": "", "nombre": ""}]
    for rid, m in reasons.get("cliente", {}).items():
        remaining &= ~m
        steps.append({"etapa": f"Tras {rid}", "clientes": int(remaining.sum()), "regla": rid,
                      "nombre": info.get(rid, {}).get("nombre", rid)})
    for rid, m in reasons.get("campana", {}).items():
        meta = info.get(rid, {})
        if meta.get("sistema") or meta.get("alcance") != "global" or m.shape[1] == 0:
            continue
        remaining &= ~m.all(axis=1)  # the rule leaves the client without any campaign
        steps.append({"etapa": f"Tras {rid}", "clientes": int(remaining.sum()), "regla": rid,
                      "nombre": meta.get("nombre", rid)})
    elig = remaining & inp.client_active & inp.eligible.any(axis=1)
    steps.append({"etapa": "Con ≥1 campaña elegible", "clientes": int(elig.sum()), "regla": "",
                  "nombre": "Pasa todas las reglas de campaña y el umbral de producto"})
    usable = (inp.eligible[:, :, None] & inp.allowed[None, :, :] & inp.channel_ok[:, None, :]).any(axis=(1, 2))
    ch = elig & usable
    steps.append({"etapa": "Con canal habilitado", "clientes": int(ch.sum()), "regla": "",
                  "nombre": "Algún canal autorizado, sobre el umbral y permitido para sus campañas"})
    assigned = np.bincount(_pairs(result)["client_idx"].to_numpy(int), minlength=n) > 0
    steps.append({"etapa": "Con acción en la parrilla", "clientes": int(assigned.sum()), "regla": "",
                  "nombre": "Recibió canal y campañas dentro del cupo"})
    return steps


# ---------------------------------------------------------------- flows
def flows(inp: SolveInput, result: SolveResult) -> pd.DataFrame:
    """campana, canal, clientes, valor — one row per used (campaign, channel)."""
    p = _pairs(result)
    if not len(p):
        return pd.DataFrame(columns=["campana", "canal", "clientes", "valor"])
    df = pd.DataFrame({"campana": np.array(inp.campaigns)[p["campaign_idx"].to_numpy(int)],
                       "canal": np.array(inp.channels)[p["channel_idx"].to_numpy(int)],
                       "valor": pair_values(inp, p)})
    return df.groupby(["campana", "canal"], as_index=False).agg(clientes=("valor", "size"), valor=("valor", "sum"))


# ---------------------------------------------------------------- capacity opportunity cost
def _value_on_channel(inp: SolveInput, c: int) -> np.ndarray:
    """Best value each client would get from one contact on channel c (top M_c feasible campaigns)."""
    feas = inp.eligible & inp.allowed[None, :, c] & inp.channel_ok[:, c, None] & inp.client_active[:, None]
    v = np.where(feas, inp.product_score * inp.channel_score[:, c, None] * inp.business_value[None, :], 0.0)
    m = int(inp.max_products[c])
    return -np.sort(-v, axis=1)[:, :m].sum(axis=1)


def capacity_opportunity(inp: SolveInput, result: SolveResult) -> list[dict]:
    """Per channel: use, and for full channels an ESTIMATED shadow price = the best gain a rejected
    client would bring with one more slot (moving from its current option to this channel)."""
    p = _pairs(result)
    pv = pair_values(inp, p) if len(p) else np.zeros(0)
    ci, cc = p["client_idx"].to_numpy(int), p["channel_idx"].to_numpy(int)
    current = np.bincount(ci, weights=pv, minlength=inp.n)
    out = []
    for c, name in enumerate(inp.channels):
        on_c = cc == c
        clients_c = np.unique(ci[on_c])
        used, cap = len(clients_c), int(inp.capacity[c])
        row = {"canal": name, "usado": used, "cupo": cap, "lleno": used >= cap, "precio_estimado": 0.0,
               "ultimo_admitido": None, "primer_rechazado": None}
        if len(clients_c):
            val_c = np.bincount(ci[on_c], weights=pv[on_c], minlength=inp.n)[clients_c]
            k = int(np.argmin(val_c))
            row["ultimo_admitido"] = {"id": str(inp.client_ids[clients_c[k]]), "valor": float(val_c[k])}
        if row["lleno"]:
            gain = _value_on_channel(inp, c) - current
            gain[clients_c] = -np.inf
            j = int(np.argmax(gain))
            if np.isfinite(gain[j]) and gain[j] > 0:
                row["precio_estimado"] = float(gain[j])
                row["primer_rechazado"] = {"id": str(inp.client_ids[j]), "valor": float(gain[j])}
        out.append(row)
    return out


# ---------------------------------------------------------------- client card
def _cond_words(meta: dict) -> str:
    return f"{meta.get('atributo', '')} {OPERATOR_WORDS.get(meta.get('operador', ''), meta.get('operador', ''))} " \
           f"{value_words(meta.get('valor', ''))}"


def _attr_value(df: pd.DataFrame, consts: dict, attr: str, i: int, p: int | None):
    if attr in consts:
        a = consts[attr]
        return a[i, p] if a.ndim == 2 and p is not None else (a[i] if a.ndim == 1 else "")
    return df[attr].iat[i] if attr in df.columns else ""


def _show(v) -> str:
    if isinstance(v, (set, frozenset)):
        return ", ".join(sorted(v)) or "vacío"
    if isinstance(v, (float, np.floating)):
        return fmt(v, 0) if float(v).is_integer() else fmt(v, 2)
    return str(v)


def client_index(inp: SolveInput, client_id: str) -> int | None:
    hit = np.nonzero(inp.client_ids == str(client_id).strip())[0]
    return int(hit[0]) if len(hit) else None


def client_detail(inp: SolveInput, result: SolveResult, df: pd.DataFrame, i: int, cfg: Config) -> dict:
    """Everything the explanation card shows for client i."""
    R = inp.exclusion_reasons
    info = R.get("info", {})
    names = {c.id: c.nombre for c in cfg.campaigns} | {c.id: c.nombre for c in cfg.channels}
    P, C = len(inp.campaigns), len(inp.channels)
    row = result.assignment.iloc[i]
    pairs = _pairs(result)
    mine = pairs[pairs["client_idx"] == i]
    chosen = {(int(c), int(p)) for c, p in zip(mine["channel_idx"], mine["campaign_idx"])}

    def checks_campaign(p: int) -> list[dict]:
        out = []
        for rid, m in R.get("campana", {}).items():
            meta = info.get(rid, {})
            if rid == SYS_PRODUCT_THRESHOLD:
                u = meta["umbral"][inp.campaigns[p]]
                sp = inp.product_score[i, p]
                out.append({"id": rid, "nombre": meta["nombre"], "ok": not m[i, p],
                            "detalle": f"score {fmt(sp)} {'≥' if not m[i, p] else '<'} umbral {fmt(u)}"})
            elif p in meta.get("objetivos", []):
                v = _attr_value(df, inp.constants, meta["atributo"], i, p)
                out.append({"id": rid, "nombre": meta["nombre"], "ok": not m[i, p],
                            "detalle": f"{meta['atributo']} = {_show(v)} · excluye si {_cond_words(meta)}"})
        for rid, m in R.get("blandas", {}).items():
            meta = info.get(rid, {})
            if meta.get("tipo") == "elegibilidad" and p in meta.get("objetivos", []) and m[i, p, 0]:
                out.append({"id": rid, "nombre": meta["nombre"], "ok": True, "blanda": True,
                            "detalle": f"{meta['accion']} {fmt(meta['peso'])} en el puntaje"})
        return out

    def checks_channel(c: int) -> list[dict]:
        out = []
        for rid, m in R.get("canal", {}).items():
            meta = info.get(rid, {})
            if rid == SYS_CHANNEL_THRESHOLD:
                u = meta["umbral"][inp.channels[c]]
                out.append({"id": rid, "nombre": meta["nombre"], "ok": not m[i, c],
                            "detalle": f"score {fmt(inp.channel_score[i, c])} {'≥' if not m[i, c] else '<'} umbral {fmt(u)}"})
            elif meta.get("sistema"):
                out.append({"id": rid, "nombre": meta["nombre"], "ok": not m[i, c], "detalle": ""})
            elif c in meta.get("objetivos", []):
                v = _attr_value(df, inp.constants, meta["atributo"], i, None)
                out.append({"id": rid, "nombre": meta["nombre"], "ok": not m[i, c],
                            "detalle": f"{meta['atributo']} = {_show(v)} · excluye si {_cond_words(meta)}"})
        return out

    client_rules = []
    for rid, m in R.get("cliente", {}).items():
        meta = info.get(rid, {})
        v = _attr_value(df, inp.constants, meta.get("atributo", ""), i, None)
        client_rules.append({"id": rid, "nombre": meta.get("nombre", rid), "ok": not m[i],
                             "detalle": f"{meta.get('atributo', '')} = {_show(v)} · máximo {meta.get('maximo', '')}"})

    matrix = []
    for p in range(P):
        for c in range(C):
            value = float(inp.product_score[i, p] * inp.channel_score[i, c] * inp.business_value[p])
            block = [r for r, m in R.get("campana", {}).items() if m[i, p]]
            block += [r for r, m in R.get("canal", {}).items() if m[i, c]]
            block += [r for r, m in R.get("cliente", {}).items() if m[i]]
            if not inp.allowed[p, c]:
                block.append(SYS_ALLOWED_CHANNEL)
            status = "elegido" if (c, p) in chosen else ("bloqueado" if block else "factible")
            matrix.append({"campana": inp.campaigns[p], "canal": inp.channels[c], "valor": value,
                           "estado": status, "bloqueo": block})

    profile_cols = [col for col in df.columns if col not in result.assignment.columns or col == "id_cliente"]
    return {
        "id": str(inp.client_ids[i]), "estado": row["estado"], "canal": row["canal"],
        "campanas": [row[k] for k in result.assignment.columns if k.startswith("campana_") and row[k]],
        "razon": row["razon"], "valor": float(row["valor_esperado"]),
        "perfil": {col: _show(df[col].iat[i]) for col in profile_cols},
        "reglas_cliente": client_rules,
        "por_campana": {inp.campaigns[p]: {"nombre": names.get(inp.campaigns[p], ""), "elegible": bool(inp.eligible[i, p]),
                                           "checks": checks_campaign(p)} for p in range(P)},
        "por_canal": {inp.channels[c]: {"nombre": names.get(inp.channels[c], ""), "habilitado": bool(inp.channel_ok[i, c]),
                                        "checks": checks_channel(c)} for c in range(C)},
        "matriz": matrix,
        "guion": script(inp, i, mine, row, names),
    }


def script(inp: SolveInput, i: int, mine: pd.DataFrame, row, names: dict) -> str:
    """One sentence for whoever contacts the client: why this client, why this product."""
    if not len(mine):
        reason = str(row["razon"]).split(":", 1)[-1].split(".")[0].strip()
        return f"No contactar en esta corrida: {reason}."
    c = int(mine["channel_idx"].iloc[0])
    ps = mine["campaign_idx"].astype(int).tolist()
    p0 = ps[0]
    others = [names.get(inp.campaigns[p], inp.campaigns[p]) for p in ps[1:]]
    extra = f", y de paso {', '.join(others)}" if others else ""
    return (f"Contactar por {names.get(inp.channels[c], inp.channels[c])} para ofrecer "
            f"{names.get(inp.campaigns[p0], inp.campaigns[p0])}{extra}: su propensión es de "
            f"{fmt(100 * inp.product_score[i, p0], 0)} % y responde por este canal en un "
            f"{fmt(100 * inp.channel_score[i, c], 0)} %, la mejor combinación con cupo disponible.")


# ---------------------------------------------------------------- run comparison
KPI_LABELS = {"valor_esperado": "Valor esperado", "clientes_con_accion": "Clientes con acción",
              "productos_asignados": "Productos asignados", "indicador_jerarquia": "Indicador de jerarquía (%)",
              "violaciones": "Violaciones", "segundos_optimizador": "Tiempo del optimizador (s)"}


def compare_metrics(named: dict[str, dict]) -> pd.DataFrame:
    """Rows = KPIs, columns = run/scenario names."""
    rows = []
    for k, label in KPI_LABELS.items():
        rows.append({"Indicador": label, **{name: m.get(k) for name, m in named.items()}})
    return pd.DataFrame(rows)


def run_diff(a: SolveResult, b: SolveResult, inp_a: SolveInput, inp_b: SolveInput) -> dict:
    """Where run b gains over run a: value by channel and clients that changed channel."""
    va = pd.Series(pair_values(inp_a, _pairs(a)) if len(_pairs(a)) else [],
                   index=np.array(inp_a.channels)[_pairs(a)["channel_idx"].to_numpy(int)], dtype=float)
    vb = pd.Series(pair_values(inp_b, _pairs(b)) if len(_pairs(b)) else [],
                   index=np.array(inp_b.channels)[_pairs(b)["channel_idx"].to_numpy(int)], dtype=float)
    by_channel = (vb.groupby(level=0).sum().subtract(va.groupby(level=0).sum(), fill_value=0)).to_dict()
    ca = a.assignment.set_index("id_cliente")["canal"]
    cb = b.assignment.set_index("id_cliente")["canal"].reindex(ca.index).fillna("")
    changed = int((ca != cb).sum())
    return {"valor_por_canal": by_channel, "clientes_cambiaron_canal": changed}


def system_rule_name(rid: str) -> str:
    return SYSTEM_RULES.get(rid, rid)
