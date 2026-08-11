---
title: 'Story 1.0b — Derive the Water organ from the legs'
type: 'refactor'
created: '2026-08-11'
status: 'done'
review_loop_iteration: 0
baseline_commit: '1c2d22d828621119ca11827b575b27d02b078318'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing writes `organs[WATER]`. `_metabolize` drains Fire/Earth/Wood/Metal only,
`ORGAN_STORAGE_DRAIN["WATER"]` is dead, and every log to date records `organ_WATER` as a constant
`100.0`. The organ went vestigial when `LegPart` took over locomotion cost. This epic exists to close
the legs organ system, and the Water organ is currently not part of it. `world.get_stats()` also
omits Metal entirely.

**Approach:** Make the Water organ a **derived summary statistic** — the mean structural integrity of
the leg parts, scaled to the 0–100 organ range — read through an accessor rather than a bare field
(`AD-5`). An organ system with no parts reads `0.0`. Add the missing Metal column to population
stats, surface Water in both inspectors, and delete the dead drain constant.

## Boundaries & Constraints

**Always:**
- Water is derived; Fire, Wood, Earth and Metal keep their placeholder scalars. `AD-5` stages the
  transition one organ per epic.
- Every organ **read** goes through the accessor. No bare `organs[...]` access survives outside the
  organism class.
- An organ with no parts reads `0.0` — absent and destroyed are deliberately indistinguishable.
- Writing a derived organ must be impossible, not merely discouraged. `_drain_organ` is never called
  for a derived element; make that a guard, not a convention.
- Adding an organ to the inspector means adding it to `WorkshopLogger` in the same change
  (`AGENTS.md`). Water is already in the workshop columns — verify rather than assume.

**Ask First:**
- Any change to how leg integrity itself is computed or bounded.
- Renaming or removing any existing CSV column (adding `mean_organ_metal` is in scope).
- Any change to the 0–100 organ range or `ORGAN_MAX`.

**Never:**
- Do not derive Metal, Wood or Fire. Metal would read `0.0` with no armor parts, stripping all damage
  absorption and invalidating Story 1.1's premise.
- Do not add a repair path for leg integrity — that is Story 1.3.
- Do not fix the inspector's layout overflow. Story 1.0e owns that; this story only adds the row.
- Do not rename the module or introduce the body singleton — still deferred.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Healthy legs | 2 legs, integrity 1.0 | Water organ reads `100.0` | N/A |
| Partial degrade | legs at 1.0 and 0.5 | Water organ reads `75.0` (mean × `ORGAN_MAX`) | N/A |
| No legs | `body` spec with zero legs | Water organ reads `0.0` (`AD-5`) | N/A |
| Legs fully starved | all legs integrity 0.0 | Water organ reads `0.0` | N/A |
| Derived organ is read-only | attempt to drain/write Water | Raises; never silently ignored | Explicit error |
| Metal in population stats | any headless run | `mean_organ_metal` present in the CSV | N/A |
| Non-derived unchanged | Fire/Wood/Earth/Metal | Still stored scalars, same values as before | N/A |

</frozen-after-approval>

## Code Map

Line anchors verified against `1c2d22d` on 2026-08-11.

- `taobot_simple.py` -- `ORGAN_STORAGE_DRAIN["WATER"]: 0.012` at `:43` is **dead** (verified: referenced
  nowhere but its own definition). Organ store initialised `:192`. Reads to migrate: `:247` (Fire
  sensing), `:268` (Earth flee), `:295` (Fire lockout), `:440` (Wood multiplier), `:468` (crisis),
  `:507` (Metal armor). Writes, all internal: `:424`, `:427` (`_drain_organ`), `:472-473` (crisis),
  `:509` (damage). `get_state` `:531`. `self.legs` already exists at `:196`.
- `body_parts.py` -- `LegPart.structural_integrity` `:31`, 0–1, **degrade-only** at `:113-114`
  (`max(0.0, … - shortfall)`). No repair path exists. See Design Notes.
- `world.py` -- `:463` death check and `:581` `mean_organ` helper both read bare. `get_stats` returns
  `:586-589` — add `mean_organ_metal` here.
- `main.py` -- `MetricsLogger.COLUMNS` `:155-161` (class at `:149`) is the population-CSV column list;
  it lacks `mean_organ_metal`. Bare reads at `:131`, `:238`, `:347`, `:452`. `WorkshopLogger._BASE_COLUMNS`
  `:198` and `_FOCAL_COLUMNS` `:49` **already carry `organ_WATER` and `organ_METAL`** — no change.
- `renderer.py` -- bare read `:308`. Water is **skipped** in both inspectors: `_draw_inspector` `:392-393`
  and `_draw_workshop_inspector` `:492-493`, each `continue`-ing with "Water is owned by legs".
- `tests/test_taobot_simple.py` -- 27 organ accesses. `:123` sets `organs[WATER] = 0.0`, which becomes
  impossible once derived; `:30-32` asserts every organ equals `ORGAN_MAX` at spawn.

## Tasks & Acceptance

**Execution:**
- [x] `taobot_simple.py` -- rename the store to `_organs` and add `organ(element) -> float`: derived elements compute from their parts, all others return the stored scalar. Water = `mean(leg.structural_integrity) * ORGAN_MAX`, or `0.0` with no legs -- `AD-5`'s single-function flip point.
- [x] `taobot_simple.py` -- declare the derived set explicitly (Water only) and make `_drain_organ` raise if called for a derived element -- the guard that stops a future epic silently writing a computed value.
- [x] `taobot_simple.py` -- delete `ORGAN_STORAGE_DRAIN["WATER"]` and route `get_state` `:531` through the accessor.
- [x] `taobot_simple.py` -- migrate the six internal reads at `:247, 268, 295, 440, 468, 507` to the accessor; leave the four internal writes on `_organs`.
- [x] `world.py` -- `:463` and `:581` read through the accessor; add `mean_organ_metal` to the `get_stats` return.
- [x] `main.py` -- add `mean_organ_metal` to `MetricsLogger.COLUMNS`; migrate the four bare reads at `:131, 238, 347, 452`.
- [x] `renderer.py` -- migrate `:308`; remove the Water `continue` in both inspectors so the Water row renders like any other organ.
- [x] `tests/test_taobot_simple.py` -- migrate reads to the accessor and setup-writes to `_organs`. Rewrite `test_taobot_water_drain_zero_when_immobile` (`:123`): drop the now-impossible `organs[WATER]` assignment, keep its real claim that `_metabolize` does not drain Water storage.
- [x] `tests/test_taobot_simple.py` -- cover the matrix: healthy legs read 100, mixed integrity reads the mean, zero legs read `0.0`, all-starved reads `0.0`, and `_drain_organ(WATER, …)` raises.
- [x] `tests/test_world.py` -- migrate the two organ writes; assert `mean_organ_metal` is present in `get_stats()`.
- [x] `PLAN.md` -- retire the ⚠ Water block `:214-222`, which asserts the dead Water organ and the missing Metal column as live defects "Story 1.0b corrects"; correct the organ table's Water row to describe the derived value. **Added during review** — omitted from the original task list. See Spec Change Log.

**Acceptance Criteria:**
- Given a workshop run where legs starve, when `organ_WATER` is read from the CSV, then it falls from 100 in step with leg integrity instead of holding constant.
- Given `make check`, when it runs, then ruff, mypy and the full suite pass.
- Given a repo-wide search after the change, when looking for `organs[` outside the organism class, then there are no hits.
- Given a headless run, when the population CSV is opened, then `mean_organ_metal` is present and populated.
- Given a seeded run before and after, then the population trajectory is unchanged — nothing reads the Water organ, so deriving it is observationally inert. See Design Notes.

## Spec Change Log

- **2026-08-11, review round 1 — `PLAN.md` task added.** *Finding:* `PLAN.md:214-222` still carried the
  ⚠ block declaring "Nothing writes `organs[WATER]`" and "`world.get_stats()` also omits Metal
  entirely" as live defects that "E1 Story 1.0b corrects". Both were fixed by this story, so the plan
  now contradicts the code it describes. *Cause:* the original task list omitted `PLAN.md` altogether
  — a spec defect, not an implementation one; the implementing agent correctly declined to edit a file
  outside its list and flagged it. *Amended:* added the `PLAN.md` execution task above. *Known-bad
  state avoided:* a plan that tells the next reader the Water organ is dead, one story after it was
  brought to life. *KEEP:* the provenance paragraph added by Story 1.0a under the organ table must
  survive — it is the only in-plan record of why the Wood/Earth mapping changed.

## Design Notes

**Why this one is behaviour-neutral, unlike 1.0a.** Nothing in the simulation reads `organs[WATER]`.
Verified: the only reads are `world.get_stats` (logging) and one test's setup. `PLAN.md`'s claim that
Water "governs speed; at 0 → immobile" is not implemented — `LegPart` owns locomotion cost. So the
seeded before/after trajectory really should be identical here, and unlike 1.0a that is worth
asserting. Any divergence means something reads Water that this investigation missed.

**The epic's acceptance asks for recovery that cannot happen yet.** It requires `organ_WATER` to
fall when legs starve "and recover when they repair" — but `LegPart.structural_integrity` is
degrade-only (`body_parts.py:113-114`) and repair is Story 1.3. The acceptance above keeps the fall
half, which is observable today. The round trip is Story 1.4's entire purpose; it should not be
half-claimed here.

**Adding the Water row makes the inspector worse before 1.0e fixes it.** The panel is already out of
vertical room at two legs, and this adds a row. That is the sequence the epic chose deliberately —
1.0e's text names this story as one of the two that overflow it further. Accepted, not worked around.

**The population logger is `MetricsLogger` (`main.py:149`)** — the epic names it correctly. An
earlier draft of this spec called it `HeadlessLogger`, which is wrong and does not exist. The
workshop and focal loggers already emit `organ_WATER` and `organ_METAL` via element loops, so only
the population logger needs the new column.

## Verification

**Commands:**
- `source .venv/bin/activate && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy make check` -- expected: ruff, mypy, full suite clean.
- `grep -rn "[^_]organs\[" --include="*.py" . --exclude-dir=.venv --exclude-dir=_bmad` -- expected: **zero hits**. Every bare access is gone.
- `grep -rn "_organs\[" --include="*.py" . --exclude-dir=.venv --exclude-dir=_bmad` -- expected: `taobot_simple.py` only (the accessor plus the internal writes) and test setup. Tests writing `_organs` is intended — see the task list.
- `python main.py --headless --duration 5 --seed 42` -- expected: `mean_organ_metal` populated; trajectory matches the pre-change run. Back up `logs/default_focal.csv` and `logs/default_deaths.csv` first — both are overwritten every run.

**Manual checks:**
- `python main.py --workshop` -- the inspector shows a WATER organ row alongside the others, and it tracks the leg integrity values shown below it as the legs starve.

## Suggested Review Order

**The derivation and its guard**

- Entry point: the declared derived set. Everything else follows from this one line.
  [`taobot_simple.py:58`](../../taobot_simple.py#L58)

- The accessor — `AD-5`'s single flip point from stored scalar to computed value.
  [`taobot_simple.py:252`](../../taobot_simple.py#L252)

- Membership is by *element*, not by `LegPart`. Clamped, so a repaired part cannot exceed `ORGAN_MAX`.
  [`taobot_simple.py:264`](../../taobot_simple.py#L264)

- Raises for a derived element — the guard that stops a later epic writing a computed value.
  [`taobot_simple.py:467`](../../taobot_simple.py#L467)

**The column that was silently missing**

- The Metal column, absent since the organ layer was built.
  [`world.py:594`](../../world.py#L594)

- `COLUMNS` is the gate: `log_tick` selects by it, so a produced key with no column is dropped unlogged.
  [`main.py:155`](../../main.py#L155)

**Display**

- Both inspectors previously skipped Water outright; the row now renders like any other organ.
  [`renderer.py:443`](../../renderer.py#L443)

**Tests — where review effort is best spent, since mutation testing broke the first attempt**

- Breaks the all-100.0 tie that made every organ column indistinguishable.
  [`test_world.py:115`](../../tests/test_world.py#L115)

- Set equality both ways; the produced-but-not-logged direction is the quiet one.
  [`test_world.py:94`](../../tests/test_world.py#L94)

- First tests to write and re-parse a real CSV — the logger path had no coverage at all.
  [`test_main.py:36`](../../tests/test_main.py#L36)

- Pins the derived set against the drain table: disjoint, and jointly total over `ElementType`.
  [`test_taobot_simple.py:209`](../../tests/test_taobot_simple.py#L209)

**Docs**

- The Water row, now describing a derived value; the ⚠ block it replaced is retired.
  [`PLAN.md:205`](../../PLAN.md#L205)
