# Epic 1 Context: Legs (Water organ system)

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Close the legs organ system so legs starve, recover, and can be watched doing both. Locomotion is
already built — thrust, push-direction, differential drive, Water drain, inspector visibility. What
is missing is the cure half: leg integrity only ever falls, there is no repair path, and the phase
cannot exit until each built part shows a degrade→recover round trip. This epic adds Earth-funded
structural repair plus a Water-deficit conversion trigger that prevents the starvation. Four
frontloaded stories come first because three assumptions underneath the original plan proved false:
the organ model has Earth and Wood swapped and never writes the Water organ at all; the seeded
determinism and byte-identical baseline this epic's own acceptance demands are not currently
constructible; and the workshop where all new constants must be derived has materially different
pressures from the world those constants will run in.

## Stories

- Story 1.0a: Correct the Wood/Earth organ roles
- Story 1.0b: Derive the Water organ from the legs
- Story 1.0c: Align the workshop with the world it calibrates
- Story 1.0d: Reproducibility and invariant harness
- Story 1.0e: Make the workshop inspector legible
- Story 1.1: Investigate the current damage model (spike)
- Story 1.2: Water deficit triggers Metal-to-Water conversion
- Story 1.3: Earth-consuming structural repair, legs first
- Story 1.4: Verify the leg integrity round trip in workshop

## Requirements & Constraints

- **Legs degrade and can be repaired.** All body parts are made of Earth and repaired by absorbing
  Earth essence — repair is Earth-funded, not Water-funded.
- **Conversion serves demand**, not only an unconditional background cycle.
- **Phase exit evidence:** one workshop run showing a part's integrity fall below 0.5 and recover
  above 0.8, and separately an organ fall below 50 and recover above 80. The halves must come from
  different sources — organ half from Earth (the body), part half from the legs — or they collapse
  into a single measurement.
- **Workshop completeness is acceptance.** A part or organ that cannot be watched tick-by-tick in the
  inspector and logged by the workshop logger is not accepted; adding one updates both together.
- **Constants are derived, never chosen.** Every new tunable (deficit threshold, elevated conversion
  rate, repair rate, Earth floor, exchange rate) is derived by stepping through the behavior it
  governs in workshop mode, with the reasoning recorded beside it.
- **Invariants asserted over runs, not examples.** A harness ticks a bot thousands of times and checks
  every tick: storage within capacity, part and organ integrity in bounds, no NaN/inf, seeded
  reproducibility, exact essence accounting.
- **Essence accounting, precisely.** Scope is conversion only — eating and metabolism legitimately
  create and destroy storage. Assert *equality*, not an upper bound, on observed pre/post storage
  deltas rather than internal bookkeeping, with a relative tolerance. A one-sided bound misses the
  inversion where the source pays full price while a capped target receives less.
- **Regression guard.** Above the deficit threshold, behavior stays byte-identical to the pre-change
  build; capture that baseline from a worktree on the same machine first.
- **Determinism is scoped to an environment** — compare two runs in the same process, never a
  committed golden file. Float summation and libm differ across architectures.
- **Spike acceptance differs.** The damage investigation is done when a finding is written down; if it
  produces implementation, it failed.

## Technical Decisions

- **Tick phases are named, ordered, exhaustive:** `sense → decide → act → chi → upkeep → age`. *All*
  conversion, passive and demand-triggered, runs in the `chi` phase from one pre-tick snapshot, so
  there is exactly one conversion site. Within `upkeep` the body resolves before every other part.
- **Chi is reached only through a port** (`request`/`deposit`); no consumer mutates a chi dict, and a
  part is handed its port rather than reaching for a global one. Under scarcity an element splits
  pro-rata by demand across *every* requester of it, not within organ systems — structural repair
  makes parts of different systems compete for Earth in the same tick. A denied request is correct.
- **Conversion is a capability of the chi tier**, landing on the chi pool, never a method on the
  organism — a later meridian network substitutes behind the same port. Any path derives `spent` from
  `produced` *after* capping on available room, so essence is lost to efficiency but never made.
- **Organ values are derived summary statistics** — the mean structural integrity of that element's
  parts, read through an accessor, never a bare field; an organ with no parts reads `0.0`. Only Water
  becomes derived here; Metal, Wood and Fire stay placeholders, since deriving them early reads `0.0`
  and disables the capability they govern.
- **Exactly one death condition:** body (Earth) integrity. No organ system may add a second.
- **Earth is the body; Wood is the transport network.** Earth owns death, damage target and flee
  trigger; Wood owns the metabolic multiplier. The code has these swapped. The body is a singleton
  Earth part.
- **Every part carries two elements and a mass** — a function element for work (Water for legs) plus
  Earth for structure. Degrade-and-repair lives on the `BodyPart` base so later part types inherit it.
  Earth cost is `Δintegrity × mass × <shared exchange rate>`: one law plus one per-part trait, instead
  of a new uncorrelated constant per part type. `mass` is read through a `mass()` accessor from day
  one because it later becomes derived from part traits; leg mass is the reference 1.0.
- **Four homes for tunables**, chosen by one test: *would making this evolvable let organisms escape a
  constraint the simulation exists to impose?* If yes it is a law (shared config); otherwise
  environment (world config), trait (genome/body spec), or — structural invariants only — a module
  constant. The Earth-per-integrity rate is a law; `mass` is a trait.
- **Reproducible by construction:** per-entity RNG streams derived from `(world_seed, entity_id)` plus
  a world stream, no module-level `random.*`; stable sort tiebreakers on order-sensitive queries; part
  ids derived from `(run seed, gene id, expression index)` rather than `uuid4()`; a per-run manifest
  recording seed, config, commit and versions.
- **The workshop is a microscope, not a different world.** It may differ in size and population, but
  the rates a bot experiences must match the world being calibrated; divergence is recorded with its
  reason.
- **Observers read, never mutate.** The organism accumulates its own per-tick deltas; loggers and the
  inspector compute their own intervals and reset nothing.
- **One organism class, thinned in place.** The module is renamed from `taobot_simple` to `taobot`
  here; there is never a parallel "full" class to cut over to.

## UX & Interaction Patterns

The workshop inspector is this epic's verification instrument and every evidence-producing story
reads off it. Two independent layout systems currently write the same region, so the organ graph
paints over the inspector once the first sample lands, and right-hand value labels run past the panel
edge. It is already out of vertical room at two legs — before this epic adds a Water organ row and
repair visibility. The fix is one layout owner: the inspector claims a bounded rect ending above the
graph and clips to it, with the graph's position derived from the same layout. That arithmetic must be
a **pure function returning rects**, callable with no display surface — the seam that makes the panel
testable rather than eyeballed. Content that does not fit is clipped or condensed inside the rect,
never drawn outside it. Tabs, scrolling and per-organ grouping are out of scope.

## Cross-Story Dependencies

Run one story at a time and stop at each boundary.

```text
1.0a organ roles → 1.0b Water organ → { 1.0c workshop | 1.0d harness | 1.0e inspector }
     → 1.1 damage spike → 1.2 deficit conversion → 1.3 parts repair → 1.4 round trip
```

- **1.0a before 1.0b** — deriving organs is hard to review while two are mislabelled. 1.0a and 1.0e
  both edit the renderer, so 1.0e follows it. 1.0c, 1.0d and 1.0e are independent of each other.
- **1.0c blocks 1.1, 1.2, 1.3** — all three derive numbers from workshop observation.
- **1.0d blocks 1.2** — both the byte-identical guard and the essence invariant that exists to catch
  the double-conversion 1.2 risks. The harness must run green on current code first; a failure there
  is an existing bug, not a harness bug.
- **1.0e blocks 1.1, 1.3, 1.4** — all three read evidence off the panel, and 1.3 adds to it.
- **1.2 and 1.3 each add a scenario to 1.0d's harness** rather than building their own. 1.2 must also
  attribute conversion per path: both paths move Metal→Water, so a whole-tick delta cannot tell "both
  ran once" from "one ran twice".
- **1.1 reports before 1.2 or 1.3 start** — its finding may reshape the armor epic and world balance.
- **Downstream epics inherit the base-class work** — armor and meridians get degrade-and-repair for
  free, and the meridian network substitutes behind the same chi port.
