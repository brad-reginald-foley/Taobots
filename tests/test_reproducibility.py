"""Phase A of Story 1.0d — the simulation is reproducible by construction (`AD-12`).

Determinism is asserted **between two runs in the same process and environment**, never
against a committed golden file: float summation order and libm differ across
architectures, so a checked-in baseline becomes a permanent false alarm rather than a
regression guard. Nothing here records an expected number; everything compares a run
to another run.
"""

from __future__ import annotations

import ast
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from main import RunLogger, config_fingerprint, git_sha, write_manifest
from rng import derive_stream
from taobot_simple import ARCHETYPES, TaobotSimple
from tests.state_snapshot import world_state
from world import World, WorldConfig

# Resolved from this file, never the working directory: several tests below chdir into
# a tmp_path so the run's `logs/` lands there, and must still find the real configs.
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "configs"

SEED_A = 42
SEED_B = 43


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(config: WorldConfig, seed: int, ticks: int) -> World:
    world = World(config, seed=seed)
    world.initialize()
    for _ in range(ticks):
        world.tick()
    return world


# ---------------------------------------------------------------------------
# Same seed → identical state and identical logs
# ---------------------------------------------------------------------------

def test_same_seed_same_ticks_produces_identical_state(default_config):
    """Matrix row 1. The headline guarantee the whole story exists for."""
    a = _run(default_config, SEED_A, ticks=200)
    b = _run(copy.deepcopy(default_config), SEED_A, ticks=200)
    assert world_state(a) == world_state(b)


def test_same_seed_produces_identical_logs(default_config, monkeypatch, tmp_path):
    """Identical *state* is not enough — the logs are what a run is judged from, and
    the focal picker used to draw from the simulation's own stream."""
    def run_logged(dirname: str, seed: int) -> tuple[bytes, bytes]:
        run_dir = tmp_path / dirname
        run_dir.mkdir()
        monkeypatch.chdir(run_dir)
        config = WorldConfig.from_json(CONFIG_DIR / "default_world.json")
        world = World(config, seed=seed)
        world.initialize()
        logger = RunLogger(config.name, rng=derive_stream(world.seed, "observer", "focal"))
        world.on_taobot_death = lambda t: logger.on_death(t, world.tick_count)
        for _ in range(150):
            world.tick()
            logger.on_tick(world)
        logger.close()
        logs = run_dir / "logs"
        return (
            (logs / f"{config.name}_focal.csv").read_bytes(),
            (logs / f"{config.name}_deaths.csv").read_bytes(),
        )

    focal_a, deaths_a = run_logged("a", SEED_A)
    focal_b, deaths_b = run_logged("b", SEED_A)
    assert focal_a == focal_b
    assert deaths_a == deaths_b
    # A vacuous pass would be two empty files.
    assert len(focal_a.splitlines()) > 1


def test_different_seed_diverges(default_config):
    """Matrix row 2. Determinism that ignored the seed would also pass row 1."""
    a = _run(default_config, SEED_A, ticks=200)
    b = _run(copy.deepcopy(default_config), SEED_B, ticks=200)
    assert world_state(a) != world_state(b)


def test_world_generates_and_exposes_a_seed_when_none_is_given(default_config):
    """Matrix row 7, at the world level: there is no unseeded mode to forget about."""
    a = World(default_config)
    b = World(copy.deepcopy(default_config))
    assert isinstance(a.seed, int)
    assert a.seed != b.seed, "each unseeded world must get its own seed"
    # And that generated seed is a real handle on the run: replaying it reproduces.
    a.initialize()
    replay = _run(copy.deepcopy(default_config), a.seed, ticks=0)
    assert world_state(replay) == world_state(a)


# ---------------------------------------------------------------------------
# Stream isolation
# ---------------------------------------------------------------------------

def _isolated_config(default_config: WorldConfig) -> WorldConfig:
    """A world with no resources and no hazards, one bot per archetype.

    Taobots never sense each other — `_sense` queries resources and hazards only — so
    with neither present the bots are genuinely independent and any cross-contamination
    can only come from a shared RNG stream. That is precisely what is under test."""
    config = copy.deepcopy(default_config)
    config.resources.initial_count = 0
    config.hazards.initial_count = 0
    config.taobots.initial_count = len(ARCHETYPES)
    config.taobots.target_population = len(ARCHETYPES)
    return config


# 60 ticks: long enough for trajectories to separate, short enough that no bot dies
# (organs fall 1.0/tick from 100 with nothing to eat) and triggers a respawn, which
# would legitimately draw from the world stream and muddy the comparison.
_ISOLATION_TICKS = 60


def _trajectories(config: WorldConfig, seed: int) -> dict[int, tuple]:
    world = World(config, seed=seed)
    world.initialize()
    for _ in range(_ISOLATION_TICKS):
        world.tick()
    return {t.entity_id: (t.archetype, t.x, t.y, t.heading) for t in world.taobots}


def test_an_extra_draw_in_one_archetype_leaves_every_other_bot_untouched(
    default_config, monkeypatch
):
    """Matrix row 3, and the failure `AD-12` exists to prevent.

    Under one global stream, a wanderer taking an extra draw shifts every number every
    later bot receives, so any behaviour change silently invalidates every recorded
    run. With per-entity streams the blast radius is exactly one archetype."""
    config = _isolated_config(default_config)
    baseline = _trajectories(config, SEED_A)

    perturbed_archetype = "wanderer"
    original_decide = TaobotSimple._decide

    def greedy_decide(self, nearby_resources, nearby_hazards, world):
        if self.archetype == perturbed_archetype:
            self._rng.random()  # the extra draw
        return original_decide(self, nearby_resources, nearby_hazards, world)

    monkeypatch.setattr(TaobotSimple, "_decide", greedy_decide)
    perturbed = _trajectories(copy.deepcopy(config), SEED_A)

    assert set(baseline) == set(perturbed), "the population itself must not change"
    changed = {eid for eid in baseline if baseline[eid] != perturbed[eid]}
    moved_archetypes = {baseline[eid][0] for eid in changed}
    assert moved_archetypes == {perturbed_archetype}, (
        f"only {perturbed_archetype} should have moved; these archetypes did: "
        f"{sorted(moved_archetypes)}"
    )
    assert changed, "the extra draw must actually change the perturbed bot"


# ---------------------------------------------------------------------------
# Part ids
# ---------------------------------------------------------------------------

def test_part_ids_reproduce_across_runs_on_the_same_seed(default_config):
    """Matrix row 4. `uuid4()` drew from `os.urandom`, where no seed could reach."""
    a = _run(default_config, SEED_A, ticks=0)
    b = _run(copy.deepcopy(default_config), SEED_A, ticks=0)

    def ids(world):
        return {
            t.entity_id: [p.part_id for p in t.body_parts]
            for t in world.taobots
        }

    assert ids(a) == ids(b)
    assert all(v for v in ids(a).values()), "bots should actually have parts"


def test_part_ids_differ_between_seeds(default_config):
    a = _run(default_config, SEED_A, ticks=0)
    b = _run(copy.deepcopy(default_config), SEED_B, ticks=0)
    assert [p.part_id for t in a.taobots for p in t.body_parts] != [
        p.part_id for t in b.taobots for p in t.body_parts
    ]


def test_make_parts_refuses_to_default_the_owner(default_config):
    """`owner_id` must have no default.

    A default is a single value every direct caller silently shares, which is exactly
    the collision `test_part_ids_are_unique_within_a_run` exists to catch — reachable
    again the moment someone builds parts outside `spawn_taobot`."""
    from body_factory import BodyFactory

    specs = [{"type": "leg", "r": 1.5, "theta": 0.0, "phi": 0.0,
              "max_thrust": 1.0, "capacity": 5.0, "drain_max": 0.01}]
    with pytest.raises(TypeError, match="owner_id"):
        BodyFactory.make_parts(specs, run_seed=1)

    # Supplied explicitly, two owners get different ids from the same spec and seed.
    a = BodyFactory.make_parts(specs, run_seed=1, owner_id=1)
    b = BodyFactory.make_parts(specs, run_seed=1, owner_id=2)
    assert a[0].part_id != b[0].part_id


def test_make_parts_rejects_duplicate_gene_ids():
    """Two genes with one id express to one part id, so the second would overwrite the
    first. Declared ids share a namespace with the positional fallback, and are
    compared as text — so `1` and `"1"` are the same gene."""
    from body_factory import BodyFactory

    def leg(**extra):
        return {"type": "leg", "r": 1.5, "theta": 0.0, "phi": 0.0,
                "max_thrust": 1.0, "capacity": 5.0, "drain_max": 0.01, **extra}

    for specs in (
        [leg(id="a"), leg(id="a")],
        [leg(id=1), leg(id="1")],
        # A declared id colliding with the positional fallback of another spec.
        [leg(), leg(id="leg[0]")],
    ):
        with pytest.raises(ValueError, match="duplicate gene id"):
            BodyFactory.make_parts(specs, run_seed=1, owner_id=1)

    # Distinct ids are fine, and produce distinct part ids.
    parts = BodyFactory.make_parts([leg(id="left"), leg(id="right")],
                                   run_seed=1, owner_id=1)
    assert parts[0].part_id != parts[1].part_id


def test_part_ids_are_unique_within_a_run(default_config):
    """Determinism must not be bought with collisions.

    Every bot shares one body spec, so a derivation over `(run seed, gene id,
    expression index)` alone would hand all twenty of them the same two ids."""
    world = _run(default_config, SEED_A, ticks=0)
    all_ids = [p.part_id for t in world.taobots for p in t.body_parts]
    assert len(all_ids) == len(set(all_ids))
    assert len(all_ids) > 2


# Directories that are not this project's simulation code: tool installs, scratch
# trees, and the test suite itself, which legitimately reaches for the global `random`
# in order to *prove* that doing so breaks determinism.
_NOT_SIMULATION = {".venv", "_bmad", ".claude", "notebooks", "tests", ".git",
                   "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
                   "saves", "logs", "screen_grabs", "docs", ".github"}


def _simulation_modules() -> list[Path]:
    """Every simulation module, at any depth.

    `rglob`, not `glob`: the top-level-only version quietly stopped covering anything
    the moment code moved into a package, while still claiming that a module added
    later was covered by default."""
    return sorted(
        p for p in REPO_ROOT.rglob("*.py")
        if not any(part in _NOT_SIMULATION for part in p.relative_to(REPO_ROOT).parts)
    )


# `random.Random(...)` is the point of the exercise, so only the *draw* functions are
# forbidden — those are the ones that share one process-global stream.
_FORBIDDEN_RANDOM_ATTRS = {
    "uniform", "choice", "choices", "random", "randint", "randrange", "sample",
    "shuffle", "gauss", "normalvariate", "seed", "getrandbits", "triangular",
    "betavariate", "expovariate", "lognormvariate", "paretovariate", "randbytes",
    "vonmisesvariate", "weibullvariate", "gammavariate",
}

# Randomness no seed can reach at all.
_UNSEEDABLE_MODULES = {"secrets", "uuid"}

# `rng.py` is the one place allowed to draw real entropy: generating the run seed is
# its job, it happens once per run, and the result is recorded in the manifest.
_ENTROPY_EXEMPT = {"rng.py"}


def _randomness_offenders(path: Path) -> list[str]:
    """Unseedable or globally-shared randomness in one module.

    Parsed rather than grepped, and alias-aware. A text search cannot tell a docstring
    explaining why `uuid4()` is banned from a call to it — but an AST walk matching only
    a receiver literally named `random` is barely better, since `import random as rnd`,
    `from random import uniform`, `numpy.random.*` and `os.urandom` all walk straight
    past it. Import aliases are resolved to the module they actually name."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    exempt = path.name in _ENTROPY_EXEMPT

    module_aliases: dict[str, str] = {}   # local name -> real dotted module
    bound_draws: dict[str, str] = {}      # local name -> `from random import <draw>`

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_aliases[alias.asname or alias.name.split(".")[0]] = alias.name
                if alias.name.split(".")[0] in _UNSEEDABLE_MODULES and not exempt:
                    found.append(f"{path.name}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local = alias.asname or alias.name
                if (module == "random" or module.endswith(".random")) \
                        and alias.name in _FORBIDDEN_RANDOM_ATTRS:
                    bound_draws[local] = f"{module}.{alias.name}"
                    found.append(
                        f"{path.name}:{node.lineno}: from {module} import {alias.name}"
                    )
                elif module.split(".")[0] in _UNSEEDABLE_MODULES and not exempt:
                    found.append(
                        f"{path.name}:{node.lineno}: from {module} import {alias.name}"
                    )
                elif module == "os" and alias.name == "urandom":
                    found.append(f"{path.name}:{node.lineno}: from os import urandom")
                else:
                    module_aliases[local] = f"{module}.{alias.name}"

    def receiver(node: ast.expr) -> str:
        """Dotted name of an attribute's receiver, with import aliases resolved."""
        if isinstance(node, ast.Name):
            return module_aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = receiver(node.value)
            return f"{base}.{node.attr}" if base else ""
        return ""

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            base = receiver(node.value)
            root = base.split(".")[0]
            if (base == "random" or base.endswith(".random")) \
                    and node.attr in _FORBIDDEN_RANDOM_ATTRS:
                found.append(f"{path.name}:{node.lineno}: {base}.{node.attr}")
            if root == "os" and node.attr == "urandom":
                found.append(f"{path.name}:{node.lineno}: os.urandom")
            if root in _UNSEEDABLE_MODULES and not exempt:
                found.append(f"{path.name}:{node.lineno}: {base}.{node.attr}")
            if node.attr == "uuid4":
                found.append(f"{path.name}:{node.lineno}: uuid4")
        elif isinstance(node, ast.Name):
            if node.id in bound_draws:
                found.append(f"{path.name}:{node.lineno}: {bound_draws[node.id]}")
            elif node.id == "uuid4":
                found.append(f"{path.name}:{node.lineno}: uuid4")
    return sorted(set(found))


def test_no_uuid4_or_module_level_random_in_simulation_code():
    """Acceptance: a repo-wide search finds no module-level `random.*` or `uuid4`."""
    modules = _simulation_modules()
    assert len(modules) >= 10, f"the module sweep found almost nothing: {modules}"
    offenders = [o for path in modules for o in _randomness_offenders(path)]
    assert not offenders, "unseedable randomness in simulation code:\n" + "\n".join(offenders)


@pytest.mark.parametrize(
    "source, expect",
    [
        ("import random\nx = random.uniform(0, 1)\n", "random.uniform"),
        # The evasions a receiver-name match walks straight past:
        ("import random as rnd\nx = rnd.uniform(0, 1)\n", "random.uniform"),
        ("from random import uniform\nx = uniform(0, 1)\n", "uniform"),
        ("from random import choice as pick\nx = pick([1])\n", "choice"),
        ("import numpy\nx = numpy.random.uniform(0, 1)\n", "numpy.random.uniform"),
        ("import numpy as np\nx = np.random.randint(3)\n", "numpy.random.randint"),
        ("import os\nb = os.urandom(8)\n", "os.urandom"),
        ("from os import urandom\nb = urandom(8)\n", "urandom"),
        ("import secrets\nx = secrets.randbits(8)\n", "secrets"),
        ("from secrets import randbits\nx = randbits(8)\n", "secrets"),
        ("import uuid\ny = uuid.uuid4()\n", "uuid"),
        ("from uuid import uuid4\ny = uuid4()\n", "uuid"),
    ],
)
def test_the_randomness_check_catches_every_way_in(tmp_path, source, expect):
    """A guard with a known hole is worse than none: it reads as coverage.

    Each case here is a real way to reach unseedable or globally-shared randomness that
    the first version of this detector missed."""
    module = tmp_path / "offending.py"
    module.write_text(source)
    found = _randomness_offenders(module)
    assert found, f"nothing detected in:\n{source}"
    assert any(expect in f for f in found), f"expected {expect!r} in {found}"


def test_the_randomness_check_does_not_fire_on_legitimate_code(tmp_path):
    """Explicit `random.Random` instances and prose about the ban are both fine."""
    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        "import random\n"
        '"""Part ids are derived, never uuid4() — random.uniform is banned here."""\n'
        "stream = random.Random(7)\n"
        "z = stream.uniform(0, 1)\n"
        "w = stream.choice([1, 2])\n"
    )
    assert _randomness_offenders(innocent) == []


def test_rng_module_may_draw_entropy_but_others_may_not(tmp_path):
    """`rng.py` generates the one run seed; everywhere else `secrets` is unreachable
    by any seed and therefore banned."""
    source = "import secrets\nx = secrets.randbits(63)\n"
    (tmp_path / "rng.py").write_text(source)
    (tmp_path / "world.py").write_text(source)
    assert _randomness_offenders(tmp_path / "rng.py") == []
    assert _randomness_offenders(tmp_path / "world.py")


def test_the_module_sweep_reaches_into_packages(tmp_path, monkeypatch):
    """`glob` would stop covering code the moment it moved into a subpackage."""
    modules = _simulation_modules()
    names = {p.name for p in modules}
    assert {"world.py", "taobot_simple.py", "rng.py", "main.py"} <= names
    # Nothing from the excluded trees leaked in.
    assert not [p for p in modules if "tests" in p.parts or ".venv" in p.parts]


# ---------------------------------------------------------------------------
# Query tiebreaks
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_world(default_config) -> World:
    """A world with nothing in it — populated explicitly by the tests below."""
    config = copy.deepcopy(default_config)
    config.resources.initial_count = 0
    config.hazards.initial_count = 0
    config.taobots.initial_count = 0
    config.taobots.target_population = 0
    return World(config, seed=SEED_A)


# The query point and a set of positions exactly 3.0 VU from it. Chosen axis-aligned so
# the distances are exactly equal in float arithmetic, not merely close.
_QX, _QY = 10.0, 10.0
_FAR = (50.0, 50.0)  # outside every bucket a radius-4 query at (_QX, _QY) touches


def test_query_resources_breaks_ties_on_entity_id(empty_world):
    """Matrix row 5. `SpatialHash.neighbors` returns a *set*, so sorting on distance
    alone leaves equidistant entities in set-iteration order — and callers read `[0]`
    as "the nearest"."""
    world = empty_world
    world.spawn_resource(x=_FAR[0], y=_FAR[1])              # id 1
    a = world.spawn_resource(x=_QX + 3.0, y=_QY)            # id 2
    b = world.spawn_resource(x=_QX + 3.0, y=_QY)            # id 3
    for _ in range(13):
        world.spawn_resource(x=_FAR[0], y=_FAR[1])          # ids 4..16
    c = world.spawn_resource(x=_QX - 3.0, y=_QY)            # id 17

    tied = [a.entity_id, b.entity_id, c.entity_id]
    raw = list(world._entity_hash.neighbors(_QX, _QY, 4.0, world.config.width,
                                            world.config.height))
    # Teeth check: if the underlying set already iterated in id order this test would
    # pass whether or not the tiebreak exists. Assert we built a case where it does not.
    assert raw != sorted(raw), f"tie group {raw} iterates in id order — test is vacuous"

    result = world.query_resources(_QX, _QY, 4.0)
    assert [r.entity_id for r in result] == sorted(tied)
    # Stable across calls, not merely sorted once.
    assert [r.entity_id for r in world.query_resources(_QX, _QY, 4.0)] == sorted(tied)


def test_query_hazards_breaks_ties_on_entity_id(empty_world):
    world = empty_world
    ids = [
        world.spawn_hazard(x=_QX + 3.0, y=_QY).entity_id,
        world.spawn_hazard(x=_QX - 3.0, y=_QY).entity_id,
        world.spawn_hazard(x=_QX, y=_QY + 3.0).entity_id,
    ]
    result = world.query_hazards(_QX, _QY, 4.0)
    assert [h.entity_id for h in result] == sorted(ids)


def test_query_taobots_breaks_ties_on_entity_id(empty_world):
    world = empty_world
    ids = [
        world.spawn_taobot(x=_QX + 3.0, y=_QY).entity_id,
        world.spawn_taobot(x=_QX - 3.0, y=_QY).entity_id,
        world.spawn_taobot(x=_QX, y=_QY + 3.0).entity_id,
    ]
    result = world.query_taobots(_QX, _QY, 4.0)
    assert [t.entity_id for t in result] == sorted(ids)


def test_hazard_damage_is_applied_in_entity_id_order(empty_world):
    """`_apply_hazard_damage` iterates the same `neighbors` set the `query_*` methods
    do, and accumulates each hit into a float — so it is the same order-sensitive path,
    and gets the same stable key. Its three siblings each have a test; this closes the
    gap where reverting its `sorted(...)` passed the whole suite."""
    world = empty_world
    # Same shape as the query tiebreak above: ids arranged so the underlying set does
    # not already iterate in ascending order, or the assertion proves nothing.
    world.spawn_hazard(x=_FAR[0], y=_FAR[1])                       # id 1
    world.spawn_hazard(x=_QX, y=_QY)                               # id 2
    world.spawn_hazard(x=_QX, y=_QY)                               # id 3
    for _ in range(13):
        world.spawn_hazard(x=_FAR[0], y=_FAR[1])                   # ids 4..16
    world.spawn_hazard(x=_QX, y=_QY)                               # id 17
    bot = world.spawn_taobot(x=_QX, y=_QY)

    raw = list(world._entity_hash.neighbors(_QX, _QY, 1.0, world.config.width,
                                            world.config.height))
    assert raw != sorted(raw), f"hazard set {raw} iterates in id order — test is vacuous"

    # Give each hazard a damage value that identifies it, so the sequence of hits is
    # readable rather than inferred.
    for eid, hazard in world._hazards.items():
        hazard.damage_per_tick = eid / 100.0

    applied: list[float] = []
    bot.record_damage = applied.append
    world._apply_hazard_damage()

    tied_ids = sorted(eid for eid in raw if eid in world._hazards)
    assert applied, "no hazard reached the bot — test is vacuous"
    assert applied == [eid / 100.0 for eid in tied_ids], (
        f"hazards applied in {applied}, expected ascending entity_id order "
        f"{[eid / 100.0 for eid in tied_ids]}"
    )


def test_tiebreak_does_not_disturb_distance_ordering(empty_world):
    """The tiebreak is secondary: a nearer entity with a higher id still comes first."""
    world = empty_world
    far = world.spawn_resource(x=_QX + 3.0, y=_QY)   # lower id, further away
    near = world.spawn_resource(x=_QX + 1.0, y=_QY)  # higher id, nearer
    result = world.query_resources(_QX, _QY, 4.0)
    assert [r.entity_id for r in result] == [near.entity_id, far.entity_id]


# ---------------------------------------------------------------------------
# Run manifest
# ---------------------------------------------------------------------------

def test_manifest_records_seed_config_sha_python_and_timestamp(default_config, tmp_path):
    """Matrix row 6. `--seed` used to be accepted and recorded nowhere, so no logged
    run could be replayed and no CSV attributed to the code that produced it."""
    log_dir = tmp_path / "logs"
    path = write_manifest(
        seed=SEED_A,
        config=default_config,
        config_path="configs/default_world.json",
        mode="headless",
        ts="20260811T120000",
        log_paths=[Path("logs/default_focal.csv")],
        log_dir=log_dir,
    )
    assert path.parent == log_dir
    manifest = json.loads(path.read_text())

    assert manifest["seed"] == SEED_A
    assert manifest["config_name"] == default_config.name
    assert manifest["config_path"] == "configs/default_world.json"
    assert manifest["timestamp"] == "20260811T120000"
    assert manifest["mode"] == "headless"
    assert manifest["python_version"].count(".") == 2
    assert manifest["logs"] == ["logs/default_focal.csv"]
    # The SHA is allowed to be null outside a checkout, but the key is never absent —
    # a reader must be able to tell "no git" from "manifest predates this field".
    assert "git_sha" in manifest
    if manifest["git_sha"] is not None:
        assert re.fullmatch(r"[0-9a-f]{40}", manifest["git_sha"])


def test_manifest_filename_carries_the_run_timestamp(default_config, tmp_path):
    """Manifests accumulate rather than overwrite, and share a stamp with the
    timestamped CSVs of the same run so the two can be paired."""
    first = write_manifest(seed=1, config=default_config, config_path="c.json",
                           mode="headless", ts="20260811T120000", log_paths=[],
                           log_dir=tmp_path)
    second = write_manifest(seed=2, config=default_config, config_path="c.json",
                            mode="headless", ts="20260811T120001", log_paths=[],
                            log_dir=tmp_path)
    assert first != second
    assert first.exists() and second.exists()
    assert first.name == f"{default_config.name}_manifest_20260811T120000.json"


def test_git_sha_survives_a_directory_that_is_not_a_checkout(tmp_path):
    """A run must never die because the code was unpacked outside git."""
    assert git_sha(tmp_path) is None


def test_manifest_fingerprints_the_resolved_config(default_config):
    """Name and path are not enough to replay a run — configs get edited.

    The fingerprint covers the *resolved* values, laws merged in, so an edit between
    two runs is detectable instead of silently producing a different run at the
    same seed under the same config name."""
    other = copy.deepcopy(default_config)
    assert config_fingerprint(default_config) == config_fingerprint(other)

    other.resources.initial_count += 1
    assert config_fingerprint(other) != config_fingerprint(default_config)

    laws_changed = copy.deepcopy(default_config)
    laws_changed.chemistry.degrade_rate *= 2
    assert config_fingerprint(laws_changed) != config_fingerprint(default_config)


# ---------------------------------------------------------------------------
# The CLI actually honours --seed
# ---------------------------------------------------------------------------

def _headless_run(work_dir: Path, args: list[str]) -> dict:
    """Run `main.py --headless` in `work_dir` and return its parsed manifest."""
    work_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"), "--headless",
         "--config", str(CONFIG_DIR / "default_world.json"), *args],
        cwd=work_dir, capture_output=True, text=True, timeout=300, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    manifests = list((work_dir / "logs").glob("*_manifest_*.json"))
    assert len(manifests) == 1, f"expected one manifest, found {manifests}"
    return json.loads(manifests[0].read_text())


def test_cli_seed_reaches_the_simulation_and_reproduces_it(tmp_path):
    """The end-to-end guarantee, and the one the unit tests could not make.

    `assert world.seed == manifest["seed"]` cannot fail — `World.__init__` just stores
    what it was handed — so it would pass even if `main()` recorded a seed and then
    built the world without it, or ignored `--seed` and generated its own. Only running
    the real CLI twice and comparing bytes distinguishes those.

    `--ticks` rather than `--duration`: a wall-clock bound reaches a different tick
    count on a busier machine, so the two runs would share only a prefix."""
    first = _headless_run(tmp_path / "a", ["--seed", "12345", "--ticks", "300"])
    second = _headless_run(tmp_path / "b", ["--seed", "12345", "--ticks", "300"])

    assert first["seed"] == 12345, "--seed must reach the manifest verbatim"
    assert second["seed"] == 12345
    assert first["ticks"] == 300, "the manifest must record how far the run got"

    for name in ("default_focal.csv", "default_deaths.csv"):
        a = (tmp_path / "a" / "logs" / name).read_bytes()
        b = (tmp_path / "b" / "logs" / name).read_bytes()
        assert a == b, f"{name} differs between two runs at the same seed"
        assert len(a.splitlines()) > 1, f"{name} is empty — the comparison is vacuous"

    # And the population CSVs, whose names carry the run timestamp.
    pop_a = next((tmp_path / "a" / "logs").glob("default_2*.csv")).read_bytes()
    pop_b = next((tmp_path / "b" / "logs").glob("default_2*.csv")).read_bytes()
    assert pop_a == pop_b


def test_cli_different_seeds_diverge(tmp_path):
    """The other half: if `--seed` were ignored, both runs above would still match."""
    _headless_run(tmp_path / "a", ["--seed", "12345", "--ticks", "300"])
    _headless_run(tmp_path / "b", ["--seed", "54321", "--ticks", "300"])
    a = (tmp_path / "a" / "logs" / "default_focal.csv").read_bytes()
    b = (tmp_path / "b" / "logs" / "default_focal.csv").read_bytes()
    assert a != b


# ---------------------------------------------------------------------------
# Observers read; they never mutate (AD-16)
# ---------------------------------------------------------------------------

def test_attaching_a_run_logger_does_not_perturb_the_simulation(
    default_config, monkeypatch, tmp_path
):
    """`AD-16`. Measuring a run must not change it.

    `main.py:109` used to pick focal individuals with module-level `random.choice`, so
    the act of logging consumed draws from the simulation's own stream and moved every
    bot. Two runs at one seed — one observed, one not — must end in the same state."""
    monkeypatch.chdir(tmp_path)

    def run(with_logger: bool) -> dict:
        config = WorldConfig.from_json(CONFIG_DIR / "default_world.json")
        world = World(config, seed=SEED_A)
        world.initialize()
        logger = None
        if with_logger:
            logger = RunLogger(
                config.name, rng=derive_stream(world.seed, "observer", "focal")
            )
            world.on_taobot_death = lambda t: logger.on_death(t, world.tick_count)
        for _ in range(150):
            world.tick()
            if logger is not None:
                logger.on_tick(world)
        if logger is not None:
            logger.close()
        return world_state(world)

    observed = run(with_logger=True)
    unobserved = run(with_logger=False)
    assert observed == unobserved, (
        "attaching a logger changed the run it was measuring — the observer is "
        "drawing from the simulation's stream"
    )


def test_the_cli_wires_the_observer_to_its_own_stream(tmp_path):
    """The same guarantee, but on `main.py`'s actual wiring.

    The test above builds its own `RunLogger` with a correctly derived observer stream,
    so it proves the *pattern* is sound and nothing about what `main()` does — rewiring
    `main()` to hand the logger `world._rng` left it green. This compares a real CLI run
    (which always attaches a logger) against an in-process run of the same seed and tick
    count with no logger at all: if logging perturbs the simulation, the population
    statistics diverge."""
    import csv as _csv

    seed, ticks = 4242, 300
    _headless_run(tmp_path / "cli", ["--seed", str(seed), "--ticks", str(ticks)])
    pop_csv = next((tmp_path / "cli" / "logs").glob("default_2*.csv"))
    logged = list(_csv.DictReader(pop_csv.open()))
    assert logged, "the population CSV is empty — the comparison would be vacuous"

    # Reproduce the same run with no observer attached, at run_headless's own cadence.
    config = WorldConfig.from_json(CONFIG_DIR / "default_world.json")
    world = World(config, seed=seed)
    world.initialize()
    unobserved = []
    for _ in range(ticks):
        world.tick()
        if world.tick_count % 60 == 0:
            unobserved.append(world.get_stats())

    assert len(logged) == len(unobserved)
    for row, expected in zip(logged, unobserved):
        for column, value in expected.items():
            assert row[column] == str(value), (
                f"tick {expected['tick']}, column {column}: the logged run says "
                f"{row[column]} but an unobserved run of the same seed says {value} — "
                f"attaching the logger changed the simulation (AD-16)"
            )


@pytest.mark.parametrize(
    "mode_args, expected",
    [
        ([], ["{name}_deaths.csv", "{name}_focal.csv"]),
        (["--headless"], ["{name}_deaths.csv", "{name}_focal.csv", "{name}_{ts}.csv"]),
        (["--workshop"], ["{name}_workshop_{ts}.csv"]),
    ],
    ids=["visual", "headless", "workshop"],
)
def test_manifest_log_list_matches_what_the_loggers_actually_write(
    mode_args, expected, tmp_path, monkeypatch
):
    """The manifest's `logs` list must come from the loggers, not from `main()`
    re-spelling the filename convention.

    Visual and workshop mode were previously hand-predicted and verified in neither, so
    renaming the predicted workshop path — or dropping focal from the non-headless
    list — left the suite green while the manifest pointed at files nobody wrote."""
    from main import LOG_DIR, MetricsLogger, RunLogger, WorkshopLogger

    ts = "20260811T120000_000"
    name = "default"
    if "--workshop" in mode_args:
        produced = [WorkshopLogger.path_name(name, ts)]
    else:
        produced = RunLogger.path_names(name)
        if "--headless" in mode_args:
            produced = produced + [LOG_DIR / f"{name}_{ts}.csv"]

    assert [str(p) for p in produced] == [
        str(LOG_DIR / template.format(name=name, ts=ts)) for template in expected
    ]

    # And the predicted paths agree with what an instance actually opens.
    probe = tmp_path / "probe"
    probe.mkdir()
    monkeypatch.chdir(probe)
    if "--workshop" in mode_args:
        workshop = WorkshopLogger(name, ts=ts, n_legs=2)
        assert workshop.path == WorkshopLogger.path_name(name, ts)
        workshop.close()
        assert workshop.path.exists()
    else:
        run_logger = RunLogger(name)
        assert run_logger.paths == RunLogger.path_names(name)
        run_logger.close()
        for path in run_logger.paths:
            assert path.exists()
        if "--headless" in mode_args:
            metrics = MetricsLogger(name, ts=ts)
            assert metrics.path == LOG_DIR / f"{name}_{ts}.csv"
            metrics.close()
            assert metrics.path.exists()


def test_workshop_run_writes_a_manifest_naming_its_real_log(tmp_path):
    """Workshop mode end to end: the manifest exists and every file it claims is there.

    The workshop opens a pygame window, so it is launched with the dummy video driver
    and stopped after a moment — enough to prove the manifest and the logger agree."""
    import os
    import signal
    import time as _time

    env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
    (tmp_path / "configs").mkdir()
    for cfg in ("workshop.json", "laws.json"):
        (tmp_path / "configs" / cfg).write_bytes((CONFIG_DIR / cfg).read_bytes())

    proc = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "main.py"), "--workshop", "--seed", "5"],
        cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _time.sleep(4)
        proc.send_signal(signal.SIGINT)
        proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:  # pragma: no cover - defensive
            proc.kill()
            proc.communicate(timeout=10)

    manifests = list((tmp_path / "logs").glob("*_manifest_*.json"))
    assert len(manifests) == 1, f"expected one workshop manifest, found {manifests}"
    manifest = json.loads(manifests[0].read_text())
    assert manifest["mode"] == "workshop"
    assert manifest["seed"] == 5
    assert manifest["logs"], "a workshop run must name the CSV it writes"
    for logged in manifest["logs"]:
        assert (tmp_path / logged).exists(), f"manifest names a missing log: {logged}"


def test_headless_run_without_a_seed_still_writes_a_replayable_manifest(
    monkeypatch, tmp_path
):
    """Matrix row 7, end to end: `--seed` omitted, run works, manifest records the
    seed that was generated — so an unflagged run is still replayable afterwards."""
    monkeypatch.chdir(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"), "--headless", "--duration", "0.2",
         "--config", str(CONFIG_DIR / "default_world.json")],
        cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stderr

    manifests = list((tmp_path / "logs").glob("*_manifest_*.json"))
    assert len(manifests) == 1, f"expected one manifest, found {manifests}"
    manifest = json.loads(manifests[0].read_text())
    assert isinstance(manifest["seed"], int)

    # Every log the manifest claims the run wrote must actually be there.
    for logged in manifest["logs"]:
        assert (tmp_path / logged).exists(), f"manifest names a missing log: {logged}"

    # The recorded seed is a real handle: feeding it back reproduces the run's start.
    config = WorldConfig.from_json(CONFIG_DIR / "default_world.json")
    replay = World(config, seed=manifest["seed"])
    replay.initialize()
    assert replay.seed == manifest["seed"]
