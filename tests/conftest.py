import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import config_store, data_loader, pipeline  # noqa: E402

ORGANIZER_FILES = [ROOT / "config" / f for f in
                   ("config_campanas.csv", "config_parametros.csv", "config_reglas.csv")] + [
    ROOT / "examples" / "casos_ejemplo_clientes.csv", ROOT / "examples" / "casos_ejemplo_parrilla_esperada.csv"]


def _digest(paths):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


@pytest.fixture(scope="session", autouse=True)
def organizer_files_untouched():
    before = _digest(ORGANIZER_FILES)
    yield
    assert _digest(ORGANIZER_FILES) == before, "Los archivos de los organizadores fueron modificados"


@pytest.fixture(scope="session")
def initial_cfg():
    return config_store.load_initial()


@pytest.fixture(scope="session")
def clients(initial_cfg):
    return data_loader.load_clients(initial_cfg.param("datos.ruta"), initial_cfg)


@pytest.fixture(scope="session")
def sample(clients):
    return clients.iloc[:5000].reset_index(drop=True)


@pytest.fixture(scope="session")
def full_run(initial_cfg, clients):
    return pipeline.run(initial_cfg, clients, "greedy")


@pytest.fixture
def cfg(initial_cfg):
    return initial_cfg.copy()


@pytest.fixture(autouse=True)
def tmp_store(tmp_path, monkeypatch):
    """Every test writes live config / history into a temp folder, never into config/."""
    monkeypatch.setattr(config_store, "LIVE_DIR", tmp_path / "activa")
    monkeypatch.setattr(config_store, "HISTORY_DIR", tmp_path / "history")
    return tmp_path
