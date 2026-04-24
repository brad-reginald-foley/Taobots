import pytest

from common import ElementType
from entities import Hazard, Resource


def make_resource(amount: float = 10.0) -> Resource:
    r = Resource(x=5.0, y=5.0, element_type=ElementType.WOOD, entity_id=1, max_amount=amount)
    r.set_respawn_delay(10)
    return r


def test_resource_initial_state():
    r = make_resource(10.0)
    assert r.amount == pytest.approx(10.0)
    assert r.is_alive is True
    assert r.respawn_ticks_remaining == 0


def test_resource_deplete_partial():
    r = make_resource(10.0)
    actual = r.deplete(4.0)
    assert actual == pytest.approx(4.0)
    assert r.amount == pytest.approx(6.0)
    assert r.is_alive is True


def test_resource_deplete_full():
    r = make_resource(10.0)
    actual = r.deplete(10.0)
    assert actual == pytest.approx(10.0)
    assert r.amount == pytest.approx(0.0)
    assert r.is_alive is False
    assert r.respawn_ticks_remaining == 10


def test_resource_deplete_more_than_available():
    r = make_resource(10.0)
    actual = r.deplete(15.0)
    assert actual == pytest.approx(10.0)
    assert r.amount == pytest.approx(0.0)
    assert r.is_alive is False


def test_resource_tick_respawn_counts_down():
    r = make_resource(10.0)
    r.deplete(10.0)
    assert r.respawn_ticks_remaining == 10
    for _ in range(9):
        revived = r.tick_respawn()
        assert revived is False
    revived = r.tick_respawn()
    assert revived is True
    assert r.is_alive is True
    assert r.amount == pytest.approx(10.0)


def test_resource_tick_respawn_on_alive_does_nothing():
    r = make_resource(10.0)
    revived = r.tick_respawn()
    assert revived is False
    assert r.is_alive is True


def test_hazard_damage_element_defaults_to_element_type():
    h = Hazard(x=0.0, y=0.0, element_type=ElementType.FIRE, entity_id=99)
    assert h.damage_element_type == ElementType.FIRE


def test_hazard_default_damage():
    h = Hazard(x=0.0, y=0.0, element_type=ElementType.WATER, entity_id=1)
    assert h.damage_per_tick == pytest.approx(1.0)
