"""Acceptance: the 5 example cases and the organizers' baseline figures, with the initial config."""
import time

import pandas as pd
import pytest

from engine import config_store, data_loader, pipeline
from engine.config_store import ROOT
from engine.metrics import BASELINE

COLS = ["estado", "canal", "campana_1", "campana_2"]


def test_example_rows_match_full_dataset(clients):
    ex = pd.read_csv(ROOT / "examples" / "casos_ejemplo_clientes.csv", dtype=str, keep_default_na=False)
    raw = pd.read_csv(ROOT / "data" / "in" / "clientes 1.csv", dtype=str, keep_default_na=False)
    merged = raw.set_index("id_cliente").loc[ex["id_cliente"]].reset_index()
    pd.testing.assert_frame_equal(merged[ex.columns], ex)


def test_five_example_cases(full_run):
    # The cases come from a full run (e.g. CL000741 gets sms because WhatsApp's capacity runs out).
    expected = pd.read_csv(ROOT / "examples" / "casos_ejemplo_parrilla_esperada.csv", dtype=str,
                           keep_default_na=False).set_index("id_cliente")
    got = full_run.parrilla.set_index("id_cliente").loc[expected.index]
    pd.testing.assert_frame_equal(got[COLS], expected[COLS])
    assert all(got["razon"].str.len() > 20)


def test_baseline_figures(full_run):
    m = full_run.metrics
    assert round(m["valor_esperado"], 1) == BASELINE["valor_esperado"]
    assert m["clientes_con_accion"] == BASELINE["clientes_con_accion"]
    assert m["productos_asignados"] == BASELINE["productos_asignados"]
    assert round(m["indicador_jerarquia"], 1) == BASELINE["indicador_jerarquia"]
    assert m["violaciones"] == 0
    for c, u in m["uso_capacidad"].items():
        assert u["usado"] <= u["cupo"], c


def test_output_format(full_run):
    p = full_run.parrilla
    assert list(p.columns) == ["id_cliente", "estado", "canal", "campana_1", "campana_2", "razon"]
    assert p["id_cliente"].is_unique and len(p) == 100_000
    assert set(p["estado"]) == {"asignado", "sin_accion"}
    assert (p.loc[p["estado"] == "sin_accion", ["canal", "campana_1", "campana_2"]] == "").all().all()


def test_full_run_under_60s(initial_cfg):
    t = time.perf_counter()
    df = data_loader.load_clients(initial_cfg.param("datos.ruta"), initial_cfg)
    pipeline.run(initial_cfg, df, "greedy")
    assert time.perf_counter() - t < 60


def test_live_config_reproduces_examples_too(tmp_store, clients):
    """Saving the migrated config as v2 and reloading it gives the same parrilla."""
    cfg = config_store.load_initial()
    config_store.save(cfg)
    again = config_store.load()
    assert again.source == "activa"
    assert config_store.config_hash(again) == config_store.config_hash(cfg)


@pytest.mark.parametrize("optimizer", ["milp"])
def test_milp_is_a_stub(full_run, optimizer):
    from engine.optimizers import get_optimizer
    with pytest.raises(NotImplementedError):
        get_optimizer(optimizer).solve(full_run.inp)
