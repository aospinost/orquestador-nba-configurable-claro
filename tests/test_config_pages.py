"""The challenge's 7 change types, driven through the console widgets (headless AppTest)."""
import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from engine.config_store import ROOT

ENTRY = str(ROOT / "app" / "Inicio.py")


@pytest.fixture
def app():
    at = AppTest.from_file(ENTRY, default_timeout=180)
    at.run()
    assert not at.exception, at.exception
    return at


def goto(at, page):
    at.switch_page(f"paginas/{page}.py").run()
    assert not at.exception, at.exception
    return at


def draft(at):
    return at.session_state["draft_config"]


def by_key(widgets, prefix):
    found = [w for w in widgets if (w.key or "").startswith(prefix)]
    assert found, f"no widget with key {prefix}"
    return found[0]


def test_campaign_pause_without_delete(app):
    goto(app, "campanas")
    by_key(app.toggle, "camp_on_C-OTT").set_value(False).run()
    cfg = draft(app)
    assert [c.id for c in cfg.active_campaigns] == ["C-VCH", "C-TER"]
    assert "C-OTT" in [c.id for c in cfg.campaigns]          # paused, not deleted
    assert "1 cambio sin aplicar" in " ".join(str(h.proto) for h in app.get("html"))


def test_rule_builder_adds_rule(app):
    goto(app, "reglas")
    by_key(app.multiselect, "rb_nueva_0_vals").set_value(["C-OTT"]).run()
    by_key(app.selectbox, "rb_nueva_0_attr").set_value("calificacion_riesgo").run()
    by_key(app.selectbox, "rb_nueva_0_op").set_value("en").run()
    by_key(app.multiselect, "rb_nueva_0_val_calificacion_riesgo_en").set_value(["P"]).run()
    page_html = " ".join(str(h.proto) for h in app.get("html"))
    assert "15.028 clientes" in page_html                    # live counter
    by_key(app.button, "rb_nueva_0_save").click().run()
    assert not app.exception, app.exception
    r = {r.id: r for r in draft(app).rules}["R12"]
    assert (r.tipo, r.alcance_nivel, r.alcance_valores, r.condicion.atributo, r.condicion.valor) == (
        "elegibilidad", "campana", ["C-OTT"], "calificacion_riesgo", "P")


def test_rule_toggle_off(app):
    goto(app, "reglas")
    by_key(app.toggle, "rule_on_R03").set_value(False).run()
    assert not {r.id: r for r in draft(app).rules}["R03"].activa


def test_thresholds(app):
    goto(app, "prioridad_canales")
    by_key(app.slider, "up_").set_value(0.45).run()
    assert draft(app).param_float("priorizacion.umbral_score_producto") == 0.45


def test_priority_weights_and_hierarchy(app):
    goto(app, "prioridad_canales")
    by_key(app.slider, "w_score_producto").set_value(0.8).run()
    cfg = draft(app)
    w = [cfg.param_float(k) for k in cfg.params if k.startswith("priorizacion.pesos.")]
    assert abs(sum(w) - 1) < 1e-9 and cfg.param_float("priorizacion.pesos.score_producto") == 0.8
    by_key(app.button, "dn_C-VCH").click().run()
    assert draft(app).hierarchy() == ["C-TER", "C-VCH", "C-OTT"]
    by_key(app.radio, "mode_").set_value("jerarquia_estricta").run()
    assert draft(app).param("priorizacion.modo") == "jerarquia_estricta"


def test_channel_criterion(app):
    goto(app, "prioridad_canales")
    by_key(app.radio, "crit_").set_value("orden_preferencia").run()
    assert draft(app).param("canal.criterio") == "orden_preferencia"


def test_contact_policy(app):
    goto(app, "politica_contacto")
    by_key(app.number_input, "cap_").set_value(4).run()
    assert draft(app).param_int("politica_contacto.max_contactos_semana") == 4
    by_key(app.number_input, "rv_R11").set_value(3).run()
    assert {r.id: r for r in draft(app).rules}["R11"].condicion.valor == "3"
    by_key(app.number_input, "k_").set_value(2).run()
    assert draft(app).param_int("politica_contacto.canales_por_cliente") == 2


def test_new_data_column_is_announced_and_usable(app, tmp_path):
    raw = pd.read_csv(ROOT / "data" / "in" / "clientes 1.csv", dtype=str, keep_default_na=False).head(2000)
    raw["usa_app_claro"] = np.random.default_rng(1).integers(0, 2, len(raw)).astype(str)
    path = tmp_path / "clientes_con_columna.csv"
    raw.to_csv(path, index=False)
    draft(app).set_param("datos.ruta", str(path))
    goto(app, "datos")
    assert any("usa_app_claro" in str(s.proto) for s in app.success)
    goto(app, "reglas")
    assert "usa_app_claro" in by_key(app.selectbox, "rb_nueva").options or \
           "usa_app_claro" in by_key(app.selectbox, "rb_nueva_0_attr").options


def test_apply_saves_snapshot_and_runs(app, tmp_store):
    goto(app, "campanas")
    by_key(app.toggle, "camp_on_C-OTT").set_value(False).run()
    by_key(app.button, "impacto_apply").click().run()
    assert not app.exception, app.exception
    assert (tmp_store / "activa" / "config_campanas.csv").exists()
    assert len(list((tmp_store / "history").iterdir())) == 1
    run = app.session_state["runs"][-1]
    assert run["metrics"]["violaciones"] == 0 and "C-OTT" not in run["metrics"]["valor_por_campana"]


def test_discard_and_restore(app):
    goto(app, "prioridad_canales")
    by_key(app.slider, "up_").set_value(0.5).run()
    by_key(app.button, "impacto_discard").click().run()
    assert draft(app).param_float("priorizacion.umbral_score_producto") == 0.35


def test_new_campaign_form(app):
    goto(app, "campanas")
    ti = {t.label: t for t in app.text_input}
    ti["Código de producto"].set_value("seg")
    ti["Nombre visible"].set_value("Seguro de equipo")
    ti["…o un objetivo nuevo"].set_value("Fidelización")
    [s for s in app.selectbox if s.label.startswith("Columna con la propensión")][0].set_value("riesgo_churn")
    [b for b in app.button if b.label == "Crear campaña"][0].click().run()
    assert not app.exception, app.exception
    c = {c.id: c for c in draft(app).campaigns}["C-SEG"]
    assert (c.producto, c.objetivo, c.columna_score, c.rango_jerarquia) == ("SEG", "Fidelización", "riesgo_churn", 4)


def test_new_channel_form_and_run(app):
    goto(app, "prioridad_canales")
    ti = {t.label: t for t in app.text_input}
    ti["ID del canal"].set_value("tienda")
    ti["Nombre visible"].set_value("Tienda física")
    [s for s in app.selectbox if s.label.startswith("Columna con la probabilidad")][0].set_value("riesgo_churn")
    [n for n in app.number_input if n.label == "Cupo por corrida"][0].set_value(500)
    [m for m in app.multiselect if m.label.startswith("Campañas que pueden")][0].set_value(["C-VCH", "C-TER"])
    [b for b in app.button if b.label == "Agregar canal"][0].click().run()
    assert not app.exception, app.exception
    cfg = draft(app)
    assert "tienda" in [c.id for c in cfg.channels]
    assert "tienda" in {c.id: c for c in cfg.campaigns}["C-TER"].canales_permitidos
    by_key(app.button, "impacto_apply").click().run()
    assert not app.exception, app.exception
    m = app.session_state["runs"][-1]["metrics"]
    assert 0 < m["uso_capacidad"]["tienda"]["usado"] <= 500 and m["violaciones"] == 0
