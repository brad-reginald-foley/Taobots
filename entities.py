from dataclasses import dataclass, field

from common import ElementType


@dataclass
class Entity:
    """Base for all world objects. Holds shared position and identity fields."""

    x: float
    y: float
    element_type: ElementType
    entity_id: int


@dataclass
class Resource(Entity):
    """A collectable resource node that depletes and respawns after a delay."""

    max_amount: float = 10.0
    amount: float = field(init=False)
    alive: bool = field(init=False, default=True)
    respawn_ticks_remaining: int = field(init=False, default=0)
    _respawn_delay: int = field(init=False, default=300)

    def __post_init__(self) -> None:
        """Start fully stocked."""
        self.amount = self.max_amount

    def set_respawn_delay(self, delay: int) -> None:
        """Set how many ticks the resource waits before reviving after depletion."""
        self._respawn_delay = delay

    def deplete(self, amount: float) -> float:
        """Remove up to `amount` units. Marks the resource dead when fully emptied.

        Returns the amount actually removed (may be less than requested if nearly empty)."""
        actual = min(amount, self.amount)
        self.amount -= actual
        if self.amount <= 0.0:
            self.amount = 0.0
            self.alive = False
            self.respawn_ticks_remaining = self._respawn_delay
        return actual

    def tick_respawn(self) -> bool:
        """Advance the respawn timer by one tick. Returns True the tick the resource revives."""
        if self.alive:
            return False
        self.respawn_ticks_remaining -= 1
        if self.respawn_ticks_remaining <= 0:
            self.alive = True
            self.amount = self.max_amount
            self.respawn_ticks_remaining = 0
            return True
        return False

    @property
    def is_alive(self) -> bool:
        """True if the resource still has supply available."""
        return self.alive


@dataclass
class Hazard(Entity):
    """A permanent environmental hazard that damages taobots in contact.

    `damage_element_type` is unused in Phase 1 but reserved for chi chemistry in Phase 2,
    where hazard damage will interact with elemental affinities."""

    damage_per_tick: float = 1.0
    damage_element_type: ElementType = field(init=False)

    def __post_init__(self) -> None:
        """Default damage element matches the hazard's own element."""
        self.damage_element_type = self.element_type
