"""What-if scenarios: demo scenarios (config/escenarios_demo.csv) and scenarios saved by users.

A scenario is a full configuration (+ the optimizer to run it with). Demo scenarios are written as
operations over the applied configuration, so they keep working when that configuration changes.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path

import pandas as pd

from engine import config_store as cs

DEMO_FILE = cs.ROOT / "config" / "escenarios_demo.csv"
SCENARIO_DIR = cs.ROOT / "config" / "escenarios"
OPERATIONS = ("asignar", "sumar", "multiplicar")


def demo_scenarios() -> dict[str, dict]:
    if not DEMO_FILE.exists():
        return {}
    t = pd.read_csv(DEMO_FILE, dtype=str, keep_default_na=False)
    out: dict[str, dict] = {}
    for sid, g in t.groupby("escenario", sort=False):
        first = g.iloc[0]
        out[sid] = {"id": sid, "nombre": first["nombre"], "descripcion": first["descripcion"],
                    "ops": g[["tabla", "clave", "campo", "operacion", "valor"]].to_dict("records")}
    return out


def apply_ops(cfg: cs.Config, ops: list[dict]) -> cs.Config:
    """Copy of ``cfg`` with the operations applied. Unknown targets raise a Spanish ValueError."""
    new = cfg.copy()
    for op in ops:
        table, key, field, how, value = (op["tabla"], op["clave"], op["campo"], op["operacion"], op["valor"])
        if table not in new.tables:
            raise ValueError(f"Escenario: la tabla '{table}' no existe.")
        t = new.tables[table]
        key_col = "parametro" if table == "parametros" else "id"
        mask = t[key_col] == key
        if not mask.any():
            if table == "parametros" and how == "asignar":
                new.set_param(key, value)
                continue
            raise ValueError(f"Escenario: '{key}' no existe en {table}.")
        if field not in t.columns:
            raise ValueError(f"Escenario: el campo '{field}' no existe en {table}.")
        if how == "asignar":
            t.loc[mask, field] = value
        elif how in ("sumar", "multiplicar"):
            cur = cs.to_float(t.loc[mask, field].iloc[0], 0.0)
            x = cs.to_float(value, 0.0)
            res = cur + x if how == "sumar" else cur * x
            t.loc[mask, field] = f"{res:g}"
        else:
            raise ValueError(f"Escenario: operación '{how}' desconocida (use {', '.join(OPERATIONS)}).")
    return new


# ---------------------------------------------------------------- saved scenarios
def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "escenario"


def save(cfg: cs.Config, nombre: str, optimizer: str) -> str:
    sid = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{_slug(nombre)}"
    d = SCENARIO_DIR / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "configuracion.zip").write_bytes(cs.export_bundle(cfg))
    (d / "escenario.json").write_text(json.dumps({
        "id": sid, "nombre": nombre, "optimizador": optimizer, "hash": cs.config_hash(cfg),
        "creado": dt.datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
    return sid


def list_saved() -> list[dict]:
    if not SCENARIO_DIR.exists():
        return []
    out = []
    for d in sorted(SCENARIO_DIR.iterdir(), reverse=True):
        meta = d / "escenario.json"
        if meta.exists():
            out.append(json.loads(meta.read_text(encoding="utf-8")))
    return out


def load(sid: str) -> tuple[cs.Config, dict]:
    d = SCENARIO_DIR / sid
    meta = json.loads((d / "escenario.json").read_text(encoding="utf-8"))
    cfg = cs.import_bundle((d / "configuracion.zip").read_bytes())
    cfg.source = f"escenario {meta['nombre']}"
    return cfg, meta


def delete(sid: str) -> None:
    d = SCENARIO_DIR / sid
    if d.exists() and d.parent == SCENARIO_DIR:
        shutil.rmtree(d)
