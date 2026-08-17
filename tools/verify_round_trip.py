"""Story 1.4 — tick-step a bot through the full leg cycle and write the evidence.

Phase 2 exit criterion 3 asks for a degrade→recover round trip, in **one** run, from
**two different sources**: a part's structural integrity, and an organ. Story 1.4 records
the decision that the organ half comes from **Earth (the body)**, not Water — once `AD-5`
made the Water organ the mean of leg integrity, sourcing both halves from Water would
collapse them into a single measurement and silently weaken the criterion.

So this drives three stages against one bot, writing a real `WorkshopLogger` CSV:

    1. starve Water only    legs thrust with an empty reserve and degrade;
                            the Earth organ is untouched, so the two halves stay
                            independent rather than one causing the other
    2. starve Earth         the Earth organ falls; repair is below its floor and
                            cannot run, so the legs stay damaged
    3. feed both            Earth-funded repair raises leg integrity, and the Earth
                            organ regenerates from its own restocked storage

Stage 1 before stage 2 on purpose: the Earth organ degrades at `ORGAN_DEGRADE_RATE`
(1.0/tick) against a leg's ~0.005/tick, so starving both at once kills the bot on Earth
long before the legs have fallen anywhere interesting.

This is a demonstration, not a test — `tests/test_round_trip.py` is the regression guard.
It exists so the evidence can be regenerated rather than trusted, and so a reader can
watch the cycle rather than read an assertion about it.

Usage:
    python tools/verify_round_trip.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from common import ELEMENT_LIST, ElementType  # noqa: E402
from main import WorkshopLogger, run_timestamp  # noqa: E402
from world import World, WorldConfig  # noqa: E402

WORKSHOP = REPO_ROOT / "configs" / "workshop.json"
SEED = 20260817

#: Exit criterion 3's thresholds, verbatim.
PART_LOW, PART_HIGH = 0.5, 0.8
ORGAN_LOW, ORGAN_HIGH = 50.0, 80.0


def _integrity(bot) -> float:
    return min(leg.structural_integrity for leg in bot.legs)


def main() -> int:
    config = WorldConfig.from_json(WORKSHOP)
    world = World(config, seed=SEED)
    world.initialize()
    bot = world.taobots[0]

    ts = run_timestamp()
    logger = WorkshopLogger(config.name, n_legs=len(bot.legs), ts=ts)

    def stock(**empty: float) -> None:
        """Refill every pool, then empty the named ones — the workshop's hand on the tap."""
        for element in ELEMENT_LIST:
            bot.storage[element] = bot.storage_capacity[element]
        for name, value in empty.items():
            bot.storage[ElementType[name]] = value

    def step(**empty: float) -> None:
        stock(**empty)
        world.tick()
        logger.log_tick(bot, world.tick_count)

    print(f"seed {SEED}, {config.name} config, {len(bot.legs)} legs\n")
    print(f"{'tick':>6}  {'stage':<16} {'leg integrity':>13} {'Earth organ':>12}")

    def show(stage: str) -> None:
        print(f"{world.tick_count:>6}  {stage:<16} {_integrity(bot):>13.4f} "
              f"{bot.organ(ElementType.EARTH):>12.2f}")

    show("start")

    # 1 — legs degrade, Earth untouched.
    while _integrity(bot) > 0.45 and world.tick_count < 500:
        step(WATER=0.0)
    show("legs starved")
    part_low = _integrity(bot)

    # 2 — the Earth organ falls; repair is below its floor and cannot mask it.
    guard = world.tick_count + 300
    while bot.organ(ElementType.EARTH) > 45.0 and world.tick_count < guard:
        step(WATER=0.0, EARTH=0.0)
    show("earth starved")
    organ_low = bot.organ(ElementType.EARTH)

    # 3 — both recover, from their own restocked storage.
    guard = world.tick_count + 1200
    while (_integrity(bot) < 0.85 or bot.organ(ElementType.EARTH) < 85.0) \
            and world.tick_count < guard:
        step()
    show("recovered")
    logger.close()

    part_high, organ_high = _integrity(bot), bot.organ(ElementType.EARTH)
    alive = bot.entity_id in world._taobots

    csv_path = WorkshopLogger.path_name(config.name, ts)
    print(f"\nCSV: {csv_path}\n")
    rows = [
        ("part  — leg integrity", part_low, PART_LOW, part_high, PART_HIGH, "leg_N_integrity"),
        ("organ — Earth (body)", organ_low, ORGAN_LOW, organ_high, ORGAN_HIGH, "organ_EARTH"),
    ]
    print(f"{'half':<22} {'fell to':>9} {'need <':>8} {'rose to':>9} {'need >':>8}  column")
    ok = alive
    for label, low, need_low, high, need_high, column in rows:
        passed = low < need_low and high > need_high
        ok = ok and passed
        print(f"{label:<22} {low:>9.4f} {need_low:>8.2f} {high:>9.4f} {need_high:>8.2f}"
              f"  {column}  {'PASS' if passed else 'FAIL'}")
    print(f"\nbot survived the whole run: {alive}")
    print("exit criterion 3:", "SATISFIED" if ok else "NOT SATISFIED")
    print("\nBoth halves come from different sources, per Story 1.4's recorded decision:")
    print("the part half from the legs, the organ half from Earth — not from the Water")
    print("organ, which since Story 1.0b *is* the mean of leg integrity and would have")
    print("made one measurement wearing two hats.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
