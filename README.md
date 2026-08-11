# Taobots

An evolutionary life simulation set in the 5-element Taoist world of Pangu. Creatures (taobots) roam a toroidal landscape, gathering elemental resources, avoiding hazards, and eventually evolving bodies, neural networks, and genetic lineages.

---

## Quick start

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt -r requirements-notebooks.txt

make sim           # visual simulation (pygame window)
make headless      # headless max-speed run, logs to logs/
make test          # run test suite
make check         # lint + typecheck + tests
```

Pin the interpreter to 3.11 — it is what `pyproject.toml` targets for ruff, black, and mypy.
An unpinned `python -m venv` picks up whatever `python` resolves to, which can leave the
simulation and the test suite running on different interpreters.

The `Makefile` calls bare `python` and `pytest`, so the venv must be active before any `make`
target. Notebook dependencies (`jupyterlab`, `matplotlib`, `numpy`, `pandas`) live in
`requirements-notebooks.txt`; installing dev requirements alone runs the sim and tests but
leaves `notebooks/` broken.

**CLI options**

```
python main.py [--headless] [--workshop] [--config PATH] [--duration SECS] [--seed INT]

  --headless        Run without display at maximum speed
  --workshop        Open Lao Tzu's Workshop — single-bot sandbox, tick-by-tick
  --config PATH     World config JSON (default: configs/default_world.json)
  --duration SECS   Stop after N wall-clock seconds (headless only; 0 = infinite)
  --seed INT        Fix random seed for reproducibility
```

---

## Visual controls

| Key / Action | Effect |
|---|---|
| `Space` | Pause / unpause |
| `↑` / `↓` arrow | Increase / decrease target FPS (10 → 20 → 30 → 60 → 120 → uncapped) |
| `G` | Toggle spatial-hash grid overlay |
| `Esc` / `Q` | Quit |
| Click taobot | Select — shows full inspector in side panel |
| Click empty space | Deselect |

---

## Lao Tzu's Workshop

A single-bot sandbox for watching one taobot in detail, tick by tick.

```bash
python main.py --workshop --seed 42
```

It opens **paused**. The world is a small 30 × 25 torus with 15 resources and 10 hazards, and
`target_population` is 1 — the bot is replaced when it dies, so you always have a subject.

| Key / Action | Effect |
|---|---|
| `N` / `→` | Step exactly one tick, stay paused |
| `R` | Toggle slow run (~2 ticks/sec) |
| `Space` | Pause / unpause at target FPS |
| `↑` / `↓` arrow | Increase / decrease target FPS by 5 (clamped 5–120) |
| `G` | Toggle grid overlay |
| `Esc` / `Q` | Quit |
| Click pause button | Pause / unpause |
| Drag speed slider | Set target FPS |

`--workshop` always loads `configs/workshop.json` and **ignores `--config`**. To run a single bot
in a different world, either edit `configs/workshop.json` or drop `--workshop` and set
`initial_count` and `target_population` to 1 in the config you pass.

Workshop mode is the only source of complete per-tick individual state — normal headless runs
sample five focal bots every ten ticks. See the workshop row under [Output files](#output-files).

---

## World

The world is an **80 × 60 virtual-unit torus** (wraps at all edges). The display maps 1 VU → 10 px, giving an 800 × 600 viewport plus a 240 px inspector panel on the right.

### Elements

| Element | Hex | Resource | Hazard |
|---|---|---|---|
| Wood | `#8B4513` | Wood | Thornwall |
| Water | `#1E50DC` | Water | Sinkhole |
| Metal | `#C0C0C0` | Metal | Shardfield |
| Fire | `#FF500A` | Fire | Pyre |
| Earth | `#786414` | Earth | Mudpit |

Resources respawn after a configurable delay. Hazards are permanent.

### Element cycles

**Productive:** Water → Wood → Fire → Earth → Metal → Water

**Destructive:** Fire → Metal → Wood → Earth → Water → Fire

(Cycles are encoded in `common.py` and will drive chi chemistry in Phase 2.)

---

## Taobots

### Behavioral states

Each taobot is always in one of four states, evaluated every tick in priority order:

| State | Color | Condition | Action |
|---|---|---|---|
| **fleeing** | yellow | Health below `flee_health_threshold` *or* hazard within `hazard_avoidance_range` | Steer away from nearest hazard; random walk if none visible |
| **seeking** | green | Resource visible and not yet adjacent | Head toward highest-scoring visible resource |
| **collecting** | green | Adjacent to target resource | Extract up to `collect_rate` units per tick; stop when storage full |
| **searching** | green | Nothing visible | Correlated random walk (bounded heading perturbation) |

The flee state uses the same yellow indicator for both low-health flight and hazard avoidance — both are defensive manoeuvres.

### Resource scoring

When choosing which visible resource to head toward, the taobot scores each candidate:

```
score = affinity[element] / max(0.1, distance)
```

Higher affinity means stronger preference; the `max(0.1, ...)` floor prevents a zero-distance resource from dominating and causing oscillation when the bot is standing on a resource.

### Metabolism

Every tick, each taobot consumes a fixed amount of each element from its storage:

```
WOOD  0.02 / tick    WATER  0.02 / tick
METAL 0.01 / tick    FIRE   0.015 / tick
EARTH 0.01 / tick
```

If storage for an element runs out, the deficit is converted to health damage:
`health_lost = deficit × 10.0`

A bot that can't feed itself will die within a few hundred ticks.

### Archetypes

Four archetypes are spawned in equal rotation at world initialisation (defined in `taobot_simple.py`):

| Archetype | Speed | Sense | Special |
|---|---|---|---|
| **Wanderer** | 2.2 | 8.0 | Covers the most ground; finds resources others miss |
| **Specialist** | 1.0 | 6.0 | FIRE affinity ×8 vs other elements; double FIRE storage; ignores most resources |
| **Survivor** | 1.4 | 6.0 | Flees at 50% health (vs 25%); hazard avoidance range 7.0 VU (vs 4.0) |
| **Hoarder** | 0.8 | 6.0 | `collect_rate` = 5.0 (vs 2.0); all storage doubled to 40 units |

All unspecified params inherit from `DEFAULT_PARAMS` in `taobot_simple.py`.

### Fitness score

```
fitness = resources_collected_total / max(1, age_ticks)
```

Resources collected per tick lived. Shown in the inspector. Will drive selection pressure in Phase 4 (genetics).

---

## Inspector panel

Click any taobot to pin it. The panel shows:

- Current state, health bar, age, fitness score
- Distance moved and total damage taken (lifetime)
- Per-element storage levels
- Speed, sensing range, and normalised affinities

The health graph below the inspector shows the last 200 ticks of population health (shaded band = min/max, bright line = mean).

---

## Output files

All logs are written to `logs/`. Timestamped files accumulate across runs; the two fixed-name
files are **overwritten** every time a run starts, so copy them out before re-running.

| File | Contents | Cadence | Per run |
|---|---|---|---|
| `<world>_<timestamp>.csv` | Population-level stats (health, counts) | Every 60 ticks | accumulates |
| `<world>_workshop_<timestamp>.csv` | Full per-tick state of the single workshop bot: organs, storage, per-element intake, damage, position, behavior, per-leg reserve/integrity/thrust | Every tick (`--workshop` only) | accumulates |
| `<world>_deaths.csv` | Per-bot death record (age, distance, damage, per-element collected) | On each death | **overwritten** |
| `<world>_focal.csv` | N=5 sampled focal bots: location, state, storage, interval deltas | Every 10 ticks | **overwritten** |

---

## World config

JSON files in `configs/`. Key fields:

```json
{
  "name": "default",
  "laws": "laws.json",
  "world":     { "width": 80, "height": 60 },
  "resources": { "initial_count": 150, "respawn_delay_ticks": 60,
                 "spawn_weights": { "WOOD": 1, "WATER": 1, ... } },
  "hazards":   { "initial_count": 20, "spawn_weights": { ... } },
  "taobots":   { "initial_count": 20, "target_population": 20 }
}
```

`target_population` is maintained at runtime — the world respawns a replacement whenever a taobot dies.

**Laws vs. world settings.** Tunables shared by every world live in `configs/laws.json` — currently
just `chemistry.degrade_rate`. A config opts in with the `laws` key, a plain filename resolved *beside
that config file*, never against the working directory; omit the key to declare no laws. The config's
own blocks are merged over the laws **key by key**: declaring a block overrides only the keys it names
and inherits the rest of that block. `configs/fire_arena.json` overrides `degrade_rate` this way and
says in the file why that is deliberate. Unrecognised law keys are ignored, so a new law needs no code
change.

**`configs/workshop.json` is a scaled-down `default_world`, not a different world.** Its resource and
hazard counts are set so the per-unit-area rates match, and `tests/test_world.py` asserts that as a
property so the two cannot drift apart. Only size and population deliberately differ.

---

---

# Lore

## Primordial Age

This is the primordial land of Pangu. It was empty and formless but the principles of Yin and Yang have begun to work to generate the first stirrings of life. With the first life comes the struggle to improve, and to transcend.


## Features
There are 5 principle elements in Pangu, with Yin and Yang aspects. 

- 5 Element types: Wood, Water, Metal, Fire, Earth

-- Wood corresponds with generation and growth
-- Fire corresponds with thinking and motion
-- Earth corresponds with substance and stability
-- Metal with hardness and attack
-- Water with willpower and motion

## Element Relationships
The elements relate to each other in both productive and destructive cucles 
### Productive Cycle
- Water produces Wood
- Wood produces Fire
- Fire produces Earth
- Earth produces Metal
- Metal produces Water

### Destructive Cycle
- Fire destroys Metal
- Metal destroys Wood
- Wood destroys Earth
- Earth destroys Water
- Water destroys Fire

## Resources and Hazards
After the primordial chaos in Pangyu, the first life and structure began to appear

### Resources
- Leaves (Wood)
- Melons (Water)
- Salt (Metal)
- Carrots (Fire)
- Potatoes (Earth)

### Hazards
- Thorns (Wood)
- Pools (Water)
- Spikes (Metal)
- Coals (Fire)
- Sand (Earth)

# Age of development
From the pieces of world combining and gaining substance, the first taobot monsters appeared. Composed of varying combinations of elements, in infinite patterns, the taobots rise, strive and fall, only to rise again, improving with each lifetime. In the age of development, hopeful monsters are spawned, most of whom are unable to sense, move, grow or reason in the world. Some very few show the signs of organisation, will and drive. These fitfully reproduce, and move towards sentience

The taobots are made of 5 parts, plus chi

- Legs: Water
- Meridians: Wood
- Nerves, eyes: Fire
- Body, mouth: Earth
- Armor, claws: Metal

The taobots move through the world, collecting elements and generating chi. When they have sufficient chi, they spawn. Spawned taobots are combinations of 2 parents, and have mutations in their characters.

We record each bots' genetic types in a bank, as well as their karma (fitness score). Bots with higher karma are more likely to respawn after death.

# Age of cultivation
There are now lineages of taobots with the skills and bodies to navigate their world. When they encounter each other they strive. Becoming more adept at resource collection, battling with their claws, and their essenced chi, they may consume each other, and rise higher


---

# Technical details

Subsystem requirements — neurons, legs, meridians, structural body, armor, internal chi, and
genetics — live in **[`docs/domain-spec.md`](docs/domain-spec.md)**, with stable requirement IDs
and an open-questions register.

They were moved out of this README on 2026-08-10 so that requirements have a single home.
`PLAN.md` schedules them by phase; this README documents what you can run today.
