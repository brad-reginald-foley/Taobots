from pathlib import Path

import pytest

from world import World, WorldConfig

# Resolved from this file, never the working directory. `pytest` run from anywhere
# must load the same configs, and several tests `monkeypatch.chdir` into `tmp_path`
# before touching a fixture — a relative path would find nothing there.
CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"

# Fixed seed for the deterministic fixtures below. Any value works; it is pinned so
# the same fixture yields the same world every run and a failure is reproducible.
TEST_SEED = 20260811


@pytest.fixture(scope="session")
def pygame_init():
    import pygame
    pygame.init()
    yield
    pygame.quit()


@pytest.fixture
def default_config() -> WorldConfig:
    return WorldConfig.from_json(CONFIG_DIR / "default_world.json")


@pytest.fixture
def small_world(default_config: WorldConfig) -> World:
    """An initialized world on the fixed test seed.

    Seeded rather than left to generate its own: an unseeded fixture makes every test
    that reads a position, a spawn order or a part id non-reproducible, so a failure
    cannot be re-run and a flake cannot be told from a bug."""
    w = World(default_config, seed=TEST_SEED)
    w.initialize()
    return w


@pytest.fixture
def seeded_world(default_config: WorldConfig) -> World:
    """An initialized world on a *different* fixed seed from `small_world`.

    Two seeded fixtures rather than one, so a test that happens to pass only under one
    particular arrangement of the world is more likely to be caught."""
    w = World(default_config, seed=TEST_SEED + 1)
    w.initialize()
    return w
