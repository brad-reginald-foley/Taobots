"""Deterministic derivation of RNG streams, seeds and ids — `AD-12`, `AD-9`.

This module is the **only** place in the project where a seed is mixed with anything
else. Every stream in the simulation comes out of `derive_stream`, every derived id
out of `derive_token`, and both are thin views onto the single `_digest` step below.
That is the point: two call sites inventing their own mixing of
`(world_seed, entity_id)` is how a "reproducible" simulation quietly stops being one.

Why `hashlib` and not `hash()`: Python randomises `hash()` for `str` and `bytes` per
process unless `PYTHONHASHSEED` is pinned, so a stream derived from it reproduces
within one process and nowhere else. A cryptographic digest is stable across
processes, machines and Python versions, which is what "same seed replays the run"
has to mean.

Streams are `random.Random` instances, never the `random` module: module-level
`random.*` is a single global stream, so one entity taking an extra draw shifts every
subsequent entity's numbers (the failure `AD-12` exists to prevent).
"""

from __future__ import annotations

import hashlib
import random
import secrets

__all__ = ["SEED_BITS", "derive_seed", "derive_stream", "derive_token", "new_seed"]

# blake2b personalisation (16 bytes max). Versioned on purpose: a change to how
# components are mixed bumps the version instead of silently returning different
# numbers for seeds already recorded in run manifests.
#
# v2 added type tagging to `_field`. Runs seeded before that bump do not replay under
# v2 — which is exactly what the version is here to make visible rather than silent.
_PERSONALISATION = b"taobots-rng-v2"

# Width of a freshly generated seed. 63 bits keeps it a positive signed 64-bit
# integer, so it round-trips through argparse, JSON manifests and CSV unchanged.
SEED_BITS = 63


def _field(value: object) -> bytes:
    """Encode one derivation component, type-tagged and length-prefixed.

    Length-prefixed rather than delimiter-joined so a component's *content* can never
    forge a boundary: `("ab", "c")` and `("a", "bc")` must derive different streams
    whatever separator character a caller happens to have inside a string.

    Type-tagged because stringifying alone collapses values that are not the same
    thing. `derive_stream(s, "taobot", 7)` and `derive_stream(s, "taobot", "7")` would
    otherwise be one stream, so an entity keyed by an int id and one keyed by the same
    id as text would silently share their randomness — and a gene declaring `"id": 1`
    would collide with one declaring `"id": "1"`. The tag is the type's name, so `int`
    7 and `str` "7" are distinct components."""
    raw = str(value).encode("utf-8")
    tag = type(value).__name__.encode("utf-8")
    return (
        len(tag).to_bytes(8, "big") + tag + len(raw).to_bytes(8, "big") + raw
    )


def _digest(world_seed: int, parts: tuple[object, ...]) -> bytes:
    """The one mixing step. Everything public in this module is a view onto it."""
    h = hashlib.blake2b(digest_size=32, person=_PERSONALISATION)
    h.update(_field(int(world_seed)))
    for part in parts:
        h.update(_field(part))
    return h.digest()


def derive_seed(world_seed: int, *parts: object) -> int:
    """Derive a stable integer seed from `(world_seed, *parts)`.

    Deterministic across processes, machines and runs. Components are stringified,
    so `1` and `"1"` are the same component — pass a distinguishing label when that
    matters (`derive_seed(s, "taobot", eid)` vs `derive_seed(s, "mutation", eid)`)."""
    return int.from_bytes(_digest(world_seed, parts), "big")


def derive_stream(world_seed: int, *parts: object) -> random.Random:
    """Return the `random.Random` stream belonging to `(world_seed, *parts)`.

    The single derivation function of `AD-12`. Call it with a label naming the
    consumer, so unrelated subsystems cannot collide on the same stream:

        world stream     derive_stream(seed, "world")
        one taobot       derive_stream(seed, "taobot", entity_id)
        an observer      derive_stream(seed, "observer", "focal")

    Two calls with the same arguments return two *independent* streams that yield the
    same sequence — a stream is owned by whoever it was derived for, never shared."""
    return random.Random(derive_seed(world_seed, *parts))


def derive_token(world_seed: int, *parts: object, length: int = 16) -> str:
    """Derive a stable lowercase-hex id from `(world_seed, *parts)` — `AD-9`.

    The id counterpart of `derive_stream`, sharing its mixing so ids and streams can
    never drift apart. Used for `part_id`, which `uuid4()` used to supply from
    `os.urandom` where no seed could reach it."""
    if not 1 <= length <= 64:
        raise ValueError(f"derive_token length must be 1..64 hex chars, got {length}")
    return _digest(world_seed, parts).hex()[:length]


def new_seed() -> int:
    """Generate a fresh run seed when the caller did not supply one.

    The *only* unseeded randomness in the project, and it happens exactly once per
    run. Whoever calls this must record what it returned — an unrecorded generated
    seed is the same unreplayable run as no seed at all (`AD-12` part 3)."""
    return secrets.randbits(SEED_BITS)
