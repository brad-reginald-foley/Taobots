from __future__ import annotations

import math
from abc import ABC, abstractmethod

from common import ElementType

# When a leg's water reserve is empty and thrust is nonzero, structural integrity
# degrades by (shortfall * this scale) per tick. At the default drain_max=0.020 and
# scale=0.5, a leg starved at cruise thrust loses integrity at 0.005/tick → reaches 0
# in ~200 ticks; at full thrust, 0.010/tick → ~100 ticks.
LEG_INTEGRITY_DEGRADE_SCALE: float = 0.5

# The reference mass, and the one row of the mass table E1 actually exercises.
#
# `mass` is a *trait* by `AD-13`'s test, not a law: it is a property of a part type,
# it will be encoded in a genome, and no organism escapes a designed constraint by
# evolving a lighter leg — the Earth *rate* is the shared knob and that is the law.
# Placeholder masses are normalised to leg = 1.0 from the rule that each organ system
# should cost about the same to repair, so per-part mass is inversely proportional to
# expected part count (body 1 part → 4.0, armor 32 → 0.125, meridians 64 → 0.0625,
# neurons 1000 → 0.004). **Only the leg row is exercised here**: legs are the only
# part type that exists, so any cross-system ratio is unfalsifiable in E1. The ratios
# are E2's to settle once armor provides a genuinely different second part type.
DEFAULT_LEG_MASS: float = 1.0


class BodyPart(ABC):
    """Base class for all physical body parts on a Taobot.

    All parts share:
    - A polar position (r, theta) on the body for rendering and future genetic encoding.
    - A stable part_id assigned at instantiation, derived by `BodyFactory` from the
      run seed and the gene that expressed it (`AD-9`) — never random, so a seeded
      run reproduces its part ids exactly.
    - **Two elements** (`AD-8`): a *function* element the part does its work with
      (Water for a leg) and a *structural* element it is built from and repaired by.
      `STR-2` says every body part is made of Earth, so `structural_element` defaults
      to Earth; the body is the degenerate case where the two coincide.
    - A `mass`, read through `mass()` and never as a bare field (`AD-5`) — see below.
    - A local reserve + capacity buffer, replenished each tick from taobot storage.
    - A structural_integrity float (0–1) that degrades when starved or damaged **and
      recovers by absorbing its structural element** (`STR-2`).
    - An abstract tick() called after replenishment.

    **Degrade-and-repair lives here, not on a subclass.** `LegPart` adds nothing to
    it: E2's armor and E3's meridians inherit the whole mechanism rather than each
    reimplementing a cure for their own decay.
    """

    def __init__(
        self,
        part_id: str,
        r: float,
        theta: float,
        element: ElementType,
        mass: float,
        structural_element: ElementType = ElementType.EARTH,
    ) -> None:
        if not math.isfinite(mass) or mass <= 0.0:
            # Not a clamp. `mass` divides the repair law (integrity gained is
            # `earth / (mass * rate)`), so a zero or negative mass is either a
            # ZeroDivisionError or a part that repairs *backwards* — and a NaN mass
            # would make every demand NaN, which `min` propagates and every ordered
            # comparison silently accepts. Refuse it where it enters.
            raise ValueError(
                f"{type(self).__name__} mass must be a positive finite number, "
                f"got {mass!r}"
            )
        self.part_id = part_id
        self.r = r
        self.theta = theta
        self.element = element
        self.structural_element = structural_element
        self._mass = float(mass)
        self.structural_integrity: float = 1.0
        self.reserve: float = 0.0
        self.capacity: float = 0.0

        # This tick's repair, overwritten every tick by the organism's repair pass and
        # reset by it when nothing was repaired. Observers read it and reset nothing
        # (the house rule): it is a record of the tick just resolved, not an
        # accumulator a logger owns. `last_repair_essence` is what the port actually
        # took out of storage for *this* part — so the CSV column and the panel report
        # the debit that happened, not the one that was planned.
        self.last_repair_essence: float = 0.0
        self.last_repair_gain: float = 0.0

    # --- Traits --------------------------------------------------------------

    def mass(self) -> float:
        """This part's mass — always through this accessor, never `part._mass`.

        A method from the first commit precisely because it is a stored placeholder
        today and becomes *derived from part traits* in a later epic (`AD-5`). When
        that flip happens it changes one method per part class; a bare field read
        would have to be chased through every caller instead. The stored value lives
        in `_mass` so a bare read is visibly reaching past the seam."""
        return self._mass

    # --- Structural integrity ------------------------------------------------

    def _set_integrity(self, value: float) -> float:
        """The single write site for `structural_integrity`, clamped to [0.0, 1.0].

        Both directions go through here — degradation floors at 0.0 and repair caps at
        1.0 — so the bound is enforced in one place rather than at each arithmetic
        site that happens to remember it. Returns the value actually stored."""
        self.structural_integrity = max(0.0, min(1.0, value))
        return self.structural_integrity

    def integrity_deficit(self) -> float:
        """How much integrity this part is missing: `1.0 - structural_integrity`."""
        return max(0.0, 1.0 - self.structural_integrity)

    def repair_demand(
        self, essence_per_integrity_mass: float, max_integrity_per_tick: float
    ) -> float:
        """Structural essence this part asks for *this tick*.

        The law is `essence = Δintegrity × mass × rate` — one shared exchange rate
        plus one per-part trait, rather than a new uncorrelated repair constant for
        every part type that ever gets built. A whole part demands nothing, which is
        what keeps it out of the pro-rata split entirely.

        **The Δ is capped at `max_integrity_per_tick`, and that cap is why damage is
        observable at all.** Without it a part asks for its entire deficit at once and
        rebuilds completely the moment Earth allows, so integrity sits pinned at 1.0
        and neither the dip nor the recovery ever appears — measured, before the cap
        existed: legs never left 1.0000 across a 1200-tick run in which repair fired
        continuously. Capping the *demand* rather than the applied gain keeps
        `apply_repair` the exact inverse of this method, so a part granted 60% of what
        it asked still repairs 60% as much, and keeps the pro-rata split honest — a
        part cannot claim a share of scarce Earth it could not spend this tick."""
        wanted = min(self.integrity_deficit(), max_integrity_per_tick)
        return wanted * self.mass() * essence_per_integrity_mass

    def clear_repair_record(self) -> None:
        """Zero this tick's repair record, before any of it is resolved."""
        self.last_repair_essence = 0.0
        self.last_repair_gain = 0.0

    def apply_repair(self, granted: float, essence_per_integrity_mass: float) -> float:
        """Turn `granted` structural essence into integrity. Returns integrity gained.

        The inverse of `repair_demand`, deliberately: a part granted 60% of what it
        asked for repairs 60% as much, because the same expression is being read
        backwards. **0.0 is not a special case** — a destroyed part repairs from 0.0
        exactly like any other value; nothing here treats it as terminal.

        `last_repair_essence` records what was *granted*, not what the gain implies.
        The two are equal by construction — the caller never grants more than
        `repair_demand` asked for — and recording the grant is what makes them
        *comparable*: the invariant harness asserts the crossing balances by checking
        the granted essence against the integrity that appeared, so a record derived
        from the gain would agree with itself no matter what storage did."""
        if granted <= 0.0 or essence_per_integrity_mass <= 0.0:
            return 0.0
        before = self.structural_integrity
        gained = granted / (self.mass() * essence_per_integrity_mass)
        after = self._set_integrity(before + gained)
        self.last_repair_essence += granted
        self.last_repair_gain += after - before
        return after - before

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
        mass: float = DEFAULT_LEG_MASS,
    ) -> None:
        # Water is the *function* element; Earth (the base-class default) is the
        # structural one. A leg works with Water and is built out of Earth.
        super().__init__(part_id, r, theta, ElementType.WATER, mass)
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
            # Same arithmetic as before, through the base class's one clamp site.
            # Repair is on `BodyPart`; nothing about *how* a leg degrades changed.
            self._set_integrity(
                self.structural_integrity - shortfall * LEG_INTEGRITY_DEGRADE_SCALE
            )
