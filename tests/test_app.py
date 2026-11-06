"""Headless smoke tests of the Streamlit shell (no browser)."""
import pytest
from streamlit.testing.v1 import AppTest

from engine.config_store import ROOT

ENTRY = str(ROOT / "app" / "Inicio.py")
PAGES = ["resumen", "parrilla", "explicabilidad", "datos", "campanas", "reglas", "prioridad_canales",
         "politica_contacto", "simulador", "validador", "metodologia", "_estilo"]


def html_text(at) -> str:
    return " ".join(str(getattr(e, "proto", e)) for e in at.get("html"))


@pytest.fixture
def app():
    at = AppTest.from_file(ENTRY, default_timeout=120)
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders(app, page):
    app.switch_page(f"pages/{page}.py").run()
    assert not app.exception, app.exception


def test_banner_only_with_unapplied_changes(app):
    assert "sin aplicar" not in html_text(app)
    app.session_state["draft_config"].set_param("canal.umbral_score_canal", "0.3")
    app.run()
    assert "Tienes 1 cambio sin aplicar" in html_text(app)


def test_run_button_executes_and_applies(app):
    milp_ok = [o for o in app.selectbox[0].options if "construcción" in o]
    assert milp_ok, "MILP debe aparecer como en construcción"
    app.session_state["draft_config"].set_param("canal.umbral_score_canal", "0.3")
    app.button[0].click().run()
    assert not app.exception, app.exception
    runs = app.session_state["runs"]
    assert len(runs) == 1 and runs[0]["metrics"]["violaciones"] == 0
    assert "sin aplicar" not in html_text(app)
