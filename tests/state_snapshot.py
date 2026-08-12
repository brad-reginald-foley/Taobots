"""One definition of "the full state of a world", shared by every test that compares runs.

Three places need to answer "did these two runs produce the same thing?" — the
same-seed reproducibility tests, the observer non-perturbation test, and the invariant
harness's determinism digest. They must agree on what *the state* is: a snapshot that
quietly omits a field turns the comparison into a weaker one without saying so, and the
determinism invariant is only as strong as the narrowest snapshot feeding it.

Deliberately unrounded and deliberately exhaustive. Rounding is what lets a drift of a
few ULPs hide until it has grown into a different decision, and an omitted field is a
place a divergence can live undetected.
"""

from __future__ import annotations

from common import ELEMENT_LIST
from taobot_simple import TaobotSimple
from world import World


def bot_state(bot: TaobotSimple) -> dict:
    """Everything about one taobot that a divergence could show up in."""
    return {
        "entity_id": bot.entity_id,
        "archetype": bot.archetype,
        "x": bot.x,
        "y": bot.y,
        "heading": bot.heading,
        "desired_heading": bot._desired_heading,
        "behavior_state": bot.behavior_state,
        "target_entity_id": bot.target_entity_id,
        "age_ticks": bot.age_ticks,
        "organs": {e.name: bot.organ(e) for e in ELEMENT_LIST},
        "storage": {e.name: bot.storage[e] for e in ELEMENT_LIST},
        "resources_collected": bot.resources_collected,
        "distance_moved": bot.distance_moved,
        "damage_taken_total": bot.damage_taken_total,
        "parts": [
            (p.part_id, p.structural_integrity, p.reserve) for p in bot.body_parts
        ],
    }


def world_state(world: World) -> dict:
    """A complete, order-stable snapshot of world state.

    Resource *positions* and element types matter as much as their count: placement is
    the world stream's main consumer, so a snapshot that recorded only how many
    resources were alive would be blind to `_pick_position` losing determinism —
    precisely the thing the world stream exists to make reproducible. `_next_id` is
    included because a divergence in how many entities were ever allocated is a real
    divergence even when the survivors happen to match."""
    return {
        "tick_count": world.tick_count,
        "seed": world.seed,
        "next_id": world._next_id,
        "resources": [
            (r.entity_id, r.x, r.y, r.element_type.name, r.amount, r.alive)
            for r in sorted(world._resources.values(), key=lambda r: r.entity_id)
        ],
        "dead_resources": [
            (r.entity_id, r.x, r.y, r.element_type.name, r.amount,
             r.respawn_ticks_remaining)
            for r in sorted(world._dead_resources.values(), key=lambda r: r.entity_id)
        ],
        "hazards": [
            (h.entity_id, h.x, h.y, h.element_type.name, h.damage_per_tick)
            for h in sorted(world._hazards.values(), key=lambda h: h.entity_id)
        ],
        "taobots": [
            bot_state(t)
            for t in sorted(world._taobots.values(), key=lambda t: t.entity_id)
        ],
    }


def state_repr(world: World) -> str:
    """`world_state` as a stable string, for folding into a rolling digest.

    `repr` of a dict of floats is deterministic within a process and across processes
    on the same build — which is the only scope determinism is ever asserted over here."""
    return repr(world_state(world))
