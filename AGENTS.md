# Taobots: Agent Design Team

Each development phase kicks off with a planning session. The relevant specialist agents are convened, given the current simulation state and target outcomes, and produce a design before implementation begins.

---

## Standing Roles

### Architecture Agent
**When:** Start of every phase planning session.
**Job:** Review the proposed design for the next phase against the existing codebase. Identify integration risks, interface mismatches, and anything that will be painful to retrofit later. Flag decisions that need to be made before coding begins.
**Input:** Current codebase state, proposed phase design from PLAN.md, exit criteria.
**Output:** Amended design with risks flagged, interface specs for new modules.

### Balance & Tuning Agent
**When:** End of Phase 1, end of Phase 2, and any time the simulation behaves unexpectedly.
**Job:** Analyze simulation run logs and metrics (population stability, element equilibrium, lifespan trends). Propose parameter adjustments. Design experiments to test hypotheses about balance (e.g., "what happens if DEGRADE_RATE doubles?").
**Input:** Headless run logs from `logs/`, world config, current constants.
**Output:** Tuned config values, documented rationale, suggested experiments.

### Test Design Agent
**When:** Start of each phase, after architecture review.
**Job:** Design the test suite for the phase — unit tests for new modules, simulation health invariants to monitor, regression tests to ensure prior phases still work. Write test stubs and fixtures.
**Input:** Interface specs from Architecture Agent, exit criteria.
**Output:** Test files with stubs, fixture definitions, invariant checklist.

---

## Phase-Specific Roles

### Phase 3: Neural Architect Agent
**When:** Phase 3 planning session.
**Job:** Specialist review of the neural graph design — update order, cycle detection, activation dynamics. Validate that the sparse graph representation will produce interesting behavior and is evolvable. Advise on whether to numpy-ify early or late.
**Input:** body_parts.py, neural_graph.py design, Phase 2 codebase.
**Output:** Validated neural update spec, numpy migration decision, test cases for neural dynamics.

### Phase 4: Evolutionary Dynamics Agent
**When:** Phase 4 planning session.
**Job:** Review crossover and mutation operators for evolvability. Check that karma signals are meaningful and multidimensional. Advise on population dynamics (mutation rate, hopeful monster rate, gene bank pruning). Identify degenerate equilibria (e.g., all taobots converging to one genome).
**Input:** gene.py, evolution.py design, karma metric spec.
**Output:** Validated operator designs, recommended starting parameters, diversity metrics to monitor.

### Phase 5: Combat Balancing Agent
**When:** Phase 5 planning session.
**Job:** Review collision and damage mechanics for balance. Ensure predator/prey dynamics are plausible — predators should be viable but not dominant. Design experiments to test whether combat creates evolutionary pressure or just noise.
**Input:** collision.py design, Phase 4 codebase, balance metrics from Phase 4 runs.
**Output:** Damage scaling recommendations, combat karma attribution design, test scenarios.

### Phase 6: Developmental Biology Agent
**When:** Phase 6 planning session.
**Job:** Design the embryo gradient system and stem cell maturation rules. Must integrate everything learned in Phases 3-5 about what body part parameters need to be gene-encodable. Advise on the matrix representation for post-development taobot state.
**Input:** Full Phase 5 codebase, gene.py, neural_graph.py, lessons-learned notes from prior phases.
**Output:** Gradient field spec, gene activation rules, maturation sequence, matrix representation design.

---

## Future: Game Layer Roles

### Visual Design Agent
**When:** Post-Phase 6, before game layer implementation.
**Job:** Given stable simulation semantics, design the visual language for taobots and the world. Produce rendering specs for organism physiology visualization, dashboards, and arena UI. Works from a clean interface (renderer.py) without touching simulation logic.

### Arena Design Agent
**When:** Game layer planning.
**Job:** Design the arena mode — competitive vs. ecological formats, genome import/export protocol, world config parameterization for arena types, matchmaking logic.

### Genetic Engineering UI Agent
**When:** Game layer, after arena mode.
**Job:** Design the genome editor UI — visual body plan inspector, parameter tweaking interface, lineage tree viewer, fork/save workflow.

---

## Planning Session Protocol

1. Convene Architecture Agent + phase-specific agent(s)
2. Review current simulation state (run a headless session, share logs)
3. Review exit criteria for the completed phase — were they met?
4. Produce design for next phase, resolving all open questions before coding
5. Convene Test Design Agent to write test stubs
6. Begin implementation only after all agents have signed off
