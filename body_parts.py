from __future__ import annotations

import math
from abc import ABC, abstractmethod

from common import ElementType

# When a leg's water reserve is empty and thrust is nonzero, structural integrity
# degrades by (shortfall * this scale) per tick. At drain_max=0.005 and scale=0.5,
# a fully-starved leg loses integrity at 0.0025/tick → reaches 0 in ~400 ticks.
LEG_INTEGRITY_DEGRADE_SCALE: float = 0.5


class BodyPart(ABC):
    """Base class for all physical body parts on a Taobot.

    All parts share:
    - A polar position (r, theta) on the body for rendering and future genetic encoding.
    - A stable part_id (UUID4) assigned at instantiation for genetics compatibility.
    - An element type that determines which chi pool the part draws from.
    - A local reserve + capacity buffer, replenished each tick from taobot storage.
    - A structural_integrity float (0–1) that degrades when starved or damaged.
    - An abstract tick() called after replenishment.
    """

    def __init__(self, part_id: str, r: float, theta: float, element: ElementType) -> None:
        self.part_id = part_id
        self.r = r
        self.theta = theta
        self.element = element
        self.structural_integrity: float = 1.0
        self.reserve: float = 0.0
        self.capacity: float = 0.0

    def replenish(self, available: float) -> float:
        """Fill reserve from the taobot's chi pool. Returns amount absorbed."""
        space = self.capacity - self.reserve
        absorbed = min(space, max(0.0, available))
        self.reserve += absorbed
        return absorbed

    @abstractmethod
    def tick(self) -> None:
        """Consume resources and update state for this tick."""


class LegPart(BodyPart):
    """A leg: consumes Water chi per tick proportional to thrust.

    `phi` is a genetic parameter — the direction the leg pushes, in the body frame
    relative to the taobot's heading. Decoupling phi from the attachment position
    theta allows any body plan to emerge through evolution:

      phi = 0          → always pushes in heading direction (default); bilateral
                          symmetric pairs produce pure forward translation
      phi = theta      → pushes radially outward from attachment point; zero torque
      phi = theta+pi/2 → pushes tangentially; maximum torque

    Steering is achieved via differential thrust across legs (differential drive).
    The neural network (Phase 3) outputs one thrust scalar per leg; physics handles
    the rest.
    """

    def __init__(
        self,
        part_id: str,
        r: float,
        theta: float,
        phi: float,
        max_thrust: float,
        capacity: float,
        drain_max: float,
    ) -> None:
        super().__init__(part_id, r, theta, ElementType.WATER)
        self.phi = phi
        self.max_thrust = max_thrust
        self.capacity = capacity
        self.reserve = capacity  # starts full
        self.drain_max = drain_max
        self._thrust: float = 0.0

    def set_thrust(self, value: float) -> None:
        self._thrust = max(-self.max_thrust, min(self.max_thrust, value))

    def effective_thrust(self) -> float:
        return self._thrust * self.structural_integrity

    @property
    def max_torque(self) -> float:
        """Maximum torque magnitude this leg can produce: r × max_thrust."""
        return self.r * self.max_thrust

    def torque(self) -> float:
        """Signed turning torque this tick: r × effective_thrust × sin(phi − theta)."""
        return self.r * self.effective_thrust() * math.sin(self.phi - self.theta)

    def force_vector(self, heading: float) -> tuple[float, float]:
        """2D force in direction (heading + phi), scaled by effective thrust."""
        d = heading + self.phi
        t = self.effective_thrust()
        return (t * math.cos(d), t * math.sin(d))

    def tick(self) -> None:
        """Drain water proportional to |thrust|; degrade integrity if reserve is empty."""
        if self.max_thrust == 0.0 or self._thrust == 0.0:
            return
        drain = abs(self._thrust) / self.max_thrust * self.drain_max
        if self.reserve >= drain:
            self.reserve -= drain
        else:
            shortfall = drain - self.reserve
            self.reserve = 0.0
            self.structural_integrity = max(
                0.0, self.structural_integrity - shortfall * LEG_INTEGRITY_DEGRADE_SCALE
            )
