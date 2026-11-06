"""Session-state model shared by all pages.

- ``draft_config``: the configuration being edited (nothing runs until "Ejecutar orquestador").
- ``applied_config``: the configuration of the last run.
- ``runs``: list of dicts {output (pipeline.RunOutput), metrics, hash, optimizer, timestamp}.
"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from engine import config_store, data_loader, pipeline
from engine.optimizers import REGISTRY

MAX_RUNS = 10


def init() -> None:
    ss = st.session_state
    if "draft_config" not in ss:
        ss["draft_config"] = config_store.load()
    if "applied_config" not in ss:
        ss["applied_config"] = ss["draft_config"].copy()
    ss.setdefault("runs", [])
    ss.setdefault("optimizer", ss["draft_config"].param("optimizador.motor", "greedy"))


def draft() -> config_store.Config:
    return st.session_state["draft_config"]


def applied() -> config_store.Config:
    return st.session_state["applied_config"]


def runs() -> list[dict]:
    return st.session_state["runs"]


def last_run() -> dict | None:
    return runs()[-1] if runs() else None


def draft_hash() -> str:
    return config_store.config_hash(draft())


def pending_changes() -> list[dict]:
    return config_store.diff(applied(), draft())


def optimizers() -> dict[str, dict]:
    """name -> {label, available, supports} for the sidebar selector."""
    return {name: {"label": cls.label, "available": getattr(cls, "available", True), "supports": cls.supports}
            for name, cls in REGISTRY.items()}


def config_version(cfg: config_store.Config) -> str:
    if cfg.source == "inicial":
        return "Inicial (organizadores)"
    snaps = config_store.list_snapshots()
    if snaps:
        stamp = snaps[0].name.split("_")[0]
        try:
            when = dt.datetime.strptime(stamp[:15], "%Y%m%d-%H%M%S")
            return f"v{len(snaps)} · {when:%d/%m/%Y %H:%M}"
        except ValueError:
            return f"v{len(snaps)}"
    return cfg.source


# ---------------------------------------------------------------- cached data + runs
def _data_key(path: str) -> tuple[str, float]:
    p = data_loader.resolve_path(path)
    return str(p), p.stat().st_mtime if p.exists() else 0.0


@st.cache_resource(show_spinner=False, max_entries=3)
def _load_clients(path: str, mtime: float, _cfg: config_store.Config):
    return data_loader.load_clients(path, _cfg)


def clients(cfg: config_store.Config | None = None):
    cfg = cfg or draft()
    path, mtime = _data_key(cfg.param("datos.ruta"))
    return _load_clients(path, mtime, cfg)


@st.cache_resource(show_spinner=False, max_entries=8)
def _run(cfg_hash: str, optimizer: str, data_path: str, mtime: float, _cfg: config_store.Config):
    df = _load_clients(data_path, mtime, _cfg)
    return pipeline.run(_cfg, df, optimizer)


def execute(optimizer: str) -> dict:
    """Run the orchestrator on the draft config; on success it becomes the applied config."""
    cfg = draft().copy()
    path, mtime = _data_key(cfg.param("datos.ruta"))
    out = _run(config_store.config_hash(cfg), optimizer, path, mtime, cfg)
    run = {"output": out, "metrics": out.metrics, "hash": out.config_hash, "optimizer": optimizer,
           "timestamp": dt.datetime.now()}
    ss = st.session_state
    ss["runs"] = (runs() + [run])[-MAX_RUNS:]
    ss["applied_config"] = cfg
    return run
