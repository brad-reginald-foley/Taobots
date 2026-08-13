---
title: 'Story 1.2 — Water deficit triggers Metal-to-Water conversion'
type: 'feature'
created: '2026-08-12'
status: 'done'
review_loop_iteration: 0
baseline_commit: '2007be4444119173be4ebb2ede9b308793060587'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Water starvation is the only source of leg damage, and nothing prevents it. The Sheng
cycle runs unconditionally at a rate proportional to source storage, so it cannot respond to demand
— a depleted Water pool receives `0.0008 × storage[METAL]` per tick whether Water is full or empty.
This is the prevention half of the legs loop, and the first conversion in the system that serves
demand rather than running as background chemistry.

**Approach:** When Water storage falls below a threshold fraction of capacity, convert Metal to
Water at an elevated rate until it recovers. Conversion becomes a capability of the **chi tier**,
not a method on the organism (`AD-4`): introduce `ChiPool` behind a `request`/`deposit` port
(`AD-3`) wrapping today's `storage` dict, which `AD-2` already designates as the pool tier. Both the
passive cycle and the new demand path run from **one conversion site** so double-conversion and
threshold thrashing are structurally impossible rather than merely test-detectable.

## Boundaries & Constraints

**Always:**
- **Exactly one conversion site.** Both paths run there, from a single pre-tick snapshot.
- Conversion is a capability of the chi tier, landing on `ChiPool` — never a method on
  `TaobotSimple`. E3 substitutes `MeridianNetwork` behind the same port.
- `spent` is derived from `produced` **after** capping on available room (`AD-4`). Essence may be
  lost to efficiency, never manufactured. Story 1.0d's harness asserts this every tick.
- **Attribute conversion per path.** Both paths move Metal→Water, so a whole-tick delta cannot
  distinguish "both ran once" from "one ran twice". Record which path moved what.
- New constants are sited by `AD-13`'s law test and **derived in the workshop**, with the reasoning
  recorded beside them — never chosen.
- A consumer calls the port; no consumer mutates a chi dict.

**Ask First:**
- Reordering the tick phases — see Design Notes. `AD-1` wants `chi → upkeep`; today upkeep runs
  first, and this story's own acceptance forbids changing behaviour above the threshold.
- Any change to `CYCLE_RATE`, `CYCLE_EFFICIENCY` or `CYCLE_SEQUENCE`.
- Introducing per-element buffers, or splitting `storage` into anything other than the pool tier.

**Never:**
- Do not add leg repair — that is Story 1.3. This story prevents the starvation; it does not cure
  the damage.
- Do not implement pro-rata allocation under scarcity yet. Conversion is the only requester here;
  `AD-3`'s pro-rata split first matters at 1.3, when structural repair competes for Earth. The port
  shape must not preclude it.
- Do not derive any further organ, and do not touch hazard damage.
- Do not change the passive cycle's behaviour when Water is above the threshold.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Above threshold | Water above deficit fraction | Passive cycle only; byte-identical to pre-change | N/A |
| Below threshold | Water below, Metal available | Water rises, Metal falls, measurably faster than passive | N/A |
| Exact boundary | Water exactly at the threshold | Deterministic, stated side; no oscillation tick to tick | N/A |
| No Metal | Water below threshold, Metal empty | No conversion; Water stays low; no negative storage | N/A |
| Water at capacity | Water full during a deficit tick | Capped; `spent` derived after capping, nothing manufactured | N/A |
| Path attribution | both paths move Metal→Water in one tick | Each path's contribution separately recorded | N/A |
| Recovery | Water climbs back above threshold | Elevated rate stops; passive resumes | N/A |

</frozen-after-approval>

## Code Map

Line anchors verified against `2007be4` on 2026-08-12.

- `taobot_simple.py` -- `_cycle_elements` is the existing and only conversion site: it snapshots
  pre-tick storage, computes `produced = min(amount_out * CYCLE_EFFICIENCY, room)` then
  `spent = produced / CYCLE_EFFICIENCY` (the cap-then-derive order `AD-4` requires and 1.0d's
  negative control inverts), and applies all transfers together. `CYCLE_SEQUENCE` includes
  `(METAL, WATER)` — the deficit path reinforces an edge that already exists.
- `taobot_simple.py` -- `tick()` runs `sense → decide → act → _tick_body_parts → _metabolize →
  _cycle_elements → age`. Note conversion runs **after** upkeep, which is the reverse of `AD-1`.
- `taobot_simple.py` -- `self.storage` and `self.storage_capacity` are the pool tier per `AD-2`.
  Consumers today mutate the dict directly: `_act` (collection), `_tick_body_parts` (part
  replenish), `_drain_organ` (upkeep). Only conversion needs to move behind the port for this
  story; the rest can follow when they must.
- `body_parts.py` -- `BodyPart.replenish(available)` is the existing per-part draw and the shape a
  `request()` call will eventually take. `LegPart.reserve` is `AD-2`'s buffer tier.
- `tests/invariant_harness.py` -- `SCENARIOS` is the list a new entry is appended to. The essence
  check watches writes to `storage` while armed inside the conversion phase, so a second path
  accumulating into the same totals is already covered — but the negative control reimplements the
  cycle by hand and **will drift**; re-verify it, do not assume it.
- `configs/laws.json` -- the home for the two new constants if they pass `AD-13`'s law test.

**Measured context for derivation.** Water storage reaches 0.00 and spends real time empty: 6 dry
spells across 6 seeds × 4000 workshop ticks, median 29 ticks, longest 466. Metal is consistently the
healthiest element — mean 7.89 at death against Fire's 0.26 — so it is the right donor.

**Read-only evidence:** `AD-1:81` (phases; all conversion in `chi`), `AD-2:92` (pool vs buffers),
`AD-3:98` (the port; pro-rata; a denied request is correct), `AD-4` (conversion belongs to the chi
tier; cap then derive), `AD-13:177` (four homes for tunables).

## Tasks & Acceptance

**Execution:**
- [x] `chi.py` (new) -- `ChiPool` implementing the `AD-3` port over the existing storage dict: `request(element, amount) -> granted` and `deposit(element, amount) -> accepted`, plus the conversion capability. No consumer mutates a chi dict through it. Leave room for pro-rata allocation without building it.
- [x] `chi.py` -- move the passive Sheng cycle onto `ChiPool` as the single conversion site, preserving cap-then-derive exactly. Behaviour must be unchanged: this step alone is a pure refactor.
- [x] `chi.py` -- add the demand-triggered Metal→Water path at the same site, from the same pre-tick snapshot: below the deficit threshold, convert Metal to Water at the elevated rate until Water recovers.
- [x] `chi.py` -- record each path's contribution separately so a tick can distinguish "both ran once" from "one ran twice", and expose it for the workshop logger.
- [x] `taobot_simple.py` -- hand the organism a `ChiPool` and replace `_cycle_elements` with a call to it. The organism must not own conversion logic.
- [x] `configs/laws.json` -- site the deficit threshold fraction and the elevated rate per `AD-13`, **derived in the workshop** with the reasoning recorded beside them. If either fails the law test, put it in the world config instead and say why.
- [x] `main.py` -- surface the per-path attribution in `WorkshopLogger` so the trigger is observable tick by tick, per the epic's workshop-completeness rule.
- [x] `renderer.py` -- show the deficit state in the workshop inspector, so the trigger firing can be watched rather than only read from a CSV.
- [x] `tests/` -- cover the matrix: above threshold, below threshold, the exact boundary, no Metal available, Water at capacity, recovery, and per-path attribution.
- [x] `tests/invariant_harness.py` -- add a scenario driving a bot repeatedly across the deficit, per the epic. Re-verify 1.0d's inverted-cycle negative control still fails; it reimplements the cycle by hand and is expected to drift.

**Acceptance Criteria:**
- Given Water above the threshold, when a seeded run is compared to the pre-change build, then the logs are byte-identical.
- Given Water below the threshold with Metal available, when the tick runs, then Water rises and Metal falls at a rate measurably above passive `CYCLE_RATE`.
- Given any conversion tick, when essence is measured on observed storage deltas, then `Δtarget == −Δsource × CYCLE_EFFICIENCY` within tolerance — 1.0d's harness asserts this and must stay green.
- Given a tick where both paths move Metal→Water, when the logs are read, then each path's contribution is separately attributable.
- Given a workshop run, when stepped to the tick the trigger fires, then the rate change is visible in `storage_METAL` and `storage_WATER`.
- Given `make check`, then ruff, mypy and the full suite pass, and the inverted-cycle negative control still fails.

## Spec Change Log

## Design Notes

**The tick order is left alone, deliberately.** `AD-1` specifies `sense → decide → act → chi →
upkeep → age`, but today conversion runs *after* upkeep. Reordering would change behaviour above the
deficit threshold, which this story's own acceptance forbids ("byte-identical to today"). The two
requirements are in direct conflict, so the narrower one wins: build the port and the demand path,
leave the ordering. The restructure needs its own story with its own baseline — recorded in
`deferred-work.md`.

**Why the port is worth building for one caller.** `AD-4` is explicit that conversion must not
accrete on the organism, because E3 lifts it wholesale. Only conversion moves behind the port here;
collection, part replenish and organ upkeep keep mutating storage directly and migrate when they
must. That is a deliberate partial migration, not an oversight — the alternative is a large refactor
inside a story that also introduces new behaviour.

**Deriving the two constants.** Both must come from workshop observation, not judgement. The
threshold should sit where a deficit is real but recoverable; measured dry spells have a median of
29 ticks and a long tail to 466. The elevated rate should refill Water over a span comparable to a
typical dry spell without emptying Metal, which is the healthiest pool at death (mean 7.89). Record
the sweep that produced them.

**Expect the negative control to break.** 1.0d's `inverted_cycle_elements` is a hand-copy of the
real algorithm, kept in sync by a digest-equality test that this story's second path invalidates by
design. That was logged as a known consequence — re-derive the control against the new
implementation rather than relaxing it.

---

## Implementation Notes (added 2026-08-12)

**The demand path is a regulator, not a pulse.** It asks for the *shortfall* — the gap between
projected Water and the threshold — granted up to what the elevated rate allows on the Metal left
after the passive cycle has taken its share. Water is therefore restored *to* the threshold and never
past it. That is what makes the boundary row of the matrix hold: a path that converted at the
elevated rate regardless of the size of the deficit would push Water over the line, switch off, let
it fall back under and fire again, which is oscillation tick to tick. It also decouples the two
constants — the threshold sets how much sits in the pool, the rate sets how fast it is restored — and
that decoupling is what let each be derived against its own criterion.

**Deriving them needed a sharper metric than the story anticipated.** Total leg integrity loss cannot
discriminate: it is dominated by bots dying with every pool empty, which no conversion reaches, and
is nearly flat across the whole grid. Splitting out *preventable* loss — integrity lost on ticks
where the bot still held Metal worth converting — turned that plateau into two clean knees, each
matching a mechanical prediction. Rate: `drain_max / (CYCLE_EFFICIENCY × metal floor)` = `0.020 /
(0.8 × 1.0)` = 0.025. Threshold: four ticks of leg draw held in the smallest Water pool in play,
`4 × 0.020 / 10.0` = 0.008. Full sweep tables and the `default_world` transfer check are recorded in
`configs/laws.json` beside the values.

**The negative control drifted exactly as predicted, and was re-derived rather than relaxed.** It is
now a hand-copy of `ChiPool.convert` with `spent` derived before the cap in *both* paths, and it
patches `ChiPool.convert` — the real conversion site — instead of a method on the organism.
`test_the_inverted_demand_path_is_caught_too` runs it in the deficit regime, where the demand path is
the one under a cap, so the second path is not riding on a net that only ever watched the first.
A new test, `test_the_negative_control_still_mirrors_the_real_algorithm`, pins the drift itself:
away from every cap the real and inverted implementations must agree digit for digit, so a third
conversion path added without updating the control fails loudly instead of silently.

**Two acceptance criteria could not be met as literally written, and were met in substance:**

- *"Given Water above the threshold ... the logs are byte-identical."* In `default_world` at seed 42
  Water reaches 0.00 within the first few ticks, so a live run diverges immediately and legitimately —
  that is the story working. The guard was instead run with the demand path disabled by a
  `water_deficit_threshold` of 0.0 in a copied config: focal, deaths and population CSVs are all
  byte-identical to the `2007be4` worktree. Because that only covers the states one seeded run
  visits, `test_above_the_threshold_is_byte_identical_to_the_pre_change_cycle` re-implements the
  pre-change `_cycle_elements` verbatim and demands *exact float equality* across six states chosen
  to take every branch — including capped and empty ones. That runs in CI; the worktree diff cannot.
- *The manifest is not byte-identical*, by design: `config_fingerprint` gained the chi block, because
  a run is not replayable without laws that are read every tick.

**Residual finding: the trigger is structurally one tick late.** The chi phase runs after upkeep, so
the legs drain and degrade before conversion is consulted. ~0.1 of preventable integrity loss
survives at every setting because of it, against 14–46 with the trigger off. It is the ordering, not
the buffer — raising the threshold fifteenfold does not reduce it. Logged in `deferred-work.md` with
the tick-order restructure it belongs to.

---

## Review Response (2026-08-12)

Two correctness bugs and eight test/documentation gaps were found. All are fixed; each is now
pinned by a mutation that was confirmed to fail. Mutation run: 11/11 caught.

**Correctness.**

- `ChiPool.moved` returned the *first* matching transfer instead of summing, so a path that ever
  committed twice on one edge would have been half-reported — hiding exactly the failure per-path
  attribution exists to expose, and silently breaking the `Δstorage == passive + deficit`
  reconciliation the logs rest on. It now sums.
- The apply step clamped only the source (`max(0.0, storage - spent)`) while crediting the target the
  full `produced`, which *creates* essence if a source cannot pay in full. Rewritten as
  `ChiPool.apply`, which withdraws through `request` and, when the withdrawal falls short, recomputes
  what arrives from what was actually withdrawn. The failure is now unrepresentable rather than
  caught. Byte-identity is preserved: `request` returns the requested amount unchanged when it can
  be met, so the common path uses the planned `produced` untouched — re-verified against the
  `2007be4` worktree, focal/deaths/population CSVs all identical.

**Design changes made in response.**

- `apply` routes through `request`/`deposit`, so the port has a real caller and there is one
  implementation of the capacity cap instead of two. Only *planning* stays outside the port, and for
  a stated reason: the passive cycle must resolve all five transfers against a frozen snapshot.
- `deficit_served` added alongside `deficit_active`. `deficit_active` keeps its meaning — Water is
  below the line, which is true and worth showing for a bot starving beside an empty Metal pool —
  and `deficit_served` says whether anything moved. New CSV column; the panel reads `no Metal`
  rather than `+0.000`.
- The deficit display now appears on **both** inspectors. It costs no rows, and `python main.py` is
  the mode a user opens first; a starving bot there should not be the one case the panel is silent
  about.
- `storage_capacity` became a property over the pool, matching `storage`.
- `WorldConfig.chi` gained a default, so the config can still be built outside `from_json`.

**Two points of disagreement, both resolved in the reviewer's favour on the substance:**

- *"`deficit_active` latches on when there is no Metal."* It is not a latch — it is the honest answer
  to "is Water below the threshold", and a starving bot really is in deficit. But the reviewer is
  right that the panel and CSV could not distinguish armed-from-helpless, so a second flag was added
  rather than the first one redefined.
- *An upper bound below 1.0 on `deficit_conversion_rate`.* The threshold got one
  (`MAX_WATER_DEFICIT_THRESHOLD = 0.5`); the rate deliberately did not. It is a ceiling on the
  *flow*, and the flow is already bounded twice over by things a law cannot raise — the path asks
  only for the shortfall, and can spend only the Metal present. A rate of a million refills the
  deficit in one tick instead of several; it cannot convert more Metal in total and cannot lift
  Water past the threshold. There is nothing to escape, and
  `test_an_enormous_rate_is_allowed_because_it_cannot_escape_anything` demonstrates it. Finiteness
  is now checked on both, which is the half of that finding that was a real bug: NaN passed
  `< 0.0` and silently disabled the demand path for a whole run.

**The derivation was corrected, not just re-explained.** Two claims in it were wrong:

- *"never improves again above 0.008"* was false — 0.120 reads marginally lower. The sweep now
  prints per-seed spread, which shows why it is noise: on the plateau each cell totals 0.03–0.10
  with a spread of 0.045–0.052, so one seed contributes essentially the whole figure. The real
  argument for 0.008 is the cost side, which is monotone and well outside the noise.
- *The rate floor was presented as an independent confirmation of the knee.* It is not: the
  prediction `drain_max / (EFFICIENCY × metal_floor)` shares its 1.0 Metal floor with the
  "preventable" metric. `tools/derive_chi_laws.py floor` now sweeps that constant and shows the
  effect — at a metric floor of 0.25 the knee moves to 0.064, at 4.0 it stays at 0.016 instead of
  following the prediction down to 0.0062. The prediction is a sanity check that lands in the right
  octave. What the sweep genuinely establishes is the knee's *shape* — a collapse over roughly one
  octave, in the same place for every archetype and under contention as well as in the workshop —
  and that the shipped 0.025 sits above the measured knee (~0.016) with margin.

**Also corrected: a false claim inherited from Story 1.0d.** `ObservedStorage`'s docstring asserted
that the essence invariant distinguishes "both paths ran once" from "one ran twice". It does not —
the check is a ratio, and a duplicated transfer doubles both sides. Verified by duplicating the
passive commit, which the harness passed. The discriminator is `last_transfers`. Docstring, scenario
comment and `deferred-work.md` all corrected, since the claim had been repeated across two stories.

**The tick order is now enforced.** `test_the_tick_runs_the_phases_in_the_recorded_order` replays the
recorded phase sequence on a twin bot and compares state digit for digit each tick, with a companion
test asserting that the `AD-1` reorder really would change behaviour — so the pin cannot be sitting
on a distinction that makes no difference. Without it, "we deliberately did not reorder" was an
unverified claim about a change that is next on the list.

**Still open, and worth stating:** the derivation script is committed and the tables are
regenerable, but "preventable integrity loss" remains a measurement the script computes rather than
a logged column, so it cannot be read off a normal run.

## Verification

**Commands:**
- `source .venv/bin/activate && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy make check` -- expected: ruff, mypy, full suite clean.
- `python main.py --headless --seed 42 --ticks 300` against a baseline worktree -- expected: byte-identical while Water stays above the threshold. Run from a temp directory; `logs/default_focal.csv` and `logs/default_deaths.csv` hold the user's data.
- `grep -rn "storage\[" --include="*.py" chi.py taobot_simple.py` -- expected: conversion touches storage only through the pool.

**Manual checks:**
- `python main.py --workshop` -- step to a tick where Water drops below the threshold and watch `storage_METAL` fall and `storage_WATER` rise faster than the passive trickle, with the deficit state visible in the inspector.

## Suggested Review Order

**The chi tier**

- Entry point: the single conversion site. Both paths, one pre-tick snapshot.
  [`chi.py:308`](../../chi.py#L308)

- Every transfer goes through the port, and what arrives is recomputed from what was actually withdrawn.
  [`chi.py:245`](../../chi.py#L245)

- Per-path attribution. Sums every match — returning the first would hide "one path ran twice".
  [`chi.py:273`](../../chi.py#L273)

- The trigger level as a fraction of *this pool's* Water capacity, so archetypes differ correctly.
  [`chi.py:302`](../../chi.py#L302)

- The two laws, with their validation. An evolvable threshold would abolish Water starvation.
  [`chi.py:94`](../../chi.py#L94)

**The derivation**

- Regenerates the numbers. Committed because a derivation nobody can re-run is a claim, not evidence.
  [`derive_chi_laws.py`](../../tools/derive_chi_laws.py)

**Tests**

- Byte-identity above the threshold, against a verbatim copy of the pre-change cycle.
  [`test_chi.py:319`](../../tests/test_chi.py#L319)

- Pins the attribution mechanism the whole story rests on.
  [`test_chi.py:652`](../../tests/test_chi.py#L652)
