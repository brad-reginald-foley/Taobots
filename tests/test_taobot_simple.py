import pytest

from common import ElementType
from taobot_simple import TaobotSimple
from world import World


@pytest.fixture
def world(default_config) -> World:
    return World(default_config)


@pytest.fixture
def taobot(world) -> TaobotSimple:
    return world.spawn_taobot(x=40.0, y=30.0)


def test_taobot_default_health(taobot):
    assert taobot.health == pytest.approx(100.0)


def test_taobot_affinity_normalizes():
    # All equal affinities should sum to ~1.0
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


def test_taobot_flee_triggered_at_low_health(world, taobot):
    taobot.health = taobot.max_health * 0.1  # below 0.25 threshold
    resources, hazards = taobot._sense(world)
    taobot._decide(resources, hazards, world)
    assert taobot.behavior_state == "fleeing"


def test_taobot_searches_when_nothing_visible(world):
    # Spawn in empty world (no resources, no hazards)
    t = world.spawn_taobot(x=40.0, y=30.0)
    t._decide([], [], world)
    assert t.behavior_state == "searching"


def test_taobot_seeks_nearest_resource(world):
    t = world.spawn_taobot(x=40.0, y=30.0)
    # Spawn a resource within sensing range
    r = world.spawn_resource(x=42.0, y=30.0, element_type=ElementType.WOOD)
    resources, hazards = t._sense(world)
    t._decide(resources, hazards, world)
    assert t.behavior_state == "seeking"
    assert t.target_entity_id == r.entity_id


def test_taobot_metabolize_depletes_storage(taobot):
    # Fill all storage to cover at least one tick of metabolic costs
    for e in ElementType:
        taobot.storage[e] = taobot.metabolic_rate[e] * 2
    initial_health = taobot.health
    wood_before = taobot.storage[ElementType.WOOD]
    taobot._metabolize()
    assert taobot.storage[ElementType.WOOD] < wood_before
    assert taobot.health == pytest.approx(initial_health)  # no deficit


def test_taobot_metabolize_damages_health_on_deficit(taobot):
    # Empty all storage — health should drop
    for e in ElementType:
        taobot.storage[e] = 0.0
    initial_health = taobot.health
    taobot._metabolize()
    assert taobot.health < initial_health


def test_taobot_get_state_keys(taobot):
    state = taobot.get_state()
    expected_keys = (
        "entity_id", "x", "y", "health", "behavior_state",
        "storage", "fitness_score", "age_ticks",
    )
    for key in expected_keys:
        assert key in state


def test_taobot_specialist_archetype():
    from taobot_simple import ARCHETYPES
    t = TaobotSimple(x=0.0, y=0.0, entity_id=1, params=ARCHETYPES["specialist"])
    # FIRE affinity should be highest
    fire_aff = t.affinity[ElementType.FIRE]
    for e, a in t.affinity.items():
        if e != ElementType.FIRE:
            assert fire_aff > a
