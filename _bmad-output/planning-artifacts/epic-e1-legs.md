# Epic E1 — Legs (Water organ system)

**Phase:** 2 · **Element:** Water · **Status:** In progress · **Drafted:** 2026-08-10

## Epic goal

Close the legs organ system: legs that starve, recover, and can be watched doing both.

Design, implementation and integration are already done — thrust, `phi` push-direction,
differential-drive steering, Water drain, and workshop inspector visibility. What remains is the
testing stage of the [epic definition of done](../../PLAN.md), and it is not cosmetic: `LEG-6`
(legs degrade and can be repaired) has no repair path, and **Phase 2 exit criterion 3 cannot pass
without it** — it requires each built part's integrity to show a degrade→recover round trip, and
leg integrity currently only falls.

## Scope decisions

| Decision | Rationale |
|---|---|
| Leg repair consumes **Earth** | Honors `STR-2` — all body parts are made of Earth and repaired by absorbing it. Gives the Earth organ a role beyond the drain multiplier. |
| Water deficit triggers **Metal→Water** conversion | Prevention half of the loop. Fires on a **storage-fraction threshold**, mirroring the existing `REGEN_STORAGE_THRESHOLD` pattern rather than introducing a second idiom. |
| Prevent and cure ship **together** | Two ends of one loop; testing either alone requires constructing artificial conditions. |
| Element-targeted hazard damage **postponed** | Hazard damage is currently element-agnostic and routes only to Wood — it never reaches a body part. Wiring `damage_element_type` to body parts touches every organ and is its own epic. E1 verifies repair against starvation damage, which already exists and is trivial to force in the workshop. |

**Requirements covered:** `LEG-6`, `STR-2`, `CHI-7`
**Evidence produced for:** `Q7` (passive vs. gated conversion) — see E1-S2

---

## QA expectations

These apply to every story in the epic and are part of its acceptance, not a separate phase.

### Invariants — asserted over a run, not a single call

The existing suite is example-based (`test_cycle_is_lossy`, `test_cycle_respects_capacity`) and
good at what it does. It cannot catch what this sprint risks: **E1-S2 adds a second conversion
path alongside the passive cycle**, and the failure modes there are double-conversion, accounting
drift, and threshold thrashing. None of those fail an example test, and all of them silently
corrupt every balance number measured afterwards — including the Phase 2 exit criteria thresholds.

Add a harness that ticks a taobot several thousand times under varied conditions and asserts, on
every tick:

| Invariant | Assertion |
|---|---|
| Storage bounded | `0 ≤ storage[e] ≤ capacity[e]` for all five elements |
| Part integrity bounded | `0.0 ≤ structural_integrity ≤ 1.0` for every body part |
| Organ integrity bounded | `0.0 ≤ organs[e] ≤ ORGAN_MAX` for all five |
| Essence is never created | For any conversion, `target_gain ≤ source_spend × CYCLE_EFFICIENCY` within tolerance — essence may be lost to efficiency, never manufactured |
| No numeric corruption | No `NaN` or `inf` in any float state |
| Determinism | Same seed, same tick count → identical state. A seeded run must reproduce exactly. |

The essence-conservation invariant is the important one. The existing passive cycle gets this right
by deriving `spent = produced / CYCLE_EFFICIENCY` *after* capping on available room
(`taobot_simple.py:484`). Any new conversion path must reproduce that discipline, and the invariant
is what proves it did.

### Constants are derived, not chosen

S2 and S3 introduce tunable constants — deficit threshold fraction, elevated conversion rate,
repair rate, Earth floor. **Do not pick plausible-looking numbers.** Derive each in workshop mode
by stepping through the behavior it governs, then record the reasoning in a comment beside the
constant, in the style of `LEG_INTEGRITY_DEGRADE_SCALE`:

```python
# At drain_max=0.005 and scale=0.5, a fully-starved leg loses integrity
# at 0.0025/tick → reaches 0 in ~400 ticks.
```

A constant without a recorded rationale is an untuned balance parameter wearing a number.

### Regression guard on unchanged paths

S2 must not alter behavior above its threshold. A seeded headless run with Water storage held above
the deficit line must produce logs identical to the pre-change build. Capture the baseline before
implementing, using a worktree at the current HEAD.

### Spike acceptance is different

E1-S1 is done when a finding is **written down**. It ships knowledge, not code. A spike that
produces implementation has failed regardless of how good the implementation is — it means the
investigation was cut short to start building.

### Run one story at a time

Start with E1-S1 and stop. Its entire purpose is to change what is known about the damage model;
if it reports that armor nullifies hazard damage at typical Metal integrity, that reshapes E2 and
possibly world balance. Building S2 and S3 before that finding lands wastes the spike.

---

## E1-S1 — Investigate the current damage model *(spike, timeboxed)*

**Why:** Repair is otherwise designed against assumptions. Analysis of 520 deaths over 59,400
ticks shows 74% involve hazard contact (median 15.0 face-value damage), but `damage_taken_total`
records damage *before* armor absorption. How much actually reaches the Wood organ at typical
Metal integrity is unmeasured — and `record_damage()` nullifies damage entirely at full Metal,
which may make hazards a far weaker pressure than the death counts suggest.

**Do:** Tick-step a single bot into a hazard in workshop mode. Record Metal integrity, Wood
integrity, leg integrity, and per-element storage before, during, and after contact.

**Acceptance:**
- A workshop CSV capturing at least one hazard contact event
- A written statement of how much damage reached Wood at the observed Metal integrity
- A recorded decision on whether hazards are a meaningful pressure at current tuning
- Findings appended to `PLAN.md` Phase 2, or filed as a new open question if they contradict the plan

**Explicitly not doing:** changing any behavior. This story ships knowledge, not code.

---

## E1-S2 — Water deficit triggers Metal→Water conversion

**Why:** Water starvation is currently the *only* source of leg damage. This is the prevention
half of the loop, and it is the first conversion in the system that serves demand rather than
running unconditionally.

**Do:** When Water storage falls below a threshold fraction of capacity, convert Metal storage to
Water at an elevated rate until it recovers.

**Acceptance:**
- New constants beside `CYCLE_RATE`: deficit threshold fraction, elevated conversion rate
- Below threshold: Water storage rises and Metal falls at a rate measurably above passive `CYCLE_RATE`
- Above threshold: behavior byte-identical to today — passive cycle only
- Conversion respects `CYCLE_EFFICIENCY` (20% loss per step), consistent with the Sheng cycle
- Workshop-observable: step to the tick the trigger fires and see the rate change in `storage_METAL` and `storage_WATER`
- Unit tests covering below-threshold, above-threshold, and the boundary
- `Q7` updated in `docs/domain-spec.md` with what this demonstrates
- **Implemented as a separable function**, not inline in `_cycle_elements`, so the meridians epic
  can lift it without a rewrite. The chi economy currently lives as private methods on
  `TaobotSimple` (`_drain_organ`, `_metabolize`, `_cycle_elements`); at E3 conversion becomes a
  property of the meridian network instead. This costs nothing now and removes most of the
  retrofit risk — see `Q6`.

**Note for Q7.** This is a demand-triggered conversion that needs **no neuron**. It is evidence
that the answer to "passive, gated, or both?" is *both* — a passive baseline plus organ-level
deficit triggers, with neurons later adding targeted control rather than introducing gating in the
first place. Record the finding; do not close the question until the neurons epic.

---

## E1-S3 — Earth-consuming leg repair

**Why:** `LEG-6`. The cure half of the loop, and the blocker on exit criterion 3.

**Do:** `LegPart.structural_integrity` recovers by consuming Earth storage when below maximum.

**Acceptance:**
- Repair draws from Earth storage, per `STR-2`
- Repair rate is a named constant with a documented rationale, in the style of `LEG_INTEGRITY_DEGRADE_SCALE`
- No repair occurs when Earth storage is below a floor — a starving bot cannot heal
- `structural_integrity` is capped at 1.0
- Repair is visible in the workshop inspector and present in `WorkshopLogger` columns
- Unit tests: repair when Earth available, no repair when starved, cap respected

---

## E1-S4 — Verify the leg integrity round trip in workshop

**Why:** The epic definition of done requires workshop tick-step verification, and this story
produces the evidence for Phase 2 exit criterion 3.

**Do:** Tick-step a bot through the full cycle — thrust until the Water reserve empties, watch
integrity degrade, let Earth-funded repair recover it.

**Acceptance:**
- Workshop CSV showing `leg_N_integrity` falling below 0.5 and recovering above 0.8 in a single run
- The E1 row of the `PLAN.md` Phase 2 status table updated to Done across all four stages, with the log filename as evidence
- A regression test covering the degrade→repair round trip
- Exit criterion 3 marked satisfied for E1

---

## Deferred to backlog

Not in this sprint. Recorded so they are not silently lost.

| Item | Why deferred |
|---|---|
| **Element-targeted hazard damage** — wire `damage_element_type` so hazards damage the body parts they should | Touches every organ and future body part; needs its own design stage. `damage_element_type` is dead code today. |
| **Taobot model variants** — 2/4/6 legs, radial vs bilateral symmetry, organ setting sweeps | Standing deliverable across the organ epics; feeds Phase 2 exit criterion 1. Most useful once more than one actuator exists. |
| **Armor wear from absorbing damage** | Surfaced by E1-S1's premise: Metal absorbs damage but never degrades from it. Belongs to E2 (Armor). |
