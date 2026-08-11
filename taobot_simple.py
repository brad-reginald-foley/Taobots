from __future__ import annotations

import copy
import math
import random
from typing import TYPE_CHECKING

from body_factory import BodyFactory
from body_parts import BodyPart, LegPart
from common import ELEMENT_LIST, ElementType
from math_utils import torus_direction, torus_distance, wrap_position

if TYPE_CHECKING:
    from world import World

# ---------------------------------------------------------------------------
# Organ system constants
# ---------------------------------------------------------------------------

ORGAN_MAX: float = 100.0

# Per tick: organ loses this much when its storage element is empty
ORGAN_DEGRADE_RATE: float = 1.0
# Per tick: organ gains this much when storage is above the regen threshold
ORGAN_REGEN_RATE: float = 0.2
# Storage must be above this fraction of capacity to trigger regeneration
REGEN_STORAGE_THRESHOLD: float = 0.3

# Earth collapse → Wood crisis conditions
WOOD_CRISIS_EARTH_THRESHOLD: float = 20.0   # Earth organ below this…
WOOD_CRISIS_STORAGE_FRACTION: float = 0.1   # …AND total storage below this fraction of capacity
WOOD_CRISIS_DRAIN: float = 0.1              # Wood organ lost per tick during crisis

# Fire organ below this value → locked into searching (random walk only)
FIRE_LOCKOUT_THRESHOLD: float = 20.0

# Base storage drain per tick for each organ (drawn from the governing element's storage)
# Water drain is further scaled by current speed fraction (locomotion is activity-dependent).
# Wood drain covers structural maintenance; Metal covers armor upkeep.
ORGAN_STORAGE_DRAIN: dict[str, float] = {
    "FIRE":  0.015,
    "WATER": 0.012,
    "EARTH": 0.010,
    "WOOD":  0.004,
    "METAL": 0.002,
}

# Generative (Sheng) cycle: each element converts a fraction of its storage into the next.
# All five transfers are computed simultaneously from pre-tick values to avoid directional bias.
CYCLE_RATE: float = 0.001       # fraction of source storage converted per tick
CYCLE_EFFICIENCY: float = 0.8   # fraction that arrives at target (20% lost per step)

CYCLE_SEQUENCE: list[tuple[ElementType, ElementType]] = [
    (ElementType.WATER, ElementType.WOOD),
    (ElementType.WOOD,  ElementType.FIRE),
    (ElementType.FIRE,  ElementType.EARTH),
    (ElementType.EARTH, ElementType.METAL),
    (ElementType.METAL, ElementType.WATER),
]

DEFAULT_PARAMS: dict = {
    "sensing_range": 6.0,
    "speed": 1.5,
    "collect_rate": 2.0,
    "affinity": {e.name: 1.0 for e in ElementType},
    "hazard_avoidance_range": 4.0,
    "storage_capacity": {e.name: 20.0 for e in ElementType},
    "collect_radius": 1.0,
    "flee_wood_threshold": 25.0,
    "random_walk_turn_rate": 0.4,
    # Phase 2 body parts. Two symmetric legs at ±0.4 rad, both pushing forward (phi=0).
    # With phi=0 each leg contributes exactly T to forward speed → T_base = speed/2 = 0.75.
    # max_thrust=1.5 covers the fastest archetype (wanderer speed=2.2, T_base=1.1)
    # and leaves headroom for differential steering corrections.
    "body": [
        {"type": "leg", "r": 1.5, "theta": 0.4, "phi": 0.0,
         "max_thrust": 1.5, "capacity": 4.0, "drain_max": 0.005},
        {"type": "leg", "r": 1.5, "theta": -0.4, "phi": 0.0,
         "max_thrust": 1.5, "capacity": 4.0, "drain_max": 0.005},
    ],
}

# Archetypes — cycled evenly at world initialization
ARCHETYPES: dict[str, dict] = {
    "wanderer": {
        "speed": 2.2,
        "sensing_range": 8.0,
    },
    "specialist": {
        "speed": 1.0,
        "affinity": {"WOOD": 0.5, "WATER": 0.5, "METAL": 0.5, "FIRE": 4.0, "EARTH": 0.5},
        "storage_capacity": {
            "WOOD": 10.0, "WATER": 10.0, "METAL": 10.0, "FIRE": 40.0, "EARTH": 10.0,
        },
    },
    "survivor": {
        "speed": 1.4,
        "flee_wood_threshold": 50.0,
        "hazard_avoidance_range": 7.0,
    },
    "hoarder": {
        "speed": 0.8,
        "collect_rate": 5.0,
        "storage_capacity": {e.name: 40.0 for e in ElementType},
    },
}


def _merge_params(overrides: dict | None) -> dict:
    """Deep-merge archetype overrides onto DEFAULT_PARAMS.

    Top-level scalar values replace the default; nested dicts (affinity,
    storage_capacity) are merged key-by-key so an archetype only needs to
    specify the keys it changes."""
    merged = copy.deepcopy(DEFAULT_PARAMS)
    if not overrides:
        return merged
    for k, v in overrides.items():
        if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def _angle_diff(a: float, b: float) -> float:
    """Signed angular difference (a − b) wrapped to (−π, π]."""
    d = (a - b) % (2 * math.pi)
    return d - 2 * math.pi if d > math.pi else d


class TaobotSimple:
    """Rule-based taobot for Phase 1. Behaviour is driven by scalar parameters;
    no neural networks or chi pools yet.

    Each tick: sense → decide → act → metabolize.

    Organ system (replaces single health value):
      Wood   — body structure; death condition at 0; damaged by Metal attacks
      Fire   — nervous system; governs sensing range; at 0 → locked to searching
      Water  — locomotion; governs speed; at 0 → immobile
      Earth  — metabolism/meridians; drain multiplier rises as it degrades
      Metal  — armor; absorbs incoming damage before Wood takes it

    Behavioral states (in priority order):
      fleeing    — Wood organ critical or hazard too close; steer away from danger
      seeking    — resource visible but not yet adjacent; head toward best target
      collecting — adjacent to target resource; extract up to collect_rate/tick
      searching  — nothing visible (or Fire too low to see); correlated random walk
    """

    def __init__(
        self,
        x: float,
        y: float,
        entity_id: int,
        params: dict | None = None,
        archetype: str = "default",
    ) -> None:
        """Create a taobot at (x, y) with the given entity_id.

        `params` is an optional archetype override dict (see ARCHETYPES).
        `archetype` is the human-readable name stored for logging."""
        self.x = x
        self.y = y
        self.entity_id = entity_id
        self.archetype: str = archetype
        self.heading: float = random.uniform(0, 2 * math.pi)

        p = _merge_params(params)
        self.sensing_range: float = p["sensing_range"]
        self.speed: float = p["speed"]
        self.collect_rate: float = p["collect_rate"]
        self.affinity: dict[ElementType, float] = {
            ElementType[k]: v for k, v in p["affinity"].items()
        }
        self.hazard_avoidance_range: float = p["hazard_avoidance_range"]
        self.storage_capacity: dict[ElementType, float] = {
            ElementType[k]: v for k, v in p["storage_capacity"].items()
        }
        self.collect_radius: float = p["collect_radius"]
        self.flee_wood_threshold: float = p["flee_wood_threshold"]
        self.random_walk_turn_rate: float = p["random_walk_turn_rate"]

        # Normalize affinities to sum=1 so absolute values don't affect scoring
        # magnitude — only relative preference between elements matters.
        total = sum(self.affinity.values())
        if total > 0:
            self.affinity = {k: v / total for k, v in self.affinity.items()}

        # Organs — all start at full integrity
        self.organs: dict[ElementType, float] = {e: ORGAN_MAX for e in ELEMENT_LIST}

        # Phase 2 body parts
        self.body_parts: list[BodyPart] = BodyFactory.make_parts(p["body"])
        self.legs: list[LegPart] = [bp for bp in self.body_parts if isinstance(bp, LegPart)]

        # Steering geometry derived from leg layout (phi-aware)
        self._desired_heading: float = self.heading
        self._moment_of_inertia: float = sum(leg.r ** 2 for leg in self.legs)
        # Leverage = r * sin(phi - theta): torque produced per unit thrust, signed
        self._sum_leverage_sq: float = sum(
            (leg.r * math.sin(leg.phi - leg.theta)) ** 2 for leg in self.legs
        )
        # Max turn rate: all legs at ±max_thrust, signs chosen to maximise torque
        self.max_turn_rate: float = (
            sum(leg.r * leg.max_thrust * abs(math.sin(leg.phi - leg.theta)) for leg in self.legs)
            / max(1e-9, self._moment_of_inertia)
        )

        # Storage and collection state
        self.storage: dict[ElementType, float] = {e: 0.0 for e in ELEMENT_LIST}
        self.behavior_state: str = "searching"
        self.target_entity_id: int | None = None
        self.age_ticks: int = 0
        self.resources_collected: float = 0.0

        # Lifetime tracking
        self.resources_by_element: dict[ElementType, float] = {e: 0.0 for e in ELEMENT_LIST}
        self.distance_moved: float = 0.0
        self.damage_taken_total: float = 0.0

        # Interval tracking (reset externally every N ticks by RunLogger)
        self._interval_resources: dict[ElementType, float] = {e: 0.0 for e in ELEMENT_LIST}
        self._interval_damage: float = 0.0

    # --- Main tick ---

    def tick(self, world: "World") -> None:
        """Advance one simulation tick: sense, decide, act, body, metabolize, cycle."""
        nearby_resources, nearby_hazards = self._sense(world)
        self._decide(nearby_resources, nearby_hazards, world)
        self._act(world)
        self._tick_body_parts()
        self._metabolize()
        self._cycle_elements()
        self.age_ticks += 1

    # --- Sense ---

    def _sense(self, world: "World") -> tuple:
        """Query the world for resources and hazards within effective sensing range.

        Sensing range is scaled by Fire organ integrity — a degraded nervous system
        sees less of the world. Returns (resources, hazards), each sorted nearest-first."""
        fire_frac = self.organs[ElementType.FIRE] / ORGAN_MAX
        effective_range = self.sensing_range * fire_frac
        resources = world.query_resources(self.x, self.y, effective_range)
        hazards = world.query_hazards(self.x, self.y, effective_range)
        return resources, hazards

    # --- Decide ---

    def _decide(self, nearby_resources: list, nearby_hazards: list, world: "World") -> None:
        """Update behavior_state and heading based on current surroundings.

        Priority order:
          1. Flee — Wood organ critical or hazard within avoidance range
          2. Fire lockout — nervous system too degraded to do anything but random walk
          3. Collect — already adjacent to a live target resource
          4. Seek — pick the best visible resource and head toward it
          5. Search — random walk when nothing is visible
        """
        ww, wh = world.config.width, world.config.height

        # Step 1: FLEE — critical Wood organ (structural integrity near zero)
        if self.organs[ElementType.WOOD] < self.flee_wood_threshold:
            self.behavior_state = "fleeing"
            if nearby_hazards:
                nearest = nearby_hazards[0]
                dx, dy = torus_direction(nearest.x, nearest.y, self.x, self.y, ww, wh)
                if dx != 0.0 or dy != 0.0:
                    self._desired_heading = math.atan2(dy, dx)
            else:
                self._desired_heading += random.uniform(-0.3, 0.3)
            self.target_entity_id = None
            return

        # Step 1b: HAZARD AVOIDANCE — hazard within avoidance range
        close_hazards = [
            h for h in nearby_hazards
            if torus_distance(self.x, self.y, h.x, h.y, ww, wh) < self.hazard_avoidance_range
        ]
        if close_hazards:
            nearest = close_hazards[0]
            self.behavior_state = "fleeing"
            dx, dy = torus_direction(nearest.x, nearest.y, self.x, self.y, ww, wh)
            if dx != 0.0 or dy != 0.0:
                self._desired_heading = math.atan2(dy, dx)
            self.target_entity_id = None
            return

        # Step 2: FIRE LOCKOUT — nervous system too degraded to sense or decide
        if self.organs[ElementType.FIRE] < FIRE_LOCKOUT_THRESHOLD:
            self.behavior_state = "searching"
            self.target_entity_id = None
            turn = self.random_walk_turn_rate
            self._desired_heading += random.uniform(-turn, turn)
            self._desired_heading %= 2 * math.pi
            return

        # Step 3: COLLECTION CHECK — adjacent to current target?
        if self.target_entity_id is not None:
            target = world._resources.get(self.target_entity_id)
            if target is not None and target.is_alive:
                dist = torus_distance(self.x, self.y, target.x, target.y, ww, wh)
                if dist <= self.collect_radius:
                    self.behavior_state = "collecting"
                    return
            else:
                self.target_entity_id = None

        # Step 4: SEEK BEST RESOURCE
        if nearby_resources:
            best_resource = None
            best_score = -1.0
            for r in nearby_resources:
                dist = torus_distance(self.x, self.y, r.x, r.y, ww, wh)
                score = self.affinity.get(r.element_type, 0.0) / max(0.1, dist)
                if score > best_score:
                    best_score = score
                    best_resource = r
            if best_resource is not None:
                self.behavior_state = "seeking"
                self.target_entity_id = best_resource.entity_id
                dx, dy = torus_direction(self.x, self.y, best_resource.x, best_resource.y, ww, wh)
                if dx != 0.0 or dy != 0.0:
                    self._desired_heading = math.atan2(dy, dx)
                return

        # Step 5: SEARCH — random walk
        self.behavior_state = "searching"
        self.target_entity_id = None
        turn = self.random_walk_turn_rate
        self._desired_heading += random.uniform(-turn, turn)
        self._desired_heading %= 2 * math.pi

    # --- Act ---

    def _act(self, world: "World") -> None:
        """Execute the current behavior: steer, collect, or move.

        Steering uses differential thrust allocation: each leg's phi determines its
        torque leverage and the general controller distributes thrust corrections to
        achieve the desired turn without a separate lateral-thrust axis.
        """
        n = len(self.legs)
        for leg in self.legs:
            leg.set_thrust(0.0)

        # Turn rate cap: advance heading toward desired at most max_turn_rate per tick
        diff = _angle_diff(self._desired_heading, self.heading)
        turn = max(-self.max_turn_rate, min(self.max_turn_rate, diff))
        self.heading = (self.heading + turn) % (2 * math.pi)

        collecting = False
        if self.behavior_state == "collecting" and self.target_entity_id is not None:
            resource = world._resources.get(self.target_entity_id)
            if resource is not None and resource.is_alive:
                elem = resource.element_type
                remaining_cap = self.storage_capacity[elem] - self.storage[elem]
                if remaining_cap <= 0.0:
                    self.target_entity_id = None
                    self.behavior_state = "searching"
                else:
                    amount = min(self.collect_rate, remaining_cap)
                    actual = world.collect_resource(self, resource, amount)
                    self.storage[elem] += actual
                    self.resources_collected += actual
                    self.resources_by_element[elem] += actual
                    self._interval_resources[elem] += actual
                    collecting = True
            else:
                self.target_entity_id = None
                self.behavior_state = "searching"

        if n > 0:
            # T_base=0 when collecting: differential correction produces pure rotation
            # (~zero net force for bilateral symmetric bodies) so the bot steers in place.
            t_base = 0.0 if collecting else self.speed / n
            if self._sum_leverage_sq > 1e-9:
                for leg in self.legs:
                    leverage = leg.r * math.sin(leg.phi - leg.theta)
                    correction = turn * self._moment_of_inertia * leverage / self._sum_leverage_sq
                    leg.set_thrust(t_base + correction)
            else:
                for leg in self.legs:
                    leg.set_thrust(t_base)

        if not collecting:
            net_fx = sum(leg.force_vector(self.heading)[0] for leg in self.legs)
            net_fy = sum(leg.force_vector(self.heading)[1] for leg in self.legs)
            dx, dy = net_fx, net_fy
            self.distance_moved += math.sqrt(dx * dx + dy * dy)
            new_x, new_y = wrap_position(
                self.x + dx, self.y + dy, world.config.width, world.config.height
            )
            self.x = new_x
            self.y = new_y
            world._taobot_hash.register(self.entity_id, self.x, self.y)

    # --- Body parts ---

    def _tick_body_parts(self) -> None:
        """Replenish each body part's reserve from taobot storage, then tick it."""
        for part in self.body_parts:
            absorbed = part.replenish(self.storage[part.element])
            self.storage[part.element] -= absorbed
            part.tick()

    # --- Metabolize ---

    def _drain_organ(self, element: ElementType, drain: float) -> None:
        """Draw `drain` units from storage for the given organ's element.

        If storage is sufficient, the cost is paid. If the remaining storage then
        exceeds the regen threshold, the organ regenerates slightly.
        If storage is insufficient, it is zeroed and the organ degrades."""
        if self.storage[element] >= drain:
            self.storage[element] -= drain
            regen_floor = REGEN_STORAGE_THRESHOLD * self.storage_capacity[element]
            if self.storage[element] > regen_floor:
                self.organs[element] = min(ORGAN_MAX, self.organs[element] + ORGAN_REGEN_RATE)
        else:
            self.storage[element] = 0.0
            self.organs[element] = max(0.0, self.organs[element] - ORGAN_DEGRADE_RATE)

    def _metabolize(self) -> None:
        """Run one tick of organ metabolism.

        Earth organ integrity sets a global drain multiplier: at full Earth all
        drains are normal; at zero Earth all drains double. This multiplier applies
        to Fire, Earth, Wood, and Metal organs.

        Water storage is consumed by LegParts (in _tick_body_parts) and is not drained here.

        Wood crisis: if Earth is critically low AND total storage is nearly empty,
        systemic metabolic failure directly damages the Wood organ on top of starvation."""
        earth_mult = 1.0 + (ORGAN_MAX - self.organs[ElementType.EARTH]) / ORGAN_MAX

        self._drain_organ(
            ElementType.FIRE,
            ORGAN_STORAGE_DRAIN["FIRE"] * earth_mult,
        )

        # Water storage is now drained by LegParts in _tick_body_parts(); no abstract drain here.

        self._drain_organ(
            ElementType.EARTH,
            ORGAN_STORAGE_DRAIN["EARTH"] * earth_mult,
        )

        self._drain_organ(
            ElementType.WOOD,
            ORGAN_STORAGE_DRAIN["WOOD"] * earth_mult,
        )

        self._drain_organ(
            ElementType.METAL,
            ORGAN_STORAGE_DRAIN["METAL"] * earth_mult,
        )

        # Wood crisis: systemic failure when metabolism has collapsed and storage is empty
        total_storage = sum(self.storage.values())
        total_capacity = sum(self.storage_capacity.values())
        crisis = (
            self.organs[ElementType.EARTH] < WOOD_CRISIS_EARTH_THRESHOLD
            and total_storage < WOOD_CRISIS_STORAGE_FRACTION * total_capacity
        )
        if crisis:
            self.organs[ElementType.WOOD] = max(
                0.0, self.organs[ElementType.WOOD] - WOOD_CRISIS_DRAIN
            )

    # --- External callbacks ---

    def _cycle_elements(self) -> None:
        """Convert a fraction of each element's storage into the next in the generative cycle.

        All five transfers are computed from pre-tick storage values then applied
        simultaneously, preventing directional bias within a single tick. If a target
        slot is at capacity the transfer is suppressed and the source is preserved."""
        transfers: list[tuple[ElementType, ElementType, float, float]] = []
        for source, target in CYCLE_SEQUENCE:
            amount_out = CYCLE_RATE * self.storage[source]
            room = self.storage_capacity[target] - self.storage[target]
            produced = min(amount_out * CYCLE_EFFICIENCY, room)
            if produced <= 0.0:
                continue
            spent = produced / CYCLE_EFFICIENCY
            transfers.append((source, target, spent, produced))
        for source, target, spent, produced in transfers:
            self.storage[source] = max(0.0, self.storage[source] - spent)
            self.storage[target] += produced

    # --- External callbacks ---

    def record_damage(self, amount: float) -> None:
        """Apply incoming damage, routed through Metal armor before reaching Wood.

        Metal organ acts as a fractional damage absorber: at full Metal integrity
        no damage reaches Wood; at zero Metal the full amount hits Wood directly.
        Damage totals are always tracked at face value for logging."""
        self.damage_taken_total += amount
        self._interval_damage += amount
        metal_frac = self.organs[ElementType.METAL] / ORGAN_MAX
        wood_damage = amount * (1.0 - metal_frac)
        self.organs[ElementType.WOOD] = max(0.0, self.organs[ElementType.WOOD] - wood_damage)

    def reset_interval(self) -> None:
        """Zero the interval accumulators. Called by RunLogger every FOCAL_INTERVAL ticks."""
        self._interval_resources = {e: 0.0 for e in ELEMENT_LIST}
        self._interval_damage = 0.0

    # --- Metrics ---

    @property
    def fitness_score(self) -> float:
        """Resources collected per tick lived. Used as the Phase 4 selection signal."""
        return self.resources_collected / max(1, self.age_ticks)

    def get_state(self) -> dict:
        """Return a serialisable snapshot of all observable state.

        Used by the renderer inspector and the focal-individual logger."""
        return {
            "entity_id": self.entity_id,
            "x": self.x,
            "y": self.y,
            "organs": {e.name: round(self.organs[e], 2) for e in ELEMENT_LIST},
            "behavior_state": self.behavior_state,
            "storage": {e.name: self.storage[e] for e in ELEMENT_LIST},
            "storage_capacity": {e.name: self.storage_capacity[e] for e in ELEMENT_LIST},
            "fitness_score": self.fitness_score,
            "age_ticks": self.age_ticks,
            "heading": self.heading,
            "speed": self.speed,
            "sensing_range": self.sensing_range,
            "affinity": {e.name: self.affinity[e] for e in ELEMENT_LIST},
            "resources_by_element": {e.name: self.resources_by_element[e] for e in ELEMENT_LIST},
            "distance_moved": self.distance_moved,
            "damage_taken_total": self.damage_taken_total,
            "legs": [
                {
                    "index": i,
                    "theta_deg": round(math.degrees(leg.theta), 1),
                    "phi_deg": round(math.degrees(leg.phi), 1),
                    "reserve": round(leg.reserve, 3),
                    "capacity": leg.capacity,
                    "integrity": round(leg.structural_integrity, 3),
                    "thrust": round(leg._thrust, 4),
                    "max_thrust": leg.max_thrust,
                }
                for i, leg in enumerate(self.legs)
            ],
        }
