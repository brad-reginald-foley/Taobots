import pytest

from world import World, WorldConfig


@pytest.fixture(scope="session")
def pygame_init():
    import pygame
    pygame.init()
    yield
    pygame.quit()


@pytest.fixture
def default_config() -> WorldConfig:
    return WorldConfig.from_json("configs/default_world.json")


@pytest.fixture
def small_world(default_config: WorldConfig) -> World:
    w = World(default_config)
    w.initialize()
    return w
