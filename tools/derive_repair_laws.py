"""Regenerate the checks behind the repair laws in `configs/laws.json` — Story 1.3.

**This is a sanity check, not a search.** Brad's direction for E1 was working systems
with enough resolution to see behaviour change, not a balanced world; real balance waits
until bots are evolvable and can be selected rather than tuned. So each law is anchored
to a stated mechanical quantity (see the `_repair_note` in `configs/laws.json`) and this
script confirms the anchored values behave as claimed. It does not fit them to an
outcome, and it will not tell you the "best" value — that question is premature.

What it does answer, and what the note rests on:

    cap        does `max_integrity_per_tick` actually bind? Without it a part rebuilds
               entirely the moment Earth allows, which is the regime the story started
               in and the reason integrity was never observable.
    trip       does a damaged part complete a round trip when fed — falling below 0.5
               and recovering above 0.8, which is Phase 2 exit criterion 3?
    cost       what does repair actually cost, per tick and per full system rebuild,
               against the Earth a bot can hold?
    free       what happens across the whole free-running population — does the mix of
               outcomes stay varied, or does one mode swallow the rest?

Usage:
    python tools/derive_repair_laws.py cap
    python tools/derive_repair_laws.py trip
    python tools/derive_repair_laws.py cost
    python tools/derive_repair_laws.py free
    python tools/derive_repair_laws.py all
"""

from __future__ import annotations

import statistics
import sys
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from chi import RepairLaws  # noqa: E402
from common import ELEMENT_LIST, ElementType  # noqa: E402
from world import World, WorldConfig  # noqa: E402

WORKSHOP = REPO_ROOT / "configs" / "workshop.json"
DEFAULT_WORLD = REPO_ROOT / "configs" / "default_world.json"
SEEDS = (1, 3, 7, 42, 99, 123, 2024, 20260811)


def _laws(**overrides) -> RepairLaws:
    base = WorldConfig.from_json(WORKSHOP).repair
    return replace(base, **overrides)


def _min_integrity(bot) -> float:
    return min(leg.structural_integrity for leg in bot.legs)


def cap() -> None:
    """Does the per-tick cap bind? Compare the shipped cap against an unbound one."""
    print("Does max_integrity_per_tick bind?")
    print("A part forced to 0.0, fed, repaired for one tick.\n")
    print(f"{'cap':>10} {'integrity after 1 tick':>24}   {'':<8}")
    for cap_value in (0.002, 0.02, 1.0):
        cfg = replace(WorldConfig.from_json(WORKSHOP),
                      repair=_laws(max_integrity_per_tick=cap_value))
        w = World(cfg, seed=42)
        w.initialize()
        bot = w.taobots[0]
        for leg in bot.legs:
            leg.structural_integrity = 0.0
        for e in ELEMENT_LIST:
            bot.storage[e] = bot.storage_capacity[e]
        bot._repair_parts()
        note = "unbound — rebuilds in one tick" if cap_value >= 1.0 else ""
        print(f"{cap_value:>10.3f} {_min_integrity(bot):>24.4f}   {note}")
    print("\nThe shipped 0.002 is ~2/5 of the ~0.005/tick a leg loses when starved at")
    print("cruise, so damage accumulates while starvation lasts and unwinds once fed.")


def trip() -> None:
    """Phase 2 exit criterion 3: below 0.5, recover above 0.8, in one run."""
    print("Controlled round trip: legs forced to 0.30, bot kept fed.\n")
    cfg = WorldConfig.from_json(WORKSHOP)
    w = World(cfg, seed=42)
    w.initialize()
    bot = w.taobots[0]
    for leg in bot.legs:
        leg.structural_integrity = 0.30
    crossed_low = _min_integrity(bot) < 0.5
    recovered_at = None
    print(f"{'tick':>6} {'integrity':>10} {'earth':>8}")
    for i in range(1, 2001):
        for e in ELEMENT_LIST:
            bot.storage[e] = bot.storage_capacity[e]
        w.tick()
        integrity = _min_integrity(bot)
        if i % 70 == 0 or integrity >= 0.9999:
            print(f"{i:>6} {integrity:>10.4f} {bot.storage[ElementType.EARTH]:>8.2f}")
        if recovered_at is None and integrity > 0.8:
            recovered_at = i
        if integrity >= 0.9999:
            break
    print(f"\nstarted below 0.5: {crossed_low}; recovered above 0.8 at tick {recovered_at}")
    print("Exit criterion 3 is satisfiable by tick-stepping — which is how Story 1.4")
    print("is chartered to demonstrate it. A *free-running* bot rarely recovers a deep")
    print("dip, because low integrity means low thrust means less foraging.")


def cost() -> None:
    """What repair costs, against what a bot can hold."""
    laws = WorldConfig.from_json(WORKSHOP).repair
    cap_earth = 20.0
    per_tick_two_legs = 2 * laws.max_integrity_per_tick * 1.0 * laws.earth_per_integrity_mass
    system = 4.0 * laws.earth_per_integrity_mass
    print("Repair economics at the shipped laws\n")
    print(f"  full rebuild of one organ system (mass 4.0) : {system:.1f} Earth"
          f"  = {100 * system / cap_earth:.0f}% of a full pool")
    print(f"  per tick while repairing two legs            : {per_tick_two_legs:.3f} Earth")
    print("  Earth organ's own upkeep                     : 0.004-0.008 Earth/tick")
    print(f"  floor held back from repair                  : {laws.earth_repair_floor:.1f} Earth"
          f"  = {laws.earth_repair_floor / 0.008:.0f}-{laws.earth_repair_floor / 0.004:.0f}"
          " ticks of body upkeep")
    print("\nRepair roughly triples Earth demand while it runs — the cost is visible,")
    print("and the floor stops healing legs from starving the one organ that kills.")


def free() -> None:
    """Free-running outcomes: is the mix varied, or does one mode swallow the rest?"""
    print(f"Free-running workshop bots, {len(SEEDS)} seeds x 3000 ticks\n")
    print(f"{'seed':>8} {'min integrity':>14} {'round trips':>12} {'lifespan':>9}")
    mins, trips = [], []
    for seed in SEEDS:
        w = World(WorldConfig.from_json(WORKSHOP), seed=seed)
        w.initialize()
        bot = w.taobots[0]
        low, n, dip, ntrip = 1.0, 0, None, 0
        for i in range(3000):
            w.tick()
            if bot.entity_id not in w._taobots:
                break
            n = i + 1
            cur = _min_integrity(bot)
            low = min(low, cur)
            if dip is None and cur < 0.95:
                dip = cur
            elif dip is not None and cur > 0.99:
                ntrip += 1
                dip = None
        mins.append(low)
        trips.append(ntrip)
        print(f"{seed:>8} {low:>14.4f} {ntrip:>12} {n:>9}")
    print(f"\nmedian min integrity {statistics.median(mins):.4f}; "
          f"{sum(1 for m in mins if m > 0.99)}/{len(SEEDS)} never degraded, "
          f"{sum(1 for m in mins if m < 0.05)}/{len(SEEDS)} lost a leg entirely.")
    print("Spread is the point: enough resolution to see a change in behaviour when")
    print("the bots change. Convergence is a job for selection, not for tuning.")


MODES = {"cap": cap, "trip": trip, "cost": cost, "free": free}

if __name__ == "__main__":
    chosen = sys.argv[1:] or ["all"]
    if chosen == ["all"]:
        chosen = list(MODES)
    for name in chosen:
        if name not in MODES:
            raise SystemExit(f"unknown mode {name!r}; pick from {', '.join(MODES)} or 'all'")
        print("=" * 72)
        MODES[name]()
        print()
