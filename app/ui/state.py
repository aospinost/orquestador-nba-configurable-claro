"""Session-state model shared by all pages.

- ``draft_config``: the configuration being edited (nothing runs until "Ejecutar orquestador").
- ``applied_config``: the configuration of the last run.
- ``runs``: list of dicts {output (pipeline.RunOutput), metrics, hash, optimizer, timestamp}.
"""
from __future__ import annotations

import datetime as dt

import streamlit as st

from engine import config_store, data_loader, impact, pipeline
from engine.optimizers import REGISTRY

MAX_RUNS = 10


def init() -> None:
    ss = st.session_state
    if "draft_config" not in ss:
        ss["draft_config"] = config_store.load()
    if "applied_config" not in ss:
        ss["applied_config"] = ss["draft_config"].copy()
    ss.setdefault("runs", [])
    ss.setdefault("cfg_rev", 0)
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
           "timestamp": dt.datetime.now(), "impacto": impact_summary(cfg)}
    ss = st.session_state
    ss["runs"] = (runs() + [run])[-MAX_RUNS:]
    ss["applied_config"] = cfg
    return run


# ---------------------------------------------------------------- draft editing
def rev() -> int:
    """Changes whenever the draft is replaced wholesale; use it in editor widget keys."""
    return st.session_state["cfg_rev"]


def replace_draft(cfg: config_store.Config) -> None:
    st.session_state["draft_config"] = cfg
    st.session_state["cfg_rev"] += 1


def discard_changes() -> None:
    replace_draft(applied().copy())


def restore_initial() -> None:
    """Load the organizers' configuration into the draft (applied with "Aplicar y re-optimizar")."""
    replace_draft(config_store.load_initial())


def touch() -> None:
    """Call after an in-place edit of the draft that other widgets must reflect."""
    st.session_state["cfg_rev"] += 1


def columns(cfg: config_store.Config | None = None) -> list[str]:
    return list(clients(cfg).columns)


def errors(cfg: config_store.Config | None = None) -> list[str]:
    cfg = cfg or draft()
    try:
        df = clients(cfg)
    except FileNotFoundError:
        return [f"Datos: no se encontró el archivo '{cfg.param('datos.ruta')}'."]
    return config_store.validate(cfg, list(df.columns), data_loader.numeric_columns(df))


@st.cache_data(show_spinner=False, max_entries=32)
def _impact(cfg_hash: str, data_path: str, mtime: float, _cfg: config_store.Config) -> dict:
    return impact.summarize(_load_clients(data_path, mtime, _cfg), _cfg)


def impact_summary(cfg: config_store.Config | None = None) -> dict:
    cfg = cfg or draft()
    path, mtime = _data_key(cfg.param("datos.ruta"))
    return _impact(config_store.config_hash(cfg), path, mtime, cfg)


@st.cache_data(show_spinner=False, max_entries=8)
def _profile(data_path: str, mtime: float, _cfg: config_store.Config):
    return impact.column_profile(_load_clients(data_path, mtime, _cfg))


def column_profile(cfg: config_store.Config | None = None):
    cfg = cfg or draft()
    path, mtime = _data_key(cfg.param("datos.ruta"))
    return _profile(path, mtime, cfg)


def apply_and_run(optimizer: str | None = None) -> dict:
    """Validate, snapshot + save the draft as the live config, then run the orchestrator."""
    errs = errors()
    if errs:
        raise config_store.ConfigError(errs)
    cfg = draft()
    config_store.save(cfg, note="Aplicado desde la consola")
    cfg.source = "activa"
    return execute(optimizer or st.session_state.get("optimizer", "greedy"))


def memo(run: dict, key: str, fn):
    """Per-run cache for derived figures (funnel, flows, downloads…): computed once per run."""
    cache = run.setdefault("_memo", {})
    if key not in cache:
        cache[key] = fn()
    return cache[key]


def run_config(cfg: config_store.Config, optimizer: str):
    """Run any configuration (e.g. a scenario) without touching the draft or the applied config."""
    path, mtime = _data_key(cfg.param("datos.ruta"))
    return _run(config_store.config_hash(cfg), optimizer, path, mtime, cfg)
