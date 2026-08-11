---
title: 'Story 1.0c — Align the workshop with the world it calibrates'
type: 'chore'
created: '2026-08-11'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'd82f48e0a06f58953db3774ecb88c8fbd4c59da9'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `AD-14`. Stories 1.1–1.3 are required to derive their constants by stepping through
workshop mode, but the workshop is not a scaled-down `default_world` — it is a different
environment. Measured: it is **3.2× more hazard-dense**, **35% more resource-scarce**, and respawns
**twice as fast**. Constants tuned there do not transfer to the world they will run in. Separately,
`degrade_rate` is duplicated verbatim across all three world configs when `AD-13` classes it as a
law — shared by all worlds, overridable only deliberately.

**Approach:** Align the workshop's per-unit-area resource and hazard density and its respawn delay
to `default_world`, adjusting counts for the smaller area. Extract the duplicated law into
`configs/laws.json`, have every world config reference it, and keep `fire_arena`'s divergent value
as an explicit, labelled arena override. Record whatever divergence remains, with its reason, in the
config itself.

## Boundaries & Constraints

**Always:**
- Alignment is on **per-unit-area rates**, not raw counts. The workshop is 750 u² against
  `default_world`'s 4800.
- Any divergence that survives must be recorded **in the config file**, with its reason, per `AD-14`.
- The laws file must resolve relative to the **config file's own location**, not the working
  directory. `tests/conftest.py` already demonstrates the CWD-relative failure mode.
- An arena overriding a law must be visibly deliberate in the config, not an accident of duplication.
- `laws.json` must be able to accept a new law without a loader change — Story 1.3 puts the
  Earth-per-integrity exchange rate there.

**Ask First:**
- Moving any organism-level constant (`ORGAN_STORAGE_DRAIN`, `CYCLE_RATE`, `CYCLE_EFFICIENCY`) into
  `laws.json`. See Design Notes — deliberately out of scope.
- Any change to `spawn_weights` or `cluster_affinity` in any config.
- Changing the workshop's world dimensions or its single-bot population.

**Never:**
- **Do not wire `degrade_rate` into behaviour.** The epic's constraint table lists `Q4`
  (destructive-cycle rate) as open and deferred, with "do not wire `degrade_rate`" stated outright.
  This story moves where the number lives; it stays unread.
- Do not align `fire_arena` — it is a deliberately harsher arena, not a calibration target.
- Do not touch `tests/conftest.py`'s CWD-relative config path. That is Story 1.0d's fix.
- Do not change population counts to match — `AD-14` permits size and population to differ; that is
  what makes the workshop a single-bot sandbox.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Law inherited | config with no `chemistry` block | `degrade_rate` comes from `laws.json` | N/A |
| Law overridden | `fire_arena` declaring `degrade_rate` | Config value wins; `0.002`, not the law's `0.001` | N/A |
| Laws file missing | `laws` key names a nonexistent file | Raises with the resolved path in the message | Explicit error |
| CWD independence | load a config from any working directory | Same result; laws resolve beside the config | N/A |
| Unknown law key | `laws.json` gains a key the loader doesn't model | Loads without error — forward-compatible for 1.3 | N/A |
| Density parity | workshop vs `default_world` | Resource and hazard per-u² within one entity of each other | N/A |

</frozen-after-approval>

## Code Map

Line anchors verified against `d82f48e` on 2026-08-11.

**Measured divergence** (recomputed from the configs, matches the epic's table exactly):

| | area | resources /u² | hazards /u² | respawn |
|---|---|---|---|---|
| `default_world` | 4800 | 150 → **0.03125** | 20 → **0.004167** | 60 |
| `workshop` | 750 | 15 → **0.02000** | 10 → **0.013333** | 30 |
| aligned target | 750 | **23** → 0.03067 | **3** → 0.004 | 60 |

- `world.py` -- `ChemistryConfig` `:68-72` (docstring says `degrade_rate` is "reserved for Phase 2");
  `WorldConfig` `:75-85`; `from_json` `:87-132` — required-key check `:93`, `c = data["chemistry"]`
  `:108`, construction `:129-131`. Extra JSON keys are ignored, so a `notes` field is safe.
  **`degrade_rate` is never read**: the only other mention is the placeholder comment at `:282`.
- `configs/default_world.json`, `configs/workshop.json`, `configs/fire_arena.json` -- each carries its
  own `chemistry.degrade_rate`; `default_world` and `workshop` both `0.001`, `fire_arena` `0.002`.
  `fire_arena` alone has no `hazards.cluster_affinity`.
- `tests/test_world.py` -- `:194` builds a config dict inline including `"chemistry": {...}`; it must
  keep working, so an inline `chemistry` block stays valid as an override.
- `tests/conftest.py` -- `:16` `WorldConfig.from_json("configs/default_world.json")` is CWD-relative.
  Out of scope (1.0d), but it is why laws must not resolve against the CWD.

**Read-only evidence:** `AD-13:177` (four homes for tunables), `AD-14:190` (the workshop is a
microscope). Epic constraint table: "`Q4` … Do not wire `degrade_rate`"; "Earth-per-integrity
exchange rate — a law in `configs/laws.json`, value derived in the workshop".

## Tasks & Acceptance

**Execution:**
- [x] `configs/laws.json` -- create it holding the one law currently duplicated across world configs (`chemistry.degrade_rate: 0.001`), with a header note that laws are shared by all worlds and overridden only deliberately -- `AD-13`.
- [x] `world.py` -- add a `laws` key to the config schema naming the laws file; resolve it **relative to the config file's directory**; deep-merge the config's own blocks over the laws as overrides. Keep unknown law keys non-fatal so Story 1.3 can add one without touching the loader.
- [x] `world.py` -- make `chemistry` optional in the required-key check now that laws supply it; raise a clear error naming the resolved path when the laws file is missing.
- [x] `configs/default_world.json` -- reference `laws.json`; drop the now-inherited `chemistry` block.
- [x] `configs/workshop.json` -- reference `laws.json`; drop `chemistry`; set `resources.initial_count` 15 → **23**, `resources.respawn_delay_ticks` 30 → **60**, `hazards.initial_count` 10 → **3** -- per-u² parity with `default_world`.
- [x] `configs/workshop.json` -- add a `notes` field recording the divergence that remains and why: population 1 vs 20 and area 750 vs 4800 are deliberate (`AD-14` permits both), and counts are integers so densities land within one entity -- `AD-14` requires recorded divergence.
- [x] `configs/fire_arena.json` -- reference `laws.json`; keep `chemistry.degrade_rate: 0.002` and label it in the file as a deliberate arena override rather than a leftover duplicate.
- [x] `tests/test_world.py` -- cover the matrix: law inherited when absent, config override wins, missing laws file raises with the path, a config loads identically from a different working directory, and an unrecognised law key does not break loading.
- [x] `tests/test_world.py` -- assert the alignment holds as a property, not as literals: workshop and `default_world` resource and hazard densities agree to within one entity per world, and respawn delays are equal. This is the regression guard against the two drifting apart again.

**Acceptance Criteria:**
- Given the workshop and `default_world` configs, when per-unit-area densities are computed, then resources and hazards agree within one entity and respawn delays are identical.
- Given `configs/laws.json` and any world config, when the config declares no `chemistry`, then `degrade_rate` resolves from the laws file.
- Given `fire_arena`, when loaded, then `degrade_rate` is `0.002` and the file makes clear that is a deliberate override.
- Given `pytest` invoked from a directory other than the repo root, when the laws-resolution tests run, then they pass.
- Given `make check`, then ruff, mypy and the full suite pass, and no simulation behaviour changes for `default_world` — `degrade_rate` remains unread.

## Spec Change Log

## Design Notes

**Why only `degrade_rate` moves.** `AD-13` names conversion efficiency and metabolic cost as laws
too, which today are `CYCLE_RATE`/`CYCLE_EFFICIENCY` and `ORGAN_STORAGE_DRAIN` — module constants in
`taobot_simple.py`. Moving those requires plumbing config into the organism, which currently receives
only a `params` dict, and would touch the RNG work in 1.0d and the tunables in 1.2/1.3. The word in
this story is *extract*: `degrade_rate` is the law that is presently **duplicated** across three
world configs, and extraction removes that duplication. Story 1.3 is the story that first needs a law
to reach the organism (the Earth-per-integrity rate), and it should build that path. The loader must
accept new law keys without modification so 1.3 only edits JSON.

**The workshop gets easier, and that is the point.** Hazards fall 10 → 3 and resources rise 15 → 23.
A bot in the workshop currently faces pressure no bot in `default_world` ever meets, which is exactly
why constants derived there would not transfer. Story 1.1 measures hazard pressure in the workshop
and must measure the real one.

**Compounding with 1.0a's shift.** 1.0a already lowered metabolic pressure world-wide (recorded in
`PLAN.md`). This story lowers workshop hazard pressure further. Anyone comparing workshop runs across
this commit is comparing two different environments; the counts are in the config diff.

## Verification

**Commands:**
- `source .venv/bin/activate && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy make check` -- expected: ruff, mypy, full suite clean.
- `cd /tmp && python -m pytest /Users/bradfoley/Desktop/taobots/tests/test_world.py -k laws` -- expected: passes from a foreign working directory.
- `python main.py --headless --duration 5 --seed 42` -- expected: trajectory unchanged from the pre-change run; `default_world` is untouched by the alignment and `degrade_rate` is unread. Back up `logs/default_focal.csv` and `logs/default_deaths.csv` first.
- `python -c "import json;d=json.load(open('configs/workshop.json'));w=d['world'];a=w['width']*w['height'];print(d['resources']['initial_count']/a, d['hazards']['initial_count']/a)"` -- expected: ≈0.0307 and ≈0.0040.

**Manual checks:**
- `python main.py --workshop` -- the sandbox still populates: roughly 23 resources and 3 hazards around a single bot, and the bot is no longer hemmed in by hazards.

## Suggested Review Order

**The laws mechanism**

- Entry point: the shared law file, and the `AD-13` test for what belongs in it.
  [`laws.json`](../../configs/laws.json)

- Resolution and validation — beside the config, never the CWD; no absolute paths, no `..`, no chaining.
  [`world.py:87`](../../world.py#L87)

- Key-by-key merge. A config overrides only the keys it names and inherits the rest.
  [`world.py:79`](../../world.py#L79)

**The alignment**

- Retuned to per-u² parity, with clustering copied across and the surviving divergence recorded.
  [`workshop.json`](../../configs/workshop.json)

- The one deliberate override, labelled in the file rather than left as a duplicate.
  [`fire_arena.json`](../../configs/fire_arena.json)

**Tests — three of these exist because mutation testing broke the first pass**

- Anti-drift guard: density, respawn and clustering asserted as properties of the two configs.
  [`test_world.py:458`](../../tests/test_world.py#L458)

- Pins the deep merge: a shallow merge passed the whole suite before this.
  [`test_world.py:239`](../../tests/test_world.py#L239)

- Every shipped config must opt in; `fire_arena` could drop `laws` silently before this.
  [`test_world.py:303`](../../tests/test_world.py#L303)

**Docs**

- Laws vs world settings, and why the workshop is a microscope.
  [`README.md:220`](../../README.md#L220)
