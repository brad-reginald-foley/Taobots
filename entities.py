from dataclasses import dataclass, field

from common import ElementType


@dataclass
class Entity:
    x: float
    y: float
    element_type: ElementType
    entity_id: int


@dataclass
class Resource(Entity):
    max_amount: float = 10.0
    amount: float = field(init=False)
    alive: bool = field(init=False, default=True)
    respawn_ticks_remaining: int = field(init=False, default=0)
    _respawn_delay: int = field(init=False, default=300)

    def __post_init__(self) -> None:
        self.amount = self.max_amount

    def set_respawn_delay(self, delay: int) -> None:
        self._respawn_delay = delay

    def deplete(self, amount: float) -> float:
        """Remove up to amount. Sets alive=False when depleted. Returns actual removed."""
        actual = min(amount, self.amount)
        self.amount -= actual
        if self.amount <= 0.0:
            self.amount = 0.0
            self.alive = False
            self.respawn_ticks_remaining = self._respawn_delay
        return actual

    def tick_respawn(self) -> bool:
        """Decrement respawn timer. Returns True if resource just revived."""
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
        return self.alive


@dataclass
class Hazard(Entity):
    damage_per_tick: float = 5.0
    # Element type of damage dealt — defaults to element_type at init
    damage_element_type: ElementType = field(init=False)

    def __post_init__(self) -> None:
        self.damage_element_type = self.element_type
