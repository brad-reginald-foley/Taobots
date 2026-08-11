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
  evidence: Renaming the columns was rejected under "Ask First" (it would break both notebooks and `HeadlessLogger.COLUMNS`). Flagged so whoever compares runs across this commit knows the meaning inverts here.

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
  evidence: Column names are element-keyed and unchanged, filenames follow the same pattern, and analysis code has no way to refuse a mixed set. A `schema_version` column in `HeadlessLogger.COLUMNS` / `_FOCAL_COLUMNS` / `WorkshopLogger._BASE_COLUMNS`, or a per-run manifest, would make it detectable. `AD-16`'s per-run manifest (seed, config, commit, versions) is the natural home — scheduled for Story 1.0d.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: Notebook staleness runs deeper than the labelling already logged above — two cells compute against numerically inverted demand constants.
  evidence: `notebooks/analysis.ipynb` cell 13's `ORGAN_DEMAND_PER_INTERVAL` hardcodes `'EARTH': 0.10, 'WOOD': 0.04`, now inverted against `ORGAN_STORAGE_DRAIN`. So the net-balance plot and the `intervals_in_deficit` percentages are computed against the wrong demand for two elements — wrong numbers, not merely wrong labels. Cells 3 and 7 also draw the flee threshold as `Wood=25` when flee now reads Earth.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: `main.py` duplicates the population organ-sampling block verbatim in `run_visual` (`:346-350`) and `run_workshop` (`:452-455`), and `renderer.py:308` hardcodes `100.0` where `ORGAN_MAX` is meant.
  evidence: The swap had to be applied twice to identical code — the shape that produces half-finished migrations. `run_visual` also does `from common import ElementType` inside its per-frame loop while `run_workshop` imports at module level. The `100.0` was left as-is deliberately: importing `ORGAN_MAX` would create a runtime `renderer → taobot_simple` dependency where only a `TYPE_CHECKING` one exists today, which is a structural change beyond a relabelling.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0a-correct-the-wood-earth-organ-roles.md`
  summary: Two stale claims survive that predate this story — "damaged by Metal attacks" describes unimplemented combat, and the CI comment misdescribes how pygame is initialised.
  evidence: The organ table's "damaged by Metal attacks" (`PLAN.md`, and the `TaobotSimple` class docstring) has no implementation — the only damage source is `World._damage_taobots_near_hazards`, and Metal is the bot's own armor, not an attacker's. Separately, `.github/workflows/check.yml` says "conftest.py calls pygame.init()", but `tests/conftest.py:6-11` only *defines* a `pygame_init` fixture and no test requests it, so it never runs; the SDL dummy drivers are currently load-bearing for nothing.
