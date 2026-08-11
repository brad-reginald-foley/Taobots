# Deferred Work

Append-only. Each entry names work that was split out of a spec, and why.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: Rename `taobot_simple.py` → `taobot.py` and class `TaobotSimple` → `Taobot`, per `AD-17`, including `tests/test_taobot_simple.py` → `tests/test_taobot.py`, the 17 type-only references in `world.py`/`renderer.py`/`main.py`, `PLAN.md`'s Phase 2 file table, and the module mentions in `README.md:154,163`, `AGENTS.md:11`, `docs/domain-spec.md:195,222`.
  evidence: Split at the token-budget gate — the combined spec ran ~2x the 1600-token guideline. The rename is independently shippable (no coupling to the organ swap; all cross-file references are `TYPE_CHECKING` string annotations). Cost accepted: the same six files are edited twice, which is the churn `AD-17` bundled them to avoid.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: Introduce the body as a singleton Earth `BodyPart` carrying the death condition, and flip the Earth organ to a derived `mean(integrity)` value read through an accessor, per `AD-5`/`AD-6`/`AD-7`.
  evidence: Story 1.0a's "Do:" sentence asks for it, but the rest of the epic contradicts that — Story 1.3 argues from "legs are the only part type that exists", and Story 1.4's exit evidence wants the Earth *organ* (below 50, recovering above 80), which the relabelled scalar already supplies. Deriving Earth early changes the organ from a 0–100 scalar to `mean(integrity)×100`, moving the death-tick boundary, and `AGENTS.md` would then require inspector + `WorkshopLogger` rows one story before 1.0e fixes a panel already out of vertical room. `AD-6` is left satisfied functionally (death fires on Earth) but not literally (not on part integrity). Needs a home epic — `PLAN.md:262-263` gives Earth/body no epic of its own.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: Update `notebooks/analysis.ipynb` and `notebooks/workshop_analysis.ipynb` — both emphasise `mean_organ_wood` as the structural line and label `WOOD` as "structural maintenance" in their drain-rate tables. Both become wrong once the roles swap.
  evidence: Not in the epic's site table; notebooks are excluded from ruff/black/mypy and from CI, so nothing catches the staleness. `analysis.ipynb` also has uncommitted local changes, making it a poor thing to edit mid-story.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: Historical log discontinuity — organ CSV columns are element-keyed (`organ_WOOD`, `mean_organ_earth`, …) and keep their names, so logs written before and after the swap are silently non-comparable.
  evidence: Renaming the columns was rejected under "Ask First" (it would break both notebooks and `MetricsLogger.COLUMNS`). Flagged so whoever compares runs across this commit knows the meaning inverts here.

<!-- Below: surfaced by the Story 1.0a code review (2026-08-11). Pre-existing or out-of-scope; none caused by the swap. -->

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: `renderer.py` and `main.py` have zero test coverage, so the organ the display reads can silently drift from the organ that kills.
  evidence: Proven by mutation — reverting `renderer.py:308` or `main.py:347`/`:452` to `ElementType.WOOD` leaves all 81 tests passing. The bar and graph would then plot the metabolic organ under an "Earth organ" label while bots die of an Earth value never shown. `pyproject.toml` sets `testpaths = ["tests"]` and nothing there imports either module. The seam: extract the sampling step (list comprehension + `push_organ_sample`) into a helper taking `list[TaobotSimple]` and returning `(mean, min, max)`, testable without pygame. Natural fit for Story 1.0e, which already rebuilds the panel's layout seam.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: The Earth crisis drain is outrun by organ regeneration — during "systemic metabolic failure" the Earth organ can *rise*, so the crisis never kills.
  evidence: Verified empirically. With Wood below `EARTH_CRISIS_WOOD_THRESHOLD` and Earth storage in the 6.0–10.0 band (above the 6.0 regen floor, below the 10.0 crisis ceiling on *total* storage), `_drain_organ` adds `ORGAN_REGEN_RATE` 0.2 and the crisis subtracts `EARTH_CRISIS_DRAIN` 0.1 — net **+0.1/tick**. Measured: Earth organ 50.000 → 50.100 in one tick. Pre-existing: the identical arithmetic applied to Wood before the swap, so 1.0a neither caused nor worsened it. Directly relevant to Story 1.1's damage-model investigation, which is chartered to explain why bots die.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: Partial armor absorption (`0 < metal_frac < 1`) is untested — only the full-armor and no-armor endpoints are covered.
  evidence: `record_damage` computes `amount * (1.0 - metal_frac)`; both existing tests pin the endpoints, where that expression is trivially 0 or `amount`. The proportional middle — the only regime where the arithmetic can invert or drop a term — has no assertion. Pre-existing coverage shape, carried across the swap unchanged. Story 1.1 investigates the damage model and should close this.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: Nothing makes pre- and post-1.0a CSVs machine-distinguishable; the only guard against concatenating incomparable runs is a human remembering to read `PLAN.md`.
  evidence: Column names are element-keyed and unchanged, filenames follow the same pattern, and analysis code has no way to refuse a mixed set. A `schema_version` column in `MetricsLogger.COLUMNS` / `_FOCAL_COLUMNS` / `WorkshopLogger._BASE_COLUMNS`, or a per-run manifest, would make it detectable. `AD-16`'s per-run manifest (seed, config, commit, versions) is the natural home — scheduled for Story 1.0d.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: Notebook staleness runs deeper than the labelling already logged above — two cells compute against numerically inverted demand constants.
  evidence: `notebooks/analysis.ipynb` cell 13's `ORGAN_DEMAND_PER_INTERVAL` hardcodes `'EARTH': 0.10, 'WOOD': 0.04`, now inverted against `ORGAN_STORAGE_DRAIN`. So the net-balance plot and the `intervals_in_deficit` percentages are computed against the wrong demand for two elements — wrong numbers, not merely wrong labels. Cells 3 and 7 also draw the flee threshold as `Wood=25` when flee now reads Earth.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: `main.py` duplicates the population organ-sampling block verbatim in `run_visual` (`:346-350`) and `run_workshop` (`:452-455`), and `renderer.py:308` hardcodes `100.0` where `ORGAN_MAX` is meant.
  evidence: The swap had to be applied twice to identical code — the shape that produces half-finished migrations. `run_visual` also does `from common import ElementType` inside its per-frame loop while `run_workshop` imports at module level. The `100.0` was left as-is deliberately: importing `ORGAN_MAX` would create a runtime `renderer → taobot_simple` dependency where only a `TYPE_CHECKING` one exists today, which is a structural change beyond a relabelling.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: Two stale claims survive that predate this story — "damaged by Metal attacks" describes unimplemented combat, and the CI comment misdescribes how pygame is initialised.
  evidence: The organ table's "damaged by Metal attacks" (`PLAN.md`, and the `TaobotSimple` class docstring) has no implementation — the only damage source is `World._damage_taobots_near_hazards`, and Metal is the bot's own armor, not an attacker's. Separately, `.github/workflows/check.yml` says "conftest.py calls pygame.init()", but `tests/conftest.py:6-11` only *defines* a `pygame_init` fixture and no test requests it, so it never runs; the SDL dummy drivers are currently load-bearing for nothing.

<!-- Below: surfaced by the Story 1.0b code review (2026-08-11). -->

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0b-derive-the-water-organ-from-the-legs.md`
  summary: Organ *writes* have no equivalent of the new read accessor — three sites poke `_organs` directly, and only `_drain_organ` carries the derived-organ guard.
  evidence: `organ()` is now the single read path, but the crisis drain in `_metabolize` and `record_damage` both write `_organs[...]` unguarded. Water has no slot in `_organs` at all, so those two sites would `KeyError` the moment Earth or Metal becomes derived — which is exactly what the body-singleton work (already deferred) and E2's armor will do. A `_set_organ`/`_adjust_organ` write path enforcing the check once is the fix. Belongs to whichever story next derives an organ.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0b-derive-the-water-organ-from-the-legs.md`
  summary: `ORGAN_STORAGE_DRAIN` reads as configuration but behaves as documentation — `_metabolize` hardcodes four `_drain_organ` calls and never iterates the dict.
  evidence: Adding or removing a key changes no behaviour, which makes the new "Water has no entry" comment misleading and leaves `_drain_organ`'s ValueError guard unreachable from production (only tests hit it). Driving the drains from the dict would fix both, and would make a future derived organ fail loudly at its own drain site. Also note the dict is string-keyed while `DERIVED_ORGANS` is `ElementType`-keyed — two collections describing the same five organs, indexed two different ways.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0b-derive-the-water-organ-from-the-legs.md`
  summary: Derived organs are recomputed on every read, and are no longer stable within a tick.
  evidence: `organ()` runs a fresh list comprehension over `body_parts` per call — per-tick in `_sense`/`_decide`/`_metabolize`, per-taobot in `_check_taobot_deaths` and `get_stats`, per-taobot-per-frame in the renderer. Separately, a stored scalar read twice in one tick gave the same answer; a derived one changes when `_tick_body_parts` runs, so intra-tick read ordering now matters. Neither bites today because nothing reads Water functionally, but Stories 1.2 and 1.3 add Water consumers. Cache per tick or precompute an element→parts index in `__init__`.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0b-derive-the-water-organ-from-the-legs.md`
  summary: Adding `mean_organ_metal` mid-header breaks concatenation with population CSVs written before this commit, and the notebooks silently drop the new column.
  evidence: Compounds the log-discontinuity entry already logged for 1.0a. Both notebooks enumerate exactly four `mean_organ_*` columns guarded by `if col in pop.columns`, so Metal is now written every run and then silently ignored by the analysis — the same "silently missing Metal" this story set out to fix, one layer downstream. Notebooks are excluded from ruff/black/mypy and from CI.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0b-derive-the-water-organ-from-the-legs.md`
  summary: The inspectors now show Water twice — once as an aggregate organ row, once as the per-leg integrity list below it.
  evidence: Removing the `continue`-on-Water skips was required to surface the organ, but the "shown below" legs section it referenced is still rendered. Aggregate and per-part are arguably both wanted; if so the legs heading should say which is which. Story 1.0e owns this panel and should decide, alongside the overflow the new row worsens.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0b-derive-the-water-organ-from-the-legs.md`
  summary: A legless taobot is now a supported, tested state for organ reads but is never ticked, leaving `_moment_of_inertia == 0` unexercised.
  evidence: `test_water_organ_zero_with_no_legs` constructs `params={"body": []}` and asserts the organ reads `0.0` without ticking. The steering path guards with `max(1e-9, self._moment_of_inertia)` and `_act` guards with `if n > 0`, so it looks safe — but nothing exercises it. Worth one test that ticks a legless bot end to end.

<!-- Below: surfaced by the Story 1.0c code review (2026-08-11). -->

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0c-align-the-workshop-with-the-world-it-calibrates.md`
  summary: A single bot in the workshop frequently dies within a few hundred to a few thousand ticks, even after the arena was aligned to `default_world`'s densities — which threatens the epic's own method of deriving constants by tick-stepping one bot through a degrade→repair cycle.
  evidence: Measured over 3000 ticks at five seeds, before and after the clustering alignment: flat scatter died at ticks 99, 2720, 2137, 278 and survived once; clustered died at 99, 1372, 2064, 2055 and survived once. Clustering is not the cause — it wins two seeds and loses two. This is pre-existing and was worse before 1.0c, when the workshop was 3.2× more hazard-dense. Directly Story 1.1's question: it is chartered to investigate the damage model and explain why bots die. Stories 1.2–1.4 need a bot that survives long enough to observe a full round trip, so this may need a workshop-specific answer (a hazard-free calibration config, or a longer-lived starting state) rather than just an explanation.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0c-align-the-workshop-with-the-world-it-calibrates.md`
  summary: Per-unit-area parity does not give per-bot parity — the workshop offers 23 resources to one bot where `default_world` offers 7.5 per bot.
  evidence: `AD-14` asks that "the rates a bot experiences" match, and density plus clustering now do. But competition, contention and depletion pressure differ ~3× because population is deliberately 1 rather than 20. Constants insensitive to crowding transfer; constants that depend on resources being contested do not. Recorded in `configs/workshop.json`'s notes, and worth re-reading before Stories 1.2 and 1.3 derive their thresholds.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0c-align-the-workshop-with-the-world-it-calibrates.md`
  summary: `degrade_rate` is called "the most sensitive balance parameter" in `PLAN.md` yet has no range validation, and the new laws mechanism has three different JSON-comment conventions.
  evidence: Nothing rejects a negative, a string or an absurd value for a law every world inherits — the one place a range check earns its keep. Separately this change introduced `_note` (top-level in `laws.json`), `_override` (nested inside `fire_arena`'s `chemistry`) and `notes` (top-level in `workshop.json`); pick one key name and one nesting rule before a schema validator has to know all three.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0c-align-the-workshop-with-the-world-it-calibrates.md`
  summary: `tests/test_world.py` now mixes `SpatialHash`, `World` and roughly 250 lines of config/laws-resolution tests; config loading deserves its own file.
  evidence: A `tests/test_config.py` would also be the natural home for fixing `tests/conftest.py`'s CWD-relative `WorldConfig.from_json("configs/default_world.json")` — currently a known CWD bug sitting in the same suite that now exists to prove CWD independence. Story 1.0d owns the conftest fix and could do the split at the same time.
