from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from common import ELEMENT_LIST, ElementType
from entities import Hazard, Resource
from math_utils import torus_distance

if TYPE_CHECKING:
    from taobot_simple import TaobotSimple


CLUSTER_RADIUS: float = 6.0        # VU — distance threshold for counting same-type neighbours
CLUSTER_CANDIDATES: int = 100      # candidate positions sampled per spawn
MIN_SPAWN_SEPARATION: float = 2.0  # VU — minimum distance between any two entities in a pool


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ResourceConfig:
    """Spawn and respawn settings for resources. Weights are normalised to sum=1."""

    initial_count: int
    respawn_delay_ticks: int
    spawn_weights: dict[ElementType, float]
    cluster_affinity: dict[ElementType, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalise spawn_weights so they can be used directly as probabilities."""
        total = sum(self.spawn_weights.values())
        if total <= 0:
            raise ValueError("spawn_weights must have at least one positive value")
        self.spawn_weights = {k: v / total for k, v in self.spawn_weights.items()}


@dataclass
class HazardConfig:
    """Spawn settings for hazards. Weights are normalised to sum=1."""

    initial_count: int
    spawn_weights: dict[ElementType, float]
    cluster_affinity: dict[ElementType, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalise spawn_weights so they can be used directly as probabilities."""
        total = sum(self.spawn_weights.values())
        if total <= 0:
            raise ValueError("spawn_weights must have at least one positive value")
        self.spawn_weights = {k: v / total for k, v in self.spawn_weights.items()}


@dataclass
class TaobotConfig:
    """Population settings. The world maintains taobots at target_population at all times."""

    initial_count: int
    target_population: int


@dataclass
class ChemistryConfig:
    """Elemental chemistry settings. degrade_rate is reserved for Phase 2 chi interactions."""

    degrade_rate: float


@dataclass
class WorldConfig:
    """Complete world configuration loaded from JSON. See configs/ for examples."""

    name: str
    width: int
    height: int
    resources: ResourceConfig
    hazards: HazardConfig
    taobots: TaobotConfig
    chemistry: ChemistryConfig

    @classmethod
    def from_json(cls, path: str | Path) -> "WorldConfig":
        """Load a WorldConfig from a JSON file. Raises ValueError on missing required keys."""
        with open(path) as f:
            data = json.load(f)

        for key in ("name", "world", "resources", "hazards", "taobots", "chemistry"):
            if key not in data:
                raise ValueError(f"WorldConfig missing required key: '{key}'")

        def parse_weights(raw: dict[str, float]) -> dict[ElementType, float]:
            """Convert a JSON {name: weight} dict to {ElementType: weight}."""
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
                cluster_affinity=parse_weights(r.get("cluster_affinity", {})),
            ),
            hazards=HazardConfig(
                initial_count=int(h["initial_count"]),
                spawn_weights=parse_weights(h["spawn_weights"]),
                cluster_affinity=parse_weights(h.get("cluster_affinity", {})),
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
    """Grid-based spatial index for O(1) neighbourhood queries on a torus.

    Entities are assigned to fixed-size buckets. A radius query collects all
    buckets whose bounding boxes overlap the search area; callers then filter
    by exact torus_distance. The result set is conservative (may include
    entities slightly outside the radius) but never misses any.
    """

    # 8 VU buckets → 10×8 grid for the 80×60 world. At max sensing range 6.0 VU,
    # a query touches at most 3×3 = 9 buckets instead of scanning all entities.
    BUCKET_W: int = 8
    BUCKET_H: int = 8

    def __init__(self, world_w: int, world_h: int) -> None:
        """Initialise an empty hash for a world of the given dimensions."""
        import math
        self._n_bx: int = math.ceil(world_w / self.BUCKET_W)
        self._n_by: int = math.ceil(world_h / self.BUCKET_H)
        self._world_w = world_w
        self._world_h = world_h
        self._grid: dict[tuple[int, int], set[int]] = {}
        self._positions: dict[int, tuple[float, float]] = {}

    def _bucket(self, x: float, y: float) -> tuple[int, int]:
        """Return the (bx, by) bucket index for a position, with torus wrap."""
        bx = int(x / self.BUCKET_W) % self._n_bx
        by = int(y / self.BUCKET_H) % self._n_by
        return (bx, by)

    def register(self, entity_id: int, x: float, y: float) -> None:
        """Insert or move an entity. Safe to call repeatedly as the entity moves."""
        if entity_id in self._positions:
            old_bucket = self._bucket(*self._positions[entity_id])
            if old_bucket in self._grid:
                self._grid[old_bucket].discard(entity_id)
        new_bucket = self._bucket(x, y)
        self._grid.setdefault(new_bucket, set()).add(entity_id)
        self._positions[entity_id] = (x, y)

    def deregister(self, entity_id: int) -> None:
        """Remove an entity from the hash. No-op if the entity is not registered."""
        if entity_id not in self._positions:
            return
        bucket = self._bucket(*self._positions[entity_id])
        if bucket in self._grid:
            self._grid[bucket].discard(entity_id)
        del self._positions[entity_id]

    def neighbors(
        self, x: float, y: float, radius: float, world_w: int, world_h: int
    ) -> set[int]:
        """Return entity_ids in buckets overlapping the search radius bounding box.

        Conservative — callers must filter by exact torus_distance to exclude
        entities in edge buckets that fall outside the true radius."""
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
    """Owns all simulation state and drives the tick loop.

    Tick order each step:
      1. _respawn_tick       — advance dead-resource timers, re-register revived ones
      2. taobot.tick(world)  — each taobot: sense → decide → act → metabolize
      3. _apply_hazard_damage — hazards within 1.0 VU deal damage to nearby taobots
      4. _check_taobot_deaths — remove dead bots, fire on_taobot_death callback, respawn
      5. tick_count += 1
    """

    def __init__(self, config: WorldConfig) -> None:
        """Create an empty world. Call initialize() to populate it."""
        self.config = config
        self.tick_count: int = 0
        self._next_id: int = 0

        self._resources: dict[int, Resource] = {}
        self._dead_resources: dict[int, Resource] = {}
        self._hazards: dict[int, Hazard] = {}
        self._taobots: dict[int, "TaobotSimple"] = {}

        self._entity_hash = SpatialHash(config.width, config.height)
        self._taobot_hash = SpatialHash(config.width, config.height)

        # Optional callback fired with the dying taobot just before removal.
        # Used by RunLogger to write death records; safe to leave as None.
        self.on_taobot_death: Callable[["TaobotSimple"], None] | None = None

    # --- Lifecycle ---

    def initialize(self) -> None:
        """Populate the world with resources, hazards, and taobots per config.

        Taobots are spawned cycling through ARCHETYPES so each archetype gets
        an equal share of the initial population."""
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
            self.spawn_taobot(params=ARCHETYPES[archetype], archetype=archetype)

    def tick(self) -> None:
        """Advance the simulation by one tick. See class docstring for step order."""
        self._respawn_tick()

        for taobot in list(self._taobots.values()):
            taobot.tick(self)

        self._apply_hazard_damage()
        self._check_taobot_deaths()

        # Phase 2: chi chemistry tick goes here (config.chemistry.degrade_rate)

        self.tick_count += 1

    # --- Spawning ---

    def _alloc_id(self) -> int:
        """Return a new unique entity id."""
        self._next_id += 1
        return self._next_id

    def _sample_element(self, weights: dict[ElementType, float]) -> ElementType:
        """Draw a random ElementType using the given probability weights."""
        elements = list(weights.keys())
        probs = [weights[e] for e in elements]
        return random.choices(elements, weights=probs, k=1)[0]

    def _pick_position(
        self,
        element_type: ElementType,
        affinity: float,
        entity_pool: dict[int, Resource] | dict[int, Hazard],
    ) -> tuple[float, float]:
        """Sample a random spawn position, respecting min separation and cluster affinity.

        Generates CLUSTER_CANDIDATES candidates, drops any within MIN_SPAWN_SEPARATION
        of an existing pool entity, then selects by exp(affinity × same-type-neighbour-count).
        Falls back to the full candidate set if the world is too crowded for valid spacing."""
        ww, wh = self.config.width, self.config.height
        candidates = [
            (random.uniform(0, ww), random.uniform(0, wh))
            for _ in range(CLUSTER_CANDIDATES)
        ]

        # Drop candidates that would stack on top of existing entities in this pool
        spaced = [
            (cx, cy) for cx, cy in candidates
            if not any(
                eid in entity_pool
                and torus_distance(cx, cy, entity_pool[eid].x, entity_pool[eid].y, ww, wh)
                < MIN_SPAWN_SEPARATION
                for eid in self._entity_hash.neighbors(cx, cy, MIN_SPAWN_SEPARATION, ww, wh)
            )
        ]
        pool = spaced if spaced else candidates

        if affinity == 0.0:
            return random.choice(pool)

        weights = []
        for cx, cy in pool:
            neighbor_ids = self._entity_hash.neighbors(cx, cy, CLUSTER_RADIUS, ww, wh)
            n = sum(
                1
                for eid in neighbor_ids
                if eid in entity_pool
                and entity_pool[eid].element_type == element_type
                and torus_distance(cx, cy, entity_pool[eid].x, entity_pool[eid].y, ww, wh)
                <= CLUSTER_RADIUS
            )
            weights.append(math.exp(affinity * n))
        return random.choices(pool, weights=weights, k=1)[0]

    def spawn_resource(
        self,
        x: float | None = None,
        y: float | None = None,
        element_type: ElementType | None = None,
    ) -> Resource:
        """Spawn a resource at (x, y) with the given element type.

        Omit any argument to randomise it from config. The resource is registered
        in the entity spatial hash and added to the live resource dict."""
        if element_type is None:
            element_type = self._sample_element(self.config.resources.spawn_weights)
        if x is None and y is None:
            affinity = self.config.resources.cluster_affinity.get(element_type, 0.0)
            x, y = self._pick_position(element_type, affinity, self._resources)
        elif x is None:
            x = random.uniform(0, self.config.width)
        elif y is None:
            y = random.uniform(0, self.config.height)

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
        """Spawn a permanent hazard at (x, y). Omit arguments to randomise from config."""
        if element_type is None:
            element_type = self._sample_element(self.config.hazards.spawn_weights)
        if x is None and y is None:
            affinity = self.config.hazards.cluster_affinity.get(element_type, 0.0)
            x, y = self._pick_position(element_type, affinity, self._hazards)
        elif x is None:
            x = random.uniform(0, self.config.width)
        elif y is None:
            y = random.uniform(0, self.config.height)

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
        archetype: str = "default",
    ) -> "TaobotSimple":
        """Spawn a taobot at (x, y) with optional archetype params dict.

        Omit x/y to place randomly. Omit params to use DEFAULT_PARAMS.
        `archetype` is stored on the taobot for logging/analysis."""
        from taobot_simple import TaobotSimple

        if x is None:
            x = random.uniform(0, self.config.width)
        if y is None:
            y = random.uniform(0, self.config.height)

        eid = self._alloc_id()
        t = TaobotSimple(x=x, y=y, entity_id=eid, params=params, archetype=archetype)
        self._taobots[eid] = t
        self._taobot_hash.register(eid, x, y)
        return t

    def remove_taobot(self, entity_id: int) -> None:
        """Remove a taobot from the world and deregister it from the spatial hash."""
        self._taobots.pop(entity_id, None)
        self._taobot_hash.deregister(entity_id)

    # --- Internal tick steps ---

    def _respawn_tick(self) -> None:
        """Advance respawn timers and move newly revived resources back to the live dict."""
        revived = []
        for eid, resource in self._dead_resources.items():
            if resource.tick_respawn():
                revived.append(eid)

        for eid in revived:
            resource = self._dead_resources.pop(eid)
            self._resources[eid] = resource
            self._entity_hash.register(eid, resource.x, resource.y)

    def _apply_hazard_damage(self) -> None:
        """Deal damage to any taobot within 1.0 VU of a hazard.

        Damage is routed through record_damage(), which applies Metal armor
        absorption before any remainder reaches the Wood organ."""
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
                    taobot.record_damage(hazard.damage_per_tick)

    def _check_taobot_deaths(self) -> None:
        """Remove taobots whose Wood organ has reached zero, fire death callback, then refill."""
        from common import ElementType
        dead_ids = [eid for eid, t in self._taobots.items() if t.organs[ElementType.WOOD] <= 0.0]
        for eid in dead_ids:
            if self.on_taobot_death is not None:
                self.on_taobot_death(self._taobots[eid])
            self.remove_taobot(eid)

        # Phase 1: immediately replace deaths to keep population stable for balance tuning.
        # Phase 4+ will replace this with fitness-weighted genetic respawn.
        while len(self._taobots) < self.config.taobots.target_population:
            self.spawn_taobot()

    # --- Queries ---

    def query_resources(self, x: float, y: float, radius: float) -> list[Resource]:
        """Return all live resources within radius of (x, y), sorted nearest-first."""
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
        """Return all hazards within radius of (x, y), sorted nearest-first."""
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
        """Return all taobots within radius of (x, y), sorted nearest-first.

        Pass exclude_id to omit the querying taobot itself from the results."""
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
        """Deplete a resource by up to `amount` units on behalf of a taobot.

        Moves the resource to the dead dict and deregisters it from the spatial
        hash if it becomes fully depleted. Returns the amount actually collected."""
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
        """All currently live (non-depleted) resources."""
        return list(self._resources.values())

    @property
    def dead_resources(self) -> list[Resource]:
        """All depleted resources waiting to respawn."""
        return list(self._dead_resources.values())

    @property
    def hazards(self) -> list[Hazard]:
        """All hazards in the world."""
        return list(self._hazards.values())

    @property
    def taobots(self) -> list["TaobotSimple"]:
        """All living taobots."""
        return list(self._taobots.values())

    def get_stats(self) -> dict:
        """Return a population-level stats snapshot for CSV logging.

        Organ columns report the mean value across all living taobots.
        Wood organ is the death condition; Fire and Water drive behavioral impairment;
        Earth drives the metabolic cascade."""
        taobots = self.taobots
        resource_counts = {e: 0 for e in ELEMENT_LIST}
        for r in self._resources.values():
            resource_counts[r.element_type] += 1

        def mean_organ(elem: ElementType) -> float:
            if not taobots:
                return 0.0
            return sum(t.organs[elem] for t in taobots) / len(taobots)

        return {
            "tick": self.tick_count,
            "n_taobots": len(taobots),
            "n_resources_alive": len(self._resources),
            "n_resources_dead": len(self._dead_resources),
            "mean_organ_wood": round(mean_organ(ElementType.WOOD), 2),
            "mean_organ_fire": round(mean_organ(ElementType.FIRE), 2),
            "mean_organ_water": round(mean_organ(ElementType.WATER), 2),
            "mean_organ_earth": round(mean_organ(ElementType.EARTH), 2),
            "resources_wood": resource_counts[ElementType.WOOD],
            "resources_water": resource_counts[ElementType.WATER],
            "resources_metal": resource_counts[ElementType.METAL],
            "resources_fire": resource_counts[ElementType.FIRE],
            "resources_earth": resource_counts[ElementType.EARTH],
        }
