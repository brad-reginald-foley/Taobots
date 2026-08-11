---
title: 'Story 1.0a — Correct the Wood/Earth organ roles'
type: 'refactor'
created: '2026-08-11'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'be3dd65ec536f248f0e2c0cc325e734e5347764e'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The organ model has Wood and Earth inverted relative to every other source
(`docs/domain-spec.md`'s element-to-part map, `MER-1`, `STR-1`, `STR-2`, `AD-7`, and `PLAN.md`'s own
epic table). Wood currently owns structure, death, damage and the flee trigger; Earth owns the
metabolic multiplier. E3 builds Wood-consuming meridians on top of this, which would make growing a
transport network structurally lethal.

**Approach:** Swap the two roles so **Earth = body/structure** (death condition, damage target, flee
trigger) and **Wood = meridians/transport** (metabolic multiplier, crisis trigger), carrying the
per-organ upkeep rates across with the roles. Rewrite `PLAN.md`'s organ table so its ⚠ defect
warning can be retired.

## Boundaries & Constraints

**Always:**
- Every change is a WOOD↔EARTH substitution, a symbol rename, or a comment/doc correction. No new
  arithmetic, no new control flow, no new classes.
- `ORGAN_STORAGE_DRAIN` values **follow the role, not the element** — structural maintenance stays at
  `0.004`/tick, metabolic upkeep at `0.010`/tick. See Design Notes.
- Rename identifiers that name the old role. A variable called `wood_frac` that reads Earth is worse
  than either alone.
- `LegPart.structural_integrity` and the inspector's leg `int:`/`integr` labels are **per-part**
  integrity — a different concept from the organ-level structural condition. No rename sweep may
  touch them.

**Ask First:**
- Any numeric change other than the two `ORGAN_STORAGE_DRAIN` entries trading places.
- Any change to CSV column names in `main.py` or `world.get_stats()`.
- Any new body part, `BodyPart` subclass, or organ accessor.

**Never:**
- Do not rename the module or class. `taobot_simple.py` and `TaobotSimple` keep their names here —
  split to a follow-up spec, logged in `deferred-work.md`.
- Do not introduce the body singleton Earth part, and do not derive any organ from parts. Deferred.
- Do not add `mean_organ_metal` — that is Story 1.0b.
- Do not touch `CYCLE_SEQUENCE`, resource/hazard element visuals, spawn weights, or `cluster_affinity`.
- Do not edit `notebooks/`, `docs/domain-spec.md` requirements, or `_bmad-output/planning-artifacts/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Death fires on body | `organs[EARTH] <= 0` | Bot removed, `on_taobot_death` fires, respawn refills | N/A |
| Wood no longer kills | `organs[WOOD] == 0`, Earth full | Bot survives; only the drain multiplier saturates | N/A |
| Flee on low body | `organs[EARTH] < flee_earth_threshold` | `behavior_state == "fleeing"` | N/A |
| Metabolic multiplier | `organs[WOOD] == 0` | All drains double (`wood_mult == 2.0`) | N/A |
| Damage routes to body | `record_damage(5)`, Metal at 0 | `organs[EARTH]` drops 5.0; Wood unchanged | Clamped at 0.0 |
| Armor absorbs | `record_damage(5)`, Metal at `ORGAN_MAX` | `organs[EARTH]` unchanged | N/A |
| Crisis drains body | `organs[WOOD] < 20` and total storage < 10% cap | `organs[EARTH]` loses `EARTH_CRISIS_DRAIN`/tick | Clamped at 0.0 |

</frozen-after-approval>

## Code Map

Line anchors verified against `HEAD` (`be3dd65`) on 2026-08-11.

- `taobot_simple.py` -- the organ model. Crisis constants `:29-32`; `ORGAN_STORAGE_DRAIN` + its
  comment `:37-46`; `flee_wood_threshold` in `DEFAULT_PARAMS` `:69` and `ARCHETYPES["survivor"]`
  `:98`; class docstring organ table `:138-149`; attribute `:182`; flee branch `:258` + `:266-267`;
  `_metabolize` `:428-473` (docstring `:431-438`, `earth_mult` `:439`, drains `:441-461`, crisis
  `:463-473`); `record_damage` `:498-508`.
- `world.py` -- `_check_taobot_deaths` `:460-463`: docstring `:460`, `organs[WOOD]` test `:462`.
  `get_stats` `mean_organ_*` `:585-588` — names stay, meaning inverts.
- `renderer.py` -- functional read `wood_frac = t.organs[ElementType.WOOD]` `:308`, var reused
  `:315-317, 320`; on-screen label literal `"Wood organ"` `:546`; comments `:87`, `:307`; docstrings
  `:97`, `:281`, `:532-536`. Inspectors `:390-396` / `:490-496` read
  `get_state()["organs"][e.name]` — **element-agnostic, no change**.
- `main.py` -- functional reads `wood_vals` `:347` and `:452`, pushed at `:349` / `:454`. Column
  literals `:51, 157, 198` are element-keyed — **no change**.
- `tests/test_taobot_simple.py` -- flee test `:50-51`; multiplier test `:119-127`; damage tests
  `:130-144`. Cycle tests `:181-217` use Water→Wood as *chemistry*, not organs — no change.
- `tests/test_world.py` -- death-forcing writes at `:86` and `:121`.
- `PLAN.md` -- organ table `:199-207`; ⚠ block `:209-223`.

**Read-only evidence:** `ARCHITECTURE-SPINE.md` `AD-5:122`, `AD-6:130`, `AD-7:136`. Two seeded runs
at `--seed 42` are byte-identical today (verified: 5711-line common prefix, matching md5), so
before/after comparison is a valid instrument — subject to Design Notes.

## Tasks & Acceptance

**Execution:**
- [x] `taobot_simple.py` -- swap the roles: flee trigger, damage target and crisis victim become Earth; the metabolic multiplier reads Wood. Rename `flee_wood_threshold`→`flee_earth_threshold`, `earth_mult`→`wood_mult`, `wood_damage`→`earth_damage`, and the three `WOOD_CRISIS_*` constants → `EARTH_CRISIS_*` -- identifiers must not outlive the roles they name.
- [x] `taobot_simple.py` -- move `ORGAN_STORAGE_DRAIN` values so `EARTH: 0.004` and `WOOD: 0.010`; correct the block comment -- keeps structural upkeep at today's cost. See Design Notes.
- [x] `taobot_simple.py` -- rewrite the class docstring organ table `:138-149` and `_metabolize`'s docstring -- both assert the inverted model today.
- [x] `world.py` -- death check reads `organs[EARTH]`; fix its docstring -- `AD-6`, single death condition.
- [x] `renderer.py` -- `:308` reads Earth; `:546` label becomes `"Earth organ"`; rename `wood_frac`; correct comments and docstrings at `:87, 97, 281, 307, 532-536` -- sampling Earth while labelled Wood is worse than either alone.
- [x] `main.py` -- `:347` and `:452` read Earth; rename `wood_vals`.
- [x] `tests/test_taobot_simple.py` -- swap organ assertions; rename `test_taobot_flee_triggered_at_low_wood`→`..._at_low_earth` and `test_taobot_earth_multiplier_increases_drain`→`test_taobot_wood_multiplier_increases_drain`.
- [x] `tests/test_world.py` -- `:86` and `:121` zero `organs[EARTH]` to force death.
- [x] `tests/test_taobot_simple.py` -- add a regression test: Wood at 0 with Earth full does **not** kill, and crisis drains Earth -- locks `AD-6` against a second death rule being reintroduced.
- [x] `PLAN.md` -- rewrite the organ table to the corrected roles; delete the Wood/Earth half of the ⚠ block, keeping its Water and Metal findings for Story 1.0b; note the log-meaning discontinuity beside the table.

**Acceptance Criteria:**
- Given a bot with `organs[WOOD]` at 0 and Earth full, when it ticks, then it survives and only the drain multiplier saturates.
- Given `make check` on a clean tree, when it runs, then ruff, mypy and the full suite pass.
- Given the diff, when reviewed line by line, then every hunk is a WOOD↔EARTH substitution, a rename, a comment correction, or the two `ORGAN_STORAGE_DRAIN` values trading places — no other numeric literal changes.
- Given a seeded headless run before and after, when compared, then population stays ≥15 with no extinction in both, and any divergence is attributable solely to the funding-element move (Design Notes).
- Given `PLAN.md` after the change, then its organ table is true, its ⚠ Wood/Earth warning is gone, and its Water/Metal findings survive for 1.0b.

## Spec Change Log

## Design Notes

**Why the drain rates follow the role.** The epic says only the `ORGAN_STORAGE_DRAIN` *comments*
change. Taken literally that is a large silent retune, because `_drain_organ` funds each organ from
its own element's storage: the death organ's upkeep would jump `0.004 → 0.010`/tick (2.5×) while
metabolic upkeep falls to `0.004`. Bots would starve structurally far faster, putting Phase 2 exit
criterion 4 (population never below 15) at risk. Moving the two values with the roles is the only
reading under which the story's own "explicitly not doing: changing any balance values" holds.

**The epic's acceptance #1 is not achievable, and this spec replaces it.** "A seeded run before and
after produces the same population trajectory with columns renamed" cannot hold for any honest
version of this swap: the death organ is now funded from Earth storage rather than Wood, and the two
are not interchangeable — `default_world.json` gives them different `cluster_affinity` (WOOD 0.5,
EARTH 0.8), and they sit at different positions in the Sheng cycle (Wood receives from Water, Earth
from Fire). Determinism itself is fine; the thing being compared genuinely changes. Byte-identity is
replaced above by a mechanical diff review plus a population-stability guard, with the expected
divergence recorded rather than treated as a regression.

**Deferrals.** The module/class rename, the body singleton, the notebooks, and the log discontinuity
are all recorded in `deferred-work.md` with their reasoning. `AD-6` is left satisfied functionally
(death fires on Earth, the body's organ) but not literally (not on part integrity).

## Verification

**Commands:**
- `source .venv/bin/activate && make check` -- expected: ruff, mypy and pytest all clean. The `.venv` matters; `make` calls bare `pytest`.
- `grep -rn "ElementType.WOOD" taobot_simple.py world.py renderer.py main.py` -- expected: only the metabolic multiplier, the crisis trigger, and the Sheng cycle.
- `python main.py --headless --duration 5 --seed 42` -- expected: population holds at 20, no extinction. Back up `logs/default_focal.csv` and `logs/default_deaths.csv` first; both are overwritten every run.

**Manual checks:**
- `python main.py` -- the organ graph is labelled "Earth organ" and its curve matches the per-bot tint bars; select a bot and confirm the inspector's EARTH row tracks the graph.

## Suggested Review Order

**The role swap itself**

- Entry point: the multiplier now reads Wood — the one line the whole story turns on.
  [`taobot_simple.py:440`](../../taobot_simple.py#L440)

- The only numeric change in the diff: upkeep rates follow the role, not the element.
  [`taobot_simple.py:41`](../../taobot_simple.py#L41)

- Crisis inverted: Wood collapse now bleeds the body instead of the reverse.
  [`taobot_simple.py:30`](../../taobot_simple.py#L30)

- Flee trigger reads body integrity.
  [`taobot_simple.py:268`](../../taobot_simple.py#L268)

- Damage lands on the body after Metal absorption.
  [`taobot_simple.py:508`](../../taobot_simple.py#L508)

**Death condition (`AD-6`)**

- The single death rule, now on Earth. No other organ may add one.
  [`world.py:463`](../../world.py#L463)

**Display — was sampling one organ while labelling another**

- Per-bot tint bar reads the organ that actually kills.
  [`renderer.py:308`](../../renderer.py#L308)

- The label that made the old mismatch visible on screen.
  [`renderer.py:546`](../../renderer.py#L546)

- Both run loops feed the graph from Earth; duplicated block, noted in deferred-work.
  [`main.py:347`](../../main.py#L347)

**Tests — the three guards added because mutation testing showed the swap was unpinned**

- Pins the balance decision; a straight value swap fails here.
  [`test_taobot_simple.py:131`](../../tests/test_taobot_simple.py#L131)

- `AD-6` lock: zero Wood must never kill.
  [`test_taobot_simple.py:160`](../../tests/test_taobot_simple.py#L160)

- Negative half of the flee swap — catches a partial revert of `_decide`.
  [`test_taobot_simple.py:60`](../../tests/test_taobot_simple.py#L60)

- Catches a half-finished rename that `_merge_params` would otherwise swallow.
  [`test_taobot_simple.py:293`](../../tests/test_taobot_simple.py#L293)

**Docs**

- The corrected organ table, with provenance so the old mapping can't drift back.
  [`PLAN.md:203`](../../PLAN.md#L203)

- Measured balance shift — Story 1.0c must derive against the post-1.0a world.
  [`PLAN.md:230`](../../PLAN.md#L230)
