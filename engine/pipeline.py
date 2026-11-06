"""End-to-end run: data + config -> SolveInput -> optimizer -> razon -> metrics -> validation."""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass

import pandas as pd

from engine import data_loader, explain, metrics, preprocess, validator
from engine.config_store import Config, ConfigError, config_hash, validate
from engine.optimizers import get_optimizer
from engine.optimizers.base import SolveInput, SolveResult

ORGANIZER_COLUMNS = ["id_cliente", "estado", "canal"]


@dataclass
class RunOutput:
    inp: SolveInput
    result: SolveResult
    metrics: dict
    validation: validator.ValidationReport | None
    config_hash: str
    timestamp: str
    seconds: dict

    @property
    def parrilla(self) -> pd.DataFrame:
        return to_parrilla(self.result.assignment)


def to_parrilla(assignment: pd.DataFrame) -> pd.DataFrame:
    """Organizer format: id_cliente, estado, canal, campana_1, campana_2 (+campana_3… if needed), razon."""
    camps = [c for c in assignment.columns if c.startswith("campana_")]
    keep = camps[:2] + [c for c in camps[2:] if (assignment[c] != "").any()]
    return assignment[ORGANIZER_COLUMNS + keep + ["razon"]]


def run(cfg: Config, df: pd.DataFrame | None = None, optimizer: str | None = None,
        validate_output: bool = True) -> RunOutput:
    t = {}
    t0 = time.perf_counter()
    if df is None:
        df = data_loader.load_clients(cfg.param("datos.ruta"), cfg)
    t["datos"] = time.perf_counter() - t0
    errors = validate(cfg, list(df.columns), data_loader.numeric_columns(df))
    if errors:
        raise ConfigError(errors)

    t0 = time.perf_counter()
    inp = preprocess.build_solve_input(df, cfg)
    t["reglas"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    opt = get_optimizer(optimizer or cfg.param("optimizador.motor", "greedy"))
    result = opt.solve(inp)
    t["optimizador"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    result.assignment["razon"] = explain.build_reasons(inp, result, df).to_numpy()
    t["explicacion"] = time.perf_counter() - t0

    m = metrics.compute(inp, result)
    report = None
    if validate_output:
        t0 = time.perf_counter()
        report = validator.validate(to_parrilla(result.assignment), df, cfg)
        t["validador"] = time.perf_counter() - t0
        m["violaciones"] = report.total
    return RunOutput(inp, result, m, report, config_hash(cfg), dt.datetime.now().isoformat(timespec="seconds"), t)
