# Taobots — Domain Specification

The subsystem-level requirements for taobot physiology: what each body part is, what it consumes,
and how it behaves. Extracted from `README.md` on 2026-08-10 so that requirements have one home.

**Relationship to the other documents:**

| Document | Holds |
|---|---|
| `docs/domain-spec.md` (this file) | What the subsystems must do — the requirements |
| `PLAN.md` | When they get built, in what order, and the exit criteria per phase |
| `README.md` | How to run what exists today, plus the world's lore |

`PLAN.md` phases reference requirement IDs from this file rather than restating them. When a
requirement changes, it changes here.

## How to read this

Each requirement has a stable ID (`NEU-3`, `MER-7`) for reference from plans, stories, and
commits. IDs are never reused or renumbered.

| Status | Meaning |
|---|---|
| **Built** | Implemented and covered by tests |
| **Partial** | Some behavior exists; the requirement is not fully satisfied |
| **Planned** | Not implemented; target phase named |
| **Open** | Design not settled — see [Open questions](#open-questions) |

Requirements marked **Open** carry a genuine unresolved decision and are not ready to be built
from. They were phrased as questions or hedges in the original notes, and that uncertainty is
preserved deliberately rather than resolved by assumption.

## Design principle: mechanism before control

A subsystem's **mechanism** and its **control** are separable, and they are built in that order.

Build the mechanism first with **autonomous triggering** — the part "just knows" when to act. A
meridian senses that an organ is starving, or that its downstream meridian is empty, and moves
essence accordingly. Later, neurons replace that built-in rule with sensed, wired, evolvable
control. The transfer itself does not change; only the decision to make it moves.

This is why neurons are built last (`PLAN.md`, epic E4). It is also why requirements below
describe *what a part does* separately from *what causes it to do so* — a requirement phrased as
"a neuron-activated junction releases chi" describes the eventual control, and its autonomous
predecessor is a legitimate first implementation, not a shortcut.

Consequences for reading this spec:

- A **Planned** requirement naming neural activation may be satisfied first by an autonomous rule
- Retiring that rule in favor of neural control is expected work in the neurons epic, not rework
- Open questions about *who decides* (Q7) do not block building *what happens*

---

## 1. Body plan (`BODY-*`)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| BODY-1 | Taobots are generated programmatically from a genetic system | 4 | Planned |
| BODY-2 | Bodies are modeled in polar coordinates (r, theta) from the taobot center; all parts are placed on this scheme | 2 | Built |
| BODY-3 | Meridians sit on the inside at specific locations | 2 | Planned |
| BODY-4 | Neurons have a start and an end, and connect at synapses at specific coordinates | 3 | Planned |
| BODY-5 | Legs and eyes are positioned around the outer edge | 2–3 | Partial — legs built, eyes planned |
| BODY-6 | Symmetry is radial or bilateral, and determines how parts are generated from genes — one gene may express as six legs at evenly spaced angles on a six-symmetry taobot | 4 | Planned |

Element-to-part mapping, which governs which chi each part consumes:

| Element | Parts |
|---|---|
| Water | Legs |
| Wood | Meridians |
| Fire | Nerves, eyes |
| Earth | Body, mouth |
| Metal | Armor, claws |

## 2. Neurons (`NEU-*`)

The most complex and subtle structures.

| ID | Requirement | Phase | Status |
|---|---|---|---|
| NEU-1 | Neurons consume Fire essence | 3 | Planned |
| NEU-2 | Activation uses a ReLU function | 3 | Planned |
| NEU-3 | A neuron may delay-decay its activation state before firing, accumulating multiple stimuli | 3 | Planned |
| NEU-4 | A neuron may have multiple dendrites, each with its own radial coordinate | 3 | Planned |
| NEU-5 | Dendrites on the outer edge are eyes, stimulated by light from the environment | 3 | Planned |
| NEU-6 | Eyes have color vision | 3 | Planned |
| NEU-7 | Synapses are inhibitory or stimulatory | 3 | Planned |
| NEU-8 | Eye sensing uses ray casting rather than cone detection | 5 | **Open** — see Q1 |
| NEU-9 | Neurons form circuits — multi-neuron chains that transform a sensory signal before it reaches an actuator, rather than eyes driving legs directly | 3 | Planned |
| NEU-10 | A circuit can threshold on signal intensity and produce different responses either side of it — e.g. high color intensity drives flight from a pyre, low intensity drives approach to a carrot | 3 | Planned |
| NEU-11 | Neurons sense internal organ state, not only the external environment — e.g. detecting that the Earth organ is low on chi | 3 | Planned |
| NEU-12 | A neuron can open a conversion gate, converting one element to another on demand — e.g. Fire to Earth when Earth runs low | 3 | **Open** — see Q7 |

## 3. Legs (`LEG-*`)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| LEG-1 | Legs are triggered by neurons | 3 | Planned |
| LEG-2 | Legs consume Water chi to move | 2 | Built |
| LEG-3 | A leg produces a motion vector whose magnitude is proportional to water consumption | 2 | Built |
| LEG-4 | Thrust may be forward or backward depending on neural wiring | 2 | Built — signed thrust |
| LEG-5 | Total taobot motion per turn is the sum of all leg vectors | 2 | Built |
| LEG-6 | Legs degrade when starved and can be repaired | 2 | Partial — degrades, no repair path |
| LEG-7 | Multiple legs act in coordination under neural control, producing directed movement rather than independent thrusts | 3 | Planned |

**Implementation note.** `LegPart` carries a genetic `phi` push-direction decoupled from
attachment angle `theta`, giving differential-drive steering. This is a design decision taken
during Phase 2 and is not in the original notes; see `body_parts.py`.

## 4. Meridians (`MER-*`)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| MER-1 | Meridians consume Wood essence | 2 | Planned |
| MER-2 | A meridian is one of the five elemental types | 2 | Planned |
| MER-3 | Meridian volume is a genetic function, occupies real space in the body, and determines holding capacity | 4 | Planned |
| MER-4 | Meridians absorb and store their own element from the internal chi | 2 | Planned |
| MER-5 | Absorption rate is proportional to Wood essence consumption | 2 | Planned |
| MER-6 | Meridians diffuse their element back into the internal chi, at a rate also proportional to Wood consumption | 2 | Planned |
| MER-7 | Meridians can synapse with neurons — e.g. emitting pulses at a rate proportional to how empty they are | 3 | Planned |
| MER-8 | Meridians detect the elemental balance of the internal chi | 2 | Planned |
| MER-9 | Meridians form directed junctions with other meridians | 2 | Planned |
| MER-10 | A neuron-activated junction releases chi from one meridian into another | 3 | Planned |
| MER-11 | External junctions let a meridian expel elements out of the body | 5 | Planned |
| MER-12 | Synapse types are distinguished: absorb, diffuse, expel | 3 | **Open** — see Q2 |
| MER-13 | Meridians connect to organs, not only to each other — they are the transport network moving essence through the whole body | 2 | Planned |
| MER-14 | Meridians convert essence from one type to another | 2 | Planned |
| MER-15 | A meridian senses that a connected organ is starving | 2 | Planned — autonomous first, see [design principle](#design-principle-mechanism-before-control) |
| MER-16 | A meridian senses that a downstream meridian is empty | 2 | Planned — autonomous first |
| MER-17 | Meridians act on those signals without neural input in their first implementation; neural control replaces the built-in rule in E4 | 2 | Planned |

## 5. Structural body (`STR-*`)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| STR-1 | The structural body consumes Earth essence | 2 | Built — Earth organ |
| STR-2 | All body parts are made of Earth and are repaired by absorbing Earth essence when damaged | 2 | Partial — organs regen; parts do not |
| STR-3 | Larger body parts require more Earth | 2 | Planned |
| STR-4 | Body is a factor required by other parts rather than its own gene type | 4 | **Open** — see Q3 |

## 6. Armor (`ARM-*`)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| ARM-1 | Armor consumes Metal essence | 2 | Built — Metal organ absorbs damage |
| ARM-2 | Scales and claws grow on the taobot exterior | 2 | Planned |
| ARM-3 | Location, size, and shape are genetically specified | 4 | Planned |
| ARM-4 | Armor has weight, creating a cost to over-armoring | 2 | Planned |
| ARM-5 | Armor wears down and must be replenished | 2 | Planned |
| ARM-6 | Claws damage other taobots on collision, proportional to relative speed and claw size | 5 | Planned |
| ARM-7 | Scales absorb damage | 5 | Planned |

## 7. Internal chi (`CHI-*`)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| CHI-1 | The chi pool has a total amount value | 2 | Planned |
| CHI-2 | Chi holds the five elements at varying proportions | 2 | Partial — per-element storage exists |
| CHI-3 | Organs absorb elements present in the chi | 2 | Built |
| CHI-4 | Elements co-present in the chi degrade each other along the **destructive** cycle | post-E3 | **Deferred by design** — `degrade_rate` parsed but deliberately unused; insertion point `world.py:282` |
| CHI-5 | The same chemistry applies inside meridians — Wood chi injected into a Fire meridian feeds it; Water chi dampens it | post-E3 | Deferred with CHI-4 |
| CHI-6 | The destructive-cycle degradation rate | post-E3 | **Open** — see Q4 |
| CHI-7 | Organs push chi through a system of conversion and use — conversion serves organ demand rather than running as an isolated process | 2 | Partial — passive conversion built; demand-driven gating open, see Q7 |

**Implementation note.** The **generative** (Sheng) cycle is built: each element converts
`CYCLE_RATE=0.001` of its storage into the next productive-cycle element per tick at
`CYCLE_EFFICIENCY=0.8`, unconditionally. **Only the constructive path is modelled for now, by
design** — the destructive cycle is deferred until the organ epics complete, so that behavior can
be attributed to a single system at a time. See `PLAN.md` Phase 2 for the epic sequence.

## 8. Spawning and genetics (`GEN-*`)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| GEN-1 | Each taobot's genes are ordered in a file, each with a numeric identifier | 4 | Planned |
| GEN-2 | Gene domains | 4 | **Open** — see Q5 |

---

<a name="open-questions"></a>
## Open questions

These block the requirements that reference them. Each needs a decision before the owning phase
can be built.

| # | Question | Blocks | Owner |
|---|---|---|---|
| Q1 | Ray casting or cone detection for eye sensing? `PLAN.md` Phase 3 currently specifies cone detection, with ray casting as an optional Phase 5 upgrade for combat. Confirm or overturn. | NEU-8 | Phase 3 planning session |
| Q2 | Do absorb / diffuse / expel need to be distinct synapse types, or one type with a mode parameter? | MER-12 | Phase 3 planning session |
| Q3 | Is Earth/body a gene type of its own, or a cost factor on other parts? | STR-4, BODY-6 | Phase 4 planning session |
| Q4 | What is the destructive-cycle degradation rate? Noted as the most sensitive balance parameter in `PLAN.md` — too high and taobots die of internal imbalance, too low and element composition carries no evolutionary pressure. | CHI-4, CHI-6 | After the organ epics (E1–E3) |
| Q7 | Once neurons exist, how much conversion stays autonomous and how much becomes neurally controlled — and does the passive unconditional cycle survive alongside both? **Staging is already decided**: mechanisms are built with autonomous triggers now and neural control is wired later (see design principle). What remains open is the end state, not the build order. | NEU-12, CHI-7, MER-10, MER-17 | Neurons epic (E4) |
| Q5 | What domains does a gene carry? | GEN-2, BODY-1 | Phase 4 planning session |
| Q6 | Once the chi pool exists, is `storage` the chi pool, or does chi sit behind meridians as a separate buffer? | MER-4, CHI-1, CHI-2 | Phase 3 planning session |
