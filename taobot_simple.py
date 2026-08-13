from __future__ import annotations

import copy
import math
import random
from typing import TYPE_CHECKING

from body_factory import BodyFactory
from body_parts import BodyPart, LegPart
from chi import ChiLaws, ChiPool, ConversionPath
from common import ELEMENT_LIST, ElementType
from math_utils import torus_direction, torus_distance, wrap_position
from rng import derive_stream, new_seed

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

# Wood collapse → Earth crisis conditions
EARTH_CRISIS_WOOD_THRESHOLD: float = 20.0    # Wood organ below this…
EARTH_CRISIS_STORAGE_FRACTION: float = 0.1   # …AND total storage below this fraction of capacity
EARTH_CRISIS_DRAIN: float = 0.1              # Earth organ lost per tick during crisis

# Fire organ below this value → locked into searching (random walk only)
FIRE_LOCKOUT_THRESHOLD: float = 20.0

# Base storage drain per tick for each organ (drawn from the governing element's storage)
# Earth drain covers structural maintenance; Wood covers meridian/metabolic upkeep;
# Metal covers armor upkeep. Rates follow the role, not the element.
# Water has no entry: the Water organ is derived from the legs (see DERIVED_ORGANS) and
# Water storage is consumed by LegPart.tick(), not by an abstract organ drain.
ORGAN_STORAGE_DRAIN: dict[str, float] = {
    "FIRE":  0.015,
    "WOOD":  0.010,
    "EARTH": 0.004,
    "METAL": 0.002,
}

# Organs that are *derived summary statistics* over the body parts of that element
# rather than stored scalars (AD-5). A derived organ has no slot in `_organs`, is read
# only through `organ()`, and cannot be drained — `_drain_organ` raises for it.
# One organ moves per epic: Water first, because LegPart already owns locomotion cost.
# The other four — Fire, Wood, Earth and Metal — stay stored scalars, because no parts
# of those elements exist yet: deriving them now reads 0.0 and silently disables the
# capability each governs.
# Invariant: DERIVED_ORGANS and ORGAN_STORAGE_DRAIN partition ElementType — every organ
# is either derived from parts or funded by a storage drain, never both and never neither.
DERIVED_ORGANS: frozenset[ElementType] = frozenset({ElementType.WATER})

# The generative (Sheng) cycle and every other conversion constant now live on the chi
# tier, in `chi.py`, together with the code that uses them (`AD-4`). Import them from
# there — this module owns no conversion arithmetic.

DEFAULT_PARAMS: dict = {
    "sensing_range": 6.0,
    "speed": 1.5,
    "collect_rate": 2.0,
    "affinity": {e.name: 1.0 for e in ElementType},
    "hazard_avoidance_range": 4.0,
    "storage_capacity": {e.name: 20.0 for e in ElementType},
    "collect_radius": 1.0,
    "flee_earth_threshold": 25.0,
    "random_walk_turn_rate": 0.4,
    # Phase 2 body parts. Two symmetric legs at ±0.4 rad, both pushing forward (phi=0).
    # With phi=0 each leg contributes exactly T to forward speed → T_base = speed/2 = 0.75.
    # max_thrust=1.5 covers the fastest archetype (wanderer speed=2.2, T_base=1.1)
    # and leaves headroom for differential steering corrections.
    #
    # `capacity` and `drain_max` are traits (AD-13), derived 2026-08-12 in the workshop
    # because Water was visibly inert: it was the slowest-moving element on screen while
    # the bot was plainly walking.
    #
    #   drain_max 0.005 → 0.020. Two legs at cruise draw `drain_max` per tick between
    #   them (each leg spends |thrust|/max_thrust × drain_max, and T_base/max_thrust is
    #   0.5). At 0.005 that was 0.005/tick against Fire's 0.015–0.030 and Wood's
    #   0.010–0.020 — three to six times slower than anything else, so Water looked
    #   static. 0.020 puts it in the same band. Note Water is still the one element not
    #   scaled by the metabolic multiplier, since legs do not consult it.
    #
    #   capacity 4.0 → 0.30. The reserve is meant to smooth brief gaps, not remove
    #   starvation. At 0.010/tick per leg, 4.0 was a 400-tick buffer against a measured
    #   median dry spell of 29 ticks — 14× too large, so leg integrity never moved off
    #   1.0 in any unforced run. 0.30 covers roughly one median dry spell.
    #
    # Measured over 6000 ticks of default_world at seed 42: median lifespan essentially
    # unchanged (1166 → 1157) and all four observed death modes retained. Rebalanced
    # again once Stories 1.2 and 1.3 close the prevention/repair loop — until 1.3 exists
    # nothing raises integrity, so degrade-and-recover cannot be tuned for here.
    "body": [
        {"type": "leg", "r": 1.5, "theta": 0.4, "phi": 0.0,
         "max_thrust": 1.5, "capacity": 0.30, "drain_max": 0.020},
        {"type": "leg", "r": 1.5, "theta": -0.4, "phi": 0.0,
         "max_thrust": 1.5, "capacity": 0.30, "drain_max": 0.020},
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
        "flee_earth_threshold": 50.0,
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
    no neural networks yet. Its essence lives in a `ChiPool` (`self.chi`), which owns
    every conversion — this class owns none.

    Each tick: sense → decide → act → body parts → metabolize → chi.

    Organ system (replaces single health value):
      Earth  — body structure; death condition at 0; damaged by Metal attacks
      Fire   — nervous system; governs sensing range; at 0 → locked to searching
      Water  — locomotion; *derived* from the mean integrity of the Water-element
               parts (today, the legs). Reported and rendered, but nothing reads it:
               the legs own locomotion cost directly, so a Water organ of 0 has no
               behavioural effect. It is a gauge, not yet a control.
      Wood   — meridians/transport; drain multiplier rises as it degrades
      Metal  — armor; absorbs incoming damage before Earth takes it

    Every organ is read through `organ(element)`, never off a bare field: some are
    stored scalars and some are computed from body parts, and callers must not care
    which. See DERIVED_ORGANS.

    Behavioral states (in priority order):
      fleeing    — Earth organ critical or hazard too close; steer away from danger
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
        rng: random.Random | None = None,
        run_seed: int | None = None,
        chi_laws: ChiLaws | None = None,
    ) -> None:
        """Create a taobot at (x, y) with the given entity_id.

        `params` is an optional archetype override dict (see ARCHETYPES).
        `archetype` is the human-readable name stored for logging.

        `rng` is this bot's private stream and `run_seed` is the seed of the run it
        belongs to — `World.spawn_taobot` supplies both. A bot never reaches for
        module-level `random.*` (`AD-12`): every draw it makes comes out of `self._rng`,
        so an archetype that starts drawing more numbers perturbs nobody but itself.

        Both default to `None` for bots built directly (tests, sandboxes), in which
        case a fresh run seed is generated and the stream is derived from it exactly as
        the world would. That is still a private stream, never a shared global.

        `chi_laws` are the laws of Pangu this organism's chi tier obeys —
        `World.spawn_taobot` passes the ones its config resolved. `None` falls back to
        the shipped `configs/laws.json`, so a bot built without a world obeys the same
        laws rather than a second copy of the numbers."""
        self.x = x
        self.y = y
        self.entity_id = entity_id
        self.archetype: str = archetype
        self.run_seed: int = new_seed() if run_seed is None else int(run_seed)
        self._rng: random.Random = (
            derive_stream(self.run_seed, "taobot", entity_id) if rng is None else rng
        )
        self.heading: float = self._rng.uniform(0, 2 * math.pi)

        p = _merge_params(params)
        self.sensing_range: float = p["sensing_range"]
        self.speed: float = p["speed"]
        self.collect_rate: float = p["collect_rate"]
        self.affinity: dict[ElementType, float] = {
            ElementType[k]: v for k, v in p["affinity"].items()
        }
        self.hazard_avoidance_range: float = p["hazard_avoidance_range"]
        # Held in a local until the pool exists — `storage_capacity` is a property over
        # `self.chi.capacity`, so there is nowhere to put it before then.
        storage_capacity: dict[ElementType, float] = {
            ElementType[k]: v for k, v in p["storage_capacity"].items()
        }
        self.collect_radius: float = p["collect_radius"]
        self.flee_earth_threshold: float = p["flee_earth_threshold"]
        self.random_walk_turn_rate: float = p["random_walk_turn_rate"]

        # Normalize affinities to sum=1 so absolute values don't affect scoring
        # magnitude — only relative preference between elements matters.
        total = sum(self.affinity.values())
        if total > 0:
            self.affinity = {k: v / total for k, v in self.affinity.items()}

        # Phase 2 body parts — built before the organ store because derived organs
        # (Water) read their value straight off the parts.
        self.body_parts: list[BodyPart] = BodyFactory.make_parts(
            p["body"], run_seed=self.run_seed, owner_id=entity_id
        )
        self.legs: list[LegPart] = [bp for bp in self.body_parts if isinstance(bp, LegPart)]

        # Stored organs — all start at full integrity. Derived organs have no slot
        # here at all, so there is nothing to write even by accident.
        self._organs: dict[ElementType, float] = {
            e: ORGAN_MAX for e in ELEMENT_LIST if e not in DERIVED_ORGANS
        }

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

        # The chi tier (`AD-2`): the pool this organism's essence lives in, and the
        # only place conversion happens (`AD-4`). The organism holds the pool; it does
        # not hold conversion logic. E3 substitutes a MeridianNetwork behind the same
        # port without touching this class.
        self.chi: ChiPool = ChiPool(
            {e: 0.0 for e in ELEMENT_LIST}, storage_capacity, chi_laws
        )

        # Collection state
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

    # --- Chi ---

    @property
    def storage(self) -> dict[ElementType, float]:
        """This organism's chi pool, as the dict every existing consumer expects.

        One dict, owned by `self.chi`, reached from two names — never two dicts that
        could drift. Resource collection, body-part replenish and organ upkeep still
        write it directly; only conversion has moved behind the port so far, which is
        the deliberate partial migration Story 1.2 describes. The setter exists so
        anything that swaps the dict wholesale (the invariant harness wraps it in an
        observer) swaps the pool's too, rather than leaving the two out of step."""
        return self.chi.storage

    @storage.setter
    def storage(self, value: dict[ElementType, float]) -> None:
        self.chi.storage = value

    @property
    def storage_capacity(self) -> dict[ElementType, float]:
        """The ceilings on that pool — likewise one dict, reached from two names.

        A property for the same reason `storage` is: the pool caps every deposit
        against these, so a caller that swapped the organism's copy while the pool kept
        the old one would leave conversion enforcing ceilings nothing else believed in.
        Mutating the dict in place was always fine; this makes rebinding it fine too."""
        return self.chi.capacity

    @storage_capacity.setter
    def storage_capacity(self, value: dict[ElementType, float]) -> None:
        self.chi.capacity = value

    # --- Organs ---

    def organ(self, element: ElementType) -> float:
        """Current integrity of one organ, 0–ORGAN_MAX.

        The single read path for every organ, inside this class and out. Derived
        organs are computed from the parts carrying that element; the rest return the
        stored scalar. An organ system with no parts reads 0.0 — absent and destroyed
        are deliberately indistinguishable, so a body plan that drops a part loses the
        capability instead of getting it for free."""
        if element in DERIVED_ORGANS:
            return self._derive_organ(element)
        return self._organs[element]

    def _derive_organ(self, element: ElementType) -> float:
        """Compute a derived organ from its parts: mean part integrity × ORGAN_MAX.

        Membership is by *element*, not by part class — every Water-element part counts
        toward the Water organ, so adding a second Water part type changes what the organ
        summarises. Today the Water-element parts are exactly the legs.

        The result is clamped to 0–ORGAN_MAX. `structural_integrity` is specified as
        0–1 but nothing on `BodyPart` enforces it, and Story 1.3's repair path is the
        first thing that could overshoot. The organ range is a hard invariant, so it is
        held here rather than trusted upstream."""
        parts: list[BodyPart] = [p for p in self.body_parts if p.element == element]
        if not parts:
            return 0.0
        mean_integrity = sum(p.structural_integrity for p in parts) / len(parts)
        return max(0.0, min(ORGAN_MAX, mean_integrity * ORGAN_MAX))

    # --- Main tick ---

    def tick(self, world: "World") -> None:
        """Advance one simulation tick: sense, decide, act, body, metabolize, chi.

        `AD-1` orders the phases `sense -> decide -> act -> chi -> upkeep -> age`, but
        conversion has always run *after* upkeep here and still does. Reordering would
        change behaviour above the deficit threshold, which Story 1.2's own acceptance
        forbids ("byte-identical to the pre-change build"); the narrower requirement
        wins and the restructure is deferred with its own baseline."""
        nearby_resources, nearby_hazards = self._sense(world)
        self._decide(nearby_resources, nearby_hazards, world)
        self._act(world)
        self._tick_body_parts()
        self._metabolize()
        self.chi.convert()
        self.age_ticks += 1

    # --- Sense ---

    def _sense(self, world: "World") -> tuple:
        """Query the world for resources and hazards within effective sensing range.

        Sensing range is scaled by Fire organ integrity — a degraded nervous system
        sees less of the world. Returns (resources, hazards), each sorted nearest-first."""
        fire_frac = self.organ(ElementType.FIRE) / ORGAN_MAX
        effective_range = self.sensing_range * fire_frac
        resources = world.query_resources(self.x, self.y, effective_range)
        hazards = world.query_hazards(self.x, self.y, effective_range)
        return resources, hazards

    # --- Decide ---

    def _decide(self, nearby_resources: list, nearby_hazards: list, world: "World") -> None:
        """Update behavior_state and heading based on current surroundings.

        Priority order:
          1. Flee — Earth organ critical or hazard within avoidance range
          2. Fire lockout — nervous system too degraded to do anything but random walk
          3. Collect — already adjacent to a live target resource
          4. Seek — pick the best visible resource and head toward it
          5. Search — random walk when nothing is visible
        """
        ww, wh = world.config.width, world.config.height

        # Step 1: FLEE — critical Earth organ (structural integrity near zero)
        if self.organ(ElementType.EARTH) < self.flee_earth_threshold:
            self.behavior_state = "fleeing"
            if nearby_hazards:
                nearest = nearby_hazards[0]
                dx, dy = torus_direction(nearest.x, nearest.y, self.x, self.y, ww, wh)
                if dx != 0.0 or dy != 0.0:
                    self._desired_heading = math.atan2(dy, dx)
            else:
                self._desired_heading += self._rng.uniform(-0.3, 0.3)
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
        if self.organ(ElementType.FIRE) < FIRE_LOCKOUT_THRESHOLD:
            self.behavior_state = "searching"
            self.target_entity_id = None
            turn = self.random_walk_turn_rate
            self._desired_heading += self._rng.uniform(-turn, turn)
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
        self._desired_heading += self._rng.uniform(-turn, turn)
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
        If storage is insufficient, it is zeroed and the organ degrades.

        Raises ValueError for a derived organ: its value is a summary of its parts, so
        writing it here would be silently discarded. Degrade the parts instead."""
        if element in DERIVED_ORGANS:
            raise ValueError(
                f"{element.name} is a derived organ — its integrity comes from its body "
                "parts and cannot be drained. Degrade the parts instead."
            )
        if self.storage[element] >= drain:
            self.storage[element] -= drain
            regen_floor = REGEN_STORAGE_THRESHOLD * self.storage_capacity[element]
            if self.storage[element] > regen_floor:
                self._organs[element] = min(ORGAN_MAX, self._organs[element] + ORGAN_REGEN_RATE)
        else:
            self.storage[element] = 0.0
            self._organs[element] = max(0.0, self._organs[element] - ORGAN_DEGRADE_RATE)

    def _metabolize(self) -> None:
        """Run one tick of organ metabolism.

        Wood organ integrity sets a global drain multiplier: at full Wood all
        drains are normal; at zero Wood all drains double. This multiplier applies
        to Fire, Earth, Wood, and Metal organs.

        Water is absent: it is a derived organ, so `_drain_organ` would raise for it.
        Water storage is consumed by LegParts (in _tick_body_parts), and the Water
        organ falls out of their structural integrity.

        Earth crisis: if Wood is critically low AND total storage is nearly empty,
        systemic metabolic failure directly damages the Earth organ on top of starvation."""
        wood_mult = 1.0 + (ORGAN_MAX - self.organ(ElementType.WOOD)) / ORGAN_MAX

        self._drain_organ(
            ElementType.FIRE,
            ORGAN_STORAGE_DRAIN["FIRE"] * wood_mult,
        )

        self._drain_organ(
            ElementType.EARTH,
            ORGAN_STORAGE_DRAIN["EARTH"] * wood_mult,
        )

        self._drain_organ(
            ElementType.WOOD,
            ORGAN_STORAGE_DRAIN["WOOD"] * wood_mult,
        )

        self._drain_organ(
            ElementType.METAL,
            ORGAN_STORAGE_DRAIN["METAL"] * wood_mult,
        )

        # Earth crisis: systemic failure when metabolism has collapsed and storage is empty
        total_storage = sum(self.storage.values())
        total_capacity = sum(self.storage_capacity.values())
        crisis = (
            self.organ(ElementType.WOOD) < EARTH_CRISIS_WOOD_THRESHOLD
            and total_storage < EARTH_CRISIS_STORAGE_FRACTION * total_capacity
        )
        if crisis:
            self._organs[ElementType.EARTH] = max(
                0.0, self._organs[ElementType.EARTH] - EARTH_CRISIS_DRAIN
            )

    # --- External callbacks ---

    def record_damage(self, amount: float) -> None:
        """Apply incoming damage, routed through Metal armor before reaching Earth.

        Metal organ acts as a fractional damage absorber: at full Metal integrity
        no damage reaches Earth; at zero Metal the full amount hits Earth directly.
        Damage totals are always tracked at face value for logging."""
        self.damage_taken_total += amount
        self._interval_damage += amount
        metal_frac = self.organ(ElementType.METAL) / ORGAN_MAX
        earth_damage = amount * (1.0 - metal_frac)
        self._organs[ElementType.EARTH] = max(0.0, self._organs[ElementType.EARTH] - earth_damage)

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
            "organs": {e.name: round(self.organ(e), 2) for e in ELEMENT_LIST},
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
            # Last tick's conversion, split by path. Both paths move METAL->WATER, so
            # a storage delta alone cannot say whether both ran once or one ran twice —
            # the split is the only thing that can.
            "chi": {
                "deficit_active": self.chi.deficit_active,
                "deficit_served": self.chi.deficit_served,
                "deficit_level": self.chi.deficit_level(),
                "passive_metal_to_water": self.chi.moved(
                    ConversionPath.PASSIVE, ElementType.METAL, ElementType.WATER
                ),
                "deficit_metal_to_water": self.chi.moved(
                    ConversionPath.DEFICIT, ElementType.METAL, ElementType.WATER
                ),
            },
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
