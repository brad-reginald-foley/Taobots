"""Tests for `rng.py` — the single derivation function every stream comes from.

`AD-12` rests on this module being the only place a seed is mixed with anything, and
on that mixing being stable outside the current process. Both are asserted here.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from rng import SEED_BITS, derive_seed, derive_stream, derive_token, new_seed

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_same_inputs_derive_the_same_seed():
    assert derive_seed(42, "taobot", 7) == derive_seed(42, "taobot", 7)


def test_different_inputs_derive_different_seeds():
    """Every component participates — a change in any one must move the result."""
    base = derive_seed(42, "taobot", 7)
    assert derive_seed(43, "taobot", 7) != base
    assert derive_seed(42, "world", 7) != base
    assert derive_seed(42, "taobot", 8) != base
    assert derive_seed(42, "taobot") != base
    assert derive_seed(42, "taobot", 7, "extra") != base


def test_components_cannot_forge_a_boundary():
    """Length-prefixed encoding, not delimiter-joined: `("ab","c")` and `("a","bc")`
    are different derivations, whatever separator a component's content contains."""
    assert derive_seed(1, "ab", "c") != derive_seed(1, "a", "bc")
    assert derive_seed(1, "a|b") != derive_seed(1, "a", "b")


def test_streams_are_independent_instances_yielding_the_same_sequence():
    """Two derivations of the same stream do not share position.

    This is what makes per-entity streams work: deriving a bot's stream must not
    advance anyone else's, and re-deriving must replay, not continue."""
    a = derive_stream(42, "taobot", 1)
    b = derive_stream(42, "taobot", 1)
    assert [a.random() for _ in range(5)] == [b.random() for _ in range(5)]


def test_distinct_entities_get_distinct_sequences():
    a = derive_stream(42, "taobot", 1)
    b = derive_stream(42, "taobot", 2)
    assert [a.random() for _ in range(5)] != [b.random() for _ in range(5)]


def test_derivation_is_stable_across_processes():
    """The reason this module uses `hashlib` rather than `hash()`.

    Python randomises `hash()` for `str`/`bytes` per process unless `PYTHONHASHSEED`
    is pinned. A derivation built on it reproduces inside one process and nowhere
    else, which is not reproducibility. Two subprocesses with deliberately different
    hash seeds must still derive the same numbers."""
    code = (
        "from rng import derive_seed, derive_token;"
        "print(derive_seed(42, 'taobot', 7));"
        "print(derive_token(42, 'part', 3, 'leg[0]', 0))"
    )
    outputs = []
    for hashseed in ("0", "1", "12345"):
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            env={"PYTHONHASHSEED": hashseed, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.append(proc.stdout)
    assert outputs[0] == outputs[1] == outputs[2]
    # And it agrees with this process, so the committed constants are not a moving target.
    assert outputs[0].splitlines()[0] == str(derive_seed(42, "taobot", 7))


def test_derive_token_is_hex_and_length_bounded():
    token = derive_token(42, "part", 1, "leg[0]", 0)
    assert len(token) == 16
    assert all(c in "0123456789abcdef" for c in token)
    assert len(derive_token(42, "x", length=8)) == 8


@pytest.mark.parametrize("length", [0, -1, 65])
def test_derive_token_rejects_out_of_range_length(length):
    with pytest.raises(ValueError):
        derive_token(42, "x", length=length)


def test_token_and_stream_share_the_derivation():
    """Ids and streams come out of one mixing step, so they cannot drift apart."""
    assert derive_token(42, "a", 1) == format(derive_seed(42, "a", 1), "064x")[:16]


# ---------------------------------------------------------------------------
# Known answers — the one place a golden constant is correct
# ---------------------------------------------------------------------------
#
# Everywhere else in this suite determinism is compared between two runs, never against
# a committed value, because float summation order and libm differ across builds. A
# blake2b digest is not float arithmetic: it is bit-exact on every architecture and
# every Python version, so pinning it is sound.
#
# And it needs pinning. `_field`, `_digest`, `digest_size` and `_PERSONALISATION` are
# four small, innocuous-looking places where an edit silently changes every stream in
# the project: every seed in every recorded manifest stops replaying its run, and every
# historical `part_id` is renamed, with nothing failing to say so. If a change here is
# deliberate, bump `_PERSONALISATION` and update these constants in the same commit.

_KNOWN_SEED = 110885669699335338491362764595081312640172473845638624480192088141678631484942
_KNOWN_TOKEN = "cbd51df0230e6a8c"


def test_derive_seed_known_answer():
    assert derive_seed(42, "taobot", 7) == _KNOWN_SEED


def test_derive_token_known_answer():
    assert derive_token(42, "part", 3, "leg[0]", 0) == _KNOWN_TOKEN


def test_known_answers_are_reproduced_in_a_fresh_process():
    """The constants above must hold outside this process too, or they pin nothing."""
    code = (
        "from rng import derive_seed, derive_token;"
        "print(derive_seed(42, 'taobot', 7));"
        "print(derive_token(42, 'part', 3, 'leg[0]', 0))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT,
        env={"PYTHONHASHSEED": "9999", "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, check=True,
    )
    seed_line, token_line = proc.stdout.split()
    assert int(seed_line) == _KNOWN_SEED
    assert token_line == _KNOWN_TOKEN


def test_components_of_different_types_do_not_collide():
    """`7` and `"7"` are different components.

    Without a type tag they stringify identically, so an entity keyed by an int id and
    one keyed by the same id as text would silently share a stream — and a gene
    declaring `"id": 1` would derive the same `part_id` as one declaring `"id": "1"`."""
    assert derive_seed(1, 7) != derive_seed(1, "7")
    assert derive_seed(1, 1) != derive_seed(1, True)
    assert derive_seed(1, 1.0) != derive_seed(1, 1)
    assert derive_token(1, "part", 7) != derive_token(1, "part", "7")


def test_new_seed_is_a_positive_int_in_range():
    seeds = {new_seed() for _ in range(50)}
    assert len(seeds) == 50, "fresh seeds should not collide"
    assert all(0 <= s < 2 ** SEED_BITS for s in seeds)
