from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from common import ELEMENT_LIST, ElementType
from entities import Hazard, Resource
from math_utils import torus_distance

if TYPE_CHECKING:
    from taobot_simple import TaobotSimple


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ResourceConfig:
    initial_count: int
    respawn_delay_ticks: int
    spawn_weights: dict[ElementType, float]

    def __post_init__(self) -> None:
        total = sum(self.spawn_weights.values())
        if total <= 0:
            raise ValueError("spawn_weights must have at least one positive value")
        self.spawn_weights = {k: v / total for k, v in self.spawn_weights.items()}


@dataclass
class HazardConfig:
    initial_count: int
    spawn_weights: dict[ElementType, float]

    def __post_init__(self) -> None:
        total = sum(self.spawn_weights.values())
        if total <= 0:
            raise ValueError("spawn_weights must have at least one positive value")
        self.spawn_weights = {k: v / total for k, v in self.spawn_weights.items()}


@dataclass
class TaobotConfig:
    initial_count: int
    target_population: int


@dataclass
class ChemistryConfig:
    degrade_rate: float  # unused in Phase 1; reserved for Phase 2


@dataclass
class WorldConfig:
    name: str
    width: int
    height: int
    resources: ResourceConfig
    hazards: HazardConfig
    taobots: TaobotConfig
    chemistry: ChemistryConfig

    @classmethod
    def from_json(cls, path: str | Path) -> "WorldConfig":
        with open(path) as f:
            data = json.load(f)

        for key in ("name", "world", "resources", "hazards", "taobots", "chemistry"):
            if key not in data:
                raise ValueError(f"WorldConfig missing required key: '{key}'")

        def parse_weights(raw: dict[str, float]) -> dict[ElementType, float]:
            result: dict[ElementType, float] = {}
            for e in ELEMENT_LIST:
                result[e] = float(raw.get(e.name, 0.0))
            return result

        r = data["resources"]
        h = data["hazards"]
        t = data["taobots"]
        w = data["world"]
        c = data["chemistry"]

        return cls(
            name=data["name"],
            width=int(w["width"]),
            height=int(w["height"]),
            resources=ResourceConfig(
                initial_count=int(r["initial_count"]),
                respawn_delay_ticks=int(r["respawn_delay_ticks"]),
                spawn_weights=parse_weights(r["spawn_weights"]),
            ),
            hazards=HazardConfig(
                initial_count=int(h["initial_count"]),
                spawn_weights=parse_weights(h["spawn_weights"]),
            ),
            taobots=TaobotConfig(
                initial_count=int(t["initial_count"]),
                target_population=int(t["target_population"]),
            ),
            chemistry=ChemistryConfig(
                degrade_rate=float(c["degrade_rate"]),
            ),
        )


# ---------------------------------------------------------------------------
# Spatial hash (internal)
# ---------------------------------------------------------------------------

class SpatialHash:
    BUCKET_W: int = 8
    BUCKET_H: int = 8

    def __init__(self, world_w: int, world_h: int) -> None:
        import math
        self._n_bx: int = math.ceil(world_w / self.BUCKET_W)
        self._n_by: int = math.ceil(world_h / self.BUCKET_H)
        self._world_w = world_w
        self._world_h = world_h
        self._grid: dict[tuple[int, int], set[int]] = {}
        self._positions: dict[int, tuple[float, float]] = {}

    def _bucket(self, x: float, y: float) -> tuple[int, int]:
        bx = int(x / self.BUCKET_W) % self._n_bx
        by = int(y / self.BUCKET_H) % self._n_by
        return (bx, by)

    def register(self, entity_id: int, x: float, y: float) -> None:
        if entity_id in self._positions:
            old_bucket = self._bucket(*self._positions[entity_id])
            if old_bucket in self._grid:
                self._grid[old_bucket].discard(entity_id)
        new_bucket = self._bucket(x, y)
        self._grid.setdefault(new_bucket, set()).add(entity_id)
        self._positions[entity_id] = (x, y)

    def deregister(self, entity_id: int) -> None:
        if entity_id not in self._positions:
            return
        bucket = self._bucket(*self._positions[entity_id])
        if bucket in self._grid:
            self._grid[bucket].discard(entity_id)
        del self._positions[entity_id]

    def neighbors(
        self, x: float, y: float, radius: float, world_w: int, world_h: int
    ) -> set[int]:
        """Return entity_ids in buckets overlapping the bounding box.
        Conservative — callers must filter by exact torus_distance."""
        import math
        n_bx_span = math.ceil((radius * 2) / self.BUCKET_W) + 1
        n_by_span = math.ceil((radius * 2) / self.BUCKET_H) + 1

        center_bx = int(x / self.BUCKET_W)
        center_by = int(y / self.BUCKET_H)

        half_x = n_bx_span // 2
        half_y = n_by_span // 2

        result: set[int] = set()
        for dbx in range(-half_x, half_x + 1):
            for dby in range(-half_y, half_y + 1):
                bx = (center_bx + dbx) % self._n_bx
                by = (center_by + dby) % self._n_by
                bucket = (bx, by)
                if bucket in self._grid:
                    result |= self._grid[bucket]
        return result


# ---------------------------------------------------------------------------
# World
# ---------------------------------------------------------------------------

class World:
    def __init__(self, config: WorldConfig) -> None:
        self.config = config
        self.tick_count: int = 0
        self._next_id: int = 0

        self._resources: dict[int, Resource] = {}
        self._dead_resources: dict[int, Resource] = {}
        self._hazards: dict[int, Hazard] = {}
        self._taobots: dict[int, "TaobotSimple"] = {}

        self._entity_hash = SpatialHash(config.width, config.height)
        self._taobot_hash = SpatialHash(config.width, config.height)

    # --- Lifecycle ---

    def initialize(self) -> None:
        from taobot_simple import (  # noqa: F401 (avoid circular at module level)
            ARCHETYPES,
            TaobotSimple,
        )

        for _ in range(self.config.resources.initial_count):
            self.spawn_resource()

        for _ in range(self.config.hazards.initial_count):
            self.spawn_hazard()

        archetype_keys = list(ARCHETYPES.keys())
        for i in range(self.config.taobots.initial_count):
            archetype = archetype_keys[i % len(archetype_keys)]
            self.spawn_taobot(params=ARCHETYPES[archetype])

    def tick(self) -> None:
        self._respawn_tick()

        for taobot in list(self._taobots.values()):
            taobot.tick(self)

        self._apply_hazard_damage()
        self._check_taobot_deaths()

        # Phase 2: chi chemistry tick goes here (config.chemistry.degrade_rate)

        self.tick_count += 1

    # --- Spawning ---

    def _alloc_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _sample_element(self, weights: dict[ElementType, float]) -> ElementType:
        elements = list(weights.keys())
        probs = [weights[e] for e in elements]
        return random.choices(elements, weights=probs, k=1)[0]

    def spawn_resource(
        self,
        x: float | None = None,
        y: float | None = None,
        element_type: ElementType | None = None,
    ) -> Resource:
        if x is None:
            x = random.uniform(0, self.config.width)
        if y is None:
            y = random.uniform(0, self.config.height)
        if element_type is None:
            element_type = self._sample_element(self.config.resources.spawn_weights)

        eid = self._alloc_id()
        r = Resource(x=x, y=y, element_type=element_type, entity_id=eid)
        r.set_respawn_delay(self.config.resources.respawn_delay_ticks)
        self._resources[eid] = r
        self._entity_hash.register(eid, x, y)
        return r

    def spawn_hazard(
        self,
        x: float | None = None,
        y: float | None = None,
        element_type: ElementType | None = None,
    ) -> Hazard:
        if x is None:
            x = random.uniform(0, self.config.width)
        if y is None:
            y = random.uniform(0, self.config.height)
        if element_type is None:
            element_type = self._sample_element(self.config.hazards.spawn_weights)

        eid = self._alloc_id()
        h = Hazard(x=x, y=y, element_type=element_type, entity_id=eid)
        self._hazards[eid] = h
        self._entity_hash.register(eid, x, y)
        return h

    def spawn_taobot(
        self,
        params: dict | None = None,
        x: float | None = None,
        y: float | None = None,
    ) -> "TaobotSimple":
        from taobot_simple import TaobotSimple

        if x is None:
            x = random.uniform(0, self.config.width)
        if y is None:
            y = random.uniform(0, self.config.height)

        eid = self._alloc_id()
        t = TaobotSimple(x=x, y=y, entity_id=eid, params=params)
        self._taobots[eid] = t
        self._taobot_hash.register(eid, x, y)
        return t

    def remove_taobot(self, entity_id: int) -> None:
        self._taobots.pop(entity_id, None)
        self._taobot_hash.deregister(entity_id)

    # --- Internal tick steps ---

    def _respawn_tick(self) -> None:
        revived = []
        for eid, resource in self._dead_resources.items():
            if resource.tick_respawn():
                revived.append(eid)

        for eid in revived:
            resource = self._dead_resources.pop(eid)
            self._resources[eid] = resource
            self._entity_hash.register(eid, resource.x, resource.y)

    def _apply_hazard_damage(self) -> None:
        for taobot in self._taobots.values():
            nearby_ids = self._entity_hash.neighbors(
                taobot.x, taobot.y, 1.0, self.config.width, self.config.height
            )
            for eid in nearby_ids:
                if eid not in self._hazards:
                    continue
                hazard = self._hazards[eid]
                dist = torus_distance(
                    taobot.x, taobot.y, hazard.x, hazard.y,
                    self.config.width, self.config.height
                )
                if dist <= 1.0:
                    taobot.health = max(0.0, taobot.health - hazard.damage_per_tick)

    def _check_taobot_deaths(self) -> None:
        dead_ids = [eid for eid, t in self._taobots.items() if t.health <= 0.0]
        for eid in dead_ids:
            self.remove_taobot(eid)

        while len(self._taobots) < self.config.taobots.target_population:
            self.spawn_taobot()

    # --- Queries ---

    def query_resources(self, x: float, y: float, radius: float) -> list[Resource]:
        ww, wh = self.config.width, self.config.height
        candidate_ids = self._entity_hash.neighbors(x, y, radius, ww, wh)
        result = []
        for eid in candidate_ids:
            if eid not in self._resources:
                continue
            r = self._resources[eid]
            dist = torus_distance(x, y, r.x, r.y, self.config.width, self.config.height)
            if dist <= radius:
                result.append((dist, r))
        result.sort(key=lambda t: t[0])
        return [r for _, r in result]

    def query_hazards(self, x: float, y: float, radius: float) -> list[Hazard]:
        ww, wh = self.config.width, self.config.height
        candidate_ids = self._entity_hash.neighbors(x, y, radius, ww, wh)
        result = []
        for eid in candidate_ids:
            if eid not in self._hazards:
                continue
            h = self._hazards[eid]
            dist = torus_distance(x, y, h.x, h.y, self.config.width, self.config.height)
            if dist <= radius:
                result.append((dist, h))
        result.sort(key=lambda t: t[0])
        return [h for _, h in result]

    def query_taobots(
        self, x: float, y: float, radius: float, exclude_id: int | None = None
    ) -> list["TaobotSimple"]:
        ww, wh = self.config.width, self.config.height
        candidate_ids = self._taobot_hash.neighbors(x, y, radius, ww, wh)
        result = []
        for eid in candidate_ids:
            if eid not in self._taobots:
                continue
            if eid == exclude_id:
                continue
            t = self._taobots[eid]
            dist = torus_distance(x, y, t.x, t.y, self.config.width, self.config.height)
            if dist <= radius:
                result.append((dist, t))
        result.sort(key=lambda t: t[0])
        return [t for _, t in result]

    def collect_resource(
        self, taobot: "TaobotSimple", resource: Resource, amount: float
    ) -> float:
        actual = resource.deplete(amount)
        if not resource.is_alive:
            eid = resource.entity_id
            self._resources.pop(eid, None)
            self._entity_hash.deregister(eid)
            self._dead_resources[eid] = resource
        return actual

    # --- Accessors ---

    @property
    def resources(self) -> list[Resource]:
        return list(self._resources.values())

    @property
    def dead_resources(self) -> list[Resource]:
        return list(self._dead_resources.values())

    @property
    def hazards(self) -> list[Hazard]:
        return list(self._hazards.values())

    @property
    def taobots(self) -> list["TaobotSimple"]:
        return list(self._taobots.values())

    def get_stats(self) -> dict:
        taobots = self.taobots
        healths = [t.health for t in taobots] if taobots else [0.0]
        resource_counts = {e: 0 for e in ELEMENT_LIST}
        for r in self._resources.values():
            resource_counts[r.element_type] += 1

        return {
            "tick": self.tick_count,
            "n_taobots": len(taobots),
            "n_resources_alive": len(self._resources),
            "n_resources_dead": len(self._dead_resources),
            "mean_health": sum(healths) / len(healths),
            "min_health": min(healths),
            "max_health": max(healths),
            "resources_wood": resource_counts[ElementType.WOOD],
            "resources_water": resource_counts[ElementType.WATER],
            "resources_metal": resource_counts[ElementType.METAL],
            "resources_fire": resource_counts[ElementType.FIRE],
            "resources_earth": resource_counts[ElementType.EARTH],
        }
