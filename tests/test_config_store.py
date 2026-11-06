import pandas as pd

from engine import config_store as cs


def test_migration_preserves_organizer_values(initial_cfg):
    cfg = initial_cfg
    ch = {c.id: c for c in cfg.channels}
    assert set(ch) == {"asesor", "whatsapp", "correo", "sms"}
    assert [ch[c].capacidad for c in ("asesor", "whatsapp", "correo", "sms")] == [2500, 15000, 30000, 40000]
    assert [ch[c].max_productos for c in ("asesor", "whatsapp", "correo", "sms")] == [1, 2, 2, 2]
    assert sorted(ch, key=lambda c: ch[c].orden_preferencia) == ["whatsapp", "correo", "sms", "asesor"]
    assert cfg.hierarchy() == ["C-VCH", "C-TER", "C-OTT"]
    org = pd.read_csv(cs.INITIAL_DIR / "config_reglas.csv", dtype=str, keep_default_na=False)
    mig = cfg.tables["reglas"][org.columns]
    pd.testing.assert_frame_equal(mig.reset_index(drop=True), org)
    assert cfg.param("priorizacion.umbral_score_producto") == "0.35"
    assert not any(k.startswith(cs.V1_CAPACITY_PREFIX) for k in cfg.params)


def test_initial_config_is_valid(initial_cfg, clients):
    from engine.data_loader import numeric_columns
    assert cs.validate(initial_cfg, list(clients.columns), numeric_columns(clients)) == []


def test_validation_messages(cfg, clients):
    cfg.set_param("priorizacion.pesos.jerarquia", "0.5")
    t = cfg.tables["canales"]
    t.loc[t["id"] == "asesor", "capacidad"] = "-1"
    c = cfg.tables["campanas"]
    c.loc[c["id"] == "C-OTT", "canales_permitidos"] = "whatsapp|telegrama"
    r = cfg.tables["reglas"]
    r.loc[r["id"] == "R03", "atributo"] = "columna_fantasma"
    r.loc[r["id"] == "R07", "operador"] = "~="
    errs = cs.validate(cfg, list(clients.columns))
    text = " ".join(errs)
    assert "pesos deben sumar 1" in text
    assert "cupo no puede ser negativo" in text
    assert "'telegrama' no existe" in text
    assert "'columna_fantasma' no es una columna" in text
    assert "operador '~=' desconocido" in text


def test_save_snapshot_and_restore(tmp_store, cfg):
    cfg.set_param("canal.umbral_score_canal", "0.3")
    snap = cs.save(cfg, note="prueba")
    assert (snap / "config_canales.csv").exists() and (snap / "nota.txt").exists()
    live = cs.load()
    assert live.param("canal.umbral_score_canal") == "0.3"
    d = cs.diff(cs.load_initial(), live)
    assert d == [{"tabla": "parametros", "clave": "canal.umbral_score_canal", "campo": "valor",
                  "antes": "0.25", "despues": "0.3"}]
    restored = cs.restore_initial()
    assert cs.config_hash(cs.load()) == cs.config_hash(restored) == cs.config_hash(cs.load_initial())
    assert len(cs.list_snapshots()) == 2


def test_save_rejects_invalid(tmp_store, cfg):
    cfg.set_param("priorizacion.pesos.jerarquia", "0.9")
    try:
        cs.save(cfg)
    except cs.ConfigError as e:
        assert any("pesos" in m for m in e.errors)
    else:
        raise AssertionError("save() debió rechazar la configuración")
    assert not (tmp_store / "activa").exists()


def test_bundle_roundtrip(cfg):
    again = cs.import_bundle(cs.export_bundle(cfg))
    assert cs.config_hash(again) == cs.config_hash(cfg)


def test_vigencia_and_pause(cfg):
    cfg.set_param("corrida.fecha", "2027-01-15")
    assert cfg.active_campaigns == []
    cfg.set_param("corrida.fecha", "2026-11-05")
    t = cfg.tables["campanas"]
    t.loc[t["id"] == "C-OTT", "activa"] = "0"
    assert [c.id for c in cfg.active_campaigns] == ["C-VCH", "C-TER"]
