import math

import pytest

from math_utils import (
    polar_to_cartesian,
    torus_delta,
    torus_direction,
    torus_distance,
    world_to_screen,
    wrap_position,
)


def test_torus_delta_normal():
    assert torus_delta(1.0, 4.0, 10.0) == pytest.approx(3.0)


def test_torus_delta_wrap_positive():
    # From 8 to 2 on size-10 torus: direct is -6 but wrapping forward is +4 (shorter)
    assert torus_delta(8.0, 2.0, 10.0) == pytest.approx(4.0)


def test_torus_delta_wrap_negative():
    # From 2 to 8 on size-10 torus: direct is +6 but wrapping backward is -4 (shorter)
    assert torus_delta(2.0, 8.0, 10.0) == pytest.approx(-4.0)


def test_torus_delta_at_boundary():
    # From 0 to 9 on size-10: shortest is -1 (wrap around)
    assert torus_delta(0.0, 9.0, 10.0) == pytest.approx(-1.0)


def test_torus_distance_simple():
    d = torus_distance(0.0, 0.0, 3.0, 4.0, 100.0, 100.0)
    assert d == pytest.approx(5.0)


def test_torus_distance_wraps():
    # Distance from (1,0) to (99,0) on 100-wide world should be 2, not 98
    d = torus_distance(1.0, 0.0, 99.0, 0.0, 100.0, 100.0)
    assert d == pytest.approx(2.0)


def test_torus_direction_normal():
    dx, dy = torus_direction(0.0, 0.0, 3.0, 4.0, 100.0, 100.0)
    assert dx == pytest.approx(0.6)
    assert dy == pytest.approx(0.8)


def test_torus_direction_identical_points():
    dx, dy = torus_direction(5.0, 5.0, 5.0, 5.0, 100.0, 100.0)
    assert dx == 0.0
    assert dy == 0.0


def test_torus_direction_is_unit_vector():
    dx, dy = torus_direction(1.0, 2.0, 5.0, 6.0, 100.0, 100.0)
    assert math.sqrt(dx * dx + dy * dy) == pytest.approx(1.0)


def test_wrap_position_no_wrap():
    x, y = wrap_position(5.0, 10.0, 80.0, 60.0)
    assert x == pytest.approx(5.0)
    assert y == pytest.approx(10.0)


def test_wrap_position_x_over():
    x, y = wrap_position(85.0, 10.0, 80.0, 60.0)
    assert x == pytest.approx(5.0)


def test_wrap_position_y_over():
    x, y = wrap_position(5.0, 65.0, 80.0, 60.0)
    assert y == pytest.approx(5.0)


def test_wrap_position_negative():
    x, y = wrap_position(-1.0, -2.0, 80.0, 60.0)
    assert x == pytest.approx(79.0)
    assert y == pytest.approx(58.0)


def test_polar_to_cartesian_right():
    x, y = polar_to_cartesian(1.0, 0.0)
    assert x == pytest.approx(1.0)
    assert y == pytest.approx(0.0)


def test_polar_to_cartesian_up():
    x, y = polar_to_cartesian(1.0, math.pi / 2)
    assert x == pytest.approx(0.0, abs=1e-9)
    assert y == pytest.approx(1.0)


def test_world_to_screen():
    px, py = world_to_screen(5.0, 3.0, 10.0, 10.0)
    assert px == 50
    assert py == 30
