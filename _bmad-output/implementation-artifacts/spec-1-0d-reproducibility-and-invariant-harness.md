---
title: 'Story 1.0d — Reproducibility and invariant harness'
type: 'feature'
created: '2026-08-11'
status: 'done'
review_loop_iteration: 0
baseline_commit: 'c2886c4b4802b54683aab7229764df8f0c85a625'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `AD-12` and `AD-9`. The simulation is not reproducible: one global RNG stream means any
agent taking an extra draw shifts every subsequent agent's numbers, so a behaviour change silently
destroys the replayability of every recorded run. `--seed` is accepted but recorded nowhere, part ids
come from `uuid4()` (drawn from `os.urandom`, unreachable by any seed), and the `query_*` methods
sort on distance alone so ties resolve by set-iteration order. Separately, the epic specifies six
per-tick invariants as an epic-wide expectation with no owning story; the essence-accounting one must
exist **before** Story 1.2 adds a second conversion path, since catching that is why it exists.

**Approach:** Two phases, in order. **Phase A — reproducibility:** explicit per-entity and per-world
`random.Random` streams from one derivation function, stable sort tiebreakers, deterministic part
ids, and a per-run manifest. **Phase B — the harness:** a reusable, scenario-parameterised harness
that ticks a bot thousands of times asserting all six invariants every tick, with the essence
invariant proven to have teeth by a deliberately-inverted cycle.

## Boundaries & Constraints

**Always:**
- One derivation function produces every stream. Two call sites must not each invent their own
  mixing of `(world_seed, entity_id)`.
- The derivation must be stable across processes. Python's `hash()` is randomised for `str`/`bytes`
  under `PYTHONHASHSEED`, so it cannot be used.
- Determinism is asserted **between two runs in the same process and environment** — never against a
  committed golden file. Float summation order and libm differ across architectures, so a committed
  baseline becomes a permanent false alarm rather than a regression guard.
- The harness is **parameterised over starting conditions**. Stories 1.2 and 1.3 must be able to add
  a scenario without writing a second harness.
- An invariant that cannot pass on current code is **reported, not relaxed**. The harness is a
  regression net, so a failure here means an existing bug.
- The essence invariant asserts **equality** on observed pre/post `storage` deltas within a relative
  tolerance — never on internal `spent`/`produced`, and never as a one-sided bound. Its scope is the
  conversion phase only: eating legitimately creates storage and `_metabolize` legitimately destroys
  it, so applying it to either would be wrong.

**Ask First:**
- Any change to the *values* produced by an RNG draw for the default seed path — reordering draws is
  expected and fine, but a changed distribution is not.
- Any change to tick ordering, or to which subsystem draws before which.
- Relaxing, narrowing or skipping any of the six invariants (report instead).

**Never:**
- Do not commit a golden log file as a determinism baseline.
- Do not change simulation behaviour to make an invariant pass. Report the failure.
- Do not add the deficit-conversion path or leg repair — those are Stories 1.2 and 1.3. This story
  builds the net they will be caught by.
- Do not derive any further organ, rename the module, or introduce the body singleton.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Same seed, same ticks | two `World`s, seed 42, N ticks | Identical state and identical logs | N/A |
| Different seed | seed 42 vs 43 | Divergent trajectories | N/A |
| Stream isolation | one archetype takes an extra draw | Every *other* bot's trajectory is unchanged | N/A |
| Part ids | same seed, two runs | Same part ids; no `uuid4()` anywhere | N/A |
| Query tiebreak | two entities at identical distance | Ordered by `entity_id`, stably, every call | N/A |
| Manifest | any run | Seed, config, git SHA, Python version, timestamp written | N/A |
| No seed given | `--seed` omitted | Run still works; manifest records the generated seed | N/A |
| Essence invariant has teeth | cycle inverted so `spent` precedes capping | Harness **fails** | Must fail, not warn |
| Harness on current code | unmodified `main` | All six invariants pass, or the failure is reported | Report, never relax |
| Foreign working directory | `pytest` from `/tmp` | Suite passes | N/A |

</frozen-after-approval>

## Code Map

Line anchors verified against `c2886c4` on 2026-08-11.

**Phase A — every `random.*` and `uuid` call that must move to an explicit stream:**

- `world.py` -- `World.__init__` `:` takes only `config`; it has no seed and no stream. Draws at
  `:398` (`random.choices` element pick), `:413` (candidate positions), `:430` (`random.choice`),
  `:444` (`random.choices` weighted), `:463,465` / `:488,490` / `:512,514` (three placement sites in
  `spawn_resource`, `spawn_hazard`, `spawn_taobot`). `_alloc_id` supplies `entity_id`.
- `taobot_simple.py` -- `:187` initial heading, `:329` flee jitter, `:352` and `:389` random-walk
  turns. Four draws, all per-entity — these are what `AD-12`'s per-entity streams exist for.
- `body_factory.py` -- `:3` `import uuid`, `:20` `part_id = str(uuid.uuid4())`. `make_parts` receives
  the spec list only, so it needs the run seed and a gene id to derive from (`AD-9`).
- `main.py` -- `:109` `random.choice(non_focal)` picks the focal bot (an *observer* drawing from the
  simulation's stream); `:519-521` `random.seed(args.seed)` is the only seeding today and is recorded
  nowhere.
- `world.py` -- `query_resources` `:577-589`, `query_hazards` `:592-604`, `query_taobots` `:607-625`.
  All three end `result.sort(key=lambda t: t[0])` — distance alone. `SpatialHash.neighbors` returns a
  set, so ties resolve by set-iteration order (`AD-12` part 2).
- `tests/conftest.py` -- `:16` `WorldConfig.from_json("configs/default_world.json")` is CWD-relative.
  `tests/test_world.py` already has a `CONFIG_DIR` resolved from `__file__` to copy.

**Phase B — what the harness asserts** (the epic's table, verbatim in intent):

| Invariant | Assertion |
|---|---|
| Storage bounded | `0 ≤ storage[e] ≤ capacity[e]`, all five |
| Part integrity bounded | `0.0 ≤ structural_integrity ≤ 1.0`, every part |
| Organ integrity bounded | `0.0 ≤ organ(e) ≤ ORGAN_MAX`, all five |
| Essence exact | per pair across the chi phase: `Δstorage[target] == −Δstorage[source] × CYCLE_EFFICIENCY`, relative tolerance, equality not `≤` |
| No numeric corruption | no `NaN`/`inf` in any float state |
| Determinism | same seed, same tick count → identical state |

- `taobot_simple.py` -- `_cycle_elements` `:534-549` is the conversion phase the essence invariant
  scopes to; `produced = min(amount_out * CYCLE_EFFICIENCY, room)` then `spent = produced /
  CYCLE_EFFICIENCY` is the cap-then-derive order the inverted-cycle negative control must reverse.
  `organ()` `:252` is the bounded read; `storage_capacity` is per-element.

**Read-only evidence:** `AD-9:148` (two ID spaces, deterministic part ids), `AD-12:166` (three
required parts: no shared global RNG, stable sort tiebreakers, per-run manifest).

## Tasks & Acceptance

**Execution — Phase A (reproducibility). Complete and verify before starting Phase B.**
- [x] `rng.py` (new) -- one derivation function mapping `(world_seed, *parts)` to a `random.Random`, using a stable hash (`hashlib`, not `hash()`) so streams reproduce across processes -- two call sites must not invent their own mixing.
- [x] `world.py` -- `World` takes a seed, owns a world stream for spawning and placement, and hands each taobot its own stream derived from `(world_seed, entity_id)`. Replace all nine module-level `random.*` draws.
- [x] `taobot_simple.py` -- accept an injected stream; replace the four `random.*` draws at `:187, 329, 352, 389`. A bot must never reach for a global.
- [x] `body_factory.py` -- derive `part_id` from `(run seed, gene id, expression index)`; delete the `uuid` import -- `AD-9`.
- [x] `world.py` -- add `entity_id` as the tiebreaker in all three `query_*` sorts -- ties currently resolve by set-iteration order.
- [x] `main.py` -- generate and record a seed when `--seed` is omitted; give the focal-bot picker its own observer stream so logging never perturbs the simulation; write a run manifest (seed, config name, git SHA, Python version, timestamp) beside the logs.
- [x] `tests/conftest.py` -- resolve the config path against the test file's location, and add a seeded world fixture.
- [x] `tests/` -- cover the Phase A matrix rows: same-seed identity, different-seed divergence, stream isolation (an extra draw in one archetype leaves other bots untouched), stable part ids, query tiebreak at equal distance, manifest contents, and the no-seed path.

**Execution — Phase B (invariant harness).**
- [x] `tests/invariant_harness.py` (new) -- a scenario-parameterised harness that ticks a bot several thousand times and checks all six invariants every tick, reporting the tick number and the offending value on failure -- Stories 1.2 and 1.3 add scenarios rather than a second harness.
- [x] `tests/invariant_harness.py` -- the essence check measures **observed pre/post `storage` deltas** across the conversion phase only, asserts equality within a relative tolerance, and is never applied across eating or `_metabolize`.
- [x] `tests/test_invariants.py` (new) -- run the harness over at least three starting conditions (healthy, starving, degraded legs) on current code. Any invariant that fails is reported in the spec's Design Notes as an existing bug, never relaxed.
- [x] `tests/test_invariants.py` -- the negative control: a deliberately inverted cycle (`spent` derived before capping) must make the essence assertion **fail**. Prove the invariant has teeth rather than assuming it.
- [x] `tests/` -- assert the suite passes from a foreign working directory.

**Acceptance Criteria:**
- Given two `World`s built with the same seed, when both are ticked N times, then their full state and their logs are identical.
- Given one archetype altered to take an extra RNG draw, when a seeded run is compared, then no other bot's trajectory changes.
- Given any run, when it completes, then a manifest records the seed, config, git SHA, Python version and timestamp — every log traceable to what produced it.
- Given a repo-wide search, when looking for module-level `random.*` or `uuid4` in simulation code, then there are no hits.
- Given the harness pointed at current code, then all six invariants pass, or each failure is reported as an existing bug with evidence.
- Given the cycle inverted so `spent` is computed before capping, when the harness runs, then the essence assertion fails.
- Given `pytest` run from a directory other than the repo root, then the full suite passes.

## Spec Change Log

## Design Notes

**Why two phases in one story.** Reproducibility and the harness are separately shippable, and the
epic bundles them only because the five non-determinism invariants "have no other home". Keeping one
story preserves the sprint's shape, but the phases are ordered and independently verified because the
determinism invariant in Phase B has nothing to assert until Phase A exists. Implement and verify A
before starting B.

**This story is expected to change the trajectory, and that is fine.** Replacing one interleaved
global stream with per-entity streams necessarily changes which numbers each bot draws. Do not try to
preserve the old trajectory — the point is that from here on, a *given* seed reproduces exactly.
Capture a fresh reference after Phase A, not before.

**The observer must not draw from the simulation's stream.** `main.py:109` picks the focal bot with
`random.choice`, so today attaching a logger perturbs the run it is measuring. That is the same class
of bug as the shared stream and is fixed the same way — `AD-16`, observers read and never mutate.

**Phase A, as built — two decisions beyond the literal task list.**

1. *Part ids carry an owner.* `AD-9`'s tuple is `(run seed, gene id, expression index)`, but every
   bot in a run shares one hand-written body spec, so that tuple alone hands all twenty of them the
   same two part ids. The derivation is `(run_seed, owner_id, gene_id, expression_index)` — still a
   pure function of the run seed, so replay is exact, but unique within a run. `gene_id` reads a
   spec's `"id"` key when present and falls back to `type[index]`, which is the seam a genome will
   use. Covered by `test_part_ids_are_unique_within_a_run`.
2. *`_apply_hazard_damage` sorts too.* The task list names the three `query_*` sorts, but the hazard
   loop iterates the same `neighbors` **set** and accumulates each hit into a float, so it is the
   same order-sensitive path `AD-12` part 2 describes. It now iterates in `entity_id` order. This
   perturbs damage totals in their low bits relative to `c2886c4` — acceptable under "this story is
   expected to change the trajectory", but flagged because it is a behaviour change the task list
   did not ask for and is a one-line revert if unwanted.

**Phase A verification.** Two `main.py --headless --duration 5 --seed 42` runs in separate
processes produced byte-identical common prefixes on all three CSVs (population 186/186 rows, focal
5571/5576, deaths 117/117) — so determinism holds across processes, not merely within one. The full
suite passes from `/tmp`. No invariant failures to report from Phase A; that reporting duty belongs
to Phase B.

**Phase B, as built — what the harness found.**

*All six invariants pass on unmodified code.* Nothing was relaxed, no scenario was skipped, and
there is no invariant failure to report. The clean result was pressure-tested rather than taken at
face value: a sweep of **160,000 ticks over 40 seeds × 4 scenarios (400 deaths)** produced zero
violations with bounds checked **exactly** (`BOUND_EPS = 0.0`) and the essence tolerance at 1e-9
relative. An epsilon on the bounds checks was tried and then removed as unearned — measurement says
no bound ever overshoots even by a ULP, so forgiving one would only have made the assertion quieter.

*The essence tolerance is measured, not guessed.* Across 160,000 observed conversion pairs on
correct code the worst deviation was **4.0e-13 relative / 2.8e-15 absolute** — this is float
cancellation from reading a ~1e-2 transfer off a ~4e1 storage, not physics. `ESSENCE_REL_TOL = 1e-9`
and `ESSENCE_ABS_TOL = 1e-12` sit ~400× above the observed noise and ~1e7× below the ~60% error the
inversion produces.

*How the essence check gets per-pair deltas from observed storage.* The two requirements pull
against each other: the assertion is per pair, but every element is both a source and a target in
the cycle, so a plain before/after snapshot of the phase nets an inflow against an outflow and the
two can no longer be separated. `ObservedStorage` resolves it by watching **writes** to
`storage` while armed — a write that lowers an element is an observed outflow, one that raises it an
observed inflow. Each element is a source once and a target once per cycle, so the pair's two deltas
fall out. Nothing reads `spent`/`produced`, and the recorder is armed only inside `_cycle_elements`,
so eating and `_metabolize` are never in scope. This is also what makes the net hold for Story 1.2: a
second Metal→Water path accumulates into the same totals, and a whole-phase net delta could not tell
a correct second path from the same path running twice.

*The negative control needs a capped scenario, and that is a finding.* Uncapped, the inverted and
correct cycles are **numerically identical** — `produced` is `amount_out × CYCLE_EFFICIENCY` either
way — so a negative control on a roomy starting state proves nothing. The inversion is observable
only where a target is partially capped, which is why the `brimming` scenario (storage at 0.9995 of
capacity, every transfer capped) exists. It fails at tick 1 with a ~2e-3 essence loss, and fails
*only* on `essence exact`, so the essence invariant is doing the catching rather than a bounds check
riding along. `test_the_inversion_is_invisible_without_a_cap_which_is_why_brimming_exists` pins this
so the scenario is not later "simplified" away.

**Two known candidates, checked explicitly — neither is a harness failure.**

1. *Earth crisis drain outrun by organ regen* (already logged in `deferred-work.md`). **Still
   reproduces**, exactly as recorded: Wood organ 10, Earth storage 8.0, total storage below the
   crisis ceiling → Earth organ **50.0 → 50.1 in one tick** during "systemic metabolic failure". It
   is a real bug and it is **outside all six invariants** — the organ stays comfortably inside
   `[0, ORGAN_MAX]`, so nothing here fires and nothing here should. Recording it so the green
   harness is not mistaken for a clean bill of health on organ *behaviour*. Story 1.1 owns it.
2. *Derived-organ clamping.* `_derive_organ` clamps to `[0, ORGAN_MAX]`, so the organ-bounded
   invariant **cannot fail for Water by construction** — legs forced to integrity 5.0 still read
   `organ(WATER) == 100.0`. The out-of-range part is caught by the *part* integrity check instead.
   That division of labour is now pinned by a test rather than assumed, because it matters for Story
   1.3: the organ check will not notice repair overshooting, and the part check is the only net
   under it.

**Review round 1 — twelve findings closed, each mutation-verified.**

The review's central finding was that four of the six invariants were **never reached through the
harness loop**: deleting their calls from `run_scenario` left the suite green, because they were only
ever exercised by unit tests calling them directly on a hand-broken bot. The net advertised six
invariants and enforced two. Each of the four now has a test that breaks a real arithmetic site
— `_drain_organ`'s affordability guard, an unclamped repair in `LegPart.tick`, regeneration without
its `min(ORGAN_MAX, …)`, and an accumulator that overflows to infinity — so the violation arises from
*simulated* state and can only be caught by the harness calling the check.

Other structural changes this round:

- **`--ticks`** was added as a reproducible stop condition. `--duration` is wall-clock, so two
  same-seed runs reach different tick counts and can only be compared on a common prefix; the CLI
  seed test now asserts byte-identical logs, which was not previously expressible.
- **The manifest can now actually replay a run.** It records `config_fingerprint` (a hash of the
  *resolved* config, laws merged in — a config can be edited while keeping its name) and the final
  `ticks` reached, filled in at exit so a crashed run still leaves an attributable manifest. The
  README's replay claim was overstated and has been corrected to say what actually has to match.
- **Log paths come off the loggers** (`RunLogger.path_names`, `WorkshopLogger.path_name`) instead of
  `main()` re-spelling the filename convention. Visual and workshop manifests were hand-predicted and
  verified in neither.
- **`_field` type-tags its components**, so `7` and `"7"` are different — otherwise two entities keyed
  by the same id in different types share a stream, and a gene declaring `"id": 1` collides with one
  declaring `"id": "1"`. This changes every derived value, so `_PERSONALISATION` is bumped to `v2`:
  seeds recorded under v1 do not replay, which is what the version exists to make visible. Golden
  known-answer tests now pin the derivation, correct here precisely because a blake2b digest — unlike
  float state — *is* bit-exact across architectures.
- **`owner_id` is keyword-required** with no default, and `make_parts` rejects duplicate gene ids.
- **The determinism digest folds the full world state**, shared with the reproducibility tests via
  `tests/state_snapshot.py`. It previously folded only live-resource count and amount sum, leaving
  resource positions, hazards, respawn timers and `_next_id` invisible — so a loss of determinism in
  `_pick_position`, the world stream's *main consumer*, would not have moved it.
- **Scenarios declare what they exercise.** `HarnessResult.evaluations` counts *meaningful*
  evaluations and `assert_invariants` checks the declaration both ways. This surfaced a real hole:
  `starving` holds no storage, so every conversion pair is skipped and it exercises the essence
  invariant **zero** times while appearing to pass it 15,000 times. Now declared on the scenario.
- **The AST randomness guard** resolves import aliases and covers `import random as rnd`,
  `from random import uniform`, `numpy.random.*`, `os.urandom`, `secrets` and `uuid`, and sweeps with
  `rglob` rather than top-level `glob`.

**Mutation verification.** All thirteen mutations — the review's plus the extras above — were
re-applied to the source and each now fails the suite. Two needed a second pass: the observer test
built its own correctly-wired logger and so said nothing about `main()`'s wiring (now compared against
an unobserved in-process run of the same seed), and the `owner_id` default was unreachable from any
call site (now a `TypeError`).

**Report, do not relax.** The harness runs against unmodified code. Two candidates are already known
from earlier reviews and may surface: the Earth crisis drain being outrun by regen, and unclamped
derived organs (now clamped). If an invariant fails, record it here with the tick and value and leave
the assertion intact.

## Verification

**Commands:**
- `source .venv/bin/activate && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy make check` -- expected: ruff, mypy, full suite clean.
- `cd /tmp && python -m pytest /Users/bradfoley/Desktop/taobots/tests` -- expected: passes from a foreign working directory.
- `grep -rn "random\.\(uniform\|choice\|choices\|random\|randint\)\|uuid4" --include="*.py" world.py taobot_simple.py body_factory.py main.py` -- expected: no module-level draws; only explicit `Random` instance method calls.
- `python main.py --headless --duration 5 --seed 42` twice, comparing the common prefix of the population CSVs -- expected: byte-identical, and a manifest written for each run. Back up `logs/default_focal.csv` and `logs/default_deaths.csv` first.

**Manual checks:**
- Open the run manifest and confirm the recorded seed replays the run.

## Suggested Review Order

**Phase A — reproducibility**

- Entry point: the one mixing step. Everything derived in the project is a view on this.
  [`rng.py:61`](../../rng.py#L61)

- Streams by label, so unrelated subsystems cannot collide.
  [`rng.py:79`](../../rng.py#L79)

- Part ids, replacing `uuid4()` — which no seed could ever reach.
  [`rng.py:94`](../../rng.py#L94)

- The only unseeded randomness left in the project, called once per run.
  [`rng.py:105`](../../rng.py#L105)

- Provenance: seed, config fingerprint, git SHA, Python version, final tick count.
  [`main.py:399`](../../main.py#L399)

- Fingerprints the *resolved* config with laws merged — a path alone cannot prove a replay.
  [`main.py:323`](../../main.py#L323)

**Phase B — the harness**

- Scenarios are data. Stories 1.2 and 1.3 add an entry, not a second harness.
  [`invariant_harness.py:128`](../../tests/invariant_harness.py#L128)

- The hard part: watches writes to `storage` so each pair's inflow and outflow separate.
  [`invariant_harness.py:170`](../../tests/invariant_harness.py#L170)

- Equality on observed deltas, scoped to conversion only — never eating or metabolism.
  [`invariant_harness.py:382`](../../tests/invariant_harness.py#L382)

- The loop. Unwiring any check here now fails eight tests; before review it failed none.
  [`invariant_harness.py:505`](../../tests/invariant_harness.py#L505)

**Tests — the ones that exist because mutation testing broke the first pass**

- Proves the essence invariant has teeth. Only observable under a cap, which is why `brimming` exists.
  [`test_invariants.py:166`](../../tests/test_invariants.py#L166)

- Catches a scenario that silently contributes nothing — `starving` exercised essence zero times.
  [`test_invariants.py:303`](../../tests/test_invariants.py#L303)
