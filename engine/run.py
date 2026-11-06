"""CLI: python -m engine.run --optimizer greedy --data "data/in/clientes 1.csv" --out data/out/parrilla_greedy.csv"""
from __future__ import annotations

import argparse
import sys
import time

from engine import config_store, data_loader, pipeline
from engine.config_store import ConfigError
from engine.explain import fmt
from engine.metrics import BASELINE


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Orquestador NBA — corrida por línea de comandos")
    ap.add_argument("--optimizer", default=None, help="greedy | milp (por defecto: optimizador.motor)")
    ap.add_argument("--data", default=None, help="CSV de clientes (por defecto: datos.ruta)")
    ap.add_argument("--out", default="data/out/parrilla.csv", help="CSV de salida (formato organizadores)")
    ap.add_argument("--extendida", default=None, help="CSV opcional con columnas extendidas")
    ap.add_argument("--config", default=None, help="Carpeta de configuración (por defecto: la activa)")
    ap.add_argument("--inicial", action="store_true", help="Usar la configuración inicial de los organizadores")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    t0 = time.perf_counter()
    cfg = (config_store.load_initial() if a.inicial
           else config_store.load_dir(a.config) if a.config else config_store.load())
    df = data_loader.load_clients(a.data or cfg.param("datos.ruta"), cfg)
    try:
        out = pipeline.run(cfg, df, a.optimizer)
    except ConfigError as e:
        print("Configuración inválida:")
        for err in e.errors:
            print("  -", err)
        return 2
    total = time.perf_counter() - t0

    path = data_loader.resolve_path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.parrilla.to_csv(path, index=False, encoding="utf-8")
    if a.extendida:
        ext = data_loader.resolve_path(a.extendida)
        out.result.assignment.to_csv(ext, index=False, encoding="utf-8")

    m = out.metrics
    print(f"Optimizador: {m['optimizador']}  ·  configuración {out.config_hash} ({cfg.source})")
    rows = [("Valor esperado", m["valor_esperado"], BASELINE["valor_esperado"], 1),
            ("Clientes con acción", m["clientes_con_accion"], BASELINE["clientes_con_accion"], 0),
            ("Productos asignados", m["productos_asignados"], BASELINE["productos_asignados"], 0),
            ("Indicador de jerarquía (%)", m["indicador_jerarquia"], BASELINE["indicador_jerarquia"], 1),
            ("Violaciones", m.get("violaciones", 0), BASELINE["violaciones"], 0)]
    print(f"{'Indicador':<28}{'Corrida':>14}{'Línea base':>14}{'Δ':>12}")
    for name, v, b, d in rows:
        print(f"{name:<28}{fmt(v, d):>14}{fmt(b, d):>14}{fmt(v - b, d):>12}")
    print("Uso de cupo: " + ", ".join(f"{c} {fmt(u['usado'], 0)}/{fmt(u['cupo'], 0)}"
                                     for c, u in m["uso_capacidad"].items()))
    if m["bono_reglas_blandas"]:
        print(f"Bono de reglas blandas (no suma al valor oficial): {fmt(m['bono_reglas_blandas'])}")
    for b in m["restricciones_negocio"]:
        print(f"Restricción {b['id']}: {fmt(b['valor_actual'])} {b['sentido']} {fmt(b['limite'])} "
              f"-> {'cumple' if b['cumple'] else 'NO cumple'}")
    if out.result.unsupported:
        print("Ignorado por este optimizador: " + "; ".join(out.result.unsupported))
    if out.validation is not None and out.validation.total:
        print(out.validation.summary[out.validation.summary["violaciones"] > 0].to_string(index=False))
    print("Tiempos (s): " + ", ".join(f"{k} {v:.1f}" for k, v in out.seconds.items()) + f", total {total:.1f}")
    print(f"Parrilla: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
