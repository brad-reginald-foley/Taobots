# E1 Readiness Delta

> **⚠ SUPERSEDED — 2026-08-11.** Everything in this document has been folded into
> [`epic-e1-legs.md`](epic-e1-legs.md), which is now the single canonical statement of E1.
> Kept as the record of *what the architect pass changed and why*. **Do not build from it** — where
> it and the epic differ in wording, the epic is current. Sprint tracking is generated from the epic
> only.

**Produced by:** architect pass, 2026-08-11 · **Against:** `epic-e1-legs.md` @ `c70ed05`
**Governed by:** [`ARCHITECTURE-SPINE.md`](architecture/architecture-taobots-2026-08-10/ARCHITECTURE-SPINE.md)

What must change in E1 before a dev agent can execute it without inventing architectural decisions.
Every item cites the `AD` that forces it.

**Story renumbering.** The epic now uses the `Epic N` / `Story N.M` numbering that sprint tracking
parses. `E1-S0a` → Story 1.0a, `E1-S0b` → 1.0b, `E1-S0c` → 1.0c, `E1-S0d` → 1.0d, `E1-S1` → 1.1,
`E1-S2` → 1.2, `E1-S3` → 1.3, `E1-S4` → 1.4.

---

## Summary

E1's four stories are sound and stay. Three things sit underneath them that the epic assumed were
already true and are not:

1. The organ model is **wrong** (Wood/Earth swapped) and **partly dead** (`organs[WATER]` is never
   written). E1-S4 produces exit-criterion evidence read off those gauges.
2. The reproducibility guarantees E1's own QA section demands — seeded determinism, a byte-identical
   regression baseline — **cannot currently be built**. There is one global RNG and no run manifest.
3. The workshop, where E1 mandates that all new constants be derived, has **materially different
   pressures** from the world those constants will run in.

That adds four frontloaded stories. E1 grows from 4 stories to 8.

---

## New stories

### E1-S0a — Correct the Wood/Earth organ roles

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
| `tests/test_world.py:86,121`, `tests/test_taobot_simple.py:51` | follow |
| `PLAN.md` organ table | rewritten, replacing the ⚠ warning block |
| `taobot_simple.py` → `taobot.py` | module rename, per `AD-17` — plus the class, and `PLAN.md`'s Phase 2 file table |

**On the rename.** `AD-17` settles the long-open `taobot_simple.py` / `taobot.py` question: there is
one organism class, hollowed out in place, never a parallel "full" class to cut over to. The name is
already wrong — `TaobotSimple` owns the organ model — and gets worse as it comes to own a
gene-expressed neural organism. This story is already a relabelling that touches the file heavily,
which makes it the cheapest moment to do it.

**Acceptance:** the swap is behaviour-preserving under relabelling — a seeded run before and after
produces the same population trajectory with columns renamed. Death fires on body integrity.
`PLAN.md`'s warning block is gone because the table is now true, and its file table records
`taobot.py` as built rather than missing.

**Explicitly not doing:** changing balance values. This is a relabelling, not a retune.

---

### E1-S0b — Derive the Water organ from the legs

**Why:** `AD-5`. Nothing writes `organs[WATER]`; `_metabolize` drains Fire/Earth/Wood/Metal only
(`taobot_simple.py:441-461`) and `ORGAN_STORAGE_DRAIN["WATER"]` is dead. Every log you hold records
`organ_WATER` as a constant `100.0`. E1's goal is to *close the legs organ system*, and the Water
organ is currently not part of it.

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

**Do not** derive Metal, Wood or Fire here. `AD-5` stages the transition per organ — Metal at E2,
Wood at E3, Fire at E4. Deriving Metal now would read `0.0` (no armor parts exist), strip all damage
absorption, and make hazards abruptly lethal mid-sprint — invalidating E1-S1's premise.

---

### E1-S0c — Align the workshop with the world it calibrates

**Why:** `AD-14`. E1 mandates that S2 and S3 constants be derived by stepping through workshop mode,
and E1-S1 measures hazard pressure there. Measured divergence today:

| | Resources /u² | Hazards /u² | Respawn |
| --- | --- | --- | --- |
| `default_world` (80×60) | 0.031 | 0.0042 | 60 ticks |
| `workshop` (30×25) | 0.020 | **0.0133** | 30 ticks |

The workshop is ~3.2× more hazard-dense and ~35% more resource-scarce, with resources returning
twice as fast. Constants tuned there do not transfer.

**Do:** align workshop resource/hazard density and respawn delay to `default_world`, adjusting counts
for the smaller area. Extract shared laws to `configs/laws.json` (`AD-13`).

**Acceptance:** per-unit-area densities and respawn match `default_world` within rounding, or any
remaining divergence is recorded in the config with its reason. `laws.json` exists and every world
config references it; `fire_arena`'s `degrade_rate` override remains, now explicit.

**Blocks:** E1-S1, E1-S2, E1-S3 — all three derive numbers from workshop observation.

---

### E1-S0d — Reproducibility harness

**Why:** `AD-12`. E1's QA section already requires a determinism invariant ("same seed, same tick
count → identical state") and a regression guard ("a seeded headless run must produce logs identical
to the pre-change build"). Neither is buildable today: one global RNG stream, no seed recorded in any
log, and tests that never seed at all.

**Do:**
- Per-entity `random.Random` streams from a single derivation function over `(world_seed, entity_id)`;
  a world stream for spawning and placement. No module-level `random.*` calls remain
- `entity_id` as tiebreaker in `query_resources`, `query_hazards`, `query_taobots` — they currently
  sort on distance alone, so ties resolve by set-iteration order
- Deterministic part ids from `(run seed, gene id, expression index)`, replacing `uuid4()`, which
  draws from `os.urandom` and no seed can reach (`AD-9`)
- A run manifest per run: seed, config name, git SHA, Python version, timestamp
- A seeded fixture in `conftest.py`
- A determinism test: same seed, N ticks, twice, identical state hash

**Acceptance:** two runs at the same seed produce byte-identical logs. Adding a `random` call to one
archetype does not change any other bot's trajectory. Every log file can be traced to the seed and
commit that produced it.

**Blocks:** E1-S2's "byte-identical above threshold" acceptance criterion.

---

## Changes to existing stories

### E1-S1 — Investigate the current damage model

- **Sequencing:** now runs after **E1-S0c**. Its finding is about hazard pressure "at current
  tuning", and workshop tuning currently differs from the world by 3.2× in hazard density — the
  headline number would be wrong.
- **Add to acceptance:** state the hazard density the observation was made at, so the finding can be
  re-read later against a changed config.
- Unchanged otherwise. It still ships knowledge, not code.

### E1-S2 — Water deficit triggers Metal→Water conversion

- **Where it lands is now specified.** The epic says "implemented as a separable function, not inline
  in `_cycle_elements`". Sharpen: it lands on `ChiPool` behind the chi port (`AD-3`, `AD-4`), and it
  executes inside the **chi phase** alongside the passive Sheng cycle, from one pre-tick snapshot
  (`AD-1`). One conversion site makes double-conversion and threshold thrashing structurally
  impossible rather than merely test-detectable — which is what the epic's QA section was worried
  about.
- **Depends on E1-S0d** for the byte-identical regression guard.
- The Metal→Water direction is unaffected by `AD-7`; that correction is about organ *roles*, not
  productive-cycle order.

### E1-S3 — Earth-consuming leg repair

- **Widens from "legs repair" to "parts repair, legs first"** (`AD-8`). `STR-2` says *all* body parts
  are made of Earth and repaired by absorbing it, so degrade-and-repair belongs on the `BodyPart`
  base, not in `LegPart`. E2's armor and E3's meridians then inherit it instead of reimplementing it.
- **Every part carries two elements:** a function element (Water for legs) and Earth for structure.
  The current `BodyPart.__init__` takes only one, which is why the epic had no room for this.
- **Earth demand goes through the port** and is split **pro-rata across every requester of Earth**,
  not per organ system — structural repair makes parts of different systems compete in one tick
  (`AD-3`).

### E1-S4 — Verify the leg integrity round trip

- **A criterion question to settle before collecting evidence.** Phase 2 exit criterion 3 asks for an
  organ round trip *and* each part's round trip. Once `AD-5` lands, the Water organ *is* the mean of
  leg integrity — so the two become one measurement. That is a genuine weakening of the criterion and
  should be a recorded decision rather than something discovered while writing the evidence up.
- Suggested resolution: keep both, but source the organ half from a *different* organ than the part
  half — Earth (the body) degrading and recovering is independent evidence from leg integrity doing so.

---

## Ordering

```
E1-S0a  correct Wood/Earth roles
   ↓
E1-S0b  derive Water organ from legs
   ↓
E1-S0c  align workshop  ──┐
E1-S0d  reproducibility ──┤   (independent of each other)
   ↓                      ↓
E1-S1   damage spike  ← needs S0c
   ↓
E1-S2   deficit conversion  ← needs S0c, S0d
   ↓
E1-S3   parts repair  ← needs S0c
   ↓
E1-S4   round-trip verification
```

`E1-S0a` before `E1-S0b` because deriving organs is confusing to review while two of them are
mislabelled. `E1-S1` still runs alone and reports before S2 or S3 start, per the epic's own
"run one story at a time" rule.

---

## What the dev agent must not decide

| Question | Status |
| --- | --- |
| `Q6` — storage/chi boundary, where the economy lives | **Answered.** `docs/domain-spec.md` § Answered questions; `AD-2`, `AD-3`, `AD-4` |
| `Q8` — how a gene reference resolves under one-to-many expression | **Open, deferred to Phase 4/6.** E3 owns the seam only (`AD-11`). Not an E1 concern |
| `Q4` — destructive-cycle rate | **Open, deferred** until the organ epics complete. Do not wire `degrade_rate` |
| Allocation policy under scarcity | **Decided:** pro-rata by demand across all requesters of an element (`AD-3`) |
| Tick ordering | **Decided:** `AD-1`. Do not add work outside a named phase |
| Where a new constant lives | **Decided:** `AD-13`'s law test |
