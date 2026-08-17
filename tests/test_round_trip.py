"""Story 1.4 — the leg degrade→repair round trip, and Phase 2 exit criterion 3.

The criterion asks for a fall and a recovery in **one** run, from **two different
sources**: a part's structural integrity and an organ. Story 1.4 records the decision
that the organ half comes from **Earth (the body)** rather than Water — since Story 1.0b
the Water organ *is* the mean of leg integrity, so drawing both halves from Water would
be one measurement wearing two hats.

`tools/verify_round_trip.py` is the demonstration a human watches, and writes the
workshop CSV named in `PLAN.md`. This is the guard that stops the cycle quietly breaking:
it drives the same three stages and asserts the thresholds.
"""

import pytest

from common import ELEMENT_LIST, ElementType
from world import World, WorldConfig

# Exit criterion 3's thresholds, verbatim.
PART_LOW, PART_HIGH = 0.5, 0.8
ORGAN_LOW, ORGAN_HIGH = 50.0, 80.0

SEED = 20260817


@pytest.fixture
def workshop_bot(request):
    config = WorldConfig.from_json(
        request.config.rootpath / "configs" / "workshop.json"
    )
    world = World(config, seed=SEED)
    world.initialize()
    return world, world.taobots[0]


def _worst_leg(bot) -> float:
    return min(leg.structural_integrity for leg in bot.legs)


def _run(world, bot, ticks: int, **empty: float) -> None:
    """Tick with every pool refilled except the ones named — the workshop's hand on
    the tap, which is what 'tick-step a bot through the cycle' means."""
    for _ in range(ticks):
        for element in ELEMENT_LIST:
            bot.storage[element] = bot.storage_capacity[element]
        for name, value in empty.items():
            bot.storage[ElementType[name]] = value
        world.tick()


def test_the_full_round_trip_happens_in_a_single_run(workshop_bot):
    """Exit criterion 3, both halves, one run.

    Three stages, and the order matters: the Earth organ degrades at 1.0/tick against a
    leg's ~0.005/tick, so starving both at once kills the bot on Earth long before the
    legs have fallen anywhere interesting. Legs first, then Earth, then feed."""
    world, bot = workshop_bot
    assert _worst_leg(bot) == pytest.approx(1.0)
    assert bot.organ(ElementType.EARTH) == pytest.approx(100.0)

    # 1 — legs degrade while the Earth organ is untouched, so the two halves stay
    #     independent rather than one causing the other.
    for _ in range(500):
        _run(world, bot, 1, WATER=0.0)
        if _worst_leg(bot) < 0.45:
            break
    part_low = _worst_leg(bot)
    assert part_low < PART_LOW, "legs never starved far enough to test recovery"
    assert bot.organ(ElementType.EARTH) > ORGAN_HIGH, (
        "the Earth organ moved during the leg stage — the two halves are not independent"
    )

    # 2 — the Earth organ falls. Repair is below its floor here, so it cannot mask it.
    for _ in range(300):
        _run(world, bot, 1, WATER=0.0, EARTH=0.0)
        if bot.organ(ElementType.EARTH) < 45.0:
            break
    organ_low = bot.organ(ElementType.EARTH)
    assert organ_low < ORGAN_LOW

    # 3 — both recover, each from its own restocked storage.
    for _ in range(1500):
        _run(world, bot, 1)
        if _worst_leg(bot) > 0.85 and bot.organ(ElementType.EARTH) > 85.0:
            break

    assert _worst_leg(bot) > PART_HIGH, "leg integrity never recovered"
    assert bot.organ(ElementType.EARTH) > ORGAN_HIGH, "the Earth organ never recovered"
    assert bot.entity_id in world._taobots, "the bot died before completing the trip"


def test_the_two_halves_come_from_different_sources(workshop_bot):
    """Story 1.4's recorded decision, made mechanical.

    If the organ half were ever sourced from Water it would track leg integrity exactly,
    and exit criterion 3 would be satisfied by one measurement counted twice. Earth and
    the legs must be able to move independently — asserted by moving the legs and
    showing Earth does not follow."""
    world, bot = workshop_bot

    for _ in range(400):
        _run(world, bot, 1, WATER=0.0)
        if _worst_leg(bot) < 0.6:
            break

    water_organ = bot.organ(ElementType.WATER)
    earth_organ = bot.organ(ElementType.EARTH)

    # Water tracks the legs by construction (AD-5) — that is exactly why it cannot
    # supply the organ half.
    assert water_organ == pytest.approx(
        100.0 * sum(leg.structural_integrity for leg in bot.legs) / len(bot.legs)
    )
    # Earth does not.
    assert earth_organ > ORGAN_HIGH


def test_a_destroyed_leg_still_comes_back(workshop_bot):
    """0.0 is not terminal. The run that produced the committed evidence drove a leg to
    exactly 0.0000 and repaired it to 0.85, so the criterion does not quietly depend on
    the damage staying shallow."""
    world, bot = workshop_bot
    bot.legs[0].structural_integrity = 0.0

    for _ in range(1500):
        _run(world, bot, 1)
        if bot.legs[0].structural_integrity > PART_HIGH:
            break

    assert bot.legs[0].structural_integrity > PART_HIGH
