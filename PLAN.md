# Taobots: Project Description & Development Plan

## Context

**Taobots** is an evolutionary life simulation set in "Pangu," a world governed by the 5 Taoist elements (Wood, Water, Metal, Fire, Earth). Taobots are creatures with genetically-encoded bodies — neurons, legs, meridians, armor, and claws — that eat, fight, reproduce, and evolve across generations.

The long-term vision has two halves:

**Simulation** (this plan): Build and tune the simulation from the ground up, staging complexity carefully. Each phase produces a running, testable system. Later phases inform the design of earlier ones — neurons before genetics because you need to know what a neuron does at runtime before encoding one in a gene; genetics before developmental encoding because you need to know what parameters need evolving before designing the developmental machinery.

**Game layer** (future, contingent on simulation working): Arena mode where people upload champion taobots to compete in parameterized worlds ("fire arena," "forest world"), trade genetic codes, trace bloodlines, and eventually do direct genetic engineering through a UI.

**Key architectural decisions made now that enable the game layer later:**
- Genome format is a clean, self-contained, portable JSON artifact — no runtime IDs. It declares the *rules* that generate a body, not the finished body; see [Design Goals](#design-goals-evolvability-first)
- World is a config object (spawn rates, hazard densities, element chemistry rates) not hardcoded constants — arena types are just different configs
- Gene bank stores rich lineage metadata (timestamps, arena context, peak karma) from Phase 4 onward
- Karma is multidimensional enough that champions have recognizable styles, not just a single scalar
- Rendering is cleanly separated from logic (renderer.py) so a visual design pass can happen without touching simulation code

**Prior prototype:** `../element_sim` — pygame, Python, 5-element system, component-based agents, no genetics or learning. Worth reusing: element definitions, torus math, pygame loop scaffold, entity classes.

**Where things are written down:**

| Document | Holds |
|---|---|
| `docs/domain-spec.md` | Subsystem requirements with stable IDs (`NEU-3`, `MER-7`) and the open-questions register |
| `PLAN.md` (this file) | Phase order, scope, and exit criteria — schedules the requirements, does not restate them |
| `README.md` | How to run what exists today, plus the world's lore |

Phases below cite requirement IDs. When a requirement changes, it changes in `docs/domain-spec.md`.

---

## Design Goals: Evolvability First

The simulation exists to evolve things. Architectural decisions are judged against whether they
make evolution work — not against biological fidelity. The aim is a system with the *properties* of
a developing organism, not a faithful model of one. **We are not building a drosophila embryo in
silico.** Where a cheaper mechanism delivers the same properties, take the cheaper mechanism.

Three properties, in priority order:

1. **Generativity** — one gene can produce many parts. A single gene expressing as six legs at
   evenly spaced angles (`BODY-6`) is the point, not an optimization. Reuse is what lets a genome
   stay small while a body grows complex.
2. **Robustness** — a mutation must never produce an invalid body. Deleting a gene that others
   reference, or nudging a part's position, has to yield something that still runs. Wherever a
   reference can dangle, there must be a rule for what happens when it does.
3. **Evolvability** — a small genotype change produces a small, *coherent* phenotype change.
   This comes mostly from reuse: when one gene governs a coordinated set of parts, a nudge moves
   the whole set together instead of breaking symmetry at random.

These are the criteria to argue from when a design choice is contested.

### The genome is a recipe, not a blueprint

The mental model that governs everything downstream:

> **A genome is a set of instructions for developmentally generating a taobot.** It is not a
> parts list, and genes do not map one-to-one onto body parts.

Gene 42 says *"create a neuron with this start point, this end point, these setpoints."* Under
radial symmetry that one instruction produces six neurons. Each of those neurons is a distinct
runtime object with its own identity and its own state.

This forces two separate ID spaces, which must not be collapsed:

| Space | What it is | Lifetime |
|---|---|---|
| **Gene / spec id** | Stable, declarable, part of the genome. What genes use to reference each other. | Persists in the genome file |
| **Part id** | Assigned when an instruction is expressed into a concrete part. | Runtime only |

A part records which instruction produced it, so provenance runs one way: gene → parts. Because
expression is one-to-many, a part id can never be *equal to* a gene id — one gene yields many parts.
It is nonetheless **deterministically derived** from `(run seed, gene id, expression index)`, not a
`uuid4()`: `uuid4()` draws from `os.urandom` and no seed can reach it, so a random part id would
break reproducibility (`AD-12`) the moment it reached a state hash, a log, or any iteration order.
See `AD-9` in the architecture spine.

**`BodyFactory` is the expression engine, not a constructor.** Its job is two passes: instantiate
parts from instructions, then resolve the references those instructions declared. Today the body
spec in `DEFAULT_PARAMS["body"]` is a hand-written stand-in for a genome, and it should keep the
shape a genome will have.

**Consequence — the genome declares rules, and expression computes structure.** When a gene says
"synapse to gene 57" and gene 57 expressed six times, something has to decide which. That decision
is open question **Q8**, and the answer is expected to change across phases: explicit lookup while
specs are hand-written, spatial resolution once mutation generates body plans nobody wrote, and
gradient-driven development at Phase 6. Reference resolution is therefore a **replaceable strategy
behind one interface**, not logic baked into part classes.

This is also why the portable-genome goal in [Context](#context) is stated the way it is. The
genome stays portable, self-contained, and free of runtime ids, and expression stays deterministic
given the genome — but under spatial or developmental resolution it does not *declare* its own
wiring. It declares the rules that generate it. That is the intended design, and Phase 6 deepens it
rather than reversing it.

---

## Staging Philosophy

Build from least to most granular. Each phase:
- Ends with a **runnable simulation** to observe and test
- Kicks off with a **planning session** (user + specialist agents) reviewing current behavior and deciding scope for the next phase
- Has **exit criteria** — defined conditions under which the phase is "done enough" to move on

Neurons are before genetics because understanding runtime neural behavior informs what needs to be gene-encoded. Genetics are before developmental encoding because understanding what parameters need to evolve informs how development should work. Developmental encoding is last because it's the most complex and builds on everything below it.

### Phase acceptance

Exit criteria only work if they are checked. Two rules, added 2026-08-10 after Phase 2 drifted
from its plan without the drift being noticed:

1. **Exit criteria must be measurable** — each one names a metric, a threshold, and the log or
   command that produces it. "Visibly different" and "feels balanced" are observations, not
   criteria; they belong in the goal paragraph, not the acceptance list.
2. **A phase is not complete until its criteria are assessed in writing** — a status table in
   this file, per criterion, with the evidence. A phase may be *entered* with prior criteria
   unmet, but that has to be a recorded decision rather than an oversight.

When implementation diverges from the plan — a file that never got built, a subsystem replaced by
a different design — update this document in the same change. A plan that describes code that
does not exist is worse than no plan, because it is trusted.

---

## Phase 1: World + Abstract Taobots

**Goal:** Pangu world running with resources/hazards and simple parameterized taobots that do "taobot things" — sense, move, eat, metabolize, die — without any biological complexity. Use this phase to tune movement feel, element/metabolism balance, and fitness signals.

**Taobots here are black boxes** with tunable scalar parameters:
- Sensing range, movement speed, element preferences (affinity weights per element)
- Storage capacity per element, metabolic consumption rates
- Behavior: rule-based (seek preferred resource, avoid hazard element, flee if health low)

This is essentially a much richer element_sim. The point is to answer: Does the world feel balanced? Do taobots go extinct too fast? Is there meaningful fitness variation? What does a "successful" taobot look like in practice?

**What to reuse from element_sim:**
- `common.py` → copy as `taobots/common.py`; add named resource/hazard types per element
- Torus distance/movement math → extract to `taobots/math_utils.py`
- pygame game loop skeleton from `main.py`
- `entities.py` Resource/Hazard classes (extend: add respawn_timer, density, damage_element_type)
- unit test scaffolding pattern

**Key files to create:**
```
common.py          # ElementType, cycles, names, colors — from element_sim
math_utils.py      # Torus math, polar<->cartesian conversion
world.py           # World class: spatial hash (8x6 buckets), resource/hazard mgmt, tick
entities.py        # Resource (respawn_timer, density), Hazard (damage_element_type)
taobot_simple.py   # Abstract Taobot: float x/y, heading, param dict, rule-based behavior
renderer.py        # All pygame drawing, separated from logic
main.py            # Game loop, 800x600 window, event handling, inspector panel
tests/
  test_common.py
  test_world.py
  test_entities.py
  test_taobot_simple.py
```

**World design:**
- 80x60 virtual units (larger than element_sim's 40x30 to give taobots room)
- Torus topology (wraps at edges)
- Spatial hash for O(1) neighborhood lookup — taobots and entities register by position
- Resources respawn after delay; hazards are permanent
- World is a **config object** from day one: spawn rates, densities, element chemistry rates all parameterized

**Exit criteria:** Simulation runs stably for 10+ minutes with ~20 taobots. Resources stay in rough equilibrium. Taobots survive at varied rates based on their parameter configs — measurable fitness variation. Inspector panel shows per-taobot health/element/behavior state.

---

## Phase 2: Body Structure + Chi

> **Status as of 2026-08-10: IN PROGRESS.** The organ layer is built and the generative cycle
> runs. The chi layer, the destructive cycle, and three of four body parts are not built. See
> [Phase 2 status](#phase-2-status) below before assuming a subsystem exists.

**Goal:** Replace the abstract taobot with a structured body — physical organs in polar coordinates, an internal chi pool with elemental chemistry, resource absorption through organs. Still rule-based behavior (no neural network yet). Introduces the data structures that genetics will later encode.

### The two layers

Phase 2 has two distinct layers that were not separated in the original plan. They are **not**
alternatives — the final design has both:

**Organ layer — structural integrity.** Five organs, one per element, each holding an integrity
value (0–100). Organs are what the taobot *is*: they degrade when their governing element runs
out, regenerate when it is plentiful, and each governs a capability. This layer replaced the
single scalar health value from Phase 1.

**Chi layer — the circulating elemental resource organs process.** The pool of raw elemental
substance that organs draw from, convert, and expel. Chi is what flows; organs are what it flows
through. Meridians (unbuilt) are the transport structures connecting them.

*Open design question for the Phase 3 planning session:* the organ layer currently reads and
writes `storage` directly. Once the chi pool exists, the boundary between `storage` and `chi`
must be defined — whether storage becomes the chi pool, or chi sits behind meridians as a
separate buffer. This decision gates the meridian subsystem and Phase 4's gene encoding.

### Organ layer (built)

| Organ | Governs | Failure behavior |
|---|---|---|
| Wood | Body structure | Death condition at 0; damaged by Metal attacks; drives flee threshold |
| Fire | Nervous system | Scales sensing range; below 20 → locked to searching (random walk only) |
| Water | Locomotion | Governs speed; at 0 → immobile; drain scales with speed fraction |
| Earth | Metabolism / meridians | Drain multiplier rises as it degrades; collapse triggers Wood crisis |
| Metal | Armor | Absorbs incoming damage before Wood takes it |

> **⚠ This table describes current code, and current code is wrong. Do not build from it.**
> The architect pass of 2026-08-10 found that the **Wood and Earth roles are swapped** relative to
> every other source — `docs/domain-spec.md`'s element-to-part map, `MER-1` (meridians consume
> Wood), `STR-1`/`STR-2` (the body is Earth), and this file's own epic table (E3 Meridians = Wood).
> The correct mapping is **Earth = body/structure** (death condition, damage target, flee trigger)
> and **Wood = meridians/transport** (metabolic multiplier, collapse trigger).
>
> The table is also wrong about Water: **nothing writes `organs[WATER]`**. `_metabolize` drains
> Fire, Earth, Wood and Metal only (`taobot_simple.py:441-461`); `ORGAN_STORAGE_DRAIN["WATER"]` is
> dead. The Water organ has logged a constant 100.0 in every run to date — it went vestigial when
> `LegPart` took over locomotion cost. `world.get_stats()` also omits Metal entirely.
>
> E1 **Stories 1.0a and 1.0b** correct all three — 1.0a the swapped roles, 1.0b the dead Water organ
> and the missing Metal column. This table is rewritten when they land, not before —
> per the rule above, the plan describes what exists.

Constants in `taobot_simple.py`: `ORGAN_MAX=100`, `ORGAN_DEGRADE_RATE=1.0` (per tick when the
governing element's storage is empty), `ORGAN_REGEN_RATE=0.2` (when storage is above
`REGEN_STORAGE_THRESHOLD=0.3` of capacity), plus per-organ `ORGAN_STORAGE_DRAIN` rates.

**Generative (Sheng) cycle — built.** Each element converts `CYCLE_RATE=0.001` of its storage
into the next element in the productive cycle each tick, at `CYCLE_EFFICIENCY=0.8` (20% lost per
step). All five transfers compute simultaneously from pre-tick values to avoid directional bias.

### Chi layer — constructive path only, by design

Organs exist to push chi through a system of conversion and use. **For now only the constructive
(Sheng) path is modelled.** This is a deliberate staging decision, not missing work: the organs
that consume and convert chi are being built one at a time, and adding destructive chemistry
before they exist would make it impossible to tell which system caused a given behavior.

**Destructive (Ke) cycle — deferred.** `degrade_rate` is present in every world config and parsed
into `WorldConfig`, but deliberately not consumed. It is the most sensitive balance parameter:
too high and taobots die of internal imbalance, too low and element composition carries no
evolutionary pressure. It lands once the organ epics are complete and there is a stable baseline
to perturb. Insertion point is marked at `world.py:282`.

**Chi pool:** `dict[ElementType, float]` with a capacity cap. Whether this is the existing
`storage` or a separate buffer behind meridians is open question **Q6**.

### Build method: one organ system per epic

Organs are abstractions at this stage, so build order follows **difficulty and dependency, not
the elemental cycle**. Each organ system is an epic covering design, implementation, integration,
and testing — carried to working, verified behavior before the next one starts.

| # | Epic | Element | Phase | Status | Why here |
|---|---|---|---|---|---|
| E1 | **Legs** | Water | 2 | **In progress** | Locomotion is the visible output; everything else is verified by watching a bot move |
| E2 | **Armor** | Metal | 2 | Next | Simplest and largely passive — wear, damage absorption. Banks a quick win and proves the epic workflow end to end |
| E3 | **Meridians** | Wood | 2 | Planned | Chi transport, conversion and junctions — the network connecting organs. Ships with autonomous triggering; neurons replace the built-in rules in E4. **Architect pass gates this epic** — see below |
| E4 | **Neurons** | Fire | 3 | Planned | Last, because it is the integration layer — see below |

**Earth/body is not its own epic.** It behaves as a cost factor required by the other parts rather
than a standalone system (`STR-4`, open question **Q3**).

**E3 opens with an architect pass.** E1 and E2 are small enough to build directly; E3 is not.
The meridian network raises genuine architectural questions — graph representation, how junctions
are declared, update ordering across a network that may contain cycles, and **Q6** (whether the
chi economy stays as methods on `TaobotSimple` or becomes a subsystem the taobot owns). Convening
the architect *after* E1 and E2 is deliberate: by then the E1 Story 1.1 damage spike has reported, a
demand-driven conversion trigger has run in practice, and armor has exercised the damage path — so
the design is made against evidence rather than intent. Do not start E3 implementation before it.

**Mechanism before control.** Each organ system is built with autonomous triggering — the part
"just knows" when to act, sensing a starving organ or an empty downstream meridian — and neurons
replace those built-in rules in E4. The transfer does not change; only the decision to make it
moves. This is what makes neurons-last viable rather than merely deferred: no epic is blocked
waiting for neural control, and E4 becomes a substitution rather than a first wiring. See the
design principle in `docs/domain-spec.md`.

**Why neurons last.** Neurons are not merely the hardest system, they are the one that *integrates
the others*. Everything hinges on their spatial order, how they sense the internal environment,
and how they modulate organ function. A worked example of the target behavior: an eye dendrite
feeds a circuit that thresholds on colour intensity — above the threshold it drives legs away
from a pyre, below it drives coordinated movement toward a carrot. Another neuron senses the Earth
organ running low and opens a gate converting Fire chi to Earth. Neither circuit can be designed
against organs that do not exist yet, and building them early would mean wiring to stubs and
rewiring on every subsequent epic.

### Epic definition of done

An organ epic is complete when all four hold:

1. **Design** — requirements identified in `docs/domain-spec.md`, open questions resolved or
   explicitly deferred with the deferral recorded
2. **Implementation** — the part exists, consumes its element, and degrades/repairs
3. **Integration** — it participates in the chi economy and is visible in the workshop inspector
4. **Testing** — unit tests pass, **and** the system has been verified by tick-stepping in
   workshop mode (see below)

### Workshop mode is the verification instrument

`--workshop` is not a debugging convenience; it is how each organ system is confirmed to do what
it is believed to do. Single bot, tick-by-tick stepping, full state inspector, and a per-tick CSV
capturing organs, storage, per-element intake, damage, and per-leg reserve/integrity/thrust.

Every organ epic is verified here before it is called done. Practically this means: step through
the ticks where the new organ acts, confirm each value moves the direction and magnitude expected,
and only then trust an aggregate run. Any organ added to the model must also be added to the
workshop inspector and to `WorkshopLogger` — an organ that cannot be watched cannot be accepted.

### Taobot model variants

A standing deliverable across the organ epics: a set of hand-crafted taobot models to run and
compare, varying independently along

- **Symmetry** — radial vs bilateral (`BODY-6`)
- **Part count** — e.g. two legs vs four vs six
- **Organ settings** — drain rates, capacities, regeneration thresholds

These are the substrate for the body-spec differentiation criterion below, and they are what turns
"does this organ work" into "does this organ produce differentiated behavior." They live as config
so that Phase 4 genetics can later generate the same structures.

**Key design decisions:**
- Taobot positions are continuous float (x, y) — not grid-snapped
- Bodies rendered as colored circles per organ at polar offset from center (upgrade to arc polygons later if desired)
- Synapse targets use stable `gene_id` references (not list indices) — set up even though genetics don't exist yet, to avoid retrofitting

**Body parts (static state, no neural activation yet):**
- `LegPart` — **built.** Polar position, `phi` push-direction, thrust, consumes Water; differential-drive steering — `LEG-2`…`LEG-5`, `LEG-6` partial
- `MeridianPart` — *not built.* Element affinity, internal storage, absorbs/diffuses its element, consumes Wood chi — `MER-1`, `MER-2`, `MER-4`…`MER-6`, `MER-8`, `MER-9`
- `NeuronPart` — *not built.* Placeholder structure (dendrites, synapses defined but inert) — `BODY-4`, `NEU-4`
- `ArmorPart` — *not built.* Scales (absorb damage) or claws (deal damage), consumes Metal chi; wear and repair — `ARM-2`, `ARM-4`, `ARM-5`

**Requirements covered by this phase:** `BODY-2`, `BODY-3`, `LEG-2`…`LEG-6`, `MER-1`…`MER-9`,
`STR-1`…`STR-3`, `ARM-1`, `ARM-2`, `ARM-4`, `ARM-5`, `CHI-1`…`CHI-5`. Open questions blocking
completion: **Q4** (destructive-cycle rate), **Q6** (storage/chi boundary).

**Body definition:** Explicit parameter structs, not genes yet. Each body part has a polar position (r, theta), size, element type, and part-specific params. A `BodyFactory` reads these and instantiates the body — same interface that genetics will later drive.

**Rendering:** Body parts as colored circles at polar offset from taobot center. Chi pool as 5-segment pie ring around center. Heading arrow.

**Files — planned vs actual:**
```
body_parts.py      BUILT     BodyPart base + LegPart only
body_factory.py    BUILT     BodyFactory: body spec -> list[BodyPart], stable part IDs
renderer.py        BUILT     Polar body rendering, organ graph
taobot_simple.py   BUILT     Organ system lives here; renamed to taobot.py in E1 Story 1.0a
chi.py             MISSING   ChiPool, destructive-cycle chemistry tick
taobot.py          PENDING   Not a second class — taobot_simple.py becomes it by subtraction
```

**On the two-class plan.** The original file table imagined `taobot_simple.py` being retired in
favour of a separately-built `taobot.py`. That assumed a big-bang cutover, which the per-subsystem
staging never offers — each epic substitutes one subsystem while the rest keep running, so there is
never a moment where both a simple and a full taobot exist to switch between. There is **one**
organism class; it *thins* as organs, chi and control move out behind their ports, and what remains
is the full Taobot. See `AD-17` in the architecture spine.

<a name="phase-2-status"></a>
### Phase 2 status against exit criteria

Phase 2 completes when epics E1–E3 are done. Progress is tracked per epic, not against the
original big-bang criteria — those assumed all four body parts landing together with full
chemistry, which is not how this is being built.

| Epic | Design | Implementation | Integration | Testing |
|---|---|---|---|---|
| E1 Legs | Done | Done — thrust, `phi`, differential drive | Done — Water drain, workshop inspector | **Partial** — unit tests pass; no repair path (`LEG-6`) |
| E2 Armor | — | — | — | — |
| E3 Meridians | — | — | — | — |

Organ layer and the constructive cycle are complete and underpin all three epics.

### Exit criteria (measurable)

Replaces the original qualitative criteria. All are measurable from logs the sim already writes —
`<world>_deaths.csv`, `<world>_workshop_<timestamp>.csv`, `<world>_<timestamp>.csv`. Thresholds
are starting proposals, to be confirmed at the Phase 3 planning session.

1. **Body-spec differentiation** — across ≥3 taobot model variants (differing in symmetry, part
   count, or organ settings), 10k ticks each at a fixed seed, median lifespan between best and
   worst differs by ≥30% (`deaths.csv`, `age_ticks`).
2. **Constructive chi economy** — in a workshop run, an organ depleted below its regeneration
   threshold recovers via conversion from an adjacent element in the productive cycle, visible as
   a fall in the source element's storage and a rise in the target's (workshop CSV, `storage_*`).
3. **Degrade and repair both observable** — in a single workshop run, at least one organ drops
   below 50 and recovers above 80 (workshop CSV, `organ_*` columns); each built part's integrity
   shows the same round trip (`leg_*_integrity` and equivalents per epic).

   **The two halves must come from different sources.** Once `AD-5` lands per organ, that organ *is*
   the mean integrity of its parts — for E1, the Water organ is the mean of leg integrity, so reading
   both halves off Water would collapse them into a single measurement and silently weaken the
   criterion. For E1 the organ half is sourced from **Earth (the body)** and the part half from the
   legs. Each later epic states which organ supplies its organ half. *(Decided 2026-08-11, architect
   pass; see Story 1.4 in `epic-e1-legs.md`.)*
4. **Population stability** — 20 taobots run 10 minutes headless with population never below 15
   and no extinction (`<world>_<timestamp>.csv`).
5. **Workshop completeness** — every organ and part built in E1–E3 is visible in the workshop
   inspector and present in `WorkshopLogger` columns. *(Met for E1.)*

Destructive-cycle tension is deliberately **not** an exit criterion for this phase — the Ke cycle
is deferred until the organ epics are complete.

---

## Phase 3: Neural Networks

**Goal:** Replace rule-based behavior with neural networks. Eye dendrites sense environment. Neurons process signals. Legs produce motion vectors. Meridians signal internal state (hunger, fullness).

**Architecture:** Sparse explicit graph — not a weight matrix. Neurons are nodes; synapses are directed weighted edges. Activation propagates one step per neural tick. Update frequency: every 6 game ticks (10 Hz effective). This is biologically plausible and maps directly to what genetics will later encode explicitly.

**Neural update order (per 6-tick interval):**
1. Eye dendrites (outer-radius NeuronParts) sense via cone detection — find entities in FOV cone using spatial hash; signal = element_color_match / distance
2. Meridians emit fullness/hunger signals to connected neurons
3. Neurons apply ReLU, check threshold, fire → propagate weight × activation to synapse targets; apply decay
4. Legs accumulate signals → sum force vectors → taobot velocity this interval
5. Meridians execute absorb/diffuse/expel commands from neuron synapses

**Sensing:** Cone-based (not ray cast) for Phase 3 — find entities within angular range around dendrite direction. Ray cast (blocked by intervening taobots) is an optional Phase 5 upgrade for combat.

**Key representation question (to decide at Phase 3 planning session):** Start with dicts for legibility, benchmark, then numpy-ify the inner loop if needed. Neural activations as numpy vector, synapse weights as sparse matrix, body part states as numpy vector — all updates become matrix ops. This matters for large populations but not for early tuning.

**Key files to create/extend:**
```
body_parts.py      # Extended: NeuronPart with full activation state, LegPart with force accumulator, MeridianPart with chi sensing
neural_graph.py    # NeuralGraph: neuron refs, update order, cycle detection
sensing.py         # EyeSensor: cone detection, color response, spatial hash query
locomotion.py      # VectorAccumulator: leg outputs -> torus-wrapped movement
tests/
  test_neural.py   # Neural update step tested independently of game loop
```

**Requirements covered by this phase:** `NEU-1`…`NEU-7`, `LEG-1`, `MER-7`, `MER-10`, `MER-12`, `BODY-4`, `BODY-5`. Open questions to resolve at the planning session: **Q1** (ray cast vs cone), **Q2** (synapse types), **Q6** (storage/chi boundary).

**Exit criteria:** Taobots navigate toward preferred resources. Different hand-crafted neural configs produce visibly different foraging strategies. Neural activity visible in inspector. Taobots with more/better-wired neurons outperform random walkers.

---

## Phase 4: Genetics + Evolution

**Goal:** Encode taobot body specs and neural wiring as genomes. Implement crossover, mutation, and karma-weighted reproduction. Gene bank persists between sessions.

**Genetic encoding:** A `Genome` is a list of `Gene` dataclasses. Each gene is an **instruction for producing parts** — not a part. A gene carries polar position, size, element type, symmetry (radial or bilateral), and part-specific params (synapse targets by gene_id, dendrite coordinates, force scale, etc.). One gene may express as many parts: symmetry expansion (a single gene → 6 legs at evenly-spaced angles) happens in `BodyFactory`, and each expressed part gets its own runtime id while recording the gene it came from. See [the genome is a recipe, not a blueprint](#the-genome-is-a-recipe-not-a-blueprint). How a `gene_id` reference resolves when the target gene expressed more than once is open question **Q8**.

**Gene bank:** Persistent JSON dict of `{genome_id: GeneRecord}`. Each record: genome, karma, generation, parent_ids, timestamps. Cap at 500 records (prune lowest karma). Karma is multidimensional — track survival time, resources gathered, offspring spawned, combat won as separate signals. This lets champions have legible styles.

**Reproduction:** Triggered when chi pool reaches threshold (~60% full across all elements). Second parent selected from gene bank by roulette wheel weighted by karma. Crossover: type-sorted (interleave genes by part_type for stability). Mutation operators: nudge (Gaussian noise on numeric params), swap (change element_type), add (new random gene), delete, rewire (change synapse gene_id target). `MUTATION_RATE=0.05`.

**Karma decay:** Multiply stored karma by 0.95 each time a genome is selected for respawn — prevents early successful lineages from permanently dominating.

**Hopeful monsters:** When population drops below target, respawn from gene bank (karma-weighted) with probability 0.9, or spawn a fully random genome with probability 0.1 — maintains genetic diversity.

**Key files to create/extend:**
```
gene.py            # Gene, Genome dataclasses; PartType, SymmetryType enums
gene_bank.py       # GeneBank singleton: karma update, JSON save/load, lineage metadata, pruning
evolution.py       # Crossover, mutation operators, genome_id allocation
spawner.py         # Reproduction trigger, population management, hopeful monsters
tests/
  test_gene.py
  test_evolution.py
```

**Requirements covered by this phase:** `BODY-1`, `BODY-6`, `MER-3`, `ARM-3`, `GEN-1`, `GEN-2`. Open questions to resolve at the planning session: **Q3** (Earth as gene type or cost factor), **Q5** (gene domains).

**Exit criteria:** Population evolves over 30+ minute runs. Karma distribution shifts over time. Lineages visible in gene bank. Taobots in later generations visibly outperform early random genomes. Gene bank persists and reloads correctly across sessions.

---

## Phase 5: Combat

**Goal:** Taobots collide, deal/absorb damage, consume defeated enemies. Predator/prey specialization emerges through evolution.

**Collision:** Spatial hash detects co-located taobots. Physical size = max polar radius across body parts (cached at instantiation). Claw damage = `hardness × size × relative_speed × CLAW_DAMAGE_SCALE`, applied to facing body parts. Scales absorb damage and wear down; repair by consuming Metal chi.

**Consumption:** Defeated taobot drops chi. An adjacent living taobot absorbs it directly (large chi bonus) rather than it scattering as world resources — strong evolutionary incentive for predation.

**Chi combat (stretch goal):** MeridianPart `expel_to_target()` — injects element into enemy's chi pool, accelerating destructive cycle degradation inside target. Requires contact. Triggered by neuron → meridian synapse.

**Sensing upgrade:** Upgrade eye sensing to cone-with-taobot-detection — taobots appear as colored entities to eyes, allowing evolved predator behavior.

**Key files to create/extend:**
```
collision.py       # Collision detection, damage resolution, consumption
body_parts.py      # Extended: ArmorPart claw/scale damage logic, wear and repair
chi.py             # Extended: external chi injection
```

**Requirements covered by this phase:** `ARM-6`, `ARM-7`, `MER-11`, `NEU-8`. Open question: **Q1** (ray casting upgrade for combat sensing).

**Exit criteria:** Distinct predator and prey lineages emerge over long runs. Armor/claw organs appear and grow in predator lineages. Karma metrics reflect combat success. Chi combat (if implemented) shows as a distinct attack strategy in some lineages.

---

## Phase 6: Developmental Encoding

**Goal:** Replace direct polar-coordinate gene expression with a biologically-inspired developmental system. Genes activate in response to element gradients in an "embryo," producing stem cells that mature into body parts. This produces more evolvable, spatially coherent body plans and sets up the genetic engineering UI in the game layer.

**Embryo:** A circular spatial scaffold with 5 radial gradient fields (one per element), each with a different spatial pattern (e.g., Water gradient peaks at the "bottom," Fire at "front"). Genes have activation thresholds per gradient: "express if Water > 0.6 AND Fire < 0.3."

**Stem cell maturation:** An activated gene generates one or more stem cells at the gradient-determined location. Stem cells mature into body parts over simulated developmental time — a new neuron "wires up" with existing neurons during development, sampling local gradient and nearby part positions to determine synapse targets. This produces context-dependent wiring rather than hardcoded synapse IDs.

**Taobot representation post-development:** Body parts as vectors/matrices (activations, weights, states) so runtime updates are bulk matrix operations. Design of this representation to be determined at the Phase 6 planning session, informed by what was learned in Phase 3 (neural network runtime) and Phase 4 (what parameters genes need to encode).

**Note:** The specific design of this phase will be planned in a dedicated session after Phase 5 is working. The design of the gradient fields, stem cell maturation rules, and matrix representation will depend heavily on what we've learned about the neural and genetic systems by then.

---

## Full File Structure

```
taobots/
  README.md
  PLAN.md
  requirements.txt          # pygame>=2.5.0, (numpy added Phase 3+)

  common.py                 # ElementType, cycles, resource/hazard names, colors
  math_utils.py             # Torus math, polar<->cartesian
  world.py                  # World, spatial hash, world config object
  entities.py               # Resource (respawn), Hazard (damage element)
  taobot_simple.py          # Phase 1 abstract taobot (retired after Phase 2)
  renderer.py               # All pygame drawing — never touches simulation logic
  main.py                   # Game loop, event handling, inspector panel

  chi.py                    # ChiPool, elemental chemistry (Phase 2+)
  body_parts.py             # All BodyPart subclasses, grows each phase (Phase 2+)
  body_factory.py           # Body spec / Genome -> body parts (Phase 2+)
  taobot.py                 # Full Taobot class, tick orchestration (Phase 2+)

  neural_graph.py           # Neural update graph (Phase 3)
  sensing.py                # Eye/cone sensing (Phase 3)
  locomotion.py             # Leg vector accumulation (Phase 3)

  gene.py                   # Gene, Genome dataclasses (Phase 4)
  gene_bank.py              # GeneBank, JSON persistence, lineage metadata (Phase 4)
  evolution.py              # Crossover, mutation (Phase 4)
  spawner.py                # Spawning, population management (Phase 4)

  collision.py              # Collision detection, damage (Phase 5)

  embryo.py                 # Gradient fields, stem cell maturation (Phase 6)

  tests/
    test_common.py
    test_world.py
    test_entities.py
    test_taobot_simple.py
    test_chi.py
    test_body_factory.py
    test_neural.py
    test_gene.py
    test_evolution.py
    test_collision.py
```

---

## Future: Game Layer (Post Phase 6)

Contingent on simulation working. Key elements:
- **Arena mode**: world config + imported genomes + run. Competitive (last standing) or ecological (whose lineage dominates after N generations)
- **Genome exchange**: portable JSON genome files that any instance of the sim can load
- **Pedigree tracing**: lineage tree viewer, champion bloodlines, ownership metadata
- **Genetic engineering UI**: inspect genome visually (body plan, neural wiring, chi preferences), tweak parameters, save forks
- **Visual design pass**: dedicated design agents working from stable simulation semantics — clean rendering spec, nice dashboards, taobot physiology visualizations
- **World configs**: "fire arena," "forest world," etc. — just different world config JSONs (enabled by parameterizing world from Phase 1)

---

## Planning Session Protocol

Each phase kicks off with a planning session: review current simulation behavior, define what the next phase needs to achieve, identify the variables and parameters that will need tuning, and agree on exit criteria before coding begins. Do not start implementation of a phase without agreed exit criteria.

### Session steps

1. Convene Architecture Agent + phase-specific agent(s)
2. Review current simulation state (run a headless session, share logs)
3. Review exit criteria for the completed phase — were they met?
4. Produce design for next phase, resolving all open questions before coding
5. Convene Test Design Agent to write test stubs
6. Begin implementation only after all agents have signed off

---

## Design Team

The relevant specialist agents are convened at each phase kickoff, given the current simulation state and target outcomes, and produce a design before implementation begins.

### Standing roles

**Architecture Agent**
- *When:* Start of every phase planning session.
- *Job:* Review the proposed design for the next phase against the existing codebase. Identify integration risks, interface mismatches, and anything that will be painful to retrofit later. Flag decisions that need to be made before coding begins.
- *In:* Current codebase state, proposed phase design, exit criteria. *Out:* Amended design with risks flagged, interface specs for new modules.

**Balance & Tuning Agent**
- *When:* End of Phase 1, end of Phase 2, and any time the simulation behaves unexpectedly.
- *Job:* Analyze simulation run logs and metrics (population stability, element equilibrium, lifespan trends). Propose parameter adjustments. Design experiments to test hypotheses about balance (e.g. "what happens if DEGRADE_RATE doubles?").
- *In:* Headless run logs from `logs/`, world config, current constants. *Out:* Tuned config values, documented rationale, suggested experiments.

**Test Design Agent**
- *When:* Start of each phase, after architecture review.
- *Job:* Design the test suite for the phase — unit tests for new modules, simulation health invariants to monitor, regression tests to ensure prior phases still work. Write test stubs and fixtures.
- *In:* Interface specs from Architecture Agent, exit criteria. *Out:* Test files with stubs, fixture definitions, invariant checklist.

### Phase-specific roles

**Phase 3 — Neural Architect Agent**
- *Job:* Specialist review of the neural graph design — update order, cycle detection, activation dynamics. Validate that the sparse graph representation will produce interesting behavior and is evolvable. Advise on whether to numpy-ify early or late.
- *In:* `body_parts.py`, `neural_graph.py` design, Phase 2 codebase. *Out:* Validated neural update spec, numpy migration decision, test cases for neural dynamics.

**Phase 4 — Evolutionary Dynamics Agent**
- *Job:* Review crossover and mutation operators for evolvability. Check that karma signals are meaningful and multidimensional. Advise on population dynamics (mutation rate, hopeful monster rate, gene bank pruning). Identify degenerate equilibria (e.g. all taobots converging to one genome).
- *In:* `gene.py`, `evolution.py` design, karma metric spec. *Out:* Validated operator designs, recommended starting parameters, diversity metrics to monitor.

**Phase 5 — Combat Balancing Agent**
- *Job:* Review collision and damage mechanics for balance. Ensure predator/prey dynamics are plausible — predators should be viable but not dominant. Design experiments to test whether combat creates evolutionary pressure or just noise.
- *In:* `collision.py` design, Phase 4 codebase, balance metrics from Phase 4 runs. *Out:* Damage scaling recommendations, combat karma attribution design, test scenarios.

**Phase 6 — Developmental Biology Agent**
- *Job:* Design the embryo gradient system and stem cell maturation rules. Must integrate everything learned in Phases 3–5 about what body part parameters need to be gene-encodable. Advise on the matrix representation for post-development taobot state.
- *In:* Full Phase 5 codebase, `gene.py`, `neural_graph.py`, lessons-learned notes from prior phases. *Out:* Gradient field spec, gene activation rules, maturation sequence, matrix representation design.

### Game layer roles (post-Phase 6)

**Visual Design Agent** — Given stable simulation semantics, design the visual language for taobots and the world. Produce rendering specs for organism physiology visualization, dashboards, and arena UI. Works from a clean interface (`renderer.py`) without touching simulation logic.

**Arena Design Agent** — Design the arena mode: competitive vs. ecological formats, genome import/export protocol, world config parameterization for arena types, matchmaking logic.

**Genetic Engineering UI Agent** — Design the genome editor UI: visual body plan inspector, parameter tweaking interface, lineage tree viewer, fork/save workflow.
