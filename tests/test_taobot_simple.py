import pytest

from chi import CYCLE_EFFICIENCY, CYCLE_RATE
from common import ElementType
from taobot_simple import (
    DERIVED_ORGANS,
    EARTH_CRISIS_DRAIN,
    EARTH_CRISIS_STORAGE_FRACTION,
    FIRE_LOCKOUT_THRESHOLD,
    ORGAN_DEGRADE_RATE,
    ORGAN_MAX,
    ORGAN_REGEN_RATE,
    ORGAN_STORAGE_DRAIN,
    REGEN_STORAGE_THRESHOLD,
    TaobotSimple,
)
from world import World


@pytest.fixture
def world(default_config) -> World:
    return World(default_config)


@pytest.fixture
def taobot(world) -> TaobotSimple:
    return world.spawn_taobot(x=40.0, y=30.0)


def test_taobot_default_organs(taobot):
    for e in ElementType:
        assert taobot.organ(e) == pytest.approx(ORGAN_MAX)


def test_taobot_affinity_normalizes():
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    total = sum(t.affinity.values())
    assert total == pytest.approx(1.0)


def test_taobot_fitness_score_zero_age():
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    assert t.fitness_score == pytest.approx(0.0)


def test_taobot_fitness_score():
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    t.resources_collected = 10.0
    t.age_ticks = 100
    assert t.fitness_score == pytest.approx(0.1)


def test_taobot_flee_triggered_at_low_earth(world, taobot):
    taobot._organs[ElementType.EARTH] = taobot.flee_earth_threshold * 0.5
    resources, hazards = taobot._sense(world)
    taobot._decide(resources, hazards, world)
    assert taobot.behavior_state == "fleeing"


def test_taobot_low_wood_does_not_trigger_flee(world, taobot):
    """The flee trigger reads Earth, not Wood. A collapsed transport network is
    not a structural emergency, so it must not put the bot into "fleeing"."""
    taobot._organs[ElementType.WOOD] = 0.0
    taobot._organs[ElementType.EARTH] = ORGAN_MAX
    taobot._decide([], [], world)  # no hazards, so fleeing could only come from the organ test
    assert taobot.behavior_state != "fleeing"


def test_taobot_searches_when_nothing_visible(world):
    t = world.spawn_taobot(x=40.0, y=30.0)
    t._decide([], [], world)
    assert t.behavior_state == "searching"


def test_taobot_seeks_nearest_resource(world):
    t = world.spawn_taobot(x=40.0, y=30.0)
    r = world.spawn_resource(x=42.0, y=30.0, element_type=ElementType.WOOD)
    resources, hazards = t._sense(world)
    t._decide(resources, hazards, world)
    assert t.behavior_state == "seeking"
    assert t.target_entity_id == r.entity_id


def test_taobot_fire_lockout_forces_searching(world):
    t = world.spawn_taobot(x=40.0, y=30.0)
    t._organs[ElementType.FIRE] = FIRE_LOCKOUT_THRESHOLD * 0.5
    # Put a resource nearby that would normally trigger seeking
    world.spawn_resource(x=41.0, y=30.0, element_type=ElementType.WOOD)
    # With near-zero Fire, sensing range is effectively zero — no resources visible
    resources, hazards = t._sense(world)
    t._decide(resources, hazards, world)
    assert t.behavior_state == "searching"


def test_taobot_organ_degrades_when_storage_empty(taobot):
    taobot.storage[ElementType.FIRE] = 0.0
    fire_before = taobot.organ(ElementType.FIRE)
    taobot._drain_organ(ElementType.FIRE, 0.015)
    assert taobot.organ(ElementType.FIRE) == pytest.approx(fire_before - ORGAN_DEGRADE_RATE)


def test_taobot_organ_regens_when_surplus(taobot):
    elem = ElementType.FIRE
    taobot._organs[elem] = 80.0
    taobot.storage[elem] = taobot.storage_capacity[elem]  # full storage
    fire_before = taobot.organ(elem)
    taobot._drain_organ(elem, 0.015)
    assert taobot.organ(elem) == pytest.approx(fire_before + ORGAN_REGEN_RATE)


def test_taobot_organ_no_regen_below_threshold(taobot):
    elem = ElementType.FIRE
    taobot._organs[elem] = 80.0
    # Storage just below regen threshold
    taobot.storage[elem] = REGEN_STORAGE_THRESHOLD * taobot.storage_capacity[elem] * 0.9
    drain = 0.001  # tiny drain so storage isn't zeroed
    fire_before = taobot.organ(elem)
    taobot._drain_organ(elem, drain)
    assert taobot.organ(elem) == pytest.approx(fire_before)


def test_taobot_metabolize_does_not_drain_water_storage(taobot):
    """`_metabolize` never touches Water storage — the legs do, in `_tick_body_parts`.

    The organ can no longer be set up at 0 to prove this (Water is derived), but the
    claim never depended on the organ value: there is no Water branch in `_metabolize`
    at all, so the storage is untouched at any leg integrity."""
    taobot.storage[ElementType.WATER] = 10.0
    storage_before = taobot.storage[ElementType.WATER]
    taobot._metabolize()
    assert taobot.storage[ElementType.WATER] == pytest.approx(storage_before)
    assert "WATER" not in ORGAN_STORAGE_DRAIN


# --- Derived organs (AD-5) ---------------------------------------------------


def test_water_organ_full_when_legs_healthy(taobot):
    assert all(leg.structural_integrity == pytest.approx(1.0) for leg in taobot.legs)
    assert taobot.organ(ElementType.WATER) == pytest.approx(ORGAN_MAX)


def test_water_organ_is_the_mean_of_leg_integrity(taobot):
    assert len(taobot.legs) == 2
    taobot.legs[0].structural_integrity = 1.0
    taobot.legs[1].structural_integrity = 0.5
    assert taobot.organ(ElementType.WATER) == pytest.approx(75.0)


def test_water_organ_zero_when_legs_starved(taobot):
    for leg in taobot.legs:
        leg.structural_integrity = 0.0
    assert taobot.organ(ElementType.WATER) == pytest.approx(0.0)


def test_water_organ_zero_with_no_legs():
    """AD-5: an organ system with no parts reads 0.0 — absent and destroyed are
    deliberately indistinguishable, so a legless body plan cannot get locomotion free."""
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1, params={"body": []})
    assert t.legs == []
    assert t.organ(ElementType.WATER) == pytest.approx(0.0)


def test_water_organ_tracks_leg_degradation(taobot):
    """The organ falls in step with the legs rather than holding at a constant."""
    before = taobot.organ(ElementType.WATER)
    taobot.legs[0].structural_integrity -= 0.4
    after = taobot.organ(ElementType.WATER)
    assert after < before
    assert after == pytest.approx(before - 0.4 / len(taobot.legs) * ORGAN_MAX)


def test_derived_organ_cannot_be_drained(taobot):
    """Writing a derived organ must be impossible, not merely discouraged."""
    with pytest.raises(ValueError, match="derived organ"):
        taobot._drain_organ(ElementType.WATER, 0.012)


def test_derived_organs_have_no_stored_slot(taobot):
    """There is no scalar behind a derived organ to write by accident."""
    assert DERIVED_ORGANS == frozenset({ElementType.WATER})
    for e in ElementType:
        assert (e in taobot._organs) is (e not in DERIVED_ORGANS)


def test_non_derived_organs_are_still_stored_scalars(taobot):
    """Only Water moves this story: the other four still read straight off the store."""
    for e in (ElementType.FIRE, ElementType.WOOD, ElementType.EARTH, ElementType.METAL):
        taobot._organs[e] = 42.0
        assert taobot.organ(e) == pytest.approx(42.0)


def test_derived_organ_clamped_above_range(taobot):
    """`structural_integrity` is specified 0–1 but nothing on BodyPart enforces it.
    Story 1.3 adds repair, which is the first code that could overshoot 1.0; the
    organ range is an invariant regardless of what the parts report."""
    for leg in taobot.legs:
        leg.structural_integrity = 1.5
    assert taobot.organ(ElementType.WATER) == pytest.approx(ORGAN_MAX)


def test_derived_organ_clamped_below_range(taobot):
    for leg in taobot.legs:
        leg.structural_integrity = -0.5
    assert taobot.organ(ElementType.WATER) == pytest.approx(0.0)


def test_every_organ_is_either_derived_or_drained():
    """DERIVED_ORGANS and ORGAN_STORAGE_DRAIN partition the elements.

    An organ derived from parts must not also be funded by a storage drain, and an
    organ that is neither is a vestigial constant — exactly the state the Water organ
    was in before this story. Adding an organ to one collection without removing it
    from the other currently breaks nothing else, so it is pinned here."""
    drained = {ElementType[name] for name in ORGAN_STORAGE_DRAIN}
    assert DERIVED_ORGANS & drained == set(), "an organ cannot be both derived and drained"
    assert DERIVED_ORGANS | drained == set(ElementType), "every organ needs a source"


def test_taobot_wood_multiplier_increases_drain(taobot):
    """Wood at 0 saturates the multiplier at 2.0, and each organ pays its own rate.

    The Earth/Wood rates are asserted here because Story 1.0a moved them with the
    roles: structural upkeep (now Earth) stays cheap, metabolic upkeep (now Wood)
    stays dear. Swapping them back must fail this test."""
    taobot._organs[ElementType.WOOD] = 0.0  # worst-case: double drain
    # Every drained element, and only those — Water has no drain since 1.0b.
    drained = [ElementType[name] for name in ORGAN_STORAGE_DRAIN]
    for e in drained:
        taobot.storage[e] = 10.0  # well above the regen floor, so every drain is paid
    mult = 2.0  # 1.0 + (ORGAN_MAX - 0) / ORGAN_MAX
    before = {e: taobot.storage[e] for e in drained}

    taobot._metabolize()

    for e in drained:
        assert taobot.storage[e] == pytest.approx(
            before[e] - ORGAN_STORAGE_DRAIN[e.name] * mult, abs=1e-6
        ), f"{e.name} did not pay its own drain rate"
    # Structure is cheap to maintain; the transport network is not.
    assert ORGAN_STORAGE_DRAIN["EARTH"] < ORGAN_STORAGE_DRAIN["WOOD"]


def test_taobot_zero_wood_does_not_kill_and_crisis_drains_earth(world, taobot):
    """AD-6: Earth is the only death condition.

    A collapsed Wood organ saturates the drain multiplier and opens the crisis,
    which bleeds the *Earth* organ — but Wood at zero never removes the bot."""
    taobot._organs[ElementType.WOOD] = 0.0
    taobot._organs[ElementType.EARTH] = ORGAN_MAX
    for e in ElementType:
        taobot.storage[e] = 0.0

    # Fund Earth's own upkeep so the only Earth organ loss is the crisis drain.
    # Stay below the regen floor (no regen masking the drain) and below the crisis
    # ceiling (so the crisis actually fires) — both derived, so retuning either
    # constant fails here loudly instead of quietly invalidating the test.
    regen_floor = REGEN_STORAGE_THRESHOLD * taobot.storage_capacity[ElementType.EARTH]
    crisis_ceiling = EARTH_CRISIS_STORAGE_FRACTION * sum(taobot.storage_capacity.values())
    taobot.storage[ElementType.EARTH] = min(regen_floor, crisis_ceiling) / 2.0
    assert taobot.storage[ElementType.EARTH] > ORGAN_STORAGE_DRAIN["EARTH"] * 2.0, (
        "Earth upkeep must be affordable, or starvation degrade masks the crisis drain"
    )
    assert taobot.entity_id in world._taobots  # precondition: the bot is alive to begin with

    taobot._metabolize()

    assert taobot.organ(ElementType.EARTH) == pytest.approx(ORGAN_MAX - EARTH_CRISIS_DRAIN)
    assert taobot.organ(ElementType.WOOD) == pytest.approx(0.0)

    world._check_taobot_deaths()
    assert taobot.entity_id in world._taobots


def test_taobot_record_damage_routes_through_metal(taobot):
    taobot._organs[ElementType.METAL] = ORGAN_MAX  # full armor — nothing reaches Earth
    earth_before = taobot.organ(ElementType.EARTH)
    taobot.record_damage(10.0)
    assert taobot.organ(ElementType.EARTH) == pytest.approx(earth_before)
    assert taobot.damage_taken_total == pytest.approx(10.0)


def test_taobot_record_damage_no_metal(taobot):
    taobot._organs[ElementType.METAL] = 0.0  # no armor — full damage to Earth
    earth_before = taobot.organ(ElementType.EARTH)
    wood_before = taobot.organ(ElementType.WOOD)
    taobot.record_damage(5.0)
    assert taobot.organ(ElementType.EARTH) == pytest.approx(earth_before - 5.0)
    # AD-7: damage targets the body only — the transport network is untouched
    assert taobot.organ(ElementType.WOOD) == pytest.approx(wood_before)
    assert taobot.damage_taken_total == pytest.approx(5.0)
    assert taobot._interval_damage == pytest.approx(5.0)


def test_taobot_reset_interval():
    from common import ElementType as ET

    t = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    t.resources_by_element[ET.WOOD] = 3.0
    t._interval_resources[ET.WOOD] = 3.0
    t.damage_taken_total = 7.0
    t._interval_damage = 7.0
    t.reset_interval()

    assert t._interval_resources[ET.WOOD] == pytest.approx(0.0)
    assert t._interval_damage == pytest.approx(0.0)
    assert t.resources_by_element[ET.WOOD] == pytest.approx(3.0)
    assert t.damage_taken_total == pytest.approx(7.0)


def test_taobot_distance_accumulates(world):
    t = world.spawn_taobot(x=40.0, y=30.0)
    t.behavior_state = "searching"
    t._act(world)
    assert t.distance_moved > 0.0


def test_taobot_get_state_keys(taobot):
    state = taobot.get_state()
    expected_keys = (
        "entity_id", "x", "y", "organs", "behavior_state",
        "storage", "fitness_score", "age_ticks",
    )
    for key in expected_keys:
        assert key in state
    assert "health" not in state


def test_cycle_transfers_storage():
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    t.storage[ElementType.WATER] = 10.0
    t.storage[ElementType.WOOD] = 0.0
    t.chi.convert()
    assert t.storage[ElementType.WATER] < 10.0
    assert t.storage[ElementType.WOOD] > 0.0


def test_cycle_is_lossy():
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    t.storage[ElementType.WATER] = 10.0
    t.storage[ElementType.WOOD] = 0.0
    t.chi.convert()
    water_spent = 10.0 - t.storage[ElementType.WATER]
    wood_gained = t.storage[ElementType.WOOD]
    # spent = CYCLE_RATE × 10; produced = spent × CYCLE_EFFICIENCY
    assert water_spent == pytest.approx(CYCLE_RATE * 10.0, rel=1e-6)
    assert wood_gained == pytest.approx(CYCLE_RATE * 10.0 * CYCLE_EFFICIENCY, rel=1e-6)
    assert wood_gained < water_spent


def test_cycle_respects_capacity():
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    t.storage[ElementType.WATER] = 10.0
    t.storage[ElementType.WOOD] = t.storage_capacity[ElementType.WOOD]  # full
    water_before = t.storage[ElementType.WATER]
    t.chi.convert()
    assert t.storage[ElementType.WATER] == pytest.approx(water_before)


def test_cycle_zero_source_no_transfer():
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    t.storage[ElementType.WATER] = 0.0
    t.storage[ElementType.WOOD] = 0.0
    t.chi.convert()
    assert t.storage[ElementType.WOOD] == pytest.approx(0.0)


def test_taobot_specialist_archetype():
    from taobot_simple import ARCHETYPES
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1, params=ARCHETYPES["specialist"])
    fire_aff = t.affinity[ElementType.FIRE]
    for e, a in t.affinity.items():
        if e != ElementType.FIRE:
            assert fire_aff > a


def test_taobot_survivor_archetype_flee_threshold():
    """`_merge_params` accepts unknown keys, so a stale `flee_wood_threshold` in the
    archetype would silently fall back to the default and cost the survivor its
    defining trait. Pin the key by pinning the value it produces."""
    from taobot_simple import ARCHETYPES
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1, params=ARCHETYPES["survivor"])
    assert t.flee_earth_threshold == pytest.approx(50.0)
    assert t.flee_earth_threshold > TaobotSimple(x=0.0, y=0.0, entity_id=2).flee_earth_threshold
