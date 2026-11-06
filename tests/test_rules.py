"""Generic rules, derived constants and config-only extensions (new channel, new column)."""
import numpy as np
import pandas as pd

from engine import pipeline, preprocess
from engine.optimizers import get_optimizer


def add_rows(cfg, table, rows):
    cfg.tables[table] = pd.concat([cfg.tables[table], pd.DataFrame(rows)], ignore_index=True).fillna("")


def set_rule(cfg, rid, **kw):
    t = cfg.tables["reglas"]
    for k, v in kw.items():
        t.loc[t["id"] == rid, k] = v


def test_reasons_keep_every_rule(sample, cfg):
    inp = preprocess.build_solve_input(sample, cfg)
    by = inp.exclusion_reasons["campana"]
    mora = sample["en_mora"].to_numpy() == 1
    assert by["R01"][mora].all() and not by["R01"][~mora].any()
    assert set(inp.exclusion_reasons["canal"]) >= {"R08", "R09", "R10", "R11", "P-UMBRAL-CANAL"}


def test_derived_constants_reproduce_r02_and_r06(sample, cfg):
    base = preprocess.build_solve_input(sample, cfg)
    add_rows(cfg, "constantes", [
        {"id": "TER_i", "nombre": "Calificación apta para terminales", "tipo": "binaria", "nivel": "cliente",
         "por_campana": "0", "orden": "1", "atributo": "calificacion_riesgo", "operador": "en",
         "valor": "E|A|B", "conector": "", "activa": "1"},
        {"id": "OF_i", "nombre": "Producto ya ofertado en el mes", "tipo": "binaria", "nivel": "cliente_campana",
         "por_campana": "1", "orden": "1", "atributo": "productos_ofertados_mes", "operador": "contiene",
         "valor": "$producto", "conector": "", "activa": "1"},
    ])
    set_rule(cfg, "R02", atributo="TER_i", operador="==", valor="0")
    set_rule(cfg, "R06", atributo="OF_i", operador="==", valor="1")
    new = preprocess.build_solve_input(sample, cfg)
    assert np.array_equal(base.eligible, new.eligible)
    assert np.array_equal(base.exclusion_reasons["campana"]["R06"], new.exclusion_reasons["campana"]["R06"])


def test_constant_with_y_o_and_numeric(sample, cfg):
    add_rows(cfg, "constantes", [
        {"id": "N_OTT", "nombre": "OTT contadas", "tipo": "numerica", "nivel": "cliente", "por_campana": "0",
         "orden": str(k), "atributo": a, "operador": "", "valor": "1", "conector": "", "activa": "1"}
        for k, a in enumerate(["tiene_netflix", "tiene_amazon_prime", "tiene_win"])])
    inp = preprocess.build_solve_input(sample, cfg)
    assert np.array_equal(inp.constants["N_OTT"], sample["cantidad_ott"].to_numpy(float))


def test_soft_rule_changes_score_not_official_value(sample, cfg):
    add_rows(cfg, "reglas", [{"id": "R90", "nombre": "Bono a clientes digitales", "tipo": "canal",
                              "alcance_nivel": "global", "alcance_valores": "", "atributo": "usa_banca_digital",
                              "operador": "==", "valor": "1", "accion": "bonificar", "peso": "0.05",
                              "activa": "1"}])
    out = pipeline.run(cfg, sample, "greedy")
    assert out.metrics["bono_reglas_blandas"] > 0
    assert out.metrics["violaciones"] == 0


def test_new_channel_and_new_column_without_code(sample, cfg):
    df = sample.copy()
    rng = np.random.default_rng(0)
    df["score_canal_app"] = rng.uniform(0, 1, len(df))
    df["usa_app"] = rng.integers(0, 2, len(df))
    add_rows(cfg, "canales", [{"id": "app", "nombre": "App Mi Claro", "columna_score": "score_canal_app",
                               "capacidad": "300", "max_productos": "3", "umbral_score": "0.5",
                               "columna_autorizacion": "usa_app", "orden_preferencia": "5", "activo": "1"}])
    t = cfg.tables["campanas"]
    t["canales_permitidos"] = t["canales_permitidos"] + "|app"
    out = pipeline.run(cfg, df, "greedy")
    a = out.parrilla
    assert "app" in set(a["canal"]) and "campana_3" in a.columns
    assert out.metrics["uso_capacidad"]["app"]["usado"] <= 300
    app = a[a["canal"] == "app"]
    assert (df.set_index("id_cliente").loc[app["id_cliente"], "usa_app"] == 1).all()
    assert out.metrics["violaciones"] == 0


def test_rule_on_objective_group_and_toggle(sample, cfg):
    add_rows(cfg, "reglas", [{"id": "R91", "nombre": "Sin ventas a estrato 1", "tipo": "elegibilidad",
                              "alcance_nivel": "objetivo", "alcance_valores": "Venta cruzada|Terminales",
                              "atributo": "estrato", "operador": "==", "valor": "1", "accion": "excluir",
                              "peso": "", "activa": "1"}])
    inp = preprocess.build_solve_input(sample, cfg)
    e1 = sample["estrato"].to_numpy() == 1
    assert not inp.eligible[e1][:, :2].any()
    set_rule(cfg, "R91", activa="0")
    assert preprocess.build_solve_input(sample, cfg).eligible[e1][:, :2].any()


def test_strict_hierarchy_and_preference_order(sample, cfg):
    cfg.set_param("priorizacion.modo", "jerarquia_estricta")
    cfg.set_param("canal.criterio", "orden_preferencia")
    out = pipeline.run(cfg, sample, "greedy")
    assert out.metrics["indicador_jerarquia"] == 100.0
    assert out.metrics["violaciones"] == 0


def test_weekly_cap_and_multichannel(sample, cfg):
    cfg.set_param("politica_contacto.canales_por_cliente", "2")
    out = pipeline.run(cfg, sample, "greedy")
    a = out.parrilla
    multi = a[a["canal"].str.contains("|", regex=False)]
    assert len(multi) > 0
    week = sample.set_index("id_cliente").loc[multi["id_cliente"], "contactos_semana_actual"]
    assert (week + 2 <= 3).all()
    assert out.metrics["violaciones"] == 0
    assert get_optimizer("greedy").supports >= {"multicanal"}
