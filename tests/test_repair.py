"""Story 1.3 — Earth-funded structural repair.

Repair spans three tiers: `BodyPart` owns the arithmetic, `ChiPool` owns the Earth and
the pro-rata split, and `TaobotSimple._repair_parts` is the pass that joins them. These
tests exercise the joined behaviour on a real bot wherever they can, because the failure
mode this project keeps rediscovering is a pure function that is correct and a caller
that ignores it.
"""

import pytest

from body_parts import LegPart
from chi import RepairLaws
from common import ELEMENT_LIST, ElementType
from taobot_simple import TaobotSimple

RATE = 4.0          # Earth per unit of integrity x mass
FLOOR = 2.0         # Earth held back from repair
PER_TICK = 0.002    # integrity a part may regain in one tick

LAWS = RepairLaws(
    earth_per_integrity_mass=RATE,
    earth_repair_floor=FLOOR,
    max_integrity_per_tick=PER_TICK,
)


def _bot(**kwargs) -> TaobotSimple:
    return TaobotSimple(x=0.0, y=0.0, entity_id=1, repair_laws=LAWS, **kwargs)


def _fill(bot: TaobotSimple, earth: float) -> None:
    """Empty every pool, then put a known amount of Earth in it."""
    for e in ELEMENT_LIST:
        bot.storage[e] = 0.0
    bot.storage[ElementType.EARTH] = earth


def _earth(bot: TaobotSimple) -> float:
    return bot.storage[ElementType.EARTH]


# --- the matrix ------------------------------------------------------------


def test_a_damaged_part_repairs_and_the_earth_is_debited():
    bot = _bot()
    _fill(bot, 20.0)
    bot.legs[0].structural_integrity = 0.5
    before = _earth(bot)

    bot._repair_parts()

    assert bot.legs[0].structural_integrity > 0.5
    assert _earth(bot) < before


def test_no_repair_below_the_earth_floor():
    """A starving bot cannot heal. The floor is what stops repair cannibalising the
    Earth the body needs, and the body is the only organ that can kill."""
    bot = _bot()
    _fill(bot, FLOOR)          # exactly at the floor: nothing is available above it
    bot.legs[0].structural_integrity = 0.5
    before = _earth(bot)

    bot._repair_parts()

    assert bot.legs[0].structural_integrity == pytest.approx(0.5)
    assert _earth(bot) == pytest.approx(before)


def test_a_whole_part_asks_for_nothing():
    bot = _bot()
    _fill(bot, 20.0)
    before = _earth(bot)

    bot._repair_parts()

    assert all(leg.structural_integrity == 1.0 for leg in bot.legs)
    assert _earth(bot) == pytest.approx(before)


def test_repair_stops_exactly_at_one_and_spends_only_what_it_needed():
    """The last sliver of a repair costs the sliver, not a whole tick's allowance."""
    bot = _bot()
    _fill(bot, 20.0)
    sliver = PER_TICK / 4
    bot.legs[0].structural_integrity = 1.0 - sliver
    before = _earth(bot)

    bot._repair_parts()

    assert bot.legs[0].structural_integrity == pytest.approx(1.0)
    assert bot.legs[0].structural_integrity <= 1.0
    assert before - _earth(bot) == pytest.approx(sliver * bot.legs[0].mass() * RATE)


def test_a_destroyed_part_repairs_from_zero_like_any_other_value():
    """0.0 is not terminal. Nothing in the mechanism treats a destroyed part as
    unrecoverable — that it usually stays destroyed is an economic outcome, not a rule."""
    bot = _bot()
    _fill(bot, 20.0)
    bot.legs[0].structural_integrity = 0.0

    bot._repair_parts()

    assert bot.legs[0].structural_integrity == pytest.approx(PER_TICK)


def test_the_per_tick_cap_binds():
    """Without this cap a part rebuilds entirely the moment Earth allows, which is why
    leg integrity sat pinned at 1.0000 and the dip was never observable."""
    bot = _bot()
    _fill(bot, 20.0)
    bot.legs[0].structural_integrity = 0.0

    bot._repair_parts()

    assert bot.legs[0].structural_integrity == pytest.approx(PER_TICK)
    assert bot.legs[0].structural_integrity < 1.0


def test_earth_cost_scales_with_mass():
    """`Δintegrity × mass × rate` — one law plus one per-part trait. The heavier part
    pays proportionally more for the same integrity."""
    light = LegPart(part_id="l", r=1.0, theta=0.0, phi=0.0, max_thrust=1.0,
                    capacity=1.0, drain_max=0.0, mass=1.0)
    heavy = LegPart(part_id="h", r=1.0, theta=0.0, phi=0.0, max_thrust=1.0,
                    capacity=1.0, drain_max=0.0, mass=3.0)
    for part in (light, heavy):
        part.structural_integrity = 0.5

    assert heavy.repair_demand(RATE, PER_TICK) == pytest.approx(
        3.0 * light.repair_demand(RATE, PER_TICK)
    )

    light.apply_repair(light.repair_demand(RATE, PER_TICK), RATE)
    heavy.apply_repair(heavy.repair_demand(RATE, PER_TICK), RATE)

    # Same integrity gained, three times the essence to gain it.
    assert light.last_repair_gain == pytest.approx(heavy.last_repair_gain)
    assert heavy.last_repair_essence == pytest.approx(3.0 * light.last_repair_essence)


def test_mass_is_read_through_the_accessor():
    """`AD-5`: a stored placeholder today, derived from part traits later. The seam has
    to exist from the first commit or the flip touches every caller."""
    leg = LegPart(part_id="x", r=1.0, theta=0.0, phi=0.0, max_thrust=1.0,
                  capacity=1.0, drain_max=0.0, mass=2.5)
    assert callable(leg.mass)
    assert leg.mass() == pytest.approx(2.5)


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_a_part_refuses_an_unusable_mass(bad):
    """Mass divides the repair law, so zero repairs infinitely, negative repairs
    backwards, and NaN propagates through the pro-rata split unnoticed."""
    with pytest.raises(ValueError, match="mass"):
        LegPart(part_id="x", r=1.0, theta=0.0, phi=0.0, max_thrust=1.0,
                capacity=1.0, drain_max=0.0, mass=bad)


# --- pro-rata (AD-3) -------------------------------------------------------


def test_scarce_earth_splits_pro_rata_and_each_part_repairs_in_proportion():
    """`AD-3`: not equal shares. A part granted 60% of its request repairs 60% as much,
    because `apply_repair` is the exact inverse of `repair_demand`."""
    bot = _bot()
    bot.legs[0].structural_integrity = 1.0 - PER_TICK          # full allowance
    bot.legs[1].structural_integrity = 1.0 - PER_TICK / 3      # a third of it

    full_demand = sum(leg.repair_demand(RATE, PER_TICK) for leg in bot.legs)
    _fill(bot, FLOOR + full_demand / 2)                        # only half to go round

    bot._repair_parts()

    gains = [leg.last_repair_gain for leg in bot.legs]
    assert gains[0] == pytest.approx(3.0 * gains[1], rel=1e-9)
    assert sum(gains) == pytest.approx(
        (PER_TICK + PER_TICK / 3) / 2, rel=1e-9
    )


def test_the_floor_is_reserved_from_the_split_not_just_from_the_decision():
    """The floor is not a gate that opens and then lets everything through: Earth below
    it stays untouchable even mid-repair."""
    bot = _bot()
    _fill(bot, FLOOR + 0.001)
    bot.legs[0].structural_integrity = 0.0

    bot._repair_parts()

    assert _earth(bot) >= FLOOR - 1e-12


# --- the crossing (chi tier -> part tier) ----------------------------------


def test_the_crossing_balances_per_part():
    """The accounting boundary Story 1.0d's essence invariant cannot see.

    That invariant watches transfers *within* the chi tier — storage to storage. Repair
    moves value out of chi and into integrity, a different unit, so essence could vanish
    with nothing gained, or integrity appear with nothing debited, and every one of the
    six invariants would stay green. Asserted here on observed storage deltas, in both
    directions."""
    bot = _bot()
    _fill(bot, 20.0)
    for leg, integrity in zip(bot.legs, (0.4, 0.7)):
        leg.structural_integrity = integrity
    before = _earth(bot)

    bot._repair_parts()

    debited = before - _earth(bot)
    per_part = [leg.last_repair_gain * leg.mass() * RATE for leg in bot.legs]

    # No integrity appeared without a debit...
    assert debited == pytest.approx(sum(per_part), rel=1e-9)
    # ...and no essence vanished without a gain.
    assert debited == pytest.approx(
        sum(leg.last_repair_essence for leg in bot.legs), rel=1e-9
    )
    assert all(gain > 0.0 for gain in (leg.last_repair_gain for leg in bot.legs))


def test_the_crossing_balances_under_a_partial_grant():
    """The half that a happy-path assertion misses: when the grant is short, the debit
    and the gain must still agree with each other, not with what was asked for."""
    bot = _bot()
    bot.legs[0].structural_integrity = 0.0
    bot.legs[1].structural_integrity = 0.0
    demand = sum(leg.repair_demand(RATE, PER_TICK) for leg in bot.legs)
    _fill(bot, FLOOR + demand / 4)          # a quarter of what was asked
    before = _earth(bot)

    bot._repair_parts()

    debited = before - _earth(bot)
    gained_cost = sum(leg.last_repair_gain * leg.mass() * RATE for leg in bot.legs)
    assert debited == pytest.approx(gained_cost, rel=1e-9)
    assert debited == pytest.approx(demand / 4, rel=1e-9)


def test_repair_this_tick_reports_what_the_parts_actually_did():
    """The CSV column, the panel label and any test read one number, from the parts."""
    bot = _bot()
    _fill(bot, 20.0)
    bot.legs[0].structural_integrity = 0.5

    bot._repair_parts()
    spent, gained = bot.repair_this_tick()

    assert spent == pytest.approx(sum(leg.last_repair_essence for leg in bot.legs))
    assert gained == pytest.approx(sum(leg.last_repair_gain for leg in bot.legs))
    assert spent == pytest.approx(gained * bot.legs[0].mass() * RATE)


def test_the_repair_record_is_cleared_each_tick():
    """A record of the tick just resolved, not an accumulator — observers read and
    reset nothing, so the record has to be owned by the pass that writes it."""
    bot = _bot()
    _fill(bot, 20.0)
    bot.legs[0].structural_integrity = 0.5
    bot._repair_parts()
    assert bot.legs[0].last_repair_gain > 0.0

    _fill(bot, 20.0)
    bot.legs[0].structural_integrity = 1.0
    bot._repair_parts()
    assert bot.legs[0].last_repair_gain == 0.0
    assert bot.legs[0].last_repair_essence == 0.0


# --- the caller, not just the mechanism ------------------------------------
#
# Everything above calls `_repair_parts()` directly, which is exactly the gap this
# project keeps rediscovering: a correct mechanism the tick loop never runs. Deleting
# `self._repair_parts()` from `TaobotSimple.tick` left the whole suite green until
# these existed.


def test_repair_actually_happens_when_a_bot_ticks(default_config):
    """Through `world.tick()`, not through the pass. If repair is not wired into the
    tick — or is wired in after `_metabolize`, where the Earth floor stops protecting
    the body — this is what notices."""
    from world import World

    world = World(default_config, seed=20260817)
    world.initialize()
    bot = world.spawn_taobot(x=40.0, y=30.0)
    bot.repair_laws = LAWS
    for part in bot.body_parts:
        part.structural_integrity = 0.5
    for e in ELEMENT_LIST:
        bot.storage[e] = bot.storage_capacity[e]
    before = min(part.structural_integrity for part in bot.body_parts)

    world.tick()

    assert min(part.structural_integrity for part in bot.body_parts) > before


def test_a_world_hands_its_own_repair_laws_to_the_bots_it_spawns(default_config):
    """A world tuned with a different rate must not quietly run the shipped physics."""
    from dataclasses import replace as _replace

    from world import World

    custom = RepairLaws(
        earth_per_integrity_mass=7.0, earth_repair_floor=1.0, max_integrity_per_tick=0.05
    )
    world = World(_replace(default_config, repair=custom), seed=1)
    world.initialize()
    bot = world.spawn_taobot(x=1.0, y=1.0)

    assert bot.repair_laws == custom


def test_the_shipped_laws_are_the_values_the_derivation_recorded():
    """A second place the numbers appear, deliberately.

    `configs/laws.json` can be edited in one character to `max_integrity_per_tick: 1.0`,
    which restores the regime this story exists to escape — a part rebuilding its whole
    deficit in one tick, integrity pinned at 1.0, nothing observable — and
    `RepairLaws.__post_init__` declines to bound it above on purpose. So the shipped
    values are pinned here, and changing them means re-running
    `tools/derive_repair_laws.py` and updating the `_repair_note` beside them."""
    from chi import default_repair_laws

    laws = default_repair_laws()
    assert laws.earth_per_integrity_mass == pytest.approx(4.0)
    assert laws.earth_repair_floor == pytest.approx(2.0)
    assert laws.max_integrity_per_tick == pytest.approx(0.002)


def test_the_derivation_is_recorded_beside_the_repair_constants():
    """"Derived, never chosen" is an epic-level rule — loosely derived here, by
    direction, but the reasoning and the script still have to survive in the repo."""
    import json
    from pathlib import Path

    raw = json.loads((Path(__file__).resolve().parent.parent / "configs" / "laws.json").read_text())
    note = " ".join(raw["_repair_note"])
    assert "max_integrity_per_tick" in note and "earth_per_integrity_mass" in note
    assert "derive_repair_laws" in note, "the note must name the script that regenerates it"


def test_a_body_spec_carries_mass_into_the_part():
    """The seam a genome will use. It reads correctly today only because the shipped
    spec's mass happens to equal the default, so ignoring the spec looks identical."""
    from body_factory import BodyFactory

    parts = BodyFactory.make_parts(
        [{"type": "leg", "r": 1.0, "theta": 0.0, "phi": 0.0, "max_thrust": 1.0,
          "capacity": 1.0, "drain_max": 0.01, "mass": 2.75}],
        run_seed=1,
        owner_id=1,
    )
    assert parts[0].mass() == pytest.approx(2.75)
