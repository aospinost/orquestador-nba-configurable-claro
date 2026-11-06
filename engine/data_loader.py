"""Load the clients CSV with proper dtypes and parsed pipe-list columns."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from engine.config_store import LIST_SEP, ROOT, V2_DEFAULT_PARAMS, Config, load_dictionary, split_list

ID_COLUMN_PARAM = "datos.columna_id"
DEFAULT_ID_COLUMN = V2_DEFAULT_PARAMS[ID_COLUMN_PARAM]


def id_column(cfg: Config | None) -> str:
    return (cfg.param(ID_COLUMN_PARAM, "") if cfg else "") or DEFAULT_ID_COLUMN


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def detect_list_columns(df: pd.DataFrame) -> list[str]:
    """Text columns whose values contain the list separator in at least one row."""
    out = []
    for c in df.columns:
        if df[c].dtype == object and df[c].astype(str).str.contains(LIST_SEP, regex=False).any():
            out.append(c)
    return out


def load_clients(path: str | Path, cfg: Config | None = None) -> pd.DataFrame:
    """Read the CSV; numeric-looking columns become numbers, list columns become frozensets."""
    raw = pd.read_csv(resolve_path(path), dtype={id_column(cfg): str}, keep_default_na=False)
    return coerce(raw, cfg)


def coerce(raw: pd.DataFrame, cfg: Config | None = None) -> pd.DataFrame:
    """Numeric-looking text columns -> numbers (blank = NaN); list columns -> frozensets."""
    df = raw.copy()
    id_col = id_column(cfg)
    configured = cfg.param_list("datos.columnas_lista") if cfg else []
    list_cols = configured or detect_list_columns(df)
    for c in df.columns:
        if c == id_col or c in list_cols or pd.api.types.is_numeric_dtype(df[c]):
            continue
        s = df[c].astype(str).str.strip()
        nonblank = s[s != ""]
        num = pd.to_numeric(nonblank, errors="coerce")
        if len(nonblank) and num.notna().all():
            col = pd.to_numeric(s.replace("", np.nan), errors="coerce")
            if col.notna().all() and (col == col.round()).all():
                col = col.astype("int64")
            df[c] = col
        else:
            df[c] = s
    for c in list_cols:
        if c in df.columns:
            df[c] = df[c].map(lambda v: frozenset(split_list(v)))
    df.attrs["list_columns"] = [c for c in list_cols if c in df.columns]
    return df


def list_columns(df: pd.DataFrame) -> list[str]:
    return list(df.attrs.get("list_columns", []))


def numeric_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def quality_report(df: pd.DataFrame, dictionary: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per issue: columna, problema, filas, ejemplo."""
    dictionary = load_dictionary() if dictionary is None else dictionary
    rows = []
    known = set(dictionary["columna"])
    for c in df.columns:
        s = df[c]
        if s.dtype == object and not isinstance(s.iloc[0] if len(s) else "", frozenset):
            nulls = int((s.astype(str).str.strip() == "").sum())
        else:
            nulls = int(s.isna().sum())
        if nulls and c not in list_columns(df):
            rows.append({"columna": c, "problema": "valores vacíos", "filas": nulls, "ejemplo": ""})
        if c not in known:
            rows.append({"columna": c, "problema": "columna nueva (no está en el diccionario)",
                         "filas": len(df), "ejemplo": str(s.iloc[0]) if len(s) else ""})
    for d in dictionary.to_dict("records"):
        c = d["columna"]
        if c not in df.columns:
            rows.append({"columna": c, "problema": "columna del diccionario ausente en la base",
                         "filas": len(df), "ejemplo": ""})
            continue
        s = df[c]
        lo, hi = d.get("minimo", ""), d.get("maximo", "")
        if (lo or hi) and pd.api.types.is_numeric_dtype(s):
            bad = pd.Series(False, index=s.index)
            if lo:
                bad |= s < float(lo)
            if hi:
                bad |= s > float(hi)
            if bad.any():
                rows.append({"columna": c, "problema": f"fuera de rango [{lo}, {hi}]",
                             "filas": int(bad.sum()), "ejemplo": str(s[bad].iloc[0])})
        elif (lo or hi) and not pd.api.types.is_numeric_dtype(s):
            rows.append({"columna": c, "problema": "se esperaba un valor numérico", "filas": len(df),
                         "ejemplo": str(s.iloc[0])})
        allowed = split_list(d.get("valores", ""))
        if allowed and not (lo or hi):
            if c in list_columns(df):
                bad = s.map(lambda v: bool(set(v) - set(allowed)))
            else:
                bad = ~s.astype(str).isin(allowed)
            if bad.any():
                rows.append({"columna": c, "problema": "valores no previstos en el diccionario",
                             "filas": int(bad.sum()), "ejemplo": str(s[bad].iloc[0])})
    return pd.DataFrame(rows, columns=["columna", "problema", "filas", "ejemplo"])
