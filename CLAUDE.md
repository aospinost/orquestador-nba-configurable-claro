# CLAUDE.md — Orquestador NBA Configurable (Hackatón Claro Colombia)

Read this file fully before writing code. It is the source of truth for scope, architecture and design.

## 1. What we are building
A Next Best Action (NBA) orchestrator that decides, for each of ~100,000 Claro clients, **which products (campaigns) to offer and through which channel**, maximising expected value without violating any business rule, and letting business change **every constant, parameter and rule from a console, never from code**.

- Engine: MILP modelled by a teammate (Juan Reina, see `docs/metodologia.md` once added). Do NOT invent modelling decisions; leave a TODO plus a config parameter. Until the MILP lands, the app runs on a **baseline greedy optimizer** behind the same interface.
- Console: a **Streamlit** app, Claro-branded, in **Spanish** (all UI text). Code, comments and identifiers in English.

### Golden rule (from the organizers)
> Any number or business rule must live in configuration, not in code.

No hard-coded product codes, channel names, thresholds, capacities, rule IDs, column names or the "3" of "three OTTs" anywhere in `engine/` or `app/`. Products, channels, rules, derived constants and business constraints are **dynamic sets read from config**. Adding a 5th channel, a 4th campaign, a new dummy or a new quota must work with zero code changes.

### Configurability principle (team decision)
The console must expose **every symbol of the mathematical model** as something editable or traceable:
1. **Scalars and per-entity constants** (VN_p, M_c, K_c, U_p, U_c, weights, time limit…) → editable fields.
2. **Client-level constants** (SC_i^c, SP_i^p) → column mappings (which column of the data feeds the symbol).
3. **Derived binary/numeric constants** (the model's "dummies": TER_i, TERm_i, H_i, Q_i^OTT, OF_i^p…) → defined in config with a no-code expression builder, never as Python code.
4. **Rules** (hard eligibility/channel exclusions, and optional soft bonuses/penalties) → rule builder.
5. **Business constraints** (linear quotas over the assignment: "at least 5.000 TER", "max 30 % of WhatsApp for OTT") → constraint builder, solved by the MILP.
Every one of these has an ID, a business-language name, an on/off switch, and is shown in the explanation of each decision.

## 2. Repo layout (existing, do not move)
- `docs/`: challenge statement + data dictionary (PDFs), plus our model doc.
- `config/config_campanas.csv`, `config/config_parametros.csv`, `config/config_reglas.csv`: organizers' initial configuration (keep them as the "Configuración inicial" that can always be restored).
- `examples/casos_ejemplo_clientes.csv` + `examples/casos_ejemplo_parrilla_esperada.csv`: 5 test cases with expected output.
- `data/in/clientes 1.csv`: real dataset (100k rows, 45 cols). Note the space in the filename.
- `data/out/`: parrillas (output CSVs).

## 3. Configuration schema v2 (organizers allow changing format if fields and meaning are kept)
All files live in `config/`; `config_store` loads v1 (organizers') files and migrates them to v2 transparently.

| File | Rows | Key fields |
|---|---|---|
| `config_campanas.csv` | one per campaign (index p) | id, nombre, producto, objetivo, columna_score (→ SP_i^p), valor_negocio (VN_p), canales_permitidos, vigencia_inicio/fin, activa, **umbral_score** (U_p override; blank = global), **rango_jerarquia** |
| `config_canales.csv` (new, migrated from `canal.*` params) | one per channel (index c) | id, nombre, columna_score (→ SC_i^c), capacidad (K_c), max_productos (M_c), **umbral_score** (U_c override; blank = global), columna_autorizacion (optional), orden_preferencia, activo |
| `config_parametros.csv` | key/value | global U_p and U_c defaults, priorización (modo, pesos, desempate), política de contacto, optimizer settings (`optimizador.motor`, `optimizador.tiempo_max_s`, `optimizador.gap`, `objetivo.peso_valor`, `objetivo.peso_jerarquia`) |
| `config_constantes.csv` (new) | one per derived constant | id (symbol, e.g. `TER_i`), nombre, tipo (binaria / numérica), nivel (cliente / cliente×campaña), expresión as rows of conditions: atributo, operador, valor, conector (Y/O), plus `por_campana` flag so `OF_i^p` = "producto de la campaña ∈ productos_ofertados_mes" is ONE definition, activa |
| `config_reglas.csv` | one per rule | organizers' fields (id, nombre, tipo, alcance_nivel, alcance_valores, atributo, operador, valor, accion, activa) + **accion** extended: `excluir` (hard) or `bonificar`/`penalizar` with **peso** (soft term in the objective). `atributo` may be a data column OR a derived constant ID. |
| `config_restricciones.csv` (new) | one per business constraint | id, nombre, campañas (list or *), canales (list or *), segmento (optional derived-constant/rule filter), métrica (contactos / productos / valor), sentido (<= / >=), valor, unidad (absoluto / % del total / % del canal), activa |

The **Model Registry** (`engine/model_registry.py`) is generated from these files and lists every symbol with: symbol, LaTeX, meaning (Spanish), source (file + field or column), current value or distribution, editable (yes/no). The UI and the methodology page render from it, so the math shown is always the math being solved.

## 4. Mapping of the team's model (Orquestador NBA Configurable, J. Reina) to config
| Model symbol / rule | Where it lives |
|---|---|
| p ∈ P, c ∈ C | rows of `config_campanas` / `config_canales` (active, in vigencia) |
| SC_i^c, SP_i^p | `columna_score` of channel / campaign |
| VN_p | `valor_negocio` |
| M_c, K_c | `max_productos`, `capacidad` |
| U_c, U_p | global default in parámetros + per-channel / per-campaign override |
| Channel activation + R14: Σ_p Z_i^{p,c} ≤ M_c Z_i^c | structural constraint (always on), uses M_c |
| R01 mora, R07 quejas, R15 tope semanal (preprocessing) | rules with `alcance_nivel = global`, the weekly cap value from `politica_contacto.max_contactos_semana` |
| R02 TER_i, R03 TERm_i, R04 H_i, R05 Q_i^OTT, R06 OF_i^p | derived constants in `config_constantes` + rules referencing them (thresholds 18 meses, letters E/A/B, "3" OTT all editable) |
| R08 U_p Z ≤ SP | product threshold (mask before solving) |
| R09–R12, R13, R16 | channel rules, `columna_autorizacion`, `canales_permitidos`, `politica_contacto.canales_por_cliente`, `capacidad` |
| Hierarchy (required by the challenge) | `rango_jerarquia` + `priorizacion.modo` + `objetivo.peso_jerarquia` |

Implementation note for the engine: hard rules and thresholds are applied as **masks** (variables never created) instead of millions of `Z ≤ constant` rows; mathematically identical to the model's constraints, much faster, and every masked pair keeps the ID of the rule that removed it.

## 5. Target architecture (to create)
```
app/
  Inicio.py                  # entrypoint: st.navigation + st.Page
  paginas/                   # one file per page (see PROMPTS). NOT "pages/": Streamlit auto-loads that name as legacy pages and deep links skip st.navigation
  ui/theme.py, ui/components.py, ui/builders.py   # builders = reusable condition/expression/constraint editors
  static/                    # logo (only if provided by organizers), fonts
.streamlit/config.toml
engine/
  config_store.py            # load v1/v2, migrate, validate, save snapshots, diff, export/import bundle (zip)
  model_registry.py          # symbol table described in §3
  data_loader.py             # load clientes csv, dtypes, pipe-list columns
  expressions.py             # vectorised evaluator of conditions (shared by constants, rules, segments)
  constants.py               # builds derived constants from config_constantes
  rules.py                   # GENERIC rule evaluator -> masks + soft-term matrices
  preprocess.py              # builds SolveInput
  optimizers/base.py, greedy.py, milp.py
  metrics.py, validator.py, explain.py, scenarios.py
tests/
```
`app/` never computes business logic; `engine/` never imports streamlit.

## 6. Optimizer contract
```python
@dataclass
class SolveInput:
    client_ids: np.ndarray            # (n,)
    campaigns: list[str]; channels: list[str]   # dynamic
    product_score: np.ndarray         # (n, P)  SP
    channel_score: np.ndarray         # (n, C)  SC
    business_value: np.ndarray        # (P,)    VN
    hierarchy_rank: np.ndarray        # (P,)
    eligible: np.ndarray              # (n, P) bool after hard rules + U_p
    channel_ok: np.ndarray            # (n, C) bool after hard rules + U_c
    allowed: np.ndarray               # (P, C) bool
    soft_bonus: np.ndarray            # (n, P, C) float, sum of active soft rules (0 if none)
    capacity: np.ndarray; max_products: np.ndarray   # (C,)
    channels_per_client: int
    client_active: np.ndarray         # (n,) bool
    business_constraints: list[BusinessConstraint]   # parsed config_restricciones
    exclusion_reasons: dict
    params: dict
    registry: ModelRegistry

@dataclass
class SolveResult:
    assignment: pd.DataFrame          # organizer format + extended cols
    objective: float; status: str; solve_seconds: float
    duals: dict | None                # {"capacity": {c: price}, "business": {constraint_id: price}}
    per_client_value: pd.Series
    unsupported: list[str]            # config features this optimizer ignored (e.g. greedy + business constraints)
    log: list[str]
```
Optimizers are registered in a dict; the UI lists them, shows which config features each supports, and compares runs.

## 7. Output format (fixed by organizers)
CSV, one row per client: `id_cliente, estado (asignado|sin_accion), canal, campana_1, campana_2, razon` (+ `campana_3…` only if some M_c > 2). `razon` must be understandable without the code and cite rule / constant / constraint IDs.

## 8. Metrics (fixed)
- Expected value = Σ assigned products of score_producto × score_canal × valor_negocio (soft bonuses are NOT part of the official metric; show them separately). Baseline 10.241,5.
- Violations of the 16 constraints → 0, checked by our independent `validator.py`.
- Hierarchy indicator (baseline 99,7 %), clients with action (55.393), products (70.443), capacity use per channel, status of each business constraint.

## 9. Rule / expression semantics
Operators: `==, !=, <, <=, >, >=, en, no_en, contiene`; `valor` may be a pipe list; `$producto` = product of the campaign evaluated. Conditions can be combined with Y/O in derived constants (rules stay single-condition as in the organizers' schema, but may point to a derived constant to express complex logic). Vectorised over 100k rows; type coercion from column dtype; empty list columns handled. Unknown column / operator / type mismatch → validation error in Spanish, never a crash. Implicit system rules from parameters get visible IDs: `P-UMBRAL-PROD`, `P-UMBRAL-CANAL`, `P-TOPE-SEMANAL`, `P-CANAL-PERMITIDO`, `P-AUTORIZACION`.

## 10. Brand & design system (Claro signage manual)
Palette: Rojo `#C22821` (primary, CTAs, key numbers), Gris `#BDC3B8` (secondary, dividers), Blanco `#FDFDFD` (background, cards), Negro `#332F2E` (text, dark bands).
Typography: Kamerik 105 Bold if the font files are in `app/static/fonts/`, else Google Font **Jost**. Uppercase section labels.
Shapes: white rounded-square tiles with centred red icon + uppercase label below; chunky rounded arrows; huge numerals for KPIs and section openers; 16 px radius cards, soft shadow, pill buttons.
Do NOT recreate Claro's logo; only use an official file dropped in `app/static/`.
Charts: Plotly template "claro" (red highlight, gray/dark rest), Colombian number format (1.234,5).

## 11. Engineering conventions
- Python 3.11, pinned `requirements.txt`; Streamlit with `st.navigation` and `[[theme.fontFaces]]`.
- `st.cache_data` keyed on config hash; never render 100k rows at once.
- All edits go through `config_store` → validate → timestamped snapshot in `config/history/` → live files. Each run stores its config hash. "Restaurar configuración inicial" always available.
- `pytest` after each phase; the 5 example cases are the acceptance test (with the initial config).
