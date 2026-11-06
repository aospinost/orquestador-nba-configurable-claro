"""Resultado / Decisión pages after a real run (headless AppTest)."""
import time

import pytest
from streamlit.testing.v1 import AppTest

from engine import scenarios
from engine.config_store import ROOT

ENTRY = str(ROOT / "app" / "Inicio.py")


def html(at) -> str:
    return " ".join(str(h.proto) for h in at.get("html"))


@pytest.fixture
def ran():
    at = AppTest.from_file(ENTRY, default_timeout=300)
    at.run()
    [b for b in at.button if b.label == "Ejecutar orquestador"][0].click().run()
    assert not at.exception, at.exception
    assert at.session_state["runs"][-1]["metrics"]["violaciones"] == 0
    return at


def goto(at, page):
    t = time.perf_counter()
    at.switch_page(f"paginas/{page}.py").run()
    assert not at.exception, at.exception
    return time.perf_counter() - t


@pytest.mark.parametrize("page", ["resumen", "parrilla", "explicabilidad", "validador", "simulador", "metodologia"])
def test_pages_render_after_run(ran, page):
    goto(ran, page)


def test_resumen_fast_and_complete(ran):
    goto(ran, "resumen")               # first render computes and memoizes the funnel / flows
    assert goto(ran, "resumen") < 3.0  # acceptance: < 3 s once cached
    text = html(ran)
    assert "10.241,5" in text and "55.393" in text and "Cumple las 16 restricciones" in text


def test_validator_sixteen_green(ran):
    goto(ran, "validador")
    text = html(ran)
    assert text.count("0 violaciones") >= 16
    assert "16 / 16" in text


def test_client_card(ran):
    goto(ran, "explicabilidad")
    ran.text_input(key="ficha_input").set_value("CL000741").run()
    assert not ran.exception, ran.exception
    text = html(ran)
    assert "CL000741" in text and "Guion" in text and "elegida" in text
    ran.button(key="btn_costs").click().run()
    assert not ran.exception, ran.exception


def test_simulator_compare_and_save(ran):
    goto(ran, "simulador")
    demo = next(iter(scenarios.demo_scenarios()))
    ran.multiselect[0].set_value(["aplicada", f"demo:{demo}"]).run()
    [b for b in ran.button if b.label == "Comparar escenarios"][0].click().run()
    assert not ran.exception, ran.exception
    sim = ran.session_state["sim"]
    assert len(sim["keys"]) == 2
    assert all(r["out"].metrics["violaciones"] == 0 for r in sim["results"].values())
    ran.text_input[0].set_value("Prueba").run()
    [b for b in ran.button if b.label == "Guardar escenario actual"][0].click().run()
    assert [s["nombre"] for s in scenarios.list_saved()] == ["Prueba"]


def test_run_comparison_section(ran):
    ran.session_state["draft_config"].set_param("canal.umbral_score_canal", "0.3")
    [b for b in ran.button if b.label == "Ejecutar orquestador"][0].click().run()
    goto(ran, "resumen")
    assert any("Dónde cambia" in str(md.proto) for md in ran.markdown)
