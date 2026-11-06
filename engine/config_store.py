"""Configuration store: load v1 (organizers) / v2 files, migrate, validate, save.

Layout:
- ``config/*.csv`` (v1, organizers): the "Configuración inicial". Never written.
- ``config/activa/*.csv`` (v2): the live configuration edited from the console.
- ``config/history/<timestamp>/``: snapshot written on every save.

If ``config/activa`` does not exist the live config is migrated in memory from
the organizers' files, so a fresh checkout always starts from the initial config.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INITIAL_DIR = ROOT / "config"
LIVE_DIR = ROOT / "config" / "activa"
HISTORY_DIR = ROOT / "config" / "history"
TRACEABILITY_FILE = ROOT / "config" / "trazabilidad_reto.csv"
DICTIONARY_FILE = ROOT / "config" / "diccionario_datos.csv"

LIST_SEP = "|"

# Organizers' v1 conventions, used ONLY to migrate v1 files (v1 has no channel table).
V1_CHANNEL_SCORE_PREFIX = "score_canal_"
V1_CAPACITY_PREFIX = "canal.capacidad_por_corrida."
V1_MAX_PRODUCTS_PREFIX = "politica_contacto.max_productos_por_canal."
V1_CHANNEL_ORDER_KEY = "canal.orden_preferencia"
V1_HIERARCHY_KEY = "priorizacion.jerarquia"

# Files and columns of the v2 schema (CLAUDE.md §3).
FILES = {
    "campanas": "config_campanas.csv",
    "canales": "config_canales.csv",
    "parametros": "config_parametros.csv",
    "constantes": "config_constantes.csv",
    "reglas": "config_reglas.csv",
    "restricciones": "config_restricciones.csv",
}
COLUMNS = {
    "campanas": ["id", "nombre", "producto", "objetivo", "columna_score", "valor_negocio",
                 "canales_permitidos", "vigencia_inicio", "vigencia_fin", "activa",
                 "umbral_score", "rango_jerarquia"],
    "canales": ["id", "nombre", "columna_score", "capacidad", "max_productos", "umbral_score",
                "columna_autorizacion", "orden_preferencia", "activo"],
    "parametros": ["parametro", "valor"],
    "constantes": ["id", "nombre", "tipo", "nivel", "por_campana", "orden", "atributo",
                   "operador", "valor", "conector", "activa"],
    "reglas": ["id", "nombre", "tipo", "alcance_nivel", "alcance_valores", "atributo",
               "operador", "valor", "accion", "peso", "activa"],
    "restricciones": ["id", "nombre", "campanas", "canales", "segmento", "metrica", "sentido",
                      "valor", "unidad", "activa"],
}

# Parameters added by the v2 schema, with their defaults (filled in when missing).
V2_DEFAULTS_FILE = ROOT / "config" / "parametros_v2_por_defecto.csv"
V2_DEFAULT_PARAMS = dict(pd.read_csv(V2_DEFAULTS_FILE, dtype=str, keep_default_na=False)[["parametro", "valor"]]
                         .itertuples(index=False, name=None))

OPERATORS = ["==", "!=", "<", "<=", ">", ">=", "en", "no_en", "contiene"]
RULE_TYPES = ["elegibilidad", "canal"]
SCOPE_LEVELS = ["global", "campana", "producto", "objetivo", "canal"]
RULE_ACTIONS = ["excluir", "bonificar", "penalizar"]
CONSTANT_TYPES = ["binaria", "numerica"]
CONSTANT_LEVELS = ["cliente", "cliente_campana"]
CONNECTORS = ["Y", "O"]
METRICS = ["contactos", "productos", "valor"]
SENSES = ["<=", ">="]
UNITS = ["absoluto", "pct_total", "pct_canal"]
PRIORITY_MODES_KEY = "priorizacion.modos_disponibles"
CHANNEL_CRITERIA_KEY = "canal.criterios_disponibles"
PRODUCT_PLACEHOLDER = "$producto"
ALL = "*"


# ---------------------------------------------------------------- typed views
def split_list(value) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [v.strip() for v in str(value).split(LIST_SEP) if v.strip()]


def to_bool(value) -> bool:
    return str(value).strip().lower() in {"1", "1.0", "true", "si", "sí", "yes", "y"}


def to_float(value, default: float | None = None) -> float | None:
    if value is None or str(value).strip() == "" or (isinstance(value, float) and pd.isna(value)):
        return default
    return float(str(value).replace(",", "."))


@dataclass
class Campaign:
    id: str
    nombre: str
    producto: str
    objetivo: str
    columna_score: str
    valor_negocio: float
    canales_permitidos: list[str]
    vigencia_inicio: dt.date | None
    vigencia_fin: dt.date | None
    activa: bool
    umbral_score: float | None
    rango_jerarquia: float


@dataclass
class Channel:
    id: str
    nombre: str
    columna_score: str
    capacidad: int
    max_productos: int
    umbral_score: float | None
    columna_autorizacion: str
    orden_preferencia: int
    activo: bool


@dataclass
class Condition:
    atributo: str
    operador: str
    valor: str
    conector: str = "Y"


@dataclass
class DerivedConstant:
    id: str
    nombre: str
    tipo: str
    nivel: str
    por_campana: bool
    condiciones: list[Condition]
    activa: bool


@dataclass
class Rule:
    id: str
    nombre: str
    tipo: str
    alcance_nivel: str
    alcance_valores: list[str]
    condicion: Condition
    accion: str
    peso: float
    activa: bool


@dataclass
class BusinessConstraint:
    id: str
    nombre: str
    campanas: list[str]  # ["*"] = all
    canales: list[str]
    segmento: str
    metrica: str
    sentido: str
    valor: float
    unidad: str
    activa: bool


def _date(value) -> dt.date | None:
    s = "" if value is None else str(value).strip()
    if not s or s.lower() == "nan":
        return None
    return dt.date.fromisoformat(s[:10])


@dataclass
class Config:
    """The whole v2 configuration as editable tables (strings) plus typed views."""
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    source: str = ""  # "inicial" | "activa" | "importada" | path

    # -- parameters
    @property
    def params(self) -> dict[str, str]:
        t = self.tables["parametros"]
        return {str(k).strip(): ("" if pd.isna(v) else str(v).strip())
                for k, v in zip(t["parametro"], t["valor"])}

    def param(self, key: str, default=None) -> str:
        v = self.params.get(key)
        return default if v is None else v

    def param_float(self, key: str, default: float | None = None) -> float | None:
        return to_float(self.params.get(key), default)

    def param_int(self, key: str, default: int | None = None) -> int | None:
        v = to_float(self.params.get(key), None)
        return default if v is None else int(v)

    def param_list(self, key: str) -> list[str]:
        return split_list(self.params.get(key))

    def nested_params(self) -> dict:
        out: dict = {}
        for k, v in self.params.items():
            node = out
            parts = k.split(".")
            for p in parts[:-1]:
                node = node.setdefault(p, {})
                if not isinstance(node, dict):
                    break
            else:
                node[parts[-1]] = v
        return out

    def set_param(self, key: str, value) -> None:
        t = self.tables["parametros"]
        mask = t["parametro"] == key
        if mask.any():
            t.loc[mask, "valor"] = str(value)
        else:
            self.tables["parametros"] = pd.concat(
                [t, pd.DataFrame([{"parametro": key, "valor": str(value)}])], ignore_index=True)

    def run_date(self) -> dt.date:
        return _date(self.param("corrida.fecha")) or dt.date.today()

    # -- typed views
    @property
    def campaigns(self) -> list[Campaign]:
        out = []
        for r in self.tables["campanas"].to_dict("records"):
            out.append(Campaign(
                id=str(r["id"]).strip(), nombre=str(r["nombre"]), producto=str(r["producto"]).strip(),
                objetivo=str(r["objetivo"]).strip(), columna_score=str(r["columna_score"]).strip(),
                valor_negocio=to_float(r["valor_negocio"], 0.0),
                canales_permitidos=split_list(r["canales_permitidos"]),
                vigencia_inicio=_date(r["vigencia_inicio"]), vigencia_fin=_date(r["vigencia_fin"]),
                activa=to_bool(r["activa"]), umbral_score=to_float(r.get("umbral_score")),
                rango_jerarquia=to_float(r.get("rango_jerarquia"), float("inf")),
            ))
        return out

    def campaign_in_force(self, c: Campaign) -> bool:
        d = self.run_date()
        return (c.activa and (c.vigencia_inicio is None or c.vigencia_inicio <= d)
                and (c.vigencia_fin is None or d <= c.vigencia_fin))

    @property
    def active_campaigns(self) -> list[Campaign]:
        return [c for c in self.campaigns if self.campaign_in_force(c)]

    @property
    def channels(self) -> list[Channel]:
        out = []
        for r in self.tables["canales"].to_dict("records"):
            out.append(Channel(
                id=str(r["id"]).strip(), nombre=str(r["nombre"]), columna_score=str(r["columna_score"]).strip(),
                capacidad=int(to_float(r["capacidad"], 0)), max_productos=int(to_float(r["max_productos"], 0)),
                umbral_score=to_float(r.get("umbral_score")),
                columna_autorizacion=_blank(r.get("columna_autorizacion")),
                orden_preferencia=int(to_float(r.get("orden_preferencia"), 999)),
                activo=to_bool(r["activo"]),
            ))
        return out

    @property
    def active_channels(self) -> list[Channel]:
        return [c for c in self.channels if c.activo]

    @property
    def constants(self) -> list[DerivedConstant]:
        t = self.tables["constantes"]
        out: list[DerivedConstant] = []
        if t.empty:
            return out
        t = t.copy()
        t["_orden"] = pd.to_numeric(t["orden"], errors="coerce").fillna(0)
        for cid, g in t.groupby("id", sort=False):
            g = g.sort_values("_orden", kind="stable")
            first = g.iloc[0]
            conds = [Condition(str(r["atributo"]).strip(), str(r["operador"]).strip(), _blank(r["valor"]),
                               (_blank(r["conector"]) or "Y").upper()) for _, r in g.iterrows()]
            out.append(DerivedConstant(
                id=str(cid).strip(), nombre=str(first["nombre"]), tipo=str(first["tipo"]).strip(),
                nivel=str(first["nivel"]).strip(), por_campana=to_bool(first["por_campana"]),
                condiciones=conds, activa=to_bool(first["activa"])))
        return out

    @property
    def rules(self) -> list[Rule]:
        out = []
        for r in self.tables["reglas"].to_dict("records"):
            out.append(Rule(
                id=str(r["id"]).strip(), nombre=str(r["nombre"]), tipo=str(r["tipo"]).strip(),
                alcance_nivel=str(r["alcance_nivel"]).strip(), alcance_valores=split_list(r["alcance_valores"]),
                condicion=Condition(str(r["atributo"]).strip(), str(r["operador"]).strip(), _blank(r["valor"])),
                accion=str(r["accion"]).strip(), peso=to_float(r.get("peso"), 0.0), activa=to_bool(r["activa"]),
            ))
        return out

    @property
    def business_constraints(self) -> list[BusinessConstraint]:
        out = []
        for r in self.tables["restricciones"].to_dict("records"):
            out.append(BusinessConstraint(
                id=str(r["id"]).strip(), nombre=str(r["nombre"]),
                campanas=split_list(r["campanas"]) or [ALL], canales=split_list(r["canales"]) or [ALL],
                segmento=_blank(r.get("segmento")), metrica=str(r["metrica"]).strip(),
                sentido=str(r["sentido"]).strip(), valor=to_float(r["valor"], 0.0),
                unidad=str(r["unidad"]).strip(), activa=to_bool(r["activa"])))
        return out

    def hierarchy(self) -> list[str]:
        """Active campaign IDs ordered by rango_jerarquia (most preferred first)."""
        cs = sorted(self.active_campaigns, key=lambda c: c.rango_jerarquia)
        return [c.id for c in cs]

    def copy(self) -> "Config":
        return Config({k: v.copy() for k, v in self.tables.items()}, self.source)


def _blank(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


# ---------------------------------------------------------------- load / migrate
def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _empty(name: str) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=str) for c in COLUMNS[name]})


def _conform(name: str, df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in COLUMNS[name]:
        if c not in df.columns:
            df[c] = ""
    extra = [c for c in df.columns if c not in COLUMNS[name]]
    return df[COLUMNS[name] + extra].fillna("").astype(str)


def migrate_v1(campanas: pd.DataFrame, parametros: pd.DataFrame, reglas: pd.DataFrame) -> Config:
    """Organizers' 3 files (v1) -> v2 tables. Semantics are preserved exactly."""
    params = dict(zip(parametros["parametro"].str.strip(), parametros["valor"].astype(str).str.strip()))

    # Channels: v1 stores them as dotted params; the score column follows the organizers' naming.
    names: list[str] = []
    for k in params:
        for prefix in (V1_CAPACITY_PREFIX, V1_MAX_PRODUCTS_PREFIX):
            if k.startswith(prefix) and k[len(prefix):] not in names:
                names.append(k[len(prefix):])
    order = split_list(params.get(V1_CHANNEL_ORDER_KEY, ""))
    canales = pd.DataFrame([{
        "id": n, "nombre": n.capitalize(), "columna_score": V1_CHANNEL_SCORE_PREFIX + n,
        "capacidad": params.get(V1_CAPACITY_PREFIX + n, "0"),
        "max_productos": params.get(V1_MAX_PRODUCTS_PREFIX + n, "1"),
        "umbral_score": "", "columna_autorizacion": "",
        "orden_preferencia": str(order.index(n) + 1 if n in order else len(order) + i + 1),
        "activo": "1",
    } for i, n in enumerate(names)])

    # Campaigns: hierarchy list -> rango_jerarquia; per-campaign threshold blank (= global).
    hierarchy = split_list(params.get(V1_HIERARCHY_KEY, ""))
    camp = campanas.copy()
    camp["umbral_score"] = camp.get("umbral_score", "")
    camp["rango_jerarquia"] = [str(hierarchy.index(i) + 1) if i in hierarchy else str(len(hierarchy) + k + 1)
                               for k, i in enumerate(camp["id"])]

    moved = (V1_CAPACITY_PREFIX, V1_MAX_PRODUCTS_PREFIX)
    kept = [(k, v) for k, v in params.items()
            if not k.startswith(moved) and k not in (V1_CHANNEL_ORDER_KEY, V1_HIERARCHY_KEY)]
    for k, v in V2_DEFAULT_PARAMS.items():
        if k not in params:
            kept.append((k, v))
    par = pd.DataFrame(kept, columns=["parametro", "valor"])

    reg = reglas.copy()
    if "peso" not in reg.columns:
        reg["peso"] = ""

    tables = {
        "campanas": _conform("campanas", camp),
        "canales": _conform("canales", canales),
        "parametros": _conform("parametros", par),
        "constantes": _empty("constantes"),
        "reglas": _conform("reglas", reg),
        "restricciones": _empty("restricciones"),
    }
    return Config(tables, source="inicial")


def _is_v2(directory: Path) -> bool:
    return (directory / FILES["canales"]).exists()


def load_dir(directory: Path) -> Config:
    directory = Path(directory)
    if not _is_v2(directory):
        return migrate_v1(_read(directory / FILES["campanas"]), _read(directory / FILES["parametros"]),
                          _read(directory / FILES["reglas"]))
    tables = {}
    for name, fname in FILES.items():
        p = directory / fname
        tables[name] = _conform(name, _read(p)) if p.exists() else _empty(name)
    # Fill parameters introduced after a snapshot was taken.
    cfg = Config(tables, source=str(directory))
    for k, v in V2_DEFAULT_PARAMS.items():
        if k not in cfg.params:
            cfg.set_param(k, v)
    return cfg


def load_initial() -> Config:
    cfg = load_dir(INITIAL_DIR)
    cfg.source = "inicial"
    return cfg


def load() -> Config:
    """Live config (config/activa) or, if never saved, the migrated initial config."""
    if _is_v2(LIVE_DIR):
        cfg = load_dir(LIVE_DIR)
        cfg.source = "activa"
        return cfg
    return load_initial()


def load_traceability() -> pd.DataFrame:
    return _read(TRACEABILITY_FILE)


def load_dictionary() -> pd.DataFrame:
    return _read(DICTIONARY_FILE)


# ---------------------------------------------------------------- hash / save / diff
def config_hash(cfg: Config) -> str:
    h = hashlib.sha256()
    for name in FILES:
        t = cfg.tables[name]
        h.update(name.encode())
        h.update(t.to_csv(index=False).encode())
    return h.hexdigest()[:12]


def _write_dir(cfg: Config, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, fname in FILES.items():
        cfg.tables[name].to_csv(directory / fname, index=False)


def save(cfg: Config, note: str = "", columns: list[str] | None = None) -> Path:
    """Validate, write a timestamped snapshot and update the live files. Returns the snapshot dir."""
    errors = validate(cfg, columns)
    if errors:
        raise ConfigError(errors)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    snap = HISTORY_DIR / f"{stamp}_{config_hash(cfg)}"
    _write_dir(cfg, snap)
    if note:
        (snap / "nota.txt").write_text(note, encoding="utf-8")
    _write_dir(cfg, LIVE_DIR)
    return snap


def restore_initial() -> Config:
    """Make the organizers' configuration the live one again (snapshot kept in history)."""
    cfg = load_initial()
    save(cfg, note="Restaurar configuración inicial")
    return cfg


def list_snapshots() -> list[Path]:
    if not HISTORY_DIR.exists():
        return []
    return sorted([p for p in HISTORY_DIR.iterdir() if p.is_dir()], reverse=True)


def diff(a: Config, b: Config) -> list[dict]:
    """Row-level differences between two configs: [{tabla, clave, campo, antes, despues}]."""
    out = []
    for name in FILES:
        key = "parametro" if name == "parametros" else "id"
        ta, tb = a.tables[name], b.tables[name]
        if name == "constantes":
            ta = ta.assign(_k=ta["id"] + "#" + ta["orden"])
            tb = tb.assign(_k=tb["id"] + "#" + tb["orden"])
            key = "_k"
        ra = {r[key]: r for r in ta.to_dict("records")}
        rb = {r[key]: r for r in tb.to_dict("records")}
        for k in ra.keys() | rb.keys():
            if k not in rb:
                out.append({"tabla": name, "clave": k, "campo": "(fila)", "antes": "existe", "despues": "eliminada"})
            elif k not in ra:
                out.append({"tabla": name, "clave": k, "campo": "(fila)", "antes": "", "despues": "nueva"})
            else:
                for col in COLUMNS[name]:
                    va, vb = str(ra[k].get(col, "")), str(rb[k].get(col, ""))
                    if va != vb:
                        out.append({"tabla": name, "clave": k, "campo": col, "antes": va, "despues": vb})
    return out


def export_bundle(cfg: Config) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, fname in FILES.items():
            z.writestr(fname, cfg.tables[name].to_csv(index=False))
        z.writestr("manifest.json", json.dumps({"hash": config_hash(cfg), "schema": 2}))
    return buf.getvalue()


def import_bundle(data: bytes) -> Config:
    tables = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        for name, fname in FILES.items():
            tables[name] = (_conform(name, pd.read_csv(z.open(fname), dtype=str, keep_default_na=False))
                            if fname in names else _empty(name))
    cfg = Config(tables, source="importada")
    for k, v in V2_DEFAULT_PARAMS.items():
        if k not in cfg.params:
            cfg.set_param(k, v)
    return cfg


def clear_live() -> None:
    """Remove the live directory (tests / hard reset). History is kept."""
    if LIVE_DIR.exists():
        shutil.rmtree(LIVE_DIR)


# ---------------------------------------------------------------- validation
class ConfigError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def validate(cfg: Config, columns: list[str] | None = None,
             numeric_columns: list[str] | None = None) -> list[str]:
    """Human-readable errors in Spanish. ``columns`` = columns of the loaded client data (optional)."""
    from engine import expressions  # local import: expressions depends on this module

    e: list[str] = []
    cols = set(columns) if columns is not None else None
    num_cols = set(numeric_columns) if numeric_columns is not None else None
    params = cfg.params

    def need_col(col: str, where: str, numeric: bool = False):
        if cols is not None and col and col not in cols:
            e.append(f"{where}: la columna '{col}' no existe en la base de clientes.")
        elif numeric and num_cols is not None and col in (cols or set()) and col not in num_cols:
            e.append(f"{where}: la columna '{col}' debe ser numérica.")

    # Channels
    channels = cfg.channels
    ch_ids = [c.id for c in channels]
    if len(set(ch_ids)) != len(ch_ids):
        e.append("Canales: hay identificadores de canal repetidos.")
    for c in channels:
        w = f"Canal '{c.id}'"
        if not c.id:
            e.append("Canales: hay un canal sin identificador.")
        if c.capacidad < 0:
            e.append(f"{w}: el cupo no puede ser negativo.")
        if c.max_productos < 1:
            e.append(f"{w}: debe caber al menos 1 producto por contacto.")
        if c.umbral_score is not None and not 0 <= c.umbral_score <= 1:
            e.append(f"{w}: el umbral de score debe estar entre 0 y 1.")
        need_col(c.columna_score, w, numeric=True)
        if c.columna_autorizacion:
            need_col(c.columna_autorizacion, w)
    if not cfg.active_channels:
        e.append("Canales: no hay ningún canal activo.")

    # Campaigns
    camps = cfg.campaigns
    camp_ids = [c.id for c in camps]
    if len(set(camp_ids)) != len(camp_ids):
        e.append("Campañas: hay identificadores de campaña repetidos.")
    for c in camps:
        w = f"Campaña '{c.id}'"
        if not 0 <= c.valor_negocio <= 1:
            e.append(f"{w}: el valor de negocio debe estar entre 0 y 1.")
        if c.umbral_score is not None and not 0 <= c.umbral_score <= 1:
            e.append(f"{w}: el umbral de score debe estar entre 0 y 1.")
        for ch in c.canales_permitidos:
            if ch not in ch_ids:
                e.append(f"{w}: el canal permitido '{ch}' no existe o no tiene cupo configurado.")
        if not c.canales_permitidos:
            e.append(f"{w}: no tiene canales permitidos.")
        if c.vigencia_inicio and c.vigencia_fin and c.vigencia_inicio > c.vigencia_fin:
            e.append(f"{w}: la vigencia termina antes de empezar.")
        need_col(c.columna_score, w, numeric=True)
    if not cfg.active_campaigns:
        e.append("Campañas: no hay ninguna campaña activa y vigente en la fecha de corrida.")

    # Parameters
    def num(key, lo=None, hi=None, integer=False):
        v = params.get(key, "")
        try:
            x = float(v.replace(",", "."))
        except ValueError:
            e.append(f"Parámetro '{key}': '{v}' no es un número.")
            return None
        if integer and x != int(x):
            e.append(f"Parámetro '{key}': debe ser un número entero.")
        if (lo is not None and x < lo) or (hi is not None and x > hi):
            e.append(f"Parámetro '{key}': {v} está fuera del rango permitido.")
        return x

    weights = [k for k in params if k.startswith("priorizacion.pesos.")]
    ws = [num(k, 0, 1) for k in weights]
    if ws and None not in ws and abs(sum(ws) - 1) > 1e-6:
        e.append(f"Prioridad: los pesos deben sumar 1 (hoy suman {sum(ws):.3f}).".replace(".", ",", 1))
    num("priorizacion.umbral_score_producto", 0, 1)
    num("canal.umbral_score_canal", 0, 1)
    num("politica_contacto.canales_por_cliente", 1, None, integer=True)
    num("politica_contacto.max_contactos_semana", 0, None, integer=True)
    num("priorizacion.decimales_puntaje", 0, 15, integer=True)
    modes = cfg.param_list(PRIORITY_MODES_KEY)
    if modes and params.get("priorizacion.modo") not in modes:
        e.append(f"Prioridad: el modo '{params.get('priorizacion.modo')}' no es uno de {', '.join(modes)}.")
    crit = cfg.param_list(CHANNEL_CRITERIA_KEY)
    if crit and params.get("canal.criterio") not in crit:
        e.append(f"Canales: el criterio '{params.get('canal.criterio')}' no es uno de {', '.join(crit)}.")
    need_col(params.get("politica_contacto.columna_contactos_semana", ""), "Política de contacto", numeric=True)
    if params.get("corrida.fecha"):
        try:
            _date(params["corrida.fecha"])
        except ValueError:
            e.append(f"Parámetro 'corrida.fecha': '{params['corrida.fecha']}' no es una fecha AAAA-MM-DD.")

    # Derived constants
    const_ids: list[str] = []
    for k in cfg.constants:
        w = f"Constante '{k.id}'"
        if k.tipo not in CONSTANT_TYPES:
            e.append(f"{w}: tipo '{k.tipo}' desconocido (use {' o '.join(CONSTANT_TYPES)}).")
        if k.nivel not in CONSTANT_LEVELS:
            e.append(f"{w}: nivel '{k.nivel}' desconocido.")
        if k.id in (cols or set()):
            e.append(f"{w}: el identificador coincide con una columna de la base.")
        for cond in k.condiciones:
            if k.tipo == "binaria":
                e += [f"{w}: {m}" for m in expressions.check_condition(cond, cols, num_cols, const_ids)]
            else:
                if cols is not None and cond.atributo not in cols and cond.atributo not in const_ids:
                    e.append(f"{w}: '{cond.atributo}' no es una columna ni una constante definida antes.")
                if to_float(cond.valor, 1.0) is None:
                    e.append(f"{w}: el peso '{cond.valor}' no es numérico.")
            if cond.conector not in CONNECTORS:
                e.append(f"{w}: conector '{cond.conector}' desconocido (use Y u O).")
        const_ids.append(k.id)
    if len(set(const_ids)) != len(const_ids):
        e.append("Constantes: hay identificadores repetidos.")

    # Rules
    rule_ids = [r.id for r in cfg.rules]
    if len(set(rule_ids)) != len(rule_ids):
        e.append("Reglas: hay identificadores de regla repetidos.")
    products = {c.producto for c in camps}
    objectives = {c.objetivo for c in camps}
    for r in cfg.rules:
        w = f"Regla '{r.id}'"
        if r.tipo not in RULE_TYPES:
            e.append(f"{w}: tipo '{r.tipo}' desconocido (use elegibilidad o canal).")
        if r.alcance_nivel not in SCOPE_LEVELS:
            e.append(f"{w}: alcance '{r.alcance_nivel}' desconocido.")
        elif r.tipo == "elegibilidad" and r.alcance_nivel == "canal":
            e.append(f"{w}: una regla de elegibilidad no puede tener alcance 'canal'; use tipo 'canal'.")
        elif r.tipo == "canal" and r.alcance_nivel not in ("global", "canal"):
            e.append(f"{w}: una regla de canal solo admite alcance 'global' o 'canal'.")
        valid = {"campana": set(camp_ids), "producto": products, "objetivo": objectives,
                 "canal": set(ch_ids)}.get(r.alcance_nivel)
        if valid is not None:
            if not r.alcance_valores:
                e.append(f"{w}: debe indicar a qué {r.alcance_nivel} aplica.")
            for v in r.alcance_valores:
                if v not in valid:
                    e.append(f"{w}: '{v}' no es un(a) {r.alcance_nivel} configurado(a).")
        if r.accion not in RULE_ACTIONS:
            e.append(f"{w}: acción '{r.accion}' desconocida (use {', '.join(RULE_ACTIONS)}).")
        elif r.accion != "excluir" and r.peso <= 0:
            e.append(f"{w}: una regla de {r.accion} necesita un peso mayor que 0.")
        e += [f"{w}: {m}" for m in expressions.check_condition(r.condicion, cols, num_cols, const_ids)]

    # Business constraints
    for b in cfg.business_constraints:
        w = f"Restricción '{b.id}'"
        for c in b.campanas:
            if c != ALL and c not in camp_ids:
                e.append(f"{w}: la campaña '{c}' no existe.")
        for c in b.canales:
            if c != ALL and c not in ch_ids:
                e.append(f"{w}: el canal '{c}' no existe.")
        if b.segmento and b.segmento not in const_ids:
            e.append(f"{w}: el segmento '{b.segmento}' debe ser una constante derivada binaria.")
        if b.metrica not in METRICS:
            e.append(f"{w}: métrica '{b.metrica}' desconocida (use {', '.join(METRICS)}).")
        if b.sentido not in SENSES:
            e.append(f"{w}: sentido '{b.sentido}' desconocido (use <= o >=).")
        if b.unidad not in UNITS:
            e.append(f"{w}: unidad '{b.unidad}' desconocida (use {', '.join(UNITS)}).")
        if b.valor < 0:
            e.append(f"{w}: el valor no puede ser negativo.")
    return e


# ---------------------------------------------------------------- edit helpers (used by the console)
def next_id(existing: list[str], prefix: str, width: int = 2) -> str:
    """Next free ID like R12 / N01 given the existing ones."""
    nums = [int(e[len(prefix):]) for e in existing if e.startswith(prefix) and e[len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) + 1 if nums else 1):0{width}d}"


def upsert_row(cfg: Config, table: str, row: dict, key: str = "id", old_key: str | None = None) -> None:
    """Insert or replace the row whose ``key`` equals ``old_key`` (default row[key]). Stored as text."""
    t = cfg.tables[table]
    clean = {c: ("" if row.get(c) is None else str(row.get(c))) for c in COLUMNS[table]}
    mask = t[key] == (old_key or clean[key])
    if mask.any():
        for c, v in clean.items():
            t.loc[mask, c] = v
    else:
        cfg.tables[table] = pd.concat([t, pd.DataFrame([clean])], ignore_index=True)


def delete_row(cfg: Config, table: str, value: str, key: str = "id") -> None:
    t = cfg.tables[table]
    cfg.tables[table] = t[t[key] != value].reset_index(drop=True)


def replace_constant(cfg: Config, cid: str, rows: list[dict], old_id: str | None = None) -> None:
    """Replace every condition row of a derived constant (each row carries id/nombre/tipo/...)."""
    delete_row(cfg, "constantes", old_id or cid)
    if rows:
        new = pd.DataFrame([{c: ("" if r.get(c) is None else str(r.get(c))) for c in COLUMNS["constantes"]}
                            for r in rows])
        cfg.tables["constantes"] = pd.concat([cfg.tables["constantes"], new], ignore_index=True)
