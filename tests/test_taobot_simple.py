import pytest

from common import ElementType
from taobot_simple import (
    CYCLE_EFFICIENCY,
    CYCLE_RATE,
    FIRE_LOCKOUT_THRESHOLD,
    ORGAN_DEGRADE_RATE,
    ORGAN_MAX,
    ORGAN_REGEN_RATE,
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
        assert taobot.organs[e] == pytest.approx(ORGAN_MAX)


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


def test_taobot_flee_triggered_at_low_wood(world, taobot):
    taobot.organs[ElementType.WOOD] = taobot.flee_wood_threshold * 0.5
    resources, hazards = taobot._sense(world)
    taobot._decide(resources, hazards, world)
    assert taobot.behavior_state == "fleeing"


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
    t.organs[ElementType.FIRE] = FIRE_LOCKOUT_THRESHOLD * 0.5
    # Put a resource nearby that would normally trigger seeking
    world.spawn_resource(x=41.0, y=30.0, element_type=ElementType.WOOD)
    # With near-zero Fire, sensing range is effectively zero — no resources visible
    resources, hazards = t._sense(world)
    t._decide(resources, hazards, world)
    assert t.behavior_state == "searching"


def test_taobot_organ_degrades_when_storage_empty(taobot):
    taobot.storage[ElementType.FIRE] = 0.0
    fire_before = taobot.organs[ElementType.FIRE]
    taobot._drain_organ(ElementType.FIRE, 0.015)
    assert taobot.organs[ElementType.FIRE] == pytest.approx(fire_before - ORGAN_DEGRADE_RATE)


def test_taobot_organ_regens_when_surplus(taobot):
    elem = ElementType.FIRE
    taobot.organs[elem] = 80.0
    taobot.storage[elem] = taobot.storage_capacity[elem]  # full storage
    fire_before = taobot.organs[elem]
    taobot._drain_organ(elem, 0.015)
    assert taobot.organs[elem] == pytest.approx(fire_before + ORGAN_REGEN_RATE)


def test_taobot_organ_no_regen_below_threshold(taobot):
    elem = ElementType.FIRE
    taobot.organs[elem] = 80.0
    # Storage just below regen threshold
    taobot.storage[elem] = REGEN_STORAGE_THRESHOLD * taobot.storage_capacity[elem] * 0.9
    drain = 0.001  # tiny drain so storage isn't zeroed
    fire_before = taobot.organs[elem]
    taobot._drain_organ(elem, drain)
    assert taobot.organs[elem] == pytest.approx(fire_before)


def test_taobot_water_drain_zero_when_immobile(taobot):
    taobot.organs[ElementType.WATER] = 0.0
    taobot.storage[ElementType.WATER] = 10.0
    storage_before = taobot.storage[ElementType.WATER]
    taobot._metabolize()
    # Water organ is 0 → speed fraction is 0 → Water drain is 0
    assert taobot.storage[ElementType.WATER] == pytest.approx(storage_before)


def test_taobot_earth_multiplier_increases_drain(taobot):
    taobot.organs[ElementType.EARTH] = 0.0  # worst-case: double drain
    taobot.storage[ElementType.FIRE] = 10.0
    taobot.storage[ElementType.EARTH] = 10.0
    taobot.storage[ElementType.WATER] = 10.0
    fire_before = taobot.storage[ElementType.FIRE]
    taobot._metabolize()
    # Earth=0 → earth_mult=2.0; Fire drain should be 0.015 * 2 = 0.030
    assert taobot.storage[ElementType.FIRE] == pytest.approx(fire_before - 0.030, abs=1e-6)


def test_taobot_record_damage_routes_through_metal(taobot):
    taobot.organs[ElementType.METAL] = ORGAN_MAX  # full armor — nothing reaches Wood
    wood_before = taobot.organs[ElementType.WOOD]
    taobot.record_damage(10.0)
    assert taobot.organs[ElementType.WOOD] == pytest.approx(wood_before)
    assert taobot.damage_taken_total == pytest.approx(10.0)


def test_taobot_record_damage_no_metal(taobot):
    taobot.organs[ElementType.METAL] = 0.0  # no armor — full damage to Wood
    wood_before = taobot.organs[ElementType.WOOD]
    taobot.record_damage(5.0)
    assert taobot.organs[ElementType.WOOD] == pytest.approx(wood_before - 5.0)
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
    t._cycle_elements()
    assert t.storage[ElementType.WATER] < 10.0
    assert t.storage[ElementType.WOOD] > 0.0


def test_cycle_is_lossy():
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    t.storage[ElementType.WATER] = 10.0
    t.storage[ElementType.WOOD] = 0.0
    t._cycle_elements()
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
    t._cycle_elements()
    assert t.storage[ElementType.WATER] == pytest.approx(water_before)


def test_cycle_zero_source_no_transfer():
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    t.storage[ElementType.WATER] = 0.0
    t.storage[ElementType.WOOD] = 0.0
    t._cycle_elements()
    assert t.storage[ElementType.WOOD] == pytest.approx(0.0)


def test_taobot_specialist_archetype():
    from taobot_simple import ARCHETYPES
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1, params=ARCHETYPES["specialist"])
    fire_aff = t.affinity[ElementType.FIRE]
    for e, a in t.affinity.items():
        if e != ElementType.FIRE:
            assert fire_aff > a
