import json

import pytest

from common import ElementType
from world import SpatialHash, World, WorldConfig


def test_world_config_from_json(default_config):
    assert default_config.name == "default"
    assert default_config.width == 80
    assert default_config.height == 60
    assert default_config.resources.initial_count == 150
    assert default_config.hazards.initial_count == 20
    assert default_config.taobots.initial_count == 20


def test_world_config_weights_normalize(default_config):
    total = sum(default_config.resources.spawn_weights.values())
    assert total == pytest.approx(1.0)
    total_h = sum(default_config.hazards.spawn_weights.values())
    assert total_h == pytest.approx(1.0)


def test_world_config_missing_key(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"name": "x"}')
    with pytest.raises(ValueError, match="missing required key"):
        WorldConfig.from_json(bad)


def test_world_initialize_spawns_entities(small_world):
    assert len(small_world.resources) == 150
    assert len(small_world.hazards) == 20
    assert len(small_world.taobots) == 20


def test_world_query_resources_sorted_by_distance(default_config):
    world = World(default_config)
    world.spawn_resource(x=5.0, y=5.0, element_type=ElementType.WOOD)
    world.spawn_resource(x=2.0, y=5.0, element_type=ElementType.FIRE)
    world.spawn_resource(x=8.0, y=5.0, element_type=ElementType.WATER)

    results = world.query_resources(5.0, 5.0, radius=10.0)
    assert len(results) == 3
    # First result should be the one at (5,5) — distance 0
    assert results[0].x == pytest.approx(5.0)
    assert results[0].y == pytest.approx(5.0)


def test_world_collect_resource_moves_to_dead(default_config):
    world = World(default_config)
    r = world.spawn_resource(x=10.0, y=10.0, element_type=ElementType.METAL)
    eid = r.entity_id

    taobot = world.spawn_taobot(x=10.0, y=10.0)
    world.collect_resource(taobot, r, 10.0)  # deplete fully

    assert eid not in world._resources
    assert eid in world._dead_resources


def test_world_respawn_tick_revives_resource(default_config):
    world = World(default_config)
    r = world.spawn_resource(x=10.0, y=10.0, element_type=ElementType.EARTH)
    eid = r.entity_id
    r.set_respawn_delay(2)

    taobot = world.spawn_taobot(x=10.0, y=10.0)
    world.collect_resource(taobot, r, 10.0)
    assert eid in world._dead_resources

    world._respawn_tick()
    world._respawn_tick()
    assert eid in world._resources
    assert world._resources[eid].is_alive


def test_world_taobot_death_triggers_respawn(default_config):
    world = World(default_config)
    # Pre-fill to target_population - 1 so one death maintains the count
    for _ in range(default_config.taobots.target_population - 1):
        world.spawn_taobot()
    dying = world.spawn_taobot(x=5.0, y=5.0)
    dying_id = dying.entity_id
    dying.organs[ElementType.WOOD] = 0.0

    world._check_taobot_deaths()

    assert dying_id not in world._taobots
    assert len(world.taobots) == default_config.taobots.target_population


def test_spatial_hash_register_and_neighbors():
    sh = SpatialHash(80, 60)
    sh.register(1, 10.0, 10.0)
    sh.register(2, 50.0, 50.0)

    near = sh.neighbors(10.0, 10.0, 5.0, 80, 60)
    assert 1 in near
    assert 2 not in near


def test_spatial_hash_deregister():
    sh = SpatialHash(80, 60)
    sh.register(1, 10.0, 10.0)
    sh.deregister(1)
    near = sh.neighbors(10.0, 10.0, 5.0, 80, 60)
    assert 1 not in near


def test_world_death_callback_fires(default_config):
    world = World(default_config)
    for _ in range(default_config.taobots.target_population - 1):
        world.spawn_taobot()
    dying = world.spawn_taobot(x=5.0, y=5.0)
    dying_id = dying.entity_id

    fired: list[int] = []
    world.on_taobot_death = lambda t: fired.append(t.entity_id)
    dying.organs[ElementType.WOOD] = 0.0
    world._check_taobot_deaths()

    assert dying_id in fired


def test_spatial_hash_move():
    sh = SpatialHash(80, 60)
    sh.register(1, 10.0, 10.0)
    sh.register(1, 50.0, 50.0)  # move same id
    near_old = sh.neighbors(10.0, 10.0, 5.0, 80, 60)
    near_new = sh.neighbors(50.0, 50.0, 5.0, 80, 60)
    assert 1 not in near_old
    assert 1 in near_new


def test_cluster_affinity_parsed_from_config(default_config):
    assert default_config.resources.cluster_affinity[ElementType.METAL] == pytest.approx(1.5)
    assert default_config.resources.cluster_affinity[ElementType.FIRE] == pytest.approx(0.0)
    assert default_config.hazards.cluster_affinity[ElementType.WATER] == pytest.approx(1.0)


def test_cluster_affinity_defaults_to_zero(tmp_path):
    cfg = {
        "name": "x", "world": {"width": 80, "height": 60},
        "resources": {"initial_count": 1, "respawn_delay_ticks": 60,
                      "spawn_weights": {"WOOD": 1.0, "WATER": 1.0, "METAL": 1.0,
                                        "FIRE": 1.0, "EARTH": 1.0}},
        "hazards": {"initial_count": 0,
                    "spawn_weights": {"WOOD": 1.0, "WATER": 1.0, "METAL": 1.0,
                                      "FIRE": 1.0, "EARTH": 1.0}},
        "taobots": {"initial_count": 1, "target_population": 1},
        "chemistry": {"degrade_rate": 0.001},
    }
    p = tmp_path / "c.json"
    p.write_text(json.dumps(cfg))
    wc = WorldConfig.from_json(p)
    for e in ElementType:
        assert wc.resources.cluster_affinity[e] == pytest.approx(0.0)


def test_spawn_resource_explicit_coords_bypass_clustering(default_config):
    world = World(default_config)
    r = world.spawn_resource(x=10.0, y=20.0, element_type=ElementType.METAL)
    assert r.x == pytest.approx(10.0)
    assert r.y == pytest.approx(20.0)
