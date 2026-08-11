import json
from pathlib import Path

import pytest

from common import ElementType
from world import SpatialHash, World, WorldConfig

# Resolved from this file, not the working directory: the laws tests below exist to
# prove config loading is CWD-independent, so they must not reintroduce a CWD
# dependency of their own (conftest's `default_config` fixture still has one — 1.0d).
CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"


def _config_dict(**extra) -> dict:
    """A minimal valid world config, with no `chemistry` and no `laws` unless given."""
    weights = {"WOOD": 1.0, "WATER": 1.0, "METAL": 1.0, "FIRE": 1.0, "EARTH": 1.0}
    return {
        "name": "x",
        "world": {"width": 80, "height": 60},
        "resources": {"initial_count": 1, "respawn_delay_ticks": 60,
                      "spawn_weights": dict(weights)},
        "hazards": {"initial_count": 0, "spawn_weights": dict(weights)},
        "taobots": {"initial_count": 1, "target_population": 1},
        **extra,
    }


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data))
    return path


def _shipped_world_configs() -> list[Path]:
    """Every world config in `configs/` — globbed, so a new one is covered by default.

    `laws.json` is excluded: it is the shared law file, not a world."""
    return sorted(p for p in CONFIG_DIR.glob("*.json") if p.name != "laws.json")


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
    dying._organs[ElementType.EARTH] = 0.0

    world._check_taobot_deaths()

    assert dying_id not in world._taobots
    assert len(world.taobots) == default_config.taobots.target_population


def test_world_stats_columns_match_producer_both_ways(default_config):
    """`get_stats()` and `MetricsLogger.COLUMNS` must agree in *both* directions.

    `log_tick` does `{k: stats[k] for k in COLUMNS}`: a column with no producer key
    raises, but a producer key with no column is silently dropped from the CSV. That
    second, quiet direction is how `mean_organ_metal` went missing for the whole of
    Phase 2. Checking only "every organ is in COLUMNS" cannot catch it."""
    from main import MetricsLogger

    world = World(default_config)
    world.spawn_taobot(x=5.0, y=5.0)
    stats = world.get_stats()

    assert set(stats) == set(MetricsLogger.COLUMNS), (
        f"produced-but-not-logged: {sorted(set(stats) - set(MetricsLogger.COLUMNS))}; "
        f"logged-but-not-produced: {sorted(set(MetricsLogger.COLUMNS) - set(stats))}"
    )
    expected_organ_keys = {f"mean_organ_{e.name.lower()}" for e in ElementType}
    assert {k for k in stats if k.startswith("mean_organ_")} == expected_organ_keys


def test_world_stats_organ_columns_are_not_interchangeable(default_config):
    """Each organ column must carry *its own* organ's value.

    With a freshly spawned bot every organ reads exactly 100.0, so a test that only
    asserts 100.0 passes even if the Water and Metal arguments are swapped, or if the
    Water entry is hardcoded back to the pre-story constant. Degrading one leg breaks
    the tie: Water is derived and moves, the four stored organs do not."""
    world = World(default_config)
    bot = world.spawn_taobot(x=5.0, y=5.0)
    assert len(bot.legs) == 2, "the derived value below assumes the two-leg default body"

    bot.legs[0].structural_integrity = 0.5  # mean integrity 0.75 → Water organ 75.0
    stats = world.get_stats()

    assert stats["mean_organ_water"] == pytest.approx(75.0)
    for elem in (ElementType.FIRE, ElementType.WOOD, ElementType.EARTH, ElementType.METAL):
        key = f"mean_organ_{elem.name.lower()}"
        assert stats[key] == pytest.approx(100.0), f"{key} moved with a leg — wrong organ"


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
    dying._organs[ElementType.EARTH] = 0.0
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


# ---------------------------------------------------------------------------
# Laws: shared tunables extracted out of the world configs (AD-13)
# ---------------------------------------------------------------------------

def test_laws_supply_chemistry_when_the_config_omits_it(tmp_path):
    """A config with no `chemistry` block inherits the law rather than failing."""
    _write(tmp_path / "laws.json", {"chemistry": {"degrade_rate": 0.007}})
    p = _write(tmp_path / "w.json", _config_dict(laws="laws.json"))

    assert WorldConfig.from_json(p).chemistry.degrade_rate == pytest.approx(0.007)


def test_laws_are_overridden_key_by_key_not_block_by_block(tmp_path):
    """A declared block overrides the keys it names and inherits the rest of that block.

    While every law block holds a single key, a real deep merge and a shallow
    `{**laws, **config}` are indistinguishable — swap one for the other and the suite
    stays green. The unrestated `respawn_delay_ticks` below is what tells them apart,
    and it is exactly the shape Story 1.3 lands: `laws.json` gains a second entry, and
    the first config to partially override a block silently drops the rest of it."""
    weights = {"WOOD": 1.0, "WATER": 1.0, "METAL": 1.0, "FIRE": 1.0, "EARTH": 1.0}
    _write(tmp_path / "laws.json", {
        "chemistry": {"degrade_rate": 0.001},
        "resources": {"respawn_delay_ticks": 999, "spawn_weights": weights},
    })
    cfg = _config_dict(laws="laws.json", chemistry={"degrade_rate": 0.002})
    cfg["resources"]["initial_count"] = 5      # stated locally — the override
    del cfg["resources"]["respawn_delay_ticks"]  # left unstated — must be inherited
    p = _write(tmp_path / "w.json", cfg)

    loaded = WorldConfig.from_json(p)

    assert loaded.chemistry.degrade_rate == pytest.approx(0.002), "declared value must win"
    assert loaded.resources.initial_count == 5, "declared value must win"
    assert loaded.resources.respawn_delay_ticks == 999, (
        "a key the config left unstated was dropped — the merge is shallow, so the "
        "rest of a partially overridden law block is being discarded"
    )


def test_laws_missing_file_raises_naming_the_resolved_path(tmp_path):
    """The error must name the path that was actually looked for, not the key."""
    p = _write(tmp_path / "w.json", _config_dict(laws="nope.json"))

    with pytest.raises(ValueError, match=r"laws file not found") as excinfo:
        WorldConfig.from_json(p)
    assert str(tmp_path / "nope.json") in str(excinfo.value)


def test_laws_resolve_beside_the_config_not_the_working_directory(tmp_path, monkeypatch):
    """Same config, two working directories, same result.

    The laws path is resolved against the config's own directory. Resolving it
    against the CWD would make `pytest` from the repo root and `pytest` from
    anywhere else load different worlds — the failure mode `tests/conftest.py`
    still demonstrates for the config path itself."""
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    _write(cfg_dir / "laws.json", {"chemistry": {"degrade_rate": 0.005}})
    p = _write(cfg_dir / "w.json", _config_dict(laws="laws.json"))

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    monkeypatch.chdir(tmp_path)
    from_here = WorldConfig.from_json(p)
    monkeypatch.chdir(elsewhere)
    from_there = WorldConfig.from_json(p)

    assert from_here.chemistry.degrade_rate == pytest.approx(0.005)
    assert from_there.chemistry.degrade_rate == from_here.chemistry.degrade_rate


def test_laws_tolerate_keys_the_loader_does_not_model(tmp_path):
    """Forward compatibility: Story 1.3 adds the Earth-per-integrity rate to
    `laws.json` and must not have to touch the loader to do it."""
    _write(tmp_path / "laws.json", {
        "chemistry": {"degrade_rate": 0.001, "future_rate": 0.5},
        "repair": {"earth_per_integrity": 4.0},
        "_note": "laws are shared by all worlds",
    })
    p = _write(tmp_path / "w.json", _config_dict(laws="laws.json"))

    assert WorldConfig.from_json(p).chemistry.degrade_rate == pytest.approx(0.001)


@pytest.mark.parametrize("bad", ["/etc/passwd", "../laws.json", "sub/../../laws.json"])
def test_laws_path_must_stay_inside_the_configs_directory(tmp_path, bad):
    """`Path("configs") / "/etc/x"` is `/etc/x` — an absolute name silently discards the
    config's directory, which is the whole guarantee the `laws` key is documented on."""
    p = _write(tmp_path / "w.json", _config_dict(laws=bad))

    with pytest.raises(ValueError, match=r"resolve inside the config's own directory"):
        WorldConfig.from_json(p)


@pytest.mark.parametrize("bad", [None, "", "   ", 42, ["laws.json"], {"a": 1}])
def test_laws_value_must_be_a_non_empty_filename(tmp_path, bad):
    """Anything but a filename is malformed, including `null`.

    Stringifying would turn `["laws.json"]` into a nonsense path and report it as a
    missing file. `null` is malformed rather than "no laws": omitting the key is how
    a config says that, and the error says so."""
    p = _write(tmp_path / "w.json", _config_dict(laws=bad))

    with pytest.raises(ValueError, match=r"'laws' must be a non-empty filename") as excinfo:
        WorldConfig.from_json(p)
    assert "omit the 'laws' key" in str(excinfo.value)


def test_laws_path_naming_a_directory_says_so(tmp_path):
    """"not found" would be a lie when the path exists."""
    (tmp_path / "laws.json").mkdir()
    p = _write(tmp_path / "w.json", _config_dict(laws="laws.json"))

    with pytest.raises(ValueError, match=r"laws path is not a file"):
        WorldConfig.from_json(p)


def test_laws_syntax_error_names_the_laws_file_not_the_config(tmp_path):
    """A typo in the shared law must not be reported against whichever world loaded it."""
    (tmp_path / "laws.json").write_text('{"chemistry": {')
    p = _write(tmp_path / "w.json", _config_dict(laws="laws.json"))

    with pytest.raises(ValueError, match=r"laws file is not valid JSON") as excinfo:
        WorldConfig.from_json(p)
    assert str(tmp_path / "laws.json") in str(excinfo.value)
    assert str(p) not in str(excinfo.value)


def test_laws_file_must_contain_an_object(tmp_path):
    (tmp_path / "laws.json").write_text("[1, 2]")
    p = _write(tmp_path / "w.json", _config_dict(laws="laws.json"))

    with pytest.raises(ValueError, match=r"laws file must contain a JSON object"):
        WorldConfig.from_json(p)


def test_laws_files_do_not_chain(tmp_path):
    """Silently ignoring a `laws` key inside `laws.json` would let someone believe
    chaining works and then wonder why the second file never took effect."""
    _write(tmp_path / "laws.json", {
        "laws": "more_laws.json", "chemistry": {"degrade_rate": 0.001},
    })
    _write(tmp_path / "more_laws.json", {"chemistry": {"degrade_rate": 0.009}})
    p = _write(tmp_path / "w.json", _config_dict(laws="laws.json"))

    with pytest.raises(ValueError, match=r"laws files do not chain"):
        WorldConfig.from_json(p)


def test_laws_config_with_neither_chemistry_nor_a_laws_key_raises(tmp_path):
    """Dropping `chemistry` from the required-key tuple must not make it optional.

    Without the explicit guard the loader reaches `data["chemistry"]` and raises a
    bare `KeyError`, which is not the documented contract — and the message would
    not tell the author that inheriting from a laws file is the other way to satisfy
    it. No default is invented here on purpose: that would re-create the duplicated
    constant this story exists to remove."""
    p = _write(tmp_path / "w.json", _config_dict())  # no `chemistry`, no `laws`

    with pytest.raises(ValueError, match=r"missing required key: 'chemistry'") as excinfo:
        WorldConfig.from_json(p)
    assert "laws" in str(excinfo.value), "the error must name the other way to supply it"


def test_laws_every_shipped_config_opts_in():
    """Every world config must declare `laws`, including one that overrides a law.

    `fire_arena` declares its own `chemistry`, so it loads correctly with or without
    the `laws` key today — and would quietly stop inheriting *future* laws while the
    other worlds got them. Globbed rather than listed so a fourth config is covered
    the day it lands."""
    configs = _shipped_world_configs()
    assert len(configs) >= 3, f"expected the shipped worlds, found {[p.name for p in configs]}"

    for p in configs:
        raw = json.loads(p.read_text())
        assert raw.get("laws") == "laws.json", (
            f"{p.name} does not opt in to configs/laws.json, so it will miss laws added later"
        )


def test_laws_shipped_configs_inherit_or_deliberately_override(tmp_path, monkeypatch):
    """The one duplicated law now lives in one place — except where a config says otherwise.

    Run from a foreign working directory so this doubles as the CWD guard for the
    real `configs/` tree, not just for synthetic fixtures."""
    monkeypatch.chdir(tmp_path)
    law = json.loads((CONFIG_DIR / "laws.json").read_text())["chemistry"]["degrade_rate"]

    overriders = []
    for p in _shipped_world_configs():
        raw = json.loads(p.read_text())
        loaded = WorldConfig.from_json(p)

        if "chemistry" not in raw:
            assert loaded.chemistry.degrade_rate == pytest.approx(law), f"{p.name} lost the law"
            continue

        overriders.append(p.name)
        note = raw["chemistry"].get("_override")
        assert note, (
            f"{p.name} keeps its own chemistry block with no `_override` note saying "
            f"that is deliberate — indistinguishable from a leftover duplicate"
        )
        assert loaded.chemistry.degrade_rate != pytest.approx(law), (
            f"{p.name} declares a deliberate override that equals the law ({law}); "
            f"the override is vacuous and should be deleted so it inherits instead"
        )

    assert overriders == ["fire_arena.json"], (
        f"only the deliberately harsher arena may override the law, got {overriders}"
    )


def test_workshop_density_matches_default_world():
    """Regression guard for AD-14: the workshop is a microscope, not a different world.

    Asserted as a property of the two configs rather than against literals, so it
    keeps holding when either world is retuned — and fails the moment they drift
    apart again. Size and population are permitted to differ and are not checked."""
    default = WorldConfig.from_json(CONFIG_DIR / "default_world.json")
    workshop = WorldConfig.from_json(CONFIG_DIR / "workshop.json")

    default_area = default.width * default.height
    workshop_area = workshop.width * workshop.height

    for label, default_n, workshop_n in (
        ("resources", default.resources.initial_count, workshop.resources.initial_count),
        ("hazards", default.hazards.initial_count, workshop.hazards.initial_count),
    ):
        target = default_n / default_area * workshop_area
        assert abs(workshop_n - target) <= 1.0, (
            f"workshop {label} density {workshop_n / workshop_area:.5f}/u^2 diverges from "
            f"default_world's {default_n / default_area:.5f}/u^2 "
            f"(workshop should hold ~{target:.2f}, holds {workshop_n})"
        )

    assert workshop.resources.respawn_delay_ticks == default.resources.respawn_delay_ticks

    # Clustering is part of "the rates a bot experiences", not a cosmetic detail: a bot
    # among clumped resources meets feast and famine where an evenly scattered arena gives
    # a steady trickle. Global density can match while the local rate does not, which is
    # exactly the transfer failure AD-14 exists to prevent.
    for label, default_cfg, workshop_cfg in (
        ("resources", default.resources, workshop.resources),
        ("hazards", default.hazards, workshop.hazards),
    ):
        assert workshop_cfg.cluster_affinity == default_cfg.cluster_affinity, (
            f"workshop {label} cluster_affinity diverges from default_world's; "
            f"align it or record the divergence in configs/workshop.json per AD-14"
        )
