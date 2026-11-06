"""Preprocessing (team model §5): split clients into posibles / eliminados before optimizing."""
import numpy as np
import pandas as pd

from engine import preprocess
from engine.config_store import ROOT


def ids(inp, idx):
    return set(inp.client_ids[idx])


def test_nobody_lost_or_repeated(full_run):
    """Every client is in exactly one of the two groups."""
    inp = full_run.inp
    posibles, eliminados = preprocess.split_clients(inp)
    assert len(posibles) + len(eliminados) == inp.n == 100_000
    assert len(np.intersect1d(posibles, eliminados)) == 0


def test_eliminados_never_get_an_action(full_run):
    """An eliminated client has no possible offer, so the parrilla must say sin_accion."""
    inp = full_run.inp
    _, eliminados = preprocess.split_clients(inp)
    estado = full_run.parrilla["estado"].to_numpy()
    assert (estado[eliminados] == "sin_accion").all()


def test_assigned_clients_are_posibles(full_run):
    """Everyone the optimizer assigned must be in the posibles group."""
    inp = full_run.inp
    posibles, _ = preprocess.split_clients(inp)
    assigned = np.flatnonzero(full_run.parrilla["estado"].to_numpy() == "asignado")
    assert set(assigned) <= set(posibles)


def test_doc_rules_r01_r07_r15_are_eliminated(full_run, clients):
    """The 3 rules of the team's document always eliminate the client."""
    inp = full_run.inp
    _, eliminados = preprocess.split_clients(inp)
    c = clients.reset_index(drop=True)
    num = lambda col: pd.to_numeric(c[col], errors="coerce").fillna(0)
    doc_rules = (num("en_mora") == 1) | (num("quejas_90d") >= 3) | (num("contactos_semana_actual") >= 3)
    assert set(np.flatnonzero(doc_rules)) <= set(eliminados)


def test_eliminados_have_a_reason(full_run):
    """Every eliminated client says in 'razon' why it was not valid."""
    _, eliminados = preprocess.split_clients(full_run.inp)
    razon = full_run.parrilla["razon"].to_numpy()[eliminados]
    assert all(r.startswith("Sin acción:") and len(r) > 20 for r in razon)


def test_reason_cites_the_rule_that_eliminated(full_run):
    """A client in mora is not valid because of R01, cited once and directly."""
    razon = full_run.parrilla.set_index("id_cliente").loc["CL000020", "razon"]
    assert razon == "Sin acción: cliente no válido por R01: Sin venta a clientes en mora (en_mora = 1)."
    razon = full_run.parrilla.set_index("id_cliente").loc["CL000089", "razon"]
    assert "P-TOPE-SEMANAL" in razon


def test_five_example_cases(full_run):
    """CL000020 (mora) and CL000089 (weekly cap) are eliminated; the other 3 are posibles."""
    inp = full_run.inp
    posibles, eliminados = preprocess.split_clients(inp)
    assert {"CL000020", "CL000089"} <= ids(inp, eliminados)
    assert {"CL000018", "CL000039", "CL000741"} <= ids(inp, posibles)
