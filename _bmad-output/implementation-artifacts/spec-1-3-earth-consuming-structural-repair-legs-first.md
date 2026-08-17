---
title: 'Story 1.3 — Earth-consuming structural repair, legs first'
type: 'feature'
created: '2026-08-12'
status: 'done'
review_loop_iteration: 0
baseline_commit: '035ff481f318fd0055464ccdd916ee5b39c2aeb3'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing in the simulation raises part integrity. `LegPart.tick` only ever subtracts, so
a damaged leg is damaged permanently and the legs organ system is a one-way decay. This is the cure
half of the loop — Story 1.2 built the prevention — and without it Phase 2 exit criterion 3 (a part
falling below 0.5 and recovering above 0.8) is unreachable by construction.

**Approach:** `BodyPart.structural_integrity` recovers by absorbing Earth, per `STR-2`. It lands on
the **base class**, not `LegPart` (`AD-8`), so E2's armor and E3's meridians inherit degrade-and-
repair rather than reimplementing it. Every part gains a structural element (Earth) alongside its
function element, and a `mass` read through a `mass()` accessor from day one (`AD-5`). Earth cost is
one law plus one per-part trait — `Δintegrity × mass` against a shared exchange rate — rather than a
new uncorrelated constant per part type. Earth is requested through the chi port and split
**pro-rata by demand** when supply is short (`AD-3`).

## Boundaries & Constraints

**Always:**
- Repair lives on `BodyPart`, never in a subclass. Legs are the only type exercised; the mechanism
  is what E2 and E3 inherit.
- `mass` is read through `mass()` from the first commit — never a bare field read. It is a stored
  placeholder now and becomes derived from part traits later, so the flip must change one method
  per part class rather than every caller.
- Earth is obtained through the chi port. Under short supply it splits **pro-rata by demand across
  every requester of Earth**, not equal shares and not within organ systems — parts of different
  systems compete in the same tick. **A denied or partial request is correct behaviour.**
- **The crossing must balance exactly.** Earth debited equals the integrity gained, converted by the
  law, per repairing part, measured on observed storage deltas. A part granted 60% of its request
  repairs 60% as much. No chi vanishing without an integrity gain; no integrity appearing without a
  debit.
- `structural_integrity` is capped at 1.0 and floored at 0.0.
- `EARTH_PER_INTEGRITY_MASS` and the Earth floor are **derived in the workshop** against legs, with
  the reasoning recorded — not plausible-looking numbers.
- Repair must be visible in the workshop inspector and present in `WorkshopLogger` columns, in the
  same change (`AGENTS.md`).

**Ask First:**
- Deriving `mass` from part traits. The seam is required now; the derivation is a later epic and
  would mean inventing a mass model for part types that do not exist.
- Any change to how integrity *degrades*, or to the leg traits tuned on 2026-08-12.
- Reordering the tick phases. Repair is upkeep; `AD-1`'s `chi → upkeep` reorder is still deferred.

**Never:**
- Do not make integrity convertible back into chi. It is a **terminal sink** — nothing converts it
  back, and that is what keeps the exchange rate safe from exploitation through E4.
- Do not repair against hazard damage as the verification case. Story 1.1 measured hazards
  delivering 7.4% of face value with 75% of contacts at full Metal; **starvation is the real damage
  source** and the one to verify against.
- Do not add a second constant for repair efficiency. Rate and efficiency are degenerate here —
  Earth→integrity has no shared currency on both sides — so it is one constant, not two.
- Do not build armor, meridians, or any second part type.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Repair when funded | integrity < 1.0, Earth above floor | Integrity rises; Earth debited by the law | N/A |
| Starved, no repair | Earth storage below the floor | No repair, no Earth debited | N/A |
| Cap respected | integrity 0.999, ample Earth | Rises to exactly 1.0, never above; only the needed Earth is spent | N/A |
| Already whole | integrity == 1.0 | No request, no debit | N/A |
| Mass scales cost | two legs, different `mass`, same Δintegrity | Heavier leg debits proportionally more Earth | N/A |
| Partial grant | two parts demand more Earth than exists | Pro-rata by demand; each repairs in proportion to what it got | N/A |
| Crossing balances | any repairing tick | Earth debited == integrity gained converted by the law, per part | N/A |
| Destroyed part | integrity 0.0, Earth available | Repairs from 0.0 like any other value — 0.0 is not special | N/A |

</frozen-after-approval>

## Code Map

Line anchors verified against the post-1.2 tree on 2026-08-12.

- `body_parts.py` -- `BodyPart.__init__` takes a single `element` (the function element); `AD-8`
  requires a structural element too, with the body as the degenerate case where both are Earth.
  `structural_integrity` is set to 1.0 and only ever decreased, in `LegPart.tick`'s starvation branch
  via `max(0.0, … - shortfall * LEG_INTEGRITY_DEGRADE_SCALE)`. `replenish(available)` is the existing
  per-part draw and the shape a port `request()` takes. No `mass` exists yet.
- `chi.py` -- `ChiPool` owns the `AD-3` port. `request`/`deposit` exist and return what was actually
  granted/accepted, so a partial grant is already a representable outcome — but **pro-rata
  allocation is not implemented**; 1.2 deliberately left it because conversion was the only
  requester. This story is where it is needed, and repairing parts are the requesters.
- `taobot_simple.py` -- `_tick_body_parts` replenishes each part from storage then ticks it; this is
  where a repair pass belongs. `_drain_organ(EARTH, …)` also consumes Earth but still writes storage
  directly rather than through the port, so it does not participate in pro-rata yet.
- `configs/laws.json` -- home for `EARTH_PER_INTEGRITY_MASS` and the Earth floor, per `AD-13`. The
  chi block already sets the pattern for derived constants with recorded reasoning.
- `tests/invariant_harness.py` -- `SCENARIOS` is the list a starvation-and-recovery scenario is
  appended to. Note the essence invariant covers transfers **within** the chi tier only; the
  chi→part crossing is a new accounting boundary this story must assert itself.
- `main.py` / `renderer.py` -- `WorkshopLogger` columns and the workshop inspector. The panel is at
  its vertical ceiling; 1.0e's condensation ladder is the mechanism for fitting anything new.

**Placeholder masses**, normalised to leg = 1.0, from Brad's rule that each organ system costs about
the same to repair — so per-part mass is inversely proportional to expected part count. Only the leg
row is exercised here:

| System | Element | Expected parts | Mass per part |
|---|---|---:|---:|
| Legs | Water | 4 | **1.0** |
| Body | Earth | 1 | 4.0 |
| Armor | Metal | 32 | 0.125 |
| Meridians | Wood | 64 | 0.0625 |
| Neurons | Fire | 1000 | 0.004 |

**Read-only evidence:** `AD-3:98` (port, pro-rata, denial is correct), `AD-5:122` (accessor from day
one), `AD-8:142` (function element + structural element, repair on the base class), `AD-13:177`
(laws). `STR-2` at `docs/domain-spec.md:138` — "all body parts are made of Earth and are repaired by
absorbing Earth essence" — currently "Partial — organs regen; parts do not". This story completes it.

## Tasks & Acceptance

**Execution:**
- [x] `body_parts.py` -- `BodyPart` gains a structural element alongside its function element (`AD-8`), and a `mass` stored placeholder read through a `mass()` accessor — never a bare field, so the later flip to derived changes one method per class.
- [x] `body_parts.py` -- degrade-and-repair on the **base class**: integrity recovers by absorbing Earth, capped at 1.0 and floored at 0.0. `LegPart` inherits it and adds nothing.
- [x] `chi.py` -- implement `AD-3` pro-rata allocation: when demand for an element exceeds supply, split by demand share across every requester. A partial grant is a correct outcome and must be reported as such.
- [x] `taobot_simple.py` -- a repair pass in the part-tick phase that requests Earth through the port for each damaged part and applies exactly the integrity the grant paid for.
- [x] `configs/laws.json` -- `EARTH_PER_INTEGRITY_MASS` and the Earth floor, **derived in the workshop** against legs with the sweep and reasoning recorded beside them, following the pattern the chi laws set.
- [x] `main.py` -- `WorkshopLogger` columns for Earth spent on repair and integrity gained, per part, so the crossing is auditable from the CSV.
- [x] `renderer.py` -- repair visible in the workshop inspector, using 1.0e's condensation ladder rather than assuming vertical room exists.
- [x] `tests/` -- cover the matrix: repair when funded, no repair below the floor, the 1.0 cap, already-whole, mass scaling the cost (two legs of different mass, same Δintegrity), pro-rata partial grant, and repair from exactly 0.0.
- [x] `tests/invariant_harness.py` -- a scenario cycling a bot through starvation and recovery, asserting the part-integrity bound holds across a long run rather than only at the cap.
- [x] `tests/invariant_harness.py` -- assert **the crossing balances**: per repairing part, Earth debited equals integrity gained converted by the law, measured on observed storage deltas, including under partial grant.

**Acceptance Criteria:**
- Given a damaged leg and Earth above the floor, when the tick runs, then integrity rises and Earth falls by the law's amount.
- Given Earth storage below the floor, when the tick runs, then no repair occurs and no Earth is debited — a starving bot cannot heal.
- Given two legs of different `mass` gaining the same integrity, when Earth is debited, then the heavier leg costs proportionally more.
- Given two parts demanding more Earth than exists, when the grant is split, then it is pro-rata by demand and each repairs in proportion to what it received.
- Given any repairing tick, when measured on observed storage deltas, then Earth debited equals integrity gained converted by the law, per part — no chi vanishing without a gain, no gain without a debit.
- Given a long starvation-and-recovery run, when the harness runs, then `0.0 ≤ structural_integrity ≤ 1.0` holds every tick and all six invariants stay green.
- Given `make check`, then ruff, mypy and the full suite pass.

## Spec Change Log

## Design Notes

**One ambiguity in the epic to settle explicitly.** The epic states the cost as `Δintegrity × mass ×
<shared exchange rate>` in prose, and its acceptance line writes `Earth debited == Δintegrity × mass
/ EARTH_PER_INTEGRITY_MASS`. Those disagree on the direction. The constant's *name* is the stronger
signal — "Earth per unit of integrity×mass" means multiply — so implement multiplication, and make
the harness assertion use the same expression as the implementation so the two cannot drift. State
the chosen direction beside the constant.

**Why the crossing needs its own assertion.** 1.0d's essence invariant watches transfers *within*
the chi tier — storage to storage. Repair moves value out of the chi tier and into a part's
integrity, a different unit entirely, so the existing invariant is blind to it. Earth could vanish
with no integrity gained, or integrity appear with no debit, and every current invariant would stay
green. That is why the epic asks for this specific assertion, and it should be written to fail on
both directions of the imbalance.

**Integrity is a terminal sink, and that is what keeps the rate safe.** Nothing converts integrity
back into chi, so there is no cycle for an exchange rate to be exploited by — `EARTH_PER_INTEGRITY_MASS`
is a pure balance knob through E4. This stops holding at Phase 5, where a defeated taobot drops chi
that a living one absorbs: if that drop derives from the corpse's mass and integrity, then
Earth → integrity → corpse → chi closes a loop and the rate acquires a second job. Flagged for
whoever designs combat.

**Verify against starvation, not hazards.** Story 1.1 measured hazard damage delivering 7.4% of face
value, with 75% of contacts landing at full Metal and a fed bot taking zero damage over 220
consecutive contact ticks. Starvation is the damage source that actually exists, and after the
2026-08-12 leg rebalance it is easy to force in the workshop.

**E1 exercises one part type, and cannot balance the ratios.** Legs are the only parts that exist, so
any cross-system mass ratio is unfalsifiable here. Set leg mass to the reference 1.0, derive the
exchange rate against legs alone, and leave the ratios to E2 when armor provides a genuinely
different second part type.

## Verification

**Commands:**
- `source .venv/bin/activate && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy make check` -- expected: ruff, mypy, full suite clean.
- `grep -rn "\.mass\b" --include="*.py" .` -- expected: no bare field reads; every access goes through `mass()`.
- `python main.py --headless --seed 42 --ticks 300` -- expected: runs clean. Run from a temp directory; `logs/default_focal.csv` and `logs/default_deaths.csv` hold the user's data.

**Manual checks:**
- `python main.py --workshop` -- step to a tick where a leg is damaged and Earth is available: integrity climbs, Earth storage falls, and both are visible in the inspector and the workshop CSV.

## Suggested Review Order

**The mechanism, on the base class**

- Entry point: repair demand, capped per tick. The cap is why damage is observable at all.
  [`body_parts.py:116`](../../body_parts.py#L116)

- `mass()` as a method from day one — a placeholder now, derived from part traits later.
  [`body_parts.py:91`](../../body_parts.py#L91)

- The single clamped write site for integrity; both directions go through it.
  [`body_parts.py:103`](../../body_parts.py#L103)

**The pass that joins the tiers**

- Two loops, not one — demand is collected from every part before any of it is served,
  which is what makes the split pro-rata rather than first-come.
  [`taobot_simple.py:564`](../../taobot_simple.py#L564)

- `AD-3` allocation. A denied or partial grant is correct behaviour.
  [`chi.py:378`](../../chi.py#L378)

**The laws**

- Three constants, loosely derived by direction, each anchored to a stated quantity.
  [`laws.json`](../../configs/laws.json)

- Regenerates the checks behind them. A sanity check, not a search — and it says so.
  [`derive_repair_laws.py`](../../tools/derive_repair_laws.py)

**Tests — the crossing, and the caller**

- The chi→part boundary the essence invariant is structurally blind to, asserted in both directions.
  [`test_repair.py:200`](../../tests/test_repair.py#L200)

- Repair reaching the tick loop at all. Deleting it from `tick()` was green until this existed.
  [`test_repair.py:280`](../../tests/test_repair.py#L280)
