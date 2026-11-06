"""The validator must catch injected violations, mapped to the challenge's IDs."""
from engine import validator


def _count(report, id_):
    s = report.summary
    return int(s.loc[s["id"] == id_, "violaciones"].iloc[0])


def test_sixteen_constraints_listed(full_run):
    ids = list(full_run.validation.summary["id"])
    assert ids[:16] == [f"R{k:02d}" for k in range(1, 17)]
    assert full_run.validation.total == 0


def test_injected_violations(full_run, clients, initial_cfg):
    p = full_run.parrilla.copy()
    c = clients.set_index("id_cliente")

    def force(cid, canal, c1, c2=""):
        p.loc[p["id_cliente"] == cid, ["estado", "canal", "campana_1", "campana_2"]] = ["asignado", canal, c1, c2]

    mora = c.index[c["en_mora"] == 1][0]
    force(mora, "sms", "C-OTT")                               # R01 (+ maybe others)
    bad_cal = c.index[(c["calificacion_riesgo"] == "P") & (c["en_mora"] == 0)][0]
    force(bad_cal, "sms", "C-TER")                            # R02
    no_wa = c.index[c["autoriza_whatsapp"] == 0][0]
    force(no_wa, "whatsapp", "C-VCH")                         # R09
    asesor_ok = p.index[p["canal"] == "sms"][0]
    p.loc[asesor_ok, ["canal", "campana_1", "campana_2"]] = ["asesor", "C-OTT", ""]   # R12
    two = p.index[p["canal"] == "correo"][0]
    p.loc[two, "canal"] = "correo|sms"                        # R13
    week = c.index[c["contactos_semana_actual"] == 3][0]
    force(week, "sms", "C-OTT")                               # R15

    r = validator.validate(p, clients, initial_cfg)
    assert _count(r, "R01") >= 1 and mora in r.offending("R01")
    assert bad_cal in r.offending("R02")
    assert no_wa in r.offending("R09")
    assert _count(r, "R12") >= 1
    assert _count(r, "R13") == 1
    assert week in r.offending("R15")


def test_capacity_violation(full_run, clients, initial_cfg):
    p = full_run.parrilla.copy()
    idle = p.index[p["estado"] == "sin_accion"][:5]
    p.loc[idle, ["estado", "canal", "campana_1"]] = ["asignado", "asesor", "C-VCH"]
    r = validator.validate(p, clients, initial_cfg)
    assert _count(r, "R16") == 5


def test_missing_and_unknown_rows(full_run, clients, initial_cfg):
    p = full_run.parrilla.iloc[1:].copy()
    r = validator.validate(p, clients, initial_cfg)
    assert _count(r, "FORMATO") == 1
