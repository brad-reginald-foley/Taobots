"""Regenerate the sweep behind `chi.water_deficit_threshold` and `deficit_conversion_rate`.

The epic's rule is that every new tunable is *derived* by stepping through the behaviour
it governs in workshop mode, never chosen. The resulting numbers and reasoning live in
`configs/laws.json`; this is the measurement that produced them, so a reader can
regenerate the tables instead of trusting them.

    python tools/derive_chi_laws.py rate         # the rate knee, threshold pinned
    python tools/derive_chi_laws.py threshold    # the threshold knee, rate pinned
    python tools/derive_chi_laws.py floor        # is the knee an artefact of the metric?
    python tools/derive_chi_laws.py transfer     # does it hold in default_world? (AD-14)
    python tools/derive_chi_laws.py all

**The metric.** `preventable` is leg integrity lost on ticks where the bot still held
Metal worth converting. Total integrity loss cannot derive anything here: it is
dominated by bots dying with every pool empty, which no conversion can reach, and is
nearly flat across the whole grid. Splitting the preventable part out is what turns that
plateau into a knee.

**The caveat that comes with it.** "Metal worth converting" is a constant — `METAL_FLOOR`
below — and the rate floor is derived as `drain_max / (CYCLE_EFFICIENCY x METAL_FLOOR)`.
The two share it, so the knee landing on the predicted floor is *partly by construction*:
raise the metric's floor and the predicted rate floor drops in proportion, and the
measured knee follows. The `floor` mode sweeps `METAL_FLOOR` explicitly so the size of
that effect is visible rather than assumed. What the sweep genuinely establishes is the
*shape* — a sharp knee rather than a gradient, in the same place for every archetype and
in `default_world` as well as the workshop — not the third significant figure.

Runs are pinned to workshop mode, per `AD-14`; nothing here writes to `logs/`.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from chi import CYCLE_EFFICIENCY, ChiLaws, ConversionPath  # noqa: E402
from common import ELEMENT_LIST, ElementType  # noqa: E402
from taobot_simple import ARCHETYPES, DEFAULT_PARAMS  # noqa: E402
from world import World, WorldConfig  # noqa: E402

WATER = ElementType.WATER
METAL = ElementType.METAL

SEEDS = (11, 22, 33, 42, 55, 66, 77, 88, 99, 101, 202, 303)
TICKS = 6000

#: Metal below which a bot has nothing left to convert, so its starvation is not
#: preventable by any conversion law. Shared with the rate floor — see the caveat above.
METAL_FLOOR = 1.0

#: Both legs at cruise draw this much Water between them per tick (`DEFAULT_PARAMS`).
LEG_DRAIN_PER_TICK = 0.020

ARCHETYPE_NAMES = ("default", *ARCHETYPES)


def predicted_rate_floor(metal_floor: float = METAL_FLOOR) -> float:
    """The demand path must replace a whole tick's leg draw out of the Metal left."""
    return LEG_DRAIN_PER_TICK / (CYCLE_EFFICIENCY * metal_floor)


def predicted_threshold_floor(ticks_of_buffer: int = 4) -> float:
    """As a fraction of the *smallest* Water pool any archetype ships."""
    smallest = min(
        params.get("storage_capacity", DEFAULT_PARAMS["storage_capacity"])["WATER"]
        for params in (DEFAULT_PARAMS, *ARCHETYPES.values())
    )
    return ticks_of_buffer * LEG_DRAIN_PER_TICK / smallest


@dataclass
class Run:
    preventable: float
    integrity_lost: float
    metal_mean: float
    deficit_produced: float
    episodes: list[int]
    deaths: int


def one_run(
    laws: ChiLaws,
    seed: int,
    archetype: str = "default",
    config: str = "workshop.json",
    metal_floor: float = METAL_FLOOR,
    ticks: int = TICKS,
) -> Run:
    """Tick one arena and measure what the demand path did and did not prevent."""
    world_config = WorldConfig.from_json(REPO / "configs" / config)
    world_config.chi = laws
    world = World(world_config, seed=seed)

    if archetype != "*":
        params = None if archetype == "default" else ARCHETYPES[archetype]
        original_spawn = world.spawn_taobot

        def pinned(*args, **kwargs):
            kwargs["params"] = params
            kwargs["archetype"] = archetype
            return original_spawn(*args, **kwargs)

        world.spawn_taobot = pinned  # type: ignore[method-assign]

    world.initialize()

    preventable = 0.0
    integrity_lost = 0.0
    deficit_produced = 0.0
    deaths = 0
    metal_samples: list[float] = []
    previous_integrity: dict[int, float] = {}
    previous_metal: dict[int, float] = {}
    episodes: list[int] = []
    open_episode: dict[int, int] = {}

    def on_death(_bot) -> None:
        nonlocal deaths
        deaths += 1

    world.on_taobot_death = on_death

    for _ in range(ticks):
        world.tick()
        for bot in world.taobots:
            eid = bot.entity_id
            metal_samples.append(bot.storage[METAL])

            total = sum(leg.structural_integrity for leg in bot.legs)
            before = previous_integrity.get(eid)
            if before is not None and total < before:
                integrity_lost += before - total
                # Metal as it stood *entering* this tick — what the demand path had to
                # work with, not what is left after it spent some.
                if previous_metal.get(eid, 0.0) >= metal_floor:
                    preventable += before - total
            previous_integrity[eid] = total
            previous_metal[eid] = bot.storage[METAL]

            if bot.chi.deficit_active:
                open_episode[eid] = open_episode.get(eid, 0) + 1
                deficit_produced += bot.chi.moved(
                    ConversionPath.DEFICIT, METAL, WATER
                )[1]
            elif eid in open_episode:
                episodes.append(open_episode.pop(eid))

    episodes += list(open_episode.values())
    return Run(
        preventable=preventable,
        integrity_lost=integrity_lost,
        metal_mean=statistics.fmean(metal_samples) if metal_samples else 0.0,
        deficit_produced=deficit_produced,
        episodes=episodes,
        deaths=deaths,
    )


@dataclass
class Cell:
    """One grid point, aggregated over `SEEDS`."""

    laws: ChiLaws
    archetype: str
    runs: list[Run]

    @property
    def preventable(self) -> float:
        return sum(r.preventable for r in self.runs)

    @property
    def integrity_lost(self) -> float:
        return sum(r.integrity_lost for r in self.runs)

    @property
    def per_seed_preventable(self) -> list[float]:
        return [r.preventable for r in self.runs]

    def line(self) -> str:
        per_seed = self.per_seed_preventable
        spread = max(per_seed) - min(per_seed) if per_seed else 0.0
        episodes = [n for r in self.runs for n in r.episodes]
        return (
            f"{self.archetype:>11} "
            f"{self.laws.water_deficit_threshold:>8.4f} "
            f"{self.laws.deficit_conversion_rate:>7.4f} | "
            f"{self.preventable:>10.3f} +-{spread:>7.3f} | "
            f"{self.integrity_lost:>9.3f} | "
            f"{statistics.median(episodes) if episodes else 0:>6.0f} | "
            f"{statistics.fmean([r.metal_mean for r in self.runs]):>6.2f} | "
            f"{sum(r.deficit_produced for r in self.runs):>8.1f} | "
            f"{sum(r.deaths for r in self.runs):>6d}"
        )


HEADER = (
    f"{'archetype':>11} {'thr':>8} {'rate':>7} | {'preventable':>10} {'spread':>9} | "
    f"{'integLost':>9} | {'epMed':>6} | {'METAL':>6} | {'defProd':>8} | {'deaths':>6}"
)


def sweep(
    grid, *, config: str = "workshop.json", metal_floor: float = METAL_FLOOR, ticks: int = TICKS
) -> list[Cell]:
    print(HEADER)
    print("-" * len(HEADER))
    cells = []
    for archetype, threshold, rate in grid:
        laws = ChiLaws(
            water_deficit_threshold=threshold, deficit_conversion_rate=rate
        )
        cell = Cell(
            laws=laws,
            archetype=archetype,
            runs=[
                one_run(laws, s, archetype, config, metal_floor, ticks) for s in SEEDS
            ],
        )
        cells.append(cell)
        print(cell.line(), flush=True)
    return cells


# ---------------------------------------------------------------------------
# The four modes
# ---------------------------------------------------------------------------

RATE_LADDER = (0.004, 0.008, 0.012, 0.016, 0.020, 0.025, 0.032, 0.064)
THRESHOLD_LADDER = (0.001, 0.002, 0.004, 0.008, 0.015, 0.030, 0.060, 0.120)


def mode_rate() -> None:
    print(f"\n# rate knee (threshold pinned at 0.03). Predicted floor: "
          f"drain_max / (EFFICIENCY x METAL_FLOOR) = {predicted_rate_floor():.4f}\n")
    sweep([(a, 0.03, r) for a in ARCHETYPE_NAMES for r in RATE_LADDER])


def mode_threshold() -> None:
    print(f"\n# threshold knee (rate pinned at 0.025). Predicted floor: "
          f"4 ticks of leg draw in the smallest Water pool = "
          f"{predicted_threshold_floor():.4f}\n")
    sweep([(a, t, 0.025) for a in ARCHETYPE_NAMES for t in THRESHOLD_LADDER])


def mode_floor() -> None:
    """How much of the rate knee is the metric's own Metal floor?

    The predicted floor is inversely proportional to `METAL_FLOOR`, so if the measured
    knee tracks it one-for-one, the agreement between prediction and measurement is
    partly circular and only the *shape* of the knee is evidence."""
    print("\n# is the rate knee an artefact of the metric's Metal floor?\n")
    for metal_floor in (0.25, 1.0, 4.0):
        print(
            f"\n## METAL_FLOOR = {metal_floor} "
            f"-> predicted rate floor {predicted_rate_floor(metal_floor):.4f}\n"
        )
        sweep(
            [("default", 0.03, r) for r in RATE_LADDER],
            metal_floor=metal_floor,
        )


def mode_transfer() -> None:
    """`AD-14`: the workshop is a microscope, not a different world — check it holds."""
    print("\n# default_world, 20 bots under contention (archetypes cycled as shipped)\n")
    grid = [("*", 0.0, 0.0)]
    grid += [("*", t, 0.025) for t in (0.004, 0.008, 0.015, 0.030, 0.060)]
    grid += [("*", 0.008, r) for r in (0.012, 0.020, 0.032)]
    sweep(grid, config="default_world.json", ticks=4000)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        nargs="?",
        default="all",
        choices=("rate", "threshold", "floor", "transfer", "all"),
    )
    args = parser.parse_args()

    print(f"seeds={list(SEEDS)} ticks={TICKS} elements={[e.name for e in ELEMENT_LIST]}")
    modes = {
        "rate": mode_rate,
        "threshold": mode_threshold,
        "floor": mode_floor,
        "transfer": mode_transfer,
    }
    if args.mode == "all":
        for run_mode in modes.values():
            run_mode()
    else:
        modes[args.mode]()


if __name__ == "__main__":
    main()
