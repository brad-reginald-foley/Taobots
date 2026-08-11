# Epic 1: Legs (Water organ system)

**Reference:** `E1` · **Phase:** 2 · **Element:** Water · **Status:** In progress
**Drafted:** 2026-08-10 · **Revised:** 2026-08-11 — architect pass folded in
**Governed by:** [`ARCHITECTURE-SPINE.md`](architecture/architecture-taobots-2026-08-10/ARCHITECTURE-SPINE.md)

This document is the single canonical statement of E1. The architect pass of 2026-08-11
(`e1-readiness-delta.md`, now superseded) added four frontloaded stories and revised the acceptance
of three existing ones; all of that is merged here. Where the delta and the 2026-08-10 draft
disagreed, the delta wins — it cites the architecture decision that forces each change.

## Goal

Close the legs organ system: legs that starve, recover, and can be watched doing both.

Design, implementation and integration of locomotion are already done — thrust, `phi` push-direction,
differential-drive steering, Water drain, and workshop inspector visibility. What remains is the
testing stage of the [epic definition of done](../../PLAN.md), and it is not cosmetic: `LEG-6`
(legs degrade and can be repaired) has no repair path, and **Phase 2 exit criterion 3 cannot pass
without it** — it requires each built part's integrity to show a degrade→recover round trip, and
leg integrity currently only falls.

Three things sit underneath that goal which the original draft assumed were already true and are not:

1. The organ model is **wrong** (Wood/Earth swapped) and **partly dead** (`organs[WATER]` is never
   written). Story 1.4 produces exit-criterion evidence read off those gauges.
2. The reproducibility guarantees this epic's own QA section demands — seeded determinism, a
   byte-identical regression baseline — **cannot currently be built**. There is one global RNG and no
   run manifest.
3. The workshop, where this epic mandates that all new constants be derived, has **materially
   different pressures** from the world those constants will run in.

Stories 1.0a–1.0d exist to make the remaining four executable.

## Scope decisions

| Decision | Rationale |
|---|---|
| Leg repair consumes **Earth** | Honors `STR-2` — all body parts are made of Earth and repaired by absorbing it. Gives the Earth organ a role beyond the drain multiplier. |
| Repair lives on the **`BodyPart` base**, not `LegPart` | `AD-8`. `STR-2` says *all* parts are Earth-repaired, so E2's armor and E3's meridians inherit degrade-and-repair rather than reimplementing it. |
| Earth cost scales with a per-part **`mass`**, against **one shared exchange rate** | `AD-13`. `structural_integrity` is normalized 0–1, so without a mass term every part type repairs identically per unit of Earth and each new part type adds an uncorrelated constant. Rate is a law; mass is a trait. Masses are fudged by part count for now — see Story 1.3. |
| Water deficit triggers **Metal→Water** conversion | Prevention half of the loop. Fires on a **storage-fraction threshold**, mirroring the existing `REGEN_STORAGE_THRESHOLD` pattern rather than introducing a second idiom. |
| Conversion lands on **`ChiPool`, behind the chi port** | `AD-3`, `AD-4`. Not a method on the organism, and not inline in `_cycle_elements` — E3 substitutes `MeridianNetwork` behind the same port instead of rewriting. |
| Prevent and cure ship **together** | Two ends of one loop; testing either alone requires constructing artificial conditions. |
| The organ-model correction is **frontloaded, not deferred** | `AD-7`. Story 1.4 reads exit-criterion evidence off organ gauges; two of them are mislabelled and one is dead. Evidence collected before the fix would have to be recollected after it. |
| Element-targeted hazard damage **postponed** | Hazard damage is currently element-agnostic and routes only to Wood — it never reaches a body part. Wiring `damage_element_type` to body parts touches every organ and is its own epic. This epic verifies repair against starvation damage, which already exists and is trivial to force in the workshop. |

**Requirements covered:** `LEG-6`, `STR-2`, `CHI-7`
**Architecture decisions applied:** `AD-1`, `AD-3`, `AD-4`, `AD-5`, `AD-6`, `AD-7`, `AD-8`, `AD-9`, `AD-12`, `AD-13`, `AD-14`, `AD-17`
**Evidence produced for:** `Q7` (passive vs. gated conversion) — see Story 1.2

---

## QA expectations

These apply to every story in the epic and are part of its acceptance, not a separate phase.

### Invariants — asserted over a run, not a single call

The existing suite is example-based (`test_cycle_is_lossy`, `test_cycle_respects_capacity`) and
good at what it does. It cannot catch what this sprint risks: **Story 1.2 adds a second conversion
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
| Essence accounting is exact | Per element pair across the chi phase: `Δstorage[target] == −Δstorage[source] × CYCLE_EFFICIENCY`, within *relative* tolerance. Equality, not `≤`. Measured on observed storage deltas, never on internal `spent`/`produced` values — see below |
| No numeric corruption | No `NaN` or `inf` in any float state |
| Determinism | Same seed, same tick count → identical state. A seeded run must reproduce exactly. |

### Essence accounting — what the invariant actually claims

The essence invariant is the important one, and it is easy to state too weakly. It is **not a
conservation law**: nothing here is conserved. The system leaks deliberately — 20% per conversion
step, plus metabolic drain, plus collection injecting new essence from the world. "Essence" means
**units in `storage[element]`**, the chi pool tier, not organ or part integrity; those have their own
bounds rows above. Its **scope is conversion only** — eating legitimately creates storage and
`_metabolize` legitimately destroys it, and the invariant would be wrong if applied to either.

**Assert equality, not an upper bound.** The passive cycle caps on available room and *then* derives
the cost (`taobot_simple.py:487-490`):

```python
produced = min(amount_out * CYCLE_EFFICIENCY, room)
spent = produced / CYCLE_EFFICIENCY
```

Because `spent` is derived *from* `produced`, `produced == spent × CYCLE_EFFICIENCY` holds exactly in
both branches, capped and uncapped. A `target_gain ≤ source_spend × EFFICIENCY` bound is therefore
strictly weaker than what the code already guarantees, and the gap is where the bug lives. The
natural-looking inversion —

```python
spent = CYCLE_RATE * storage[source]             # pay first
produced = min(spent * CYCLE_EFFICIENCY, room)   # deliver what fits
```

— makes the source pay full price while the target receives less whenever `room` binds, silently
*destroying* essence. It satisfies the `≤` bound and would pass a one-sided invariant. That inversion
is precisely the discipline `AD-4` exists to enforce, so the invariant that guards `AD-4` has to be
able to see it violated.

**Assert on observed storage deltas, not on `spent`/`produced`.** Checking the internal values only
proves the arithmetic agrees with itself. The divergence that matters is the clamp at
`taobot_simple.py:493` — `max(0.0, storage[source] - spent)`. If `spent` ever exceeded the source's
holdings, less is removed than intended while the target still gains `produced`, genuinely
manufacturing essence. It cannot bind at today's constants (`spent ≤ 0.001 × storage[source]`, and
each element is a source exactly once per cycle), but that is a property of current tuning, not a
guarantee. Pre/post storage measurement catches it; bookkeeping measurement does not.

**Use a relative tolerance.** Storage spans orders of magnitude across a run; an absolute epsilon is
either useless at the top of the range or false-positive at the bottom.

`AD-1` makes this structural as well as tested: all conversion happens in the `chi` phase from a
single pre-tick snapshot, so there is exactly one conversion site to measure across.

**Story 1.0d builds this harness** and is the story accountable for it. Later stories add scenarios
to it rather than writing their own — an expectation that applies to every story but is owned by
none gets built by none.

### Constants are derived, not chosen

Stories 1.2 and 1.3 introduce tunable constants — deficit threshold fraction, elevated conversion
rate, repair rate, Earth floor. **Do not pick plausible-looking numbers.** Derive each in workshop
mode by stepping through the behavior it governs, then record the reasoning in a comment beside the
constant, in the style of `LEG_INTEGRITY_DEGRADE_SCALE`:

```python
# At drain_max=0.005 and scale=0.5, a fully-starved leg loses integrity
# at 0.0025/tick → reaches 0 in ~400 ticks.
```

A constant without a recorded rationale is an untuned balance parameter wearing a number.

Where each constant lives is decided by `AD-13`'s law test — **would making this evolvable let
organisms escape a constraint the simulation exists to impose?** If yes it is a law and belongs in
`configs/laws.json`, not module scope.

This is why Story 1.0c blocks 1.1, 1.2 and 1.3: derivation happens in the workshop, and the workshop
does not currently reproduce the world's pressures.

### Regression guard on unchanged paths

Story 1.2 must not alter behavior above its threshold. A seeded headless run with Water storage held
above the deficit line must produce logs identical to the pre-change build. Capture the baseline
before implementing, using a worktree at the current HEAD.

This depends on Story 1.0d — with one global RNG stream and no seed recorded in any log, a
byte-identical comparison is not currently constructible.

### Spike acceptance is different

Story 1.1 is done when a finding is **written down**. It ships knowledge, not code. A spike that
produces implementation has failed regardless of how good the implementation is — it means the
investigation was cut short to start building.

### Run one at a time

Follow the ordering below and stop at each boundary. Story 1.1's entire purpose is to change what is
known about the damage model; if it reports that armor nullifies hazard damage at typical Metal
integrity, that reshapes E2 and possibly world balance. Building 1.2 and 1.3 before that finding
lands wastes the spike.

---

## Ordering

```text
1.0a  correct Wood/Earth roles
   ↓
1.0b  derive Water organ from legs
   ↓
1.0c  align workshop                ──┐
1.0d  reproducibility + invariants  ──┤   (independent of each other)
1.0e  inspector legibility          ──┤
                                      ↓
1.1   damage spike             ← needs 1.0c, 1.0e
   ↓
1.2   deficit conversion       ← needs 1.0c, 1.0d
   ↓
1.3   parts repair             ← needs 1.0c, 1.0e
   ↓
1.4   round-trip verification  ← needs 1.0e
```

`1.0a` before `1.0b` because deriving organs is confusing to review while two of them are
mislabelled. `1.1` still runs alone and reports before 1.2 or 1.3 start, per the "run one at a time"
rule above.

---

## Stories

### Story 1.0a: Correct the Wood/Earth organ roles

**Why:** `AD-7`. The code has Earth and Wood inverted relative to `docs/domain-spec.md`, `MER-1`,
`STR-1`, `STR-2` and `PLAN.md`'s own epic table. E3 builds Wood-consuming meridians; if Wood remains
the death organ, growing a transport network makes a taobot structurally fragile.

**Do:** swap the two organs' roles, and introduce the body as a singleton Earth part carrying the
death condition (`AD-6`, `AD-7`).

| Site | Change |
| --- | --- |
| `world.py:463` | death check `organs[WOOD]` → body integrity |
| `taobot_simple.py:267` | flee trigger → Earth; rename `flee_wood_threshold` (touches `DEFAULT_PARAMS`, `ARCHETYPES["survivor"]`) |
| `taobot_simple.py:439` | `earth_mult` sources from Wood |
| `taobot_simple.py:466-472` | crisis condition Earth→Wood, damage target Wood→Earth, constants renamed |
| `taobot_simple.py:508` | `record_damage` target → Earth |
| `taobot_simple.py:40-46` | `ORGAN_STORAGE_DRAIN` comments corrected |
| `renderer.py:308` | bot tint reads Earth |
| `main.py:347,452` | organ graph samples Earth |
| `renderer.py:546` | graph label literal `"Wood organ"` → Earth. Visible on screen; sampling Earth while labelled Wood is worse than either alone |
| `renderer.py:97,532-534` | `push_organ_sample` and `_draw_organ_graph` docstrings — both assert Wood is "the structural integrity / death condition", which `AD-7` inverts |
| `tests/test_world.py:86,121`, `tests/test_taobot_simple.py:51` | follow |
| `PLAN.md` organ table | rewritten, replacing the ⚠ warning block |
| `taobot_simple.py` → `taobot.py` | module rename, per `AD-17` — plus the class, and `PLAN.md`'s Phase 2 file table |

**On the rename.** `AD-17` settles the long-open `taobot_simple.py` / `taobot.py` question: there is
one organism class, hollowed out in place, never a parallel "full" class to cut over to. The name is
already wrong — `TaobotSimple` owns the organ model — and gets worse as it comes to own a
gene-expressed neural organism. This story is already a relabelling that touches the file heavily,
which makes it the cheapest moment to do it.

**Acceptance:**
- The swap is behaviour-preserving under relabelling — a seeded run before and after produces the
  same population trajectory with columns renamed
- Death fires on body integrity, and no other organ system introduces a death rule (`AD-6`)
- `PLAN.md`'s warning block is gone because the organ table is now true
- `PLAN.md`'s Phase 2 file table records `taobot.py` as built rather than missing

**Explicitly not doing:** changing any balance values. This is a relabelling, not a retune.

---

### Story 1.0b: Derive the Water organ from the legs

**Why:** `AD-5`. Nothing writes `organs[WATER]`; `_metabolize` drains Fire/Earth/Wood/Metal only
(`taobot_simple.py:441-461`) and `ORGAN_STORAGE_DRAIN["WATER"]` is dead. Every log you hold records
`organ_WATER` as a constant `100.0`. This epic's goal is to *close the legs organ system*, and the
Water organ is currently not part of it.

**Do:** the Water organ becomes the mean structural integrity of the leg parts, read through an
accessor. Add the missing Metal column to `world.get_stats()` and `MetricsLogger.COLUMNS`. Delete
the dead Water drain constant.

**Acceptance:**
- `organ_WATER` tracks leg integrity in a workshop run — it falls when legs starve and recovers when
  they repair
- An organ system with no parts reads `0.0` (`AD-5`)
- All organ reads go through an accessor, no bare field access
- `mean_organ_metal` present in population logs
- Unit test: a bot with zero legs reports Water `0.0`

**Explicitly not doing:** deriving Metal, Wood or Fire. `AD-5` stages the transition per organ —
Metal at E2, Wood at E3, Fire at E4. Deriving Metal now would read `0.0` (no armor parts exist),
strip all damage absorption, and make hazards abruptly lethal mid-sprint — invalidating Story 1.1's
premise.

---

### Story 1.0c: Align the workshop with the world it calibrates

**Why:** `AD-14`. This epic mandates that Story 1.2 and 1.3 constants be derived by stepping through
workshop mode, and Story 1.1 measures hazard pressure there. Measured divergence today:

| | Resources /u² | Hazards /u² | Respawn |
| --- | --- | --- | --- |
| `default_world` (80×60) | 0.031 | 0.0042 | 60 ticks |
| `workshop` (30×25) | 0.020 | **0.0133** | 30 ticks |

The workshop is ~3.2× more hazard-dense and ~35% more resource-scarce, with resources returning
twice as fast. Constants tuned there do not transfer.

**Do:** align workshop resource/hazard density and respawn delay to `default_world`, adjusting counts
for the smaller area. Extract shared laws to `configs/laws.json` (`AD-13`).

**Acceptance:**
- Per-unit-area densities and respawn match `default_world` within rounding, or any remaining
  divergence is recorded in the config with its reason
- `laws.json` exists and every world config references it
- `fire_arena`'s `degrade_rate` override remains, now explicit as a deliberate arena override

**Blocks:** Stories 1.1, 1.2, 1.3 — all three derive numbers from workshop observation.

---

### Story 1.0d: Reproducibility and invariant harness

**Why:** `AD-12`, plus the invariant table in this epic's QA expectations. Two things are required
by that section and buildable by neither the code nor the test suite as they stand:

1. **Reproducibility** — a determinism invariant ("same seed, same tick count → identical state")
   and a regression guard ("a seeded headless run must produce logs identical to the pre-change
   build"). Today there is one global RNG stream, no seed recorded in any log, and tests that never
   seed at all.
2. **The invariant harness itself** — the QA section specifies six invariants asserted on every
   tick, but states them as an epic-wide expectation rather than assigning them to a story. This
   story owns building it. Determinism is only one of the six; the other five have no other home,
   and the essence-conservation invariant in particular must exist **before** Story 1.2 adds a
   second conversion path, since that is precisely what it exists to catch.

**Do — reproducibility:**
- Per-entity `random.Random` streams from a single derivation function over `(world_seed, entity_id)`;
  a world stream for spawning and placement. No module-level `random.*` calls remain
- `entity_id` as tiebreaker in `query_resources`, `query_hazards`, `query_taobots` — they currently
  sort on distance alone, so ties resolve by set-iteration order
- Deterministic part ids from `(run seed, gene id, expression index)`, replacing `uuid4()`, which
  draws from `os.urandom` and no seed can reach (`AD-9`)
- A run manifest per run: seed, config name, git SHA, Python version, timestamp
- A seeded fixture in `conftest.py`
- **Determinism is asserted between two runs in the same process and environment — never against a
  committed golden file.** Float summation order and libm differ across architectures, so a baseline
  captured on one machine fails everywhere else and becomes a permanent false alarm rather than a
  regression guard. Reproducibility is scoped to an environment, which is exactly what the run
  manifest exists to record. The same constraint applies to Story 1.2's byte-identical guard: capture
  its baseline from a worktree on the same machine, in the same session

**Do — invariant harness:**
- A reusable harness that ticks a taobot several thousand times under varied conditions and asserts,
  on every tick, all six invariants from the QA expectations table above: storage bounded, part
  integrity bounded, organ integrity bounded, essence never created, no `NaN`/`inf`, determinism
- Parameterised over starting conditions, so a later story points it at a new scenario rather than
  writing a second harness. Stories 1.2 and 1.3 both add scenarios to it
- Fix the relative config path in `tests/conftest.py` — `WorldConfig.from_json("configs/…")`
  resolves against the working directory, so the suite passes only when invoked from the repo root.
  Resolve against the test file's location instead

**Acceptance:**
- Two runs at the same seed produce byte-identical logs
- Adding a `random` call to one archetype does not change any other bot's trajectory
- Every log file can be traced to the seed and commit that produced it
- The harness runs green against current `main` — it is a regression net, so it must pass **before**
  any behaviour change in this epic, and a failure at this point means an existing bug, not a
  harness bug. Any invariant that cannot pass on current code is reported rather than relaxed
- Essence accounting is asserted for the existing passive Sheng cycle in the equality-on-deltas form
  described above, establishing the baseline Story 1.2's new conversion path must also satisfy. A
  deliberately-inverted cycle (`spent` computed before capping) must make the assertion **fail** —
  demonstrate this once during development, so the invariant is known to have teeth rather than
  assumed to
- The suite passes when `pytest` is invoked from any working directory

**Blocks:** Story 1.2 — both its "byte-identical above threshold" criterion and its essence-
conservation guard.

---

### Story 1.0e: Make the workshop inspector legible

**Why:** The workshop is this epic's verification instrument, and its panel currently destroys its
own output. Two independent layout systems write the same region:

- `_draw_workshop_inspector` flows top-down from `y=8` with an unbounded running `y` and no clip
- `_draw_organ_graph` runs **after** it (`renderer.py:146`) and fills an **opaque** rect at a fixed
  `gy = window_h - _BOTTOM_SECTION_H` = 408px (`renderer.py:541,544`), erasing whatever was beneath

The graph returns early while `_organ_history` is empty (`renderer.py:537`), so the panel looks
correct at tick 0 and breaks the moment the first sample lands — which is why this was easy to miss.

It is already out of room, not merely misordered. Roughly 400px sit above the graph; the header,
organs and storage blocks consume ~300, leaving space for about 1.5 legs. Two legs already overlap.
**Story 1.0b adds the Water organ row** (currently skipped, `renderer.py:492`) and **Story 1.3 adds
repair visibility** — both land in a panel that has no room, before reaching the four legs of a
target body plan.

Right-edge clipping is a second defect from the same cause: `_draw_compact_bar_row` blits its right
label at `bar_x + bar_w + 4` (`renderer.py:443`) with no regard for `PANEL_W`, so reserve values and
`phi` run off the window.

**Do:** give the panel **one layout owner**. The inspector claims a bounded rect ending above the
graph and clips to it; the graph's position derives from the same layout rather than an independent
constant. Fix the right-label overflow against the panel width.

Extract the layout arithmetic into a **pure function returning rects**, separate from any pygame
drawing call. That is the seam that makes this verifiable rather than eyeballed, and it is the
surface a tabbed inspector would later sit on.

**Acceptance:**
- A pure layout function returns the inspector rect, the graph rect and per-section rects for a given
  part inventory, callable without a display surface
- Unit test: for part inventories from 1 to 8 legs, no returned rect overlaps the graph rect and none
  extends beyond `PANEL_W`. This is the regression guard — the current code fails it at 2 legs
- Content that does not fit is clipped or condensed within the inspector rect, never drawn outside it
- Right-hand value labels stay inside the panel at the longest values the bars produce
- Verified by eye in the workshop at 4 legs, past tick 0, with the graph populated

**Explicitly not doing:** tabs, scrolling, or per-organ grouping. This story makes the existing panel
correct and gives the layout a testable seam; navigation is sized by part counts that do not exist
yet — see the deferred backlog.

**Blocks:** Stories 1.1, 1.3 and 1.4 — all three read evidence off this panel, and 1.3 adds to it.
**Sequenced after 1.0a**, which also edits `renderer.py`.

---

### Story 1.1: Investigate the current damage model

*(spike, timeboxed — ships knowledge, not code)*

**Why:** Repair is otherwise designed against assumptions. Analysis of 520 deaths over 59,400
ticks shows 74% involve hazard contact (median 15.0 face-value damage), but `damage_taken_total`
records damage *before* armor absorption. How much actually reaches the death organ at typical
Metal integrity is unmeasured — and `record_damage()` nullifies damage entirely at full Metal,
which may make hazards a far weaker pressure than the death counts suggest.

**Do:** Tick-step a single bot into a hazard in workshop mode. Record Metal integrity, Earth (body)
integrity, leg integrity, and per-element storage before, during, and after contact.

**Sequencing:** runs after Story 1.0c. The finding is about hazard pressure "at current tuning", and
workshop tuning currently differs from the world by 3.2× in hazard density — the headline number
would be wrong.

**Acceptance:**
- A workshop CSV capturing at least one hazard contact event
- A written statement of how much damage reached the body at the observed Metal integrity
- **The hazard density the observation was made at is stated**, so the finding can be re-read later
  against a changed config
- A recorded decision on whether hazards are a meaningful pressure at current tuning
- Findings appended to `PLAN.md` Phase 2, or filed as a new open question if they contradict the plan

**Explicitly not doing:** changing any behavior.

---

### Story 1.2: Water deficit triggers Metal-to-Water conversion

**Why:** Water starvation is currently the *only* source of leg damage. This is the prevention
half of the loop, and it is the first conversion in the system that serves demand rather than
running unconditionally.

**Do:** When Water storage falls below a threshold fraction of capacity, convert Metal storage to
Water at an elevated rate until it recovers.

**Where it lands:** on `ChiPool`, behind the chi port (`AD-3`, `AD-4`), executing inside the **chi
phase** alongside the passive Sheng cycle, from one pre-tick snapshot (`AD-1`). Conversion is a
capability of the chi tier, not a method on the organism — E3 substitutes `MeridianNetwork` behind
the same port rather than lifting logic out of `TaobotSimple`. One conversion site makes
double-conversion and threshold thrashing structurally impossible rather than merely test-detectable.

The Metal→Water direction is unaffected by `AD-7`; that correction is about organ *roles*, not
productive-cycle order.

**Depends on:** Story 1.0c (constant derivation), Story 1.0d (byte-identical regression guard).

**Acceptance:**
- New constants sited per `AD-13`'s law test: deficit threshold fraction, elevated conversion rate
- Below threshold: Water storage rises and Metal falls at a rate measurably above passive `CYCLE_RATE`
- Above threshold: behavior byte-identical to today — passive cycle only
- Conversion respects `CYCLE_EFFICIENCY` (20% loss per step), consistent with the Sheng cycle, with
  `spent` derived from `produced` **after** capping on available room (`AD-4`)
- Workshop-observable: step to the tick the trigger fires and see the rate change in `storage_METAL`
  and `storage_WATER`
- Unit tests covering below-threshold, above-threshold, and the boundary
- **A scenario added to Story 1.0d's invariant harness** driving a bot repeatedly across the deficit
  threshold, so essence accounting and threshold stability are asserted over thousands of ticks
  rather than at the three example points above
- **Conversion is attributed per path.** The demand-triggered path moves Metal→Water, which is a pair
  the passive Sheng cycle already moves — so a whole-tick storage delta cannot distinguish "both
  paths ran once, correctly" from "one path ran twice". Either the two paths report their transfers
  separately for the harness to check independently, or the harness runs a scenario with the passive
  cycle contribution held at a known value. Without this, the essence invariant cannot detect
  double-conversion — the failure mode it was added for
- `Q7` updated in `docs/domain-spec.md` with what this demonstrates

**Note for Q7.** This is a demand-triggered conversion that needs **no neuron**. It is evidence
that the answer to "passive, gated, or both?" is *both* — a passive baseline plus organ-level
deficit triggers, with neurons later adding targeted control rather than introducing gating in the
first place. Record the finding; do not close the question until the neurons epic.

---

### Story 1.3: Earth-consuming structural repair, legs first

**Why:** `LEG-6`. The cure half of the loop, and the blocker on Phase 2 exit criterion 3.

**Do:** `BodyPart.structural_integrity` recovers by consuming Earth storage when below maximum.
This lands on the **base class**, not `LegPart` (`AD-8`) — `STR-2` says *all* body parts are made of
Earth and repaired by absorbing it, so E2's armor and E3's meridians inherit degrade-and-repair
instead of reimplementing it.

**Every part carries two elements:** a function element (Water for legs, Metal for armor, Fire for
neurons) and Earth for structure. The current `BodyPart.__init__` takes only one, which is why the
original draft had no room for this. The body is the degenerate case where both elements are Earth.

**Every part also carries a `mass`.** `structural_integrity` is a normalized 0–1 fraction
(`body_parts.py:31`), so a leg at 0.5 and a neuron at 0.5 are the same number but very different
amounts of missing substance. Without a mass term, one repair-rate constant makes every part type
repair at the same speed for the same Earth — and each new part type at E2/E3/E4 re-opens the balance
question with its own uncorrelated constant. With it, Earth cost is:

```
earth_cost = Δintegrity × part_mass × EARTH_PER_INTEGRITY_MASS
```

one shared exchange rate, one trait per part. A neuron costs less than a leg because it *is* smaller,
not because someone picked a smaller number for it.

`AD-13` places the two halves in different homes, and they are not both tunable:

- **`EARTH_PER_INTEGRITY_MASS` is a law** → `configs/laws.json`. If it were evolvable, organisms
  would evolve cheap repair and stop paying for having a body — a constraint the simulation exists to
  impose. Exogenous.
- **`mass` is a trait** → body spec / genome. This one *should* evolve; big legs costing more to
  maintain than small ones is the tradeoff evolution ought to be exploring.

Name it `mass`, not `size` — `PLAN.md`'s Phase 5 collision model already uses "physical size" for max
polar radius across the body.

**`mass` is a placeholder scalar destined to become derived, so it is read through an accessor from
the start** — `AD-5`, the project's standard staging device. The intent (Brad, 2026-08-11) is that
mass eventually falls out of the traits a part already carries rather than being declared alongside
them: for a leg, some function of `max_thrust` and `capacity`; for a meridian, of its storage
capacity; and so on per part type. Declaring it independently forever would let a genome evolve a
massive-thrust leg that is somehow weightless.

That flip is **not** in this epic's scope — deriving mass now would mean inventing the mass model for
part types that do not exist. What E1 owes the later work is that `part.mass()` is a method from day
one, never a bare field read, so the transition changes one function per part class instead of every
caller. This is the same discipline `AD-5` applies to organ values, `speed`, and `sensing_range`.

This also resolves the independent-vs-derived question in favour of *derived eventually*: the
coupling concern (a mutation to thrust silently changing repair cost) is real but is the intended
behaviour — a bigger leg **should** cost more to maintain, and that link is what makes the tradeoff
evolvable rather than free.

**Placeholder masses — fudged by part count, deliberately.** Brad's rule (2026-08-11): *each organ
system has approximately the same repair cost*, i.e. 1 Earth repairs the same percentage of any
system. That fixes total system mass equal across all five, so per-part mass is inversely
proportional to expected part count. Anticipated counts and the resulting masses, normalized to
leg = 1.0:

| System | Element | Expected parts | Mass per part | System mass |
| --- | --- | ---: | ---: | ---: |
| Legs | Water | 4 | 1.0 | 4.0 |
| Body | Earth | 1 | 4.0 | 4.0 |
| Armor | Metal | 32 | 0.125 | 4.0 |
| Meridians | Wood | 64 | 0.0625 | 4.0 |
| Neurons | Fire | 1000 | 0.004 | 4.0 |

These are **placeholders standing in for a real mass model**, not derived values — recorded so the
mechanism has numbers to run on and so the ratios are legible when they are revisited. Only the leg
row is exercised in E1. The counts are Brad's working intuition for a median mature taobot
(roughly beetle-shaped), not a specification; they are here to fix *ratios*, not to constrain any
body plan.

**Neurons are expected to be a special case, deferred.** The intuition is that neurons take little
localized damage — their degradation is mostly starvation, which is shared — and that if they are
all connected they may crossfeed, behaving more like one pooled organ than 1000 independent parts.
Whether the Fire system is modelled as many parts or one aggregate is **open and decided at E4**, not
here. It has no bearing on E1 beyond the placeholder row above.

**Integrity is a terminal sink, and that is what makes the rate safe.** Nothing converts part
integrity back into chi — degraded integrity simply vanishes. With no cycle there is nothing for an
exchange rate to be exploited by, so `EARTH_PER_INTEGRITY_MASS` is a pure balance knob through E4.
**This stops holding at Phase 5:** `PLAN.md`'s consumption rule has a defeated taobot drop chi that a
living one absorbs. If that drop derives from the corpse's mass and integrity — the natural design —
then Earth → integrity → corpse → chi closes a loop across organisms and the rate acquires a second
job. Flagged for whoever designs combat; not an E1 concern.

**E1 builds the mechanism; E2 does the first real balance pass.** Legs are the only part type that
exists, so nothing here is falsifiable within this epic and any cross-system ratio is unfalsifiable
by construction. Set leg mass to the reference 1.0, derive `EARTH_PER_INTEGRITY_MASS` in the workshop
against legs alone, and revisit the ratios at E2 when armor provides a genuinely different second
part type to compare against.

**Earth demand goes through the port** (`AD-3`) and is split **pro-rata across every requester of
Earth**, not per organ system — structural repair makes parts of different systems compete in the
same tick.

**Depends on:** Story 1.0c (repair rate and Earth floor are derived in the workshop).

**Acceptance:**
- Repair draws from Earth storage through the chi port, per `STR-2` and `AD-3`
- `BodyPart` gains a `mass`, read through a `mass()` accessor and never as a bare field (`AD-5`) —
  a stored placeholder now, derived from part traits in a later epic
- `EARTH_PER_INTEGRITY_MASS` lives in `configs/laws.json` (`AD-13`), derived in the workshop against
  legs with a recorded rationale — **not** a plausible-looking number
- Earth cost scales with `Δintegrity × mass`, verified by a unit test using two legs of different
  mass: the heavier leg consumes proportionally more Earth for the same integrity gain
- **The crossing balances exactly.** A scenario in Story 1.0d's harness asserting
  `Earth debited == Δintegrity × mass / EARTH_PER_INTEGRITY_MASS` per repairing part, measured on
  observed storage deltas. Under partial grant (`AD-3` pro-rata), a part granted 60% of its request
  repairs 60% as much — no chi vanishing without an integrity gain, no integrity appearing without a
  debit. This is the chi-tier→part-tier accounting boundary; the essence invariant covers only
  transfers *within* the chi tier
- No repair occurs when Earth storage is below a floor — a starving bot cannot heal
- `structural_integrity` is capped at 1.0
- Repair is visible in the workshop inspector and present in `WorkshopLogger` columns
- Unit tests: repair when Earth available, no repair when starved, cap respected
- **A scenario added to Story 1.0d's invariant harness** cycling a bot through starvation and
  recovery, so the part-integrity bound holds across a long run and not just at the cap
- Legs are the only part type exercised; the base-class mechanism is what E2 and E3 inherit

---

### Story 1.4: Verify the leg integrity round trip in workshop

**Why:** The epic definition of done requires workshop tick-step verification, and this story
produces the evidence for Phase 2 exit criterion 3.

**Do:** Tick-step a bot through the full cycle — thrust until the Water reserve empties, watch
integrity degrade, let Earth-funded repair recover it.

**Recorded decision — which organ supplies the organ half of exit criterion 3.** Phase 2 exit
criterion 3 asks for an organ round trip *and* each part's round trip. Once `AD-5` lands via Story
1.0b, the Water organ *is* the mean of leg integrity — so sourcing both halves from Water collapses
them into one measurement and silently weakens the criterion. **Decision: keep both halves, and
source the organ half from Earth (the body), not Water.** Earth degrading and recovering is
independent evidence from leg integrity doing so. `PLAN.md` exit criterion 3 is updated to say so.

**Acceptance:**
- Workshop CSV showing `leg_N_integrity` falling below 0.5 and recovering above 0.8 in a single run
- The same CSV showing the Earth organ falling below 50 and recovering above 80 — the organ half,
  per the decision above
- The E1 row of the `PLAN.md` Phase 2 status table updated to Done across all four stages, with the
  log filename as evidence
- A regression test covering the degrade→repair round trip
- Exit criterion 3 marked satisfied for E1

---

## What the dev agent must not decide

| Question | Status |
| --- | --- |
| `Q6` — storage/chi boundary, where the economy lives | **Answered.** `docs/domain-spec.md` § Answered questions; `AD-2`, `AD-3`, `AD-4` |
| `Q7` — passive vs. neurally-gated conversion | **Open by design.** Story 1.2 records evidence; the question closes at E4, not here |
| `Q8` — how a gene reference resolves under one-to-many expression | **Open, deferred to Phase 4/6.** E3 owns the seam only (`AD-11`). Not an E1 concern |
| `Q4` — destructive-cycle rate | **Open, deferred** until the organ epics complete. Do not wire `degrade_rate` |
| Allocation policy under scarcity | **Decided:** pro-rata by demand across all requesters of an element (`AD-3`) |
| Tick ordering | **Decided:** `AD-1`. Do not add work outside a named phase |
| Where a new constant lives | **Decided:** `AD-13`'s law test |
| Which organ supplies exit criterion 3's organ half | **Decided:** Earth, not Water — see Story 1.4 |
| Part id generation | **Decided:** deterministic from `(run seed, gene id, expression index)`, never `uuid4()` (`AD-9`) |
| Earth-per-integrity exchange rate | **Decided where, not what.** A law in `configs/laws.json` (`AD-13`); the value is derived in the workshop, never chosen |
| Relative part masses | **Decided provisionally:** equal cost per organ system, so mass ∝ 1/count — see Story 1.3. Placeholder pending a real mass model; revisit at E2 |
| How `mass` is ultimately computed | **Deferred, but the seam is fixed.** Read through `mass()` from day one (`AD-5`); becomes derived from part traits per part type in a later epic. Do not derive it here |
| Whether neurons are many parts or one pooled organ | **Open, decided at E4.** Crossfeed between connected neurons is plausible; not an E1 concern |
| Whether repair is lossy | **Resolved — the question was ill-posed.** "Efficiency" needs a shared currency on both sides; Earth→integrity has none (chi units vs. a dimensionless fraction), so rate and efficiency are degenerate and only their product is identifiable. **One constant, not two.** See Story 1.3 |

---

## Deferred to backlog

Not in this sprint. Recorded so they are not silently lost.

| Item | Why deferred |
|---|---|
| **Element-targeted hazard damage** — wire `damage_element_type` so hazards damage the body parts they should | Touches every organ and future body part; needs its own design stage. `damage_element_type` is dead code today. |
| **Taobot model variants** — 2/4/6 legs, radial vs bilateral symmetry, organ setting sweeps | Standing deliverable across the organ epics; feeds Phase 2 exit criterion 1. Most useful once more than one actuator exists. |
| **Armor wear from absorbing damage** | Surfaced by Story 1.1's premise: Metal absorbs damage but never degrades from it. Belongs to E2 (Armor). |
| **Deriving Metal, Wood and Fire organs from parts** | `AD-5` stages these at E2, E3 and E4 respectively. Doing any of them here reads `0.0` and disables the capability it governs. |
| **Lineage-stable RNG derivation** | `AD-12` streams derive from `entity_id`, which shifts when spawn order changes. Replaying a lineage across code changes needs derivation from genome id + birth tick. Phase 4. |
| **Tabbed inspector — body parts grouped by organ type, in scrollable lists** | Story 1.0e makes the existing panel correct and gives its layout a testable seam; this is the navigation built on top. Sized by part counts that do not exist yet (32 armor, 64 meridians, 1000 neurons), so designing it now means guessing at navigation for four part types that cannot be seen. **Trigger: E2**, when armor makes 32 parts real and a flat list becomes genuinely impossible. |
