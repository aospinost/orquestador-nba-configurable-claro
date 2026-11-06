# Prompts for Claude Code — Consola del Orquestador NBA

**How to use:** put `CLAUDE.md` in the repo root (Claude Code loads it automatically). Then paste the prompts below **one at a time**, in order. Review and run the app (`streamlit run app/Inicio.py`) after each phase before moving on. Each prompt ends with acceptance criteria — ask Claude Code to verify them before it says it's done.

---

## Phase 0 — Plan first (no code)

```
Read CLAUDE.md, every file in config/ and examples/, and the two PDFs in docs/. Also read the header + first 20 rows of "data/in/clientes 1.csv".
Do NOT write code yet. Reply with:
1. A summary of the 16 mandatory constraints and, for each, whether it is represented by config_reglas.csv, by config_parametros.csv, by config_campanas.csv, or not represented at all (gap).
2. Any inconsistency you find between the PDFs and the config CSVs (rule numbering differs between the statement and config_reglas — map them).
3. The file-by-file plan for the architecture in CLAUDE.md §3, and the exact requirements.txt.
Wait for my OK.
```

---

## Phase 1 — Engine skeleton that works end-to-end (baseline)

```
Implement engine/ per CLAUDE.md §3–§7:
- data_loader.py: load clientes CSV (path configurable), coerce dtypes, parse pipe-list columns into sets, report data-quality issues (nulls, out-of-range vs dictionary) as a DataFrame.
- config_store.py: load the 3 CSVs into typed objects (Campaign, Rule, Params with dotted keys -> nested dict). validate() returns a list of human-readable errors in Spanish (e.g. weights don't sum 1, unknown column in a rule, capacity < 0, channel in canales_permitidos without capacity). save() writes a timestamped snapshot to config/history/ and updates live CSVs. config_hash().
- rules.py: generic, vectorised evaluator for every operator incl. "en", "no_en", "contiene" and "$producto". Returns eligible (n,P), channel_ok (n,C), client_active (n,), and a reasons structure. No rule ID may appear as a literal in code. Implicit system rules from parameters get IDs P-UMBRAL-PROD, P-UMBRAL-CANAL, P-TOPE-SEMANAL, P-CANAL-PERMITIDO, P-TOPE-ASESOR if applicable.
- preprocess.py: build SolveInput.
- optimizers/base.py (dataclasses + Protocol + registry), optimizers/greedy.py reproducing the organizers' baseline exactly (score = w1*score_producto + w2*valor_negocio + w3*nivel_jerarquia with levels 1, 0.5, 0 generalised as linear from 1 to 0 over the hierarchy length; sort clients; best permitted channel with remaining capacity by score_canal or by orden_preferencia depending on canal.criterio; fill up to max_products), optimizers/milp.py as a stub that raises NotImplementedError with a docstring describing the expected model and the duals it must return.
- metrics.py and validator.py (validator re-checks all 16 constraints from raw data + config, independent of rules.py, and returns a per-constraint violation count + offending ids).
- explain.py: build the razon string per client in Spanish, e.g. "Asignado por WhatsApp (mejor canal habilitado con cupo). C-VCH (valor 0,31) + C-OTT (valor 0,08). Excluido: C-TER por R03 (equipo de 12 meses < 18)." For sin_accion, list the rules that blocked each campaign/channel, or "Cupo agotado en canales elegibles: asesor, whatsapp".
- A CLI: `python -m engine.run --optimizer greedy --data "data/in/clientes 1.csv" --out data/out/parrilla_greedy.csv` printing all metrics.
Tests: tests/test_examples.py must reproduce estado/canal/campana_1/campana_2 of examples/casos_ejemplo_parrilla_esperada.csv for the 5 cases. Run the CLI on the full dataset and report value, clients with action, products, hierarchy % and violations; compare with the baseline (10.241,5 / 55.393 / 70.443 / 99,7% / 0) and explain any difference.
Acceptance: pytest green, 0 violations, full run < 60 s.
```

---

## Phase 2 — Claro design system + app shell

```
Create the Streamlit shell and design system per CLAUDE.md §8. No business pages yet, just the frame.
- .streamlit/config.toml: theme with primaryColor #C22821, backgroundColor #FDFDFD, secondaryBackgroundColor #F2F3F0 (a light tint of #BDC3B8), textColor #332F2E, base light; fonts via [[theme.fontFaces]] (Kamerik 105 if files exist in app/static/fonts, else Jost from Google Fonts); enableStaticServing = true.
- ui/theme.py: palette constants, inject_css() (cards 16px radius, soft shadow, pill buttons, uppercase section labels with letter-spacing, red underline on active nav, dark #332F2E hero band), a Plotly template "claro" (red highlight, gray/dark others, Jost font, Spanish separators), fmt_num()/fmt_pct() in Colombian format.
- ui/components.py: hero(title, subtitle, big_numeral) inspired by the manual's section openers (huge numeral at right), kpi_card(label, value, delta_vs_baseline, icon) with big bold numbers, tile(icon, LABEL) = white rounded square, red Material icon, uppercase label below (signage style), rule_chip(rule_id, state), status_badge(asignado/sin_accion), step_header(n, title) with a large red numeral.
- app/Inicio.py with st.navigation grouped in sections:
  "Resultado": Resumen ejecutivo, Parrilla, Explicabilidad
  "Configuración": Datos, Campañas, Reglas, Prioridad y canales, Política de contacto
  "Decisión": Simulador ¿Qué pasa si?, Validador, Metodología
  Use :material/...: icons. Sidebar: config version + hash, selected optimizer (greedy | milp — milp disabled with tooltip "En construcción" until implemented), a red "Ejecutar orquestador" button, last run timestamp.
- Session state model: st.session_state["draft_config"] (being edited) vs ["applied_config"] (last run), and ["runs"] (list of SolveResult + metrics + config hash). A global banner appears when draft != applied: "Tienes N cambios sin aplicar · Ver impacto".
- Create a hidden page "_Estilo" showing every component, palette and chart template for visual QA.
Acceptance: app launches, navigation works, the style page looks like the Claro manual (red/white/gray/black, rounded tiles, big numerals), works at 1366px and on a projector (min font 15px, contrast AA).
```

---

## Phase 3 — Configuration pages (business edits without code)

```
Build the Configuración pages. All of them edit draft_config only; nothing runs until "Aplicar". Each page shows validation errors inline (from config_store.validate) and a "Vista previa de impacto" card (see below).

1. Datos: upload a new clientes CSV or use data/in; show rows, columns, data-quality table, and a "Columnas nuevas" box that detects columns not in the dictionary and announces they are now available in the rule builder (challenge change type "Datos").
2. Campañas: grid of campaign cards (tile style) + st.data_editor for: nombre, producto, objetivo, columna_score (selectbox of numeric columns), valor_negocio (0–1 slider), canales_permitidos (multiselect from the channel list in params), vigencia, activa toggle ("Pausar sin borrar"). Button "Nueva campaña" with a form. Campaigns outside vigencia are shown greyed with a reason.
3. Reglas: a rule builder that reads like a sentence:
   "[Excluir] [campañas: C-TER ▾ | objetivo | producto | canal | todas] cuando [columna ▾] [operador ▾] [valor]"
   - valor widget adapts to dtype (multiselect of unique values for categories, number input for numerics, "$producto" option for list columns).
   - live counter: "Esta regla afecta a 12.431 clientes (12,4 %)" computed on the loaded data.
   - table of all rules with on/off toggles, scope chips, the business-language name, and the last-run count of exclusions. Edit/duplicate/delete. IDs auto-generated (next free R##).
4. Prioridad y canales:
   - hierarchy: drag-and-drop ordering of campaigns (streamlit-sortables; fallback up/down buttons).
   - modo: ponderado | jerarquia_estricta (radio with a one-line explanation of each).
   - weights: three linked sliders (modelo / valor de negocio / jerarquía) that always sum to 1, plus a stacked bar showing the mix.
   - thresholds: umbral_score_producto, umbral_score_canal with a histogram of the score distribution and a vertical red line at the threshold showing how many clients/pairs fall below.
   - channels: table with capacity, max products per contact, criterio (score_canal | orden_preferencia), orden_preferencia (sortable), and "Agregar canal" (name, score column, capacity, max products, authorization column optional).
5. Política de contacto: canales_por_cliente, max_contactos_semana, tope de llamadas de asesor (wired to the corresponding rule value), each with a "clientes afectados" counter.

"Vista previa de impacto" (shared component, used on every config page): runs rules.py only (fast, cached) on draft vs applied and shows deltas: eligible client-campaign pairs, clients with ≥1 eligible campaign, eligible client-channel pairs. Then a button "Aplicar y re-optimizar".
Acceptance: each of the 7 change types in the challenge (Campañas, Reglas, Umbrales, Prioridad, Canales y cupos, Política, Datos) can be done from the UI with no code; I want a short checklist at the end showing the exact clicks for each one.
```

---

## Phase 4 — Results, explainability and validation

```
Build the Resultado and Decisión pages.

1. Resumen ejecutivo (landing page, this is our pitch screen):
   - hero: "Orquestador NBA · Claro Colombia" with the run's expected value as a giant numeral.
   - KPI row: Valor esperado (Δ vs línea base 10.241,5 and Δ % ), Clientes con acción, Productos asignados, Indicador de jerarquía, Violaciones (big green 0 / red if >0), Tiempo de cómputo.
   - Funnel/waterfall "De 100.000 clientes a la parrilla": total → after global rules (one bar per rule) → with ≥1 eligible campaign → with ≥1 eligible channel → assigned. Each step labelled with its rule ID and name.
   - Sankey campaña → canal (widths = clients), channel capacity utilisation bars (used vs cupo, red when 100%).
   - "Valor por canal" and "Valor por campaña" bars.
   - If ≥2 runs exist (e.g. greedy vs milp), a comparison table + "dónde gana el optimizador": value delta by channel and number of clients that switched channel.
2. Parrilla: filterable table (estado, canal, campaña, región, estrato), paginated; download CSV in the exact organizer format; download a "parrilla extendida" with value per product and scores.
3. Explicabilidad:
   - Ficha de cliente: search by id_cliente → profile card + a checklist per campaign and per channel (✔/✖ with rule id, rule name, and the client's actual value vs the threshold), the chosen option, the expected value per option in a small matrix campaign×channel (feasible cells coloured, chosen cell red, blocked cells grey with the blocking rule), and the razon sentence. Add a one-sentence "Guion para el asesor": why this client, why this product.
   - Explicación global: which rules exclude the most, value lost per rule ("si apagaras R03 el valor potencial elegible subiría X" computed by re-running rules without it — on demand), and, when the optimizer returns duals, a card per channel: "Precio sombra del cupo: un cupo adicional de asesor vale ≈ 0,0xx de valor esperado" plus the marginal client (last admitted / first rejected). For greedy, show the opportunity-cost estimate instead and label it as estimated.
4. Validador: run validator.py on the current parrilla; 16 tiles (signage style) R01…R16, each green with "0 violaciones" or red with count + downloadable offending ids. Also an upload box to validate any external parrilla CSV.
5. Simulador ¿Qué pasa si?: pick up to 3 saved scenarios (config snapshot + optimizer) and compare KPIs side by side, plus a diff of the config (which parameters/rules changed). Preloaded demo scenarios: "Pausar OTT", "Cupo asesor +1.000", "Jerarquía estricta", "Umbral producto 0,45", "Prioridad: más peso al modelo". Button "Guardar escenario actual".
6. Metodología: plain-language explanation + LaTeX of the model (objective, constraints) loaded from a markdown file docs/metodologia.md that the modelling teammate will edit; include the pipeline diagram (datos → reglas → elegibilidad → optimizador → validador → parrilla) and the explicit statement of the hierarchy-vs-value balance we chose and how to change it (the challenge requires this).
Acceptance: Resumen loads in < 3 s after a run (cached); every chart uses the claro Plotly template; all text in Spanish; validator shows 16/16 green for the greedy run.
```

---

## Phase 5 — MILP plug-in point (prepare for the teammate)

```
Prepare engine/optimizers/milp.py so the modelling teammate only writes the model:
- Keep the Optimizer interface. Add helper build_option_values(inp) that, for every (client, channel) feasible pair, precomputes the best set of up to max_products eligible & allowed campaigns and its value (score_producto*score_canal*valor_negocio, plus the hierarchy term defined in params). Return a sparse table (client_idx, channel_idx, value, campaigns).
- Write the skeleton using highspy (HiGHS) with the reduced formulation x[i,c] ∈ {0,1}: max Σ value·x ; Σ_c x[i,c] ≤ channels_per_client ; Σ_i x[i,c] ≤ capacity[c]. Leave clear TODOs where the teammate adjusts the objective (weighted vs strict hierarchy) and extra constraints. Also solve the LP relaxation and return capacity duals in SolveResult.duals["capacity"].
- Add a time limit and MIP gap in params (optimizador.tiempo_max_s, optimizador.gap) so they are configurable.
- Enable "milp" in the sidebar selector once NotImplementedError is gone; run both optimizers and fill the comparison on Resumen.
- tests: the 5 example cases + validator must pass with milp too.
Do not change the expected-value metric definition.
```

---

## Phase 6 — Pitch polish

```
Polish for the final presentation to Claro:
- "Modo presentación" toggle in the sidebar: hides config widgets, enlarges fonts/KPIs, shows a guided 5-step story with step_header numerals: 1 El reto → 2 Las reglas (funnel) → 3 La decisión (Sankey + valor vs línea base) → 4 Por qué (ficha de un cliente + precio sombra del asesor) → 5 Negocio tiene el control (live change: pause a campaign and re-run, show the delta).
- Empty/loading/error states with on-brand illustrations (simple tiles/icons only, no logo recreation), st.status progress during runs ("Evaluando reglas…", "Optimizando cupos…", "Validando 16 restricciones…").
- Performance pass: profile a full run, make sure re-runs after a config change take < 30 s.
- README.md in Spanish: what it is, how to run, how business makes each type of change, architecture diagram, results table vs baseline.
- Final check: grep the code for hard-coded campaign codes, channel names, thresholds or rule IDs outside config/tests and remove them.
```

---

## Tips while working with Claude Code
- Start each session with: "Read CLAUDE.md and continue with Phase N."
- If it drifts into modelling decisions (objective weights, hierarchy treatment), tell it: "That is the modelling teammate's decision — leave a TODO and a config parameter."
- Commit after each green phase so you can roll back.
