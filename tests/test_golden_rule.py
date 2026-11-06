"""Golden rule: no product codes, campaign/channel names, rule IDs or data columns in engine/ code.

Checks identifiers and string literals (docstrings and comments are free text and may cite them).
"""
import ast
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FORMAT = {"id_cliente", "estado", "canal", "razon"}  # fixed by the organizers


def forbidden() -> set[str]:
    cfg = ROOT / "config"
    camp = pd.read_csv(cfg / "config_campanas.csv", dtype=str)
    rules = pd.read_csv(cfg / "config_reglas.csv", dtype=str)
    data_cols = pd.read_csv(ROOT / "data" / "in" / "clientes 1.csv", nrows=0).columns
    words = set(camp["id"]) | set(camp["producto"]) | set(rules["id"])
    words |= {c for v in camp["canales_permitidos"] for c in v.split("|")}
    words |= set(data_cols) - OUTPUT_FORMAT
    return words


def _literals(tree):
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            yield node.lineno, node.value
        elif isinstance(node, ast.Name):
            yield node.lineno, node.id


def test_no_hardcoded_business_values():
    words = forbidden()
    pattern = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, sorted(words, key=len, reverse=True))) + r")(?![\w-])")
    hits = []
    for path in (ROOT / "engine").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, text in _literals(tree):
            for m in pattern.finditer(text):
                hits.append(f"{path.relative_to(ROOT)}:{line}: {m.group(0)!r}")
    assert not hits, "Valores de negocio en el código:\n" + "\n".join(hits)
