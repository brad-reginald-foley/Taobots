# Taobots: Project Description & Development Plan

## Context

**Taobots** is an evolutionary life simulation set in "Pangu," a world governed by the 5 Taoist elements (Wood, Water, Metal, Fire, Earth). Taobots are creatures with genetically-encoded bodies — neurons, legs, meridians, armor, and claws — that eat, fight, reproduce, and evolve across generations.

The long-term vision has two halves:

**Simulation** (this plan): Build and tune the simulation from the ground up, staging complexity carefully. Each phase produces a running, testable system. Later phases inform the design of earlier ones — neurons before genetics because you need to know what a neuron does at runtime before encoding one in a gene; genetics before developmental encoding because you need to know what parameters need evolving before designing the developmental machinery.

**Game layer** (future, contingent on simulation working): Arena mode where people upload champion taobots to compete in parameterized worlds ("fire arena," "forest world"), trade genetic codes, trace bloodlines, and eventually do direct genetic engineering through a UI.

**Key architectural decisions made now that enable the game layer later:**
- Genome format is a clean, self-contained, portable JSON artifact — no runtime IDs, fully declarable
- World is a config object (spawn rates, hazard densities, element chemistry rates) not hardcoded constants — arena types are just different configs
- Gene bank stores rich lineage metadata (timestamps, arena context, peak karma) from Phase 4 onward
- Karma is multidimensional enough that champions have recognizable styles, not just a single scalar
- Rendering is cleanly separated from logic (renderer.py) so a visual design pass can happen without touching simulation code

**Prior prototype:** `../element_sim` — pygame, Python, 5-element system, component-based agents, no genetics or learning. Worth reusing: element definitions, torus math, pygame loop scaffold, entity classes.

---

## Staging Philosophy

Build from least to most granular. Each phase:
- Ends with a **runnable simulation** to observe and test
- Kicks off with a **planning session** (user + specialist agents) reviewing current behavior and deciding scope for the next phase
- Has **exit criteria** — defined conditions under which the phase is "done enough" to move on

Neurons are before genetics because understanding runtime neural behavior informs what needs to be gene-encoded. Genetics are before developmental encoding because understanding what parameters need to evolve informs how development should work. Developmental encoding is last because it's the most complex and builds on everything below it.

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

**Goal:** Replace the abstract taobot with a structured body — physical organs in polar coordinates, an internal chi pool with elemental chemistry, resource absorption through organs. Still rule-based behavior (no neural network yet). Introduces the data structures that genetics will later encode.

**Key design decisions:**
- Taobot positions are continuous float (x, y) — not grid-snapped
- Bodies rendered as colored circles per organ at polar offset from center (upgrade to arc polygons later if desired)
- Synapse targets use stable `gene_id` references (not list indices) — set up even though genetics don't exist yet, to avoid retrofitting

**Chi pool:** `dict[ElementType, float]` with a capacity cap. Elemental chemistry: destructive cycle pairs degrade each other per tick at `DEGRADE_RATE=0.001` (tunable constant). This is the most sensitive balance parameter — too high and taobots die from internal imbalance; too low and element composition has no evolutionary pressure.

**Body parts (static state, no neural activation yet):**
- `LegPart` — polar position, force scale, consumes Water chi
- `MeridianPart` — element affinity, internal storage, absorbs/diffuses its element, consumes Wood chi
- `NeuronPart` — placeholder structure (dendrites, synapses defined but inert)
- `ArmorPart` — scales (absorb damage) or claws (deal damage), consumes Metal chi; wear and repair

**Body definition:** Explicit parameter structs, not genes yet. Each body part has a polar position (r, theta), size, element type, and part-specific params. A `BodyFactory` reads these and instantiates the body — same interface that genetics will later drive.

**Rendering:** Body parts as colored circles at polar offset from taobot center. Chi pool as 5-segment pie ring around center. Heading arrow.

**Key files to create/extend:**
```
chi.py             # ChiPool, elemental chemistry tick
body_parts.py      # BodyPart base + Leg, Meridian, Neuron (inert), Armor subclasses
body_factory.py    # BodyFactory: body spec -> list[BodyPart], assigns stable part IDs
taobot.py          # Full Taobot: chi pool, body parts, tick (consume, absorb, chemistry)
renderer.py        # Extended: polar body rendering, chi ring
```

**Exit criteria:** Taobots with varied hand-crafted body specs survive at visibly different rates. Chi chemistry creates internal tension (a taobot loaded with incompatible elements degrades faster). Body part health degrades and repairs. Inspector shows per-organ state.

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

**Exit criteria:** Taobots navigate toward preferred resources. Different hand-crafted neural configs produce visibly different foraging strategies. Neural activity visible in inspector. Taobots with more/better-wired neurons outperform random walkers.

---

## Phase 4: Genetics + Evolution

**Goal:** Encode taobot body specs and neural wiring as genomes. Implement crossover, mutation, and karma-weighted reproduction. Gene bank persists between sessions.

**Genetic encoding:** A `Genome` is a list of `Gene` dataclasses. Each gene encodes one body part: polar position, size, element type, symmetry (radial or bilateral), and part-specific params (synapse targets by gene_id, dendrite coordinates, force scale, etc.). Symmetry expansion (a single gene → 6 legs at evenly-spaced angles) happens in `BodyFactory`.

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
