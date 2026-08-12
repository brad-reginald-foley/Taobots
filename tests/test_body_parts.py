from __future__ import annotations

import math

import pytest

from body_factory import BodyFactory
from body_parts import LegPart


def make_leg(
    theta: float = 0.0,
    phi: float = 0.0,
    max_thrust: float = 1.0,
    capacity: float = 10.0,
    drain_max: float = 0.1,
) -> LegPart:
    return LegPart(
        part_id="test",
        r=1.0,
        theta=theta,
        phi=phi,
        max_thrust=max_thrust,
        capacity=capacity,
        drain_max=drain_max,
    )


def test_force_vector_heading_zero() -> None:
    """phi=0, heading=0 → force in +x direction."""
    leg = make_leg(theta=0.0, phi=0.0)
    leg.set_thrust(1.0)
    fx, fy = leg.force_vector(heading=0.0)
    assert abs(fx - 1.0) < 1e-9
    assert abs(fy) < 1e-9


def test_force_vector_phi_offset() -> None:
    """phi=pi/2, heading=0 → force in +y direction regardless of theta."""
    leg = make_leg(theta=0.3, phi=math.pi / 2)
    leg.set_thrust(1.0)
    fx, fy = leg.force_vector(heading=0.0)
    assert abs(fx) < 1e-9
    assert abs(fy - 1.0) < 1e-9


def test_water_drain_proportional() -> None:
    leg = make_leg(max_thrust=1.0, drain_max=0.1)
    leg.set_thrust(0.5)
    before = leg.reserve
    leg.tick()
    assert abs((before - leg.reserve) - 0.05) < 1e-9


def test_no_drain_at_zero_thrust() -> None:
    leg = make_leg()
    leg.set_thrust(0.0)
    before = leg.reserve
    leg.tick()
    assert leg.reserve == before


def test_integrity_degrades_on_starvation() -> None:
    leg = make_leg(capacity=0.0, drain_max=0.1)
    leg.reserve = 0.0
    leg.set_thrust(1.0)
    leg.tick()
    assert leg.structural_integrity < 1.0


def test_effective_thrust_scales_with_integrity() -> None:
    leg = make_leg()
    leg.structural_integrity = 0.5
    leg.set_thrust(1.0)
    assert abs(leg.effective_thrust() - 0.5) < 1e-9


def test_replenish_respects_capacity() -> None:
    leg = make_leg(capacity=5.0)
    leg.reserve = 4.0
    absorbed = leg.replenish(10.0)
    assert absorbed == pytest.approx(1.0)
    assert leg.reserve == pytest.approx(5.0)


def test_body_factory_dispatch() -> None:
    specs = [{"type": "leg", "r": 1.5, "theta": 0.0, "phi": 0.0,
              "max_thrust": 1.0, "capacity": 5.0, "drain_max": 0.01}]
    parts = BodyFactory.make_parts(specs, run_seed=1, owner_id="test-bot")
    assert len(parts) == 1
    assert isinstance(parts[0], LegPart)
    assert parts[0].part_id  # non-empty derived id
    assert parts[0].phi == 0.0


def test_body_factory_phi_default() -> None:
    """Specs without phi field default to 0.0."""
    specs = [{"type": "leg", "r": 1.5, "theta": 0.0,
              "max_thrust": 1.0, "capacity": 5.0, "drain_max": 0.01}]
    parts = BodyFactory.make_parts(specs, run_seed=1, owner_id="test-bot")
    assert isinstance(parts[0], LegPart)
    assert parts[0].phi == 0.0


def test_torque_with_phi() -> None:
    """torque() == r * effective_thrust * sin(phi - theta)."""
    leg = make_leg(theta=0.3, phi=0.8)
    leg.r = 2.0
    leg.set_thrust(1.0)
    expected = 2.0 * 1.0 * math.sin(0.8 - 0.3)
    assert abs(leg.torque() - expected) < 1e-9


def test_phi_equals_theta_zero_torque() -> None:
    """When phi == theta, the leg pushes radially and produces zero torque."""
    theta = 0.6
    leg = make_leg(theta=theta, phi=theta)
    leg.set_thrust(1.0)
    assert abs(leg.torque()) < 1e-9


def test_symmetric_phi0_net_speed() -> None:
    """Two phi=0 legs at ±theta with equal thrust T each → net speed = 2T in heading direction."""
    T = 0.75
    theta = 0.4
    leg_pos = make_leg(theta=+theta, phi=0.0, max_thrust=T * 1.5)
    leg_neg = make_leg(theta=-theta, phi=0.0, max_thrust=T * 1.5)
    leg_pos.set_thrust(T)
    leg_neg.set_thrust(T)

    heading = 0.0
    fx = leg_pos.force_vector(heading)[0] + leg_neg.force_vector(heading)[0]
    fy = leg_pos.force_vector(heading)[1] + leg_neg.force_vector(heading)[1]

    assert abs(fx - 2 * T) < 1e-9   # both push in heading (+x) direction
    assert abs(fy) < 1e-9            # lateral components cancel
