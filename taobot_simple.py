from __future__ import annotations

import copy
import math
import random
from typing import TYPE_CHECKING

from common import ELEMENT_LIST, ElementType
from math_utils import torus_direction, torus_distance, wrap_position

if TYPE_CHECKING:
    from world import World

STARVATION_DAMAGE_SCALE: float = 10.0

DEFAULT_PARAMS: dict = {
    "sensing_range": 6.0,
    "speed": 1.5,
    "collect_rate": 2.0,
    "affinity": {e.name: 1.0 for e in ElementType},
    "hazard_avoidance_range": 4.0,
    "storage_capacity": {e.name: 20.0 for e in ElementType},
    "metabolic_rate": {
        "WOOD": 0.02,
        "WATER": 0.02,
        "METAL": 0.01,
        "FIRE": 0.015,
        "EARTH": 0.01,
    },
    "collect_radius": 1.0,
    "flee_health_threshold": 0.25,
    "max_health": 100.0,
    "random_walk_turn_rate": 0.4,
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
        "flee_health_threshold": 0.5,
        "hazard_avoidance_range": 7.0,
    },
    "hoarder": {
        "speed": 0.8,
        "collect_rate": 5.0,
        "storage_capacity": {e.name: 40.0 for e in ElementType},
    },
}


def _merge_params(overrides: dict | None) -> dict:
    """Deep-merge overrides onto DEFAULT_PARAMS."""
    merged = copy.deepcopy(DEFAULT_PARAMS)
    if not overrides:
        return merged
    for k, v in overrides.items():
        if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


class TaobotSimple:
    def __init__(self, x: float, y: float, entity_id: int, params: dict | None = None) -> None:
        self.x = x
        self.y = y
        self.entity_id = entity_id
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
        self.metabolic_rate: dict[ElementType, float] = {
            ElementType[k]: v for k, v in p["metabolic_rate"].items()
        }
        self.collect_radius: float = p["collect_radius"]
        self.flee_health_threshold: float = p["flee_health_threshold"]
        self.max_health: float = p["max_health"]
        self.random_walk_turn_rate: float = p["random_walk_turn_rate"]

        # Normalize affinities so they sum to 1
        total = sum(self.affinity.values())
        if total > 0:
            self.affinity = {k: v / total for k, v in self.affinity.items()}

        # Runtime state
        self.health: float = self.max_health
        self.storage: dict[ElementType, float] = {e: 0.0 for e in ELEMENT_LIST}
        self.behavior_state: str = "searching"
        self.target_entity_id: int | None = None
        self.age_ticks: int = 0
        self.resources_collected: float = 0.0

    # --- Main tick ---

    def tick(self, world: "World") -> None:
        nearby_resources, nearby_hazards = self._sense(world)
        self._decide(nearby_resources, nearby_hazards, world)
        self._act(world)
        self._metabolize()
        self.age_ticks += 1

    # --- Sense ---

    def _sense(self, world: "World") -> tuple:
        resources = world.query_resources(self.x, self.y, self.sensing_range)
        hazards = world.query_hazards(self.x, self.y, self.sensing_range)
        return resources, hazards

    # --- Decide ---

    def _decide(self, nearby_resources: list, nearby_hazards: list, world: "World") -> None:
        ww, wh = world.config.width, world.config.height

        # Step 1: FLEE — low health
        if self.health / self.max_health < self.flee_health_threshold:
            self.behavior_state = "fleeing"
            if nearby_hazards:
                nearest = nearby_hazards[0]
                dx, dy = torus_direction(nearest.x, nearest.y, self.x, self.y, ww, wh)
                if dx != 0.0 or dy != 0.0:
                    self.heading = math.atan2(dy, dx)
            else:
                self.heading += random.uniform(-0.3, 0.3)
            self.target_entity_id = None
            return

        # Step 2: HAZARD AVOIDANCE — hazard within avoidance range
        close_hazards = [
            h for h in nearby_hazards
            if torus_distance(self.x, self.y, h.x, h.y, ww, wh) < self.hazard_avoidance_range
        ]
        if close_hazards:
            nearest = close_hazards[0]
            self.behavior_state = "fleeing"
            dx, dy = torus_direction(nearest.x, nearest.y, self.x, self.y, ww, wh)
            if dx != 0.0 or dy != 0.0:
                self.heading = math.atan2(dy, dx)
            self.target_entity_id = None
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
                    self.heading = math.atan2(dy, dx)
                return

        # Step 5: SEARCH — random walk
        self.behavior_state = "searching"
        self.target_entity_id = None
        self.heading += random.uniform(-self.random_walk_turn_rate, self.random_walk_turn_rate)
        self.heading %= 2 * math.pi

    # --- Act ---

    def _act(self, world: "World") -> None:
        if self.behavior_state == "collecting" and self.target_entity_id is not None:
            resource = world._resources.get(self.target_entity_id)
            if resource is not None and resource.is_alive:
                elem = resource.element_type
                remaining_cap = self.storage_capacity[elem] - self.storage[elem]
                if remaining_cap <= 0.0:
                    # Storage full for this element — stop collecting, find another target
                    self.target_entity_id = None
                    self.behavior_state = "searching"
                else:
                    amount = min(self.collect_rate, remaining_cap)
                    actual = world.collect_resource(self, resource, amount)
                    self.storage[resource.element_type] += actual
                    self.resources_collected += actual
            else:
                self.target_entity_id = None
                self.behavior_state = "searching"
        else:
            # Move along heading
            dx = math.cos(self.heading) * self.speed
            dy = math.sin(self.heading) * self.speed
            new_x, new_y = wrap_position(
                self.x + dx, self.y + dy, world.config.width, world.config.height
            )
            self.x = new_x
            self.y = new_y
            world._taobot_hash.register(self.entity_id, self.x, self.y)

    # --- Metabolize ---

    def _metabolize(self) -> None:
        for element in ELEMENT_LIST:
            rate = self.metabolic_rate[element]
            if self.storage[element] >= rate:
                self.storage[element] -= rate
            else:
                deficit = rate - self.storage[element]
                self.storage[element] = 0.0
                self.health -= deficit * STARVATION_DAMAGE_SCALE

    # --- Metrics ---

    @property
    def fitness_score(self) -> float:
        return self.resources_collected / max(1, self.age_ticks)

    def get_state(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "x": self.x,
            "y": self.y,
            "health": self.health,
            "max_health": self.max_health,
            "behavior_state": self.behavior_state,
            "storage": {e.name: self.storage[e] for e in ELEMENT_LIST},
            "storage_capacity": {e.name: self.storage_capacity[e] for e in ELEMENT_LIST},
            "fitness_score": self.fitness_score,
            "age_ticks": self.age_ticks,
            "heading": self.heading,
            "speed": self.speed,
            "sensing_range": self.sensing_range,
            "affinity": {e.name: self.affinity[e] for e in ELEMENT_LIST},
        }
