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

<!-- Below: surfaced by the Story 1.0d code review (2026-08-11). -->

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0d-reproducibility-and-invariant-harness.md`
  summary: World-level draws all share one stream, so changing a config's resource count still shifts every bot's placement — per-entity isolation was achieved, per-subsystem isolation was not.
  evidence: Resource spawning, hazard spawning and taobot placement all draw from `derive_stream(seed, "world")`. `AD-12`'s stated failure mode is "one agent taking an extra draw shifts every subsequent agent's numbers"; the same reasoning applies one level up, where an environment tweak perturbs everything downstream of it and silently invalidates comparison against earlier recorded runs. Splitting into `("world","resource")`, `("world","hazard")` and `("world","placement")` would make config tweaks non-destructive. Not urgent — recorded runs are replayable as long as the config is unchanged, which the manifest now records.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0d-reproducibility-and-invariant-harness.md`
  summary: `derive_token` and `derive_seed` are two views on the same digest with no domain separation, so a publicly logged part id is the top bits of a stream seed whenever their component tuples coincide.
  evidence: Both call `_digest(world_seed, parts)` and differ only in how they read the bytes. No collision exists today because callers use distinct labels (`"part"` vs `"taobot"`), and the shared mixing is deliberate — the module docstring argues ids and streams should never drift apart. A domain byte in `_digest` would preserve that intent while removing the coupling. Harmless now; matters if part ids ever become externally meaningful (gene-bank export, Phase 4).

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0d-reproducibility-and-invariant-harness.md`
  summary: The essence invariant's negative control reimplements `_cycle_elements` by hand, and will silently drift from the real algorithm when Story 1.2 adds its second conversion path.
  evidence: `inverted_cycle_elements` is a hand-copied variant kept in sync only by a digest-equality test, which itself breaks the moment a second Metal→Water path exists. The harness docstring claims the essence check survives 1.2; the *control* will not. Deriving the control by wrapping the real method instead of reimplementing it would make it immune. **Story 1.2 must re-verify the negative control still fails, not assume it.**

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0d-reproducibility-and-invariant-harness.md`
  summary: Part ids are no longer globally unique — two worlds run at the same seed now mint identical part ids, where `uuid4()` guaranteed uniqueness across every run and process.
  evidence: A deliberate and correct trade: `AD-9` requires derivation from `(run seed, gene id, expression index)` precisely because `uuid4()` is unreachable by any seed. Uniqueness now holds *within* a run, which is all the simulation needs. It stops being sufficient at the persistence boundary — a gene bank storing parts from many runs (Phase 4) needs a run identity in the key, or a uniqueness check on import.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0d-reproducibility-and-invariant-harness.md`
  summary: Suite runtime went 2.6s → 11s, roughly half of it a test that re-runs the entire suite in a child process.
  evidence: `test_the_full_suite_passes_from_a_foreign_working_directory` spawns a full `pytest tests/` from a temp directory, re-running four 3000-tick scenarios (each internally run twice for the determinism check) plus a `main.py` subprocess test. The child inherits none of the parent's options (coverage, `-x`, markers) and its output is truncated to 4000 chars, so a child-only failure is hard to read. Scoping the child to a handful of path-sensitive tests via `-k` would keep the guarantee at a fraction of the cost. Related: run timestamps are second-resolution, so two runs started in the same second overwrite each other's manifest and population CSV despite those being documented as accumulating.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0e-make-the-workshop-inspector-legible.md`
  summary: The organ-sampling seam is still unextracted. `main.py:347`/`:452` still build the `(mean, min, max)` tuple inline before calling `push_organ_sample`, so the mutation described in the 1.0a entry above — plotting the metabolic organ under an "Earth organ" label — still passes the suite.
  evidence: That entry nominated Story 1.0e as the natural home, but 1.0e's Boundaries list "any change to what the organ graph plots or how it is sampled" under **Ask First**, and the sampling call sites are in `main.py`, which the story's Code Map does not touch. What 1.0e did deliver is the layout seam: `panel_layout.py` is pure and fully covered, and `tests/test_renderer_panel.py` now gives `renderer.py` its first coverage — but only of the panel's geometry, not of which organ feeds it. The extraction remains a one-function change against `main.py`.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0e-make-the-workshop-inspector-legible.md`
  summary: At seven or more legs the workshop leg list is clipped, not merely condensed — seven legs shows five, eight shows five, each with an on-screen "N of M legs hidden" notice.
  evidence: The declared ladder condenses to one 14px row per leg and then runs out: the inspector rect is 380px on the shipping 240×600 panel and the header, bot info, five organ rows and five storage rows consume 286 of it. Four legs — the epic's target body plan — fit with room to spare, and one or two legs still get full integrity/reserve bars, so nothing E1 needs is lost. Above that the honest fix is navigation, which the epic defers to E2 ("tabs, scrolling and per-organ grouping" are explicitly out of scope here, sized by part counts that do not exist yet). Until then the truncation is stated rather than silent, which is what the story required.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0e-make-the-workshop-inspector-legible.md`
  summary: The non-workshop inspector (`_draw_inspector`) is bounded and clipped but has no condensation ladder, so on a two-legged bot it runs out of room part-way through Storage and shows "panel full - rows hidden" instead of Legs, Params and Affinities.
  evidence: The story scoped condensation to the workshop panel — that is the panel this epic reads its evidence from, and the one whose rows the spec enumerates. The plain inspector previously drew all of it and let the organ graph erase the overflow, so a reader saw a truncated panel either way; the difference now is that the truncation is bounded, inside the rect, and admitted. Giving it the same ladder means teaching `panel_layout` a second content model (18px rows, per-organ bars, affinity block), which is more naturally done when E2's navigation replaces both flows.

<!-- Below: corrections and additions from the Story 1.0e review (2026-08-11). The two 1.0e entries above about the leg-list ceiling and the plain inspector are superseded by the first two entries here. -->

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0e-make-the-workshop-inspector-legible.md`
  summary: **Supersedes the earlier 1.0e entry on the plain inspector.** It is no longer permanently truncated: it shares the layout, the row-driven drawing and the condensation ladder with the workshop panel, and fits complete at the shipping two-leg body — Organs, Storage, Legs, Params and Affinities all visible with no notice. What remains deferred is the leg ceiling: at three legs it is exactly full, and at four or more it shows "N of M legs hidden".
  evidence: The review established that `python main.py` is the mode a user opens first and that a panel which always says it is full is not legible. Fitting it needed a sixth ladder rung that folds the five affinity bar rows into two text rows and drops the Params heading — both static genome traits, the least urgent thing on the panel, and condensed rather than removed (every value is still shown). At 240x600 the plain content needs 366px of a 380px inspector at that rung, so a four-leg body genuinely does not fit and the ceiling is arithmetic, not an oversight. E2's navigation is the real answer for both panels.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0e-make-the-workshop-inspector-legible.md`
  summary: **Supersedes the earlier 1.0e entry on the leg-list ceiling.** Current ceilings at 240x600: the workshop panel shows all legs up to six and clips above that; the plain panel shows all legs up to three. Both state what they hid.
  evidence: The numbers moved because the ladder gained a rung and the notice row is now reserved before any leg is placed, which costs one leg slot wherever it fires. Four legs — the epic's target body plan — fits in the workshop panel, and two legs (today's body) fits both panels with bars.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0e-make-the-workshop-inspector-legible.md`
  summary: Two guards in the panel are provably redundant rather than test-pinned, and a reviewer re-running mutation coverage will find them surviving: removing `or b.overflowed` from `content_clipped`, and removing the `_clip_to(layout.graph)` around the plot body.
  evidence: Both are equivalent mutants at every legal geometry, not coverage gaps. `b.overflowed` can only be true when the ladder already reserved a notice, which `test_dropped_rows_are_always_announced` asserts across a sweep of panel heights, and `test_predicted_height_matches_the_built_layout` pins `_content_h` to what the builder places. The graph clip is redundant because `to_px` clamps `val / _ORGAN_MAX` into 0..1 and `push_organ_sample` clamps again at the door; removing the clip *and* the inner clamp is caught by `test_the_graph_is_bounded_even_if_the_history_is_not`, which writes past the door on purpose. Both are kept as defence in depth: the cost is zero and the failure they cover is content vanishing silently.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-0e-make-the-workshop-inspector-legible.md`
  summary: `main.py` still has no test coverage, and it owns the organ-sampling step that decides which organ the graph plots.
  evidence: Restates the still-open item above with what 1.0e changed around it. `renderer.py` now has pixel-level coverage of the whole panel — every allotted row is asserted to carry ink, the graph is asserted to be painted exactly at `layout.graph`, and `render()` is driven end to end against a stub world — but the `(mean, min, max)` tuple is built inline at `main.py:347`/`:452`, outside all of it. The 1.0a mutation (plotting the metabolic organ under an "Earth organ" label) still passes.
