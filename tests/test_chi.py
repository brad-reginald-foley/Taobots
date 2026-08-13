"""Story 1.2 — the chi tier: the port, the two conversion paths, and the trigger.

The I/O matrix from the spec is covered here row by row: above the threshold, below it,
the exact boundary, no Metal, Water at capacity, per-path attribution, and recovery.

Two of these tests carry more weight than the rest:

* `test_above_the_threshold_is_byte_identical_to_the_pre_change_cycle` re-implements the
  pre-change `_cycle_elements` verbatim and demands **exact float equality** with the
  refactored pool across a spread of states. That is the regression guard the story's
  first acceptance criterion asks for, pinned in-process rather than by diffing two
  worktrees' CSVs — the diff can only ever cover the states one seeded run happens to
  visit, and it cannot run in CI.
* `test_the_demand_path_never_overdraws_metal` is the one that would catch the two paths
  double-spending. Story 1.0d's harness catches it too, over whole runs; this pins the
  arithmetic directly at the boundary where it is tightest.
"""

from __future__ import annotations

import json

import pytest

from chi import (
    CYCLE_EFFICIENCY,
    CYCLE_RATE,
    CYCLE_SEQUENCE,
    LAWS_PATH,
    MAX_WATER_DEFICIT_THRESHOLD,
    ChiLaws,
    ChiPool,
    ConversionPath,
    Transfer,
    default_chi_laws,
)
from common import ELEMENT_LIST, ElementType
from taobot_simple import TaobotSimple

WATER = ElementType.WATER
METAL = ElementType.METAL
WOOD = ElementType.WOOD


@pytest.fixture
def pool() -> ChiPool:
    """A pool with the shipped laws and the default 20-unit capacities."""
    return ChiPool(
        {e: 0.0 for e in ELEMENT_LIST},
        {e: 20.0 for e in ELEMENT_LIST},
        default_chi_laws(),
    )


def _set(pool: ChiPool, **amounts: float) -> None:
    for name, value in amounts.items():
        pool.storage[ElementType[name]] = value


# ---------------------------------------------------------------------------
# The laws are read from configs/laws.json, and derived rather than chosen
# ---------------------------------------------------------------------------

def test_the_shipped_laws_come_from_the_laws_file():
    """Not a second copy of the numbers in Python. `AD-13` puts them in the config."""
    block = json.loads(LAWS_PATH.read_text())["chi"]
    laws = default_chi_laws()
    assert laws.water_deficit_threshold == block["water_deficit_threshold"]
    assert laws.deficit_conversion_rate == block["deficit_conversion_rate"]


def test_the_shipped_laws_are_the_values_the_sweep_derived():
    """The derived values themselves, pinned.

    Without this, the entire derivation is decoration: editing `0.008` or `0.025` in
    `configs/laws.json` fails nothing, and the sweep tables recorded beside them
    quietly stop describing the simulation. This is deliberately a second place the
    numbers appear — that is the point. It is not a duplicate to keep in sync, it is a
    tripwire that says the derivation must be redone."""
    laws = default_chi_laws()
    assert (laws.water_deficit_threshold, laws.deficit_conversion_rate) == (0.008, 0.025), (
        "the chi laws no longer match the values derived for Story 1.2. These were "
        "swept, not chosen — re-run tools/derive_chi_laws.py, update the tables in "
        "configs/laws.json, and change this assertion last, not first."
    )


def test_the_derivation_is_recorded_beside_the_constants():
    """"Derived, never chosen" is an epic-level rule, and the reasoning has to survive
    in the repository rather than in a pull request comment."""
    raw = json.loads(LAWS_PATH.read_text())
    note = " ".join(raw["_chi_note"])
    assert "water_deficit_threshold" in note and "deficit_conversion_rate" in note
    assert "workshop" in note.lower()
    assert "derive_chi_laws" in note, "the note must name the script that regenerates it"


@pytest.mark.parametrize("bad", [-0.001, 0.6, 1.0, 1.5])
def test_a_threshold_outside_the_permitted_band_is_rejected(bad):
    """It is a *fraction* of capacity, and the ceiling is well below 1.0.

    At 1.0 the demand path pins Water at capacity every tick, which abolishes Water
    starvation — the exact pressure this organ system exists to impose, and the reason
    `ChiLaws` cites for these being laws rather than genes. A validator that accepted
    the value its own docstring names as the failure mode is not a validator."""
    with pytest.raises(ValueError, match="water_deficit_threshold"):
        ChiLaws(water_deficit_threshold=bad, deficit_conversion_rate=0.025)


def test_the_threshold_ceiling_is_where_the_sweep_says_the_trigger_stops_helping():
    """Pinned so the bound cannot drift back up towards the failure it guards against."""
    assert MAX_WATER_DEFICIT_THRESHOLD == 0.5
    ChiLaws(water_deficit_threshold=MAX_WATER_DEFICIT_THRESHOLD, deficit_conversion_rate=0.025)


def test_a_negative_conversion_rate_is_rejected():
    with pytest.raises(ValueError, match="deficit_conversion_rate"):
        ChiLaws(water_deficit_threshold=0.1, deficit_conversion_rate=-0.1)


@pytest.mark.parametrize("field", ["water_deficit_threshold", "deficit_conversion_rate"])
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_law_is_rejected(field, bad):
    """NaN is the one a range check cannot catch, and it fails silently.

    `nan < 0.0` is False, so a bare lower-bound check *accepts* it — and then
    `rate * metal` is NaN, `min(NaN, ...)` is NaN, `NaN > 0.0` is False, and the demand
    path never commits a transfer for the whole run. A law that switches the mechanism
    off without a word is worse than one that crashes."""
    values = {"water_deficit_threshold": 0.1, "deficit_conversion_rate": 0.025}
    values[field] = bad
    with pytest.raises(ValueError, match="finite"):
        ChiLaws(**values)


def test_a_nan_rate_would_otherwise_silently_disable_the_demand_path():
    """The failure the check above prevents, demonstrated rather than asserted.

    Constructed by bypassing `__post_init__` on a *fresh* instance — never by mutating
    `default_chi_laws()`, which is cached and shared with every other test."""
    unvalidated = ChiLaws.__new__(ChiLaws)
    object.__setattr__(unvalidated, "water_deficit_threshold", 0.008)
    object.__setattr__(unvalidated, "deficit_conversion_rate", float("nan"))

    pool = ChiPool(
        {e: 0.0 for e in ELEMENT_LIST},
        {e: 20.0 for e in ELEMENT_LIST},
        unvalidated,
    )
    _set(pool, WATER=0.0, METAL=10.0)
    pool.convert()

    assert pool.deficit_active, "the deficit is still detected..."
    assert not pool.deficit_served, "...but nothing is ever converted, on any tick"


def test_an_enormous_rate_is_allowed_because_it_cannot_escape_anything():
    """Deliberately unbounded above, unlike the threshold.

    The rate is a ceiling on the *flow*, and the flow is bounded twice over by things a
    law cannot raise: the path asks only for the shortfall, and can spend only the Metal
    that is there. A huge rate refills the deficit in one tick instead of several; it
    cannot convert more Metal in total and cannot lift Water past the threshold."""
    pool = ChiPool(
        {e: 0.0 for e in ELEMENT_LIST},
        {e: 20.0 for e in ELEMENT_LIST},
        ChiLaws(water_deficit_threshold=0.008, deficit_conversion_rate=1e6),
    )
    _set(pool, WATER=0.0, METAL=10.0)
    pool.convert()

    assert pool.storage[WATER] == pytest.approx(pool.deficit_level(), rel=1e-12)
    assert pool.storage[METAL] > 9.7, "it can only ever spend the shortfall's worth"


def test_a_chi_block_missing_a_key_names_it():
    with pytest.raises(ValueError, match="deficit_conversion_rate"):
        ChiLaws.from_mapping({"water_deficit_threshold": 0.1})


# ---------------------------------------------------------------------------
# The threshold is a fraction of *Water* capacity, and capacity varies by archetype
# ---------------------------------------------------------------------------
#
# This is not a detail. `ARCHETYPES` are cycled evenly at world init, so a default run
# holds specialists (Water capacity 10) and hoarders (40) alongside the 20 of everyone
# else. A `deficit_level` that ignored capacity, or read the wrong element's, would give
# every bot the same absolute trigger level — specialists over-converting and hoarders
# left unprotected — and the per-archetype sweep recorded in `configs/laws.json` would
# stop describing the code while every other test stayed green.

# Distinct per element on purpose: with all five equal, reading `capacity[METAL]` in
# place of `capacity[WATER]` is indistinguishable.
_LOPSIDED_CAPACITY = {
    ElementType.WATER: 10.0,
    ElementType.METAL: 40.0,
    ElementType.WOOD: 25.0,
    ElementType.FIRE: 30.0,
    ElementType.EARTH: 35.0,
}


@pytest.mark.parametrize("water_capacity", [10.0, 20.0, 40.0])
def test_the_trigger_level_scales_with_this_bot_s_water_capacity(water_capacity):
    """`ARCHETYPES` really does ship all three of these."""
    capacity = dict(_LOPSIDED_CAPACITY)
    capacity[ElementType.WATER] = water_capacity
    pool = ChiPool({e: 0.0 for e in ELEMENT_LIST}, capacity, default_chi_laws())

    assert pool.deficit_level() == pytest.approx(
        default_chi_laws().water_deficit_threshold * water_capacity
    )


@pytest.mark.parametrize("water_capacity", [10.0, 20.0, 40.0])
def test_the_trigger_fires_at_that_bot_s_own_level_not_a_fixed_one(water_capacity):
    """Behavioural, not just arithmetic: the level the pool is *held to* must scale.

    A hoarder held to a specialist's level is under-protected by a factor of four."""
    capacity = dict(_LOPSIDED_CAPACITY)
    capacity[ElementType.WATER] = water_capacity
    pool = ChiPool({e: 0.0 for e in ELEMENT_LIST}, capacity, default_chi_laws())
    expected = default_chi_laws().water_deficit_threshold * water_capacity

    pool.storage[METAL] = 20.0
    pool.convert()
    assert pool.storage[WATER] == pytest.approx(expected, rel=1e-9)

    # And just above that level it stays quiet, wherever the level happens to be.
    pool.storage.update({e: 0.0 for e in ELEMENT_LIST})
    pool.storage[WATER] = expected * 1.5
    pool.convert()
    assert not pool.deficit_active


def test_archetype_water_capacities_really_do_differ():
    """Guards the premise of the two tests above rather than assuming it."""
    from taobot_simple import ARCHETYPES, DEFAULT_PARAMS

    caps = {DEFAULT_PARAMS["storage_capacity"]["WATER"]}
    for params in ARCHETYPES.values():
        caps.add(
            params.get("storage_capacity", DEFAULT_PARAMS["storage_capacity"])["WATER"]
        )
    assert len(caps) > 1, f"all archetypes share one Water capacity ({caps})"


# ---------------------------------------------------------------------------
# The port (`AD-3`)
# ---------------------------------------------------------------------------

def test_request_grants_what_is_there_and_no_more(pool):
    _set(pool, WOOD=3.0)
    assert pool.request(WOOD, 1.0) == pytest.approx(1.0)
    assert pool.storage[WOOD] == pytest.approx(2.0)


def test_a_request_larger_than_the_pool_is_partially_granted_not_refused(pool):
    """A denied or partial request is a correct outcome, not an error. This is the
    return shape pro-rata allocation will need when Story 1.3 makes repair compete."""
    _set(pool, WOOD=0.5)
    assert pool.request(WOOD, 2.0) == pytest.approx(0.5)
    assert pool.storage[WOOD] == pytest.approx(0.0)
    assert pool.request(WOOD, 2.0) == 0.0


def test_deposit_accepts_only_what_fits_under_capacity(pool):
    _set(pool, WOOD=19.5)
    assert pool.deposit(WOOD, 2.0) == pytest.approx(0.5)
    assert pool.storage[WOOD] == pytest.approx(20.0)
    assert pool.deposit(WOOD, 2.0) == 0.0


@pytest.mark.parametrize("amount", [0.0, -1.0])
def test_the_port_ignores_non_positive_amounts(pool, amount):
    _set(pool, WOOD=5.0)
    assert pool.request(WOOD, amount) == 0.0
    assert pool.deposit(WOOD, amount) == 0.0
    assert pool.storage[WOOD] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Row 1 of the matrix: above the threshold, nothing changes
# ---------------------------------------------------------------------------

def legacy_cycle_elements(storage: dict, capacity: dict) -> None:
    """`TaobotSimple._cycle_elements` as it stood at `2007be4`, verbatim.

    Kept as the comparison target for the regression guard below, not as a second
    implementation: nothing in the simulation calls it."""
    transfers: list[tuple[ElementType, ElementType, float, float]] = []
    for source, target in CYCLE_SEQUENCE:
        amount_out = CYCLE_RATE * storage[source]
        room = capacity[target] - storage[target]
        produced = min(amount_out * CYCLE_EFFICIENCY, room)
        if produced <= 0.0:
            continue
        spent = produced / CYCLE_EFFICIENCY
        transfers.append((source, target, spent, produced))
    for source, target, spent, produced in transfers:
        storage[source] = max(0.0, storage[source] - spent)
        storage[target] += produced


# States chosen so that between them every branch of the passive cycle is taken:
# a roomy one, one where the targets are capped, one with a pool at zero, and the
# lopsided mixes an eating bot actually reaches.
ABOVE_THRESHOLD_STATES = [
    {"WATER": 12.0, "WOOD": 8.0, "FIRE": 4.0, "EARTH": 6.0, "METAL": 10.0},
    {"WATER": 19.99, "WOOD": 19.99, "FIRE": 19.99, "EARTH": 19.99, "METAL": 19.99},
    {"WATER": 20.0, "WOOD": 20.0, "FIRE": 20.0, "EARTH": 20.0, "METAL": 20.0},
    {"WATER": 5.0, "WOOD": 0.0, "FIRE": 0.0, "EARTH": 0.0, "METAL": 0.0},
    {"WATER": 0.2, "WOOD": 20.0, "FIRE": 1.5, "EARTH": 0.0, "METAL": 3.25},
    {"WATER": 1.0, "WOOD": 13.7, "FIRE": 0.03, "EARTH": 19.5, "METAL": 0.001},
]


@pytest.mark.parametrize("state", ABOVE_THRESHOLD_STATES, ids=lambda s: f"H2O{s['WATER']}")
def test_above_the_threshold_is_byte_identical_to_the_pre_change_cycle(pool, state):
    """Acceptance: with Water above the threshold, behaviour is unchanged.

    Exact equality, not `approx`: the claim is byte-identical logs, and a refactor that
    reassociated one multiplication would still pass a tolerance while changing every
    seeded trajectory downstream of it."""
    _set(pool, **state)
    assert pool.storage[WATER] >= pool.deficit_level(), "state must be above the trigger"

    expected = dict(pool.storage)
    legacy_cycle_elements(expected, pool.capacity)

    pool.convert()

    assert pool.storage == expected
    assert not pool.deficit_active
    assert all(t.path is ConversionPath.PASSIVE for t in pool.last_transfers)


def test_above_the_threshold_no_demand_transfer_is_recorded(pool):
    _set(pool, WATER=12.0, METAL=10.0)
    pool.convert()
    assert pool.moved(ConversionPath.DEFICIT, METAL, WATER) == (0.0, 0.0)
    assert pool.moved(ConversionPath.PASSIVE, METAL, WATER)[1] > 0.0


# ---------------------------------------------------------------------------
# Row 2: below the threshold with Metal available
# ---------------------------------------------------------------------------

def test_below_the_threshold_water_rises_and_metal_falls(pool):
    _set(pool, WATER=0.0, METAL=10.0)
    pool.convert()

    assert pool.deficit_active
    assert pool.storage[WATER] > 0.0
    assert pool.storage[METAL] < 10.0


def test_the_demand_path_moves_far_more_than_the_passive_cycle(pool):
    """Acceptance: "measurably above passive `CYCLE_RATE`"."""
    _set(pool, WATER=0.0, METAL=10.0)
    pool.convert()

    _, passive = pool.moved(ConversionPath.PASSIVE, METAL, WATER)
    _, demand = pool.moved(ConversionPath.DEFICIT, METAL, WATER)
    assert demand > 10 * passive


def test_the_demand_path_restores_water_to_the_threshold_and_stops_there(pool):
    """It asks for the *shortfall*, so it regulates rather than pulses.

    Overshooting the line is what would make the trigger oscillate: above the line it
    switches off, Water falls back under, and it fires again."""
    _set(pool, WATER=0.0, METAL=10.0)
    pool.convert()
    assert pool.storage[WATER] == pytest.approx(pool.deficit_level(), rel=1e-12)


def test_the_rate_caps_how_fast_a_deep_deficit_is_refilled(pool):
    """With little Metal the shortfall cannot be met in one tick, and the elevated
    *rate* is what is left binding. Recovery then takes several ticks."""
    _set(pool, WATER=0.0, METAL=0.5)
    pool.convert()
    assert pool.deficit_active
    assert pool.storage[WATER] < pool.deficit_level()
    assert pool.storage[METAL] < 0.5


# ---------------------------------------------------------------------------
# Row 3: the exact boundary
# ---------------------------------------------------------------------------

def _isolated_water(pool: ChiPool, level: float) -> None:
    """Put `level` in Water and suppress every transfer that could perturb it.

    Wood at capacity kills the WATER->WOOD outflow and empty Metal kills the
    METAL->WATER inflow, so Water's pre-tick value *is* the value the trigger sees.
    What is left is a bare test of the threshold comparison itself."""
    _set(pool, WATER=level, WOOD=20.0, FIRE=0.0, EARTH=0.0, METAL=0.0)


def test_water_exactly_at_the_threshold_does_not_trigger(pool):
    """The stated side of the boundary: at the threshold Water counts as recovered.

    `<`, not `<=`, and the comparison is made once against the pre-tick snapshot, so it
    cannot flip part-way through a tick."""
    _isolated_water(pool, pool.deficit_level())
    pool.convert()
    assert not pool.deficit_active


def test_water_one_ulp_below_the_threshold_does_trigger(pool):
    """The boundary is sharp, not a band: one representable step under the line arms
    the trigger. Metal is left empty so the passive cycle cannot nudge Water back over
    the line before the comparison is made."""
    import math

    _isolated_water(pool, math.nextafter(pool.deficit_level(), 0.0))
    pool.convert()
    assert pool.deficit_active


def test_the_boundary_decision_is_deterministic_not_alternating(pool):
    """Presented with the same boundary state repeatedly, the answer never differs.

    "Deterministic, stated side, no oscillation tick to tick" is a claim about the
    *decision*. Held at the line, the trigger must be quiet every single time — a
    `<=` comparison, or one recomputed against a partially-applied tick, would show up
    here as an answer that alternates."""
    for _ in range(20):
        _isolated_water(pool, pool.deficit_level())
        pool.convert()
        assert not pool.deficit_active
        assert pool.storage[WATER] == pytest.approx(pool.deficit_level())


def test_a_regulated_pool_stays_armed_rather_than_flickering(pool):
    """The other half of "no oscillation": with Water being drawn down every tick, the
    trigger stays on and simply replaces what was taken. It does not flap."""
    _set(pool, WATER=0.0, METAL=15.0)
    pool.convert()
    for _ in range(20):
        pool.storage[WATER] -= 0.02  # a tick of leg draw
        pool.convert()
        assert pool.deficit_active
        assert pool.storage[WATER] == pytest.approx(pool.deficit_level(), rel=1e-9)


# ---------------------------------------------------------------------------
# Row 4: no Metal
# ---------------------------------------------------------------------------

def test_no_metal_means_no_conversion_and_no_negative_storage(pool):
    _set(pool, WATER=0.0, METAL=0.0)
    pool.convert()

    assert pool.deficit_active, "the deficit is real even when it cannot be served"
    assert not pool.deficit_served, "...but nothing moved, and that must be sayable"
    assert pool.moved(ConversionPath.DEFICIT, METAL, WATER) == (0.0, 0.0)
    assert pool.storage[WATER] == pytest.approx(0.0)
    assert all(v >= 0.0 for v in pool.storage.values())


def test_armed_and_helpless_is_distinguishable_from_armed_and_working(pool):
    """Two flags, because they answer two different questions.

    `deficit_active` says Water is below the line — true of a bot starving beside an
    empty Metal pool, and worth showing. `deficit_served` says the demand path actually
    moved something. One flag doing both jobs either hides a real deficit or reports the
    trigger holding the line while nothing happens and the legs start to go."""
    _set(pool, WATER=0.0, METAL=0.0)
    pool.convert()
    assert (pool.deficit_active, pool.deficit_served) == (True, False)

    pool.storage[METAL] = 10.0
    pool.convert()
    assert (pool.deficit_active, pool.deficit_served) == (True, True)

    _set(pool, WATER=12.0)
    pool.convert()
    assert (pool.deficit_active, pool.deficit_served) == (False, False)


def test_the_served_flag_is_cleared_and_not_left_latched(pool):
    """It describes this tick, like every other thing on the pool."""
    _set(pool, WATER=0.0, METAL=10.0)
    pool.convert()
    assert pool.deficit_served

    pool.storage[METAL] = 0.0
    pool.convert()
    assert not pool.deficit_served, "left latched from the tick before"


# ---------------------------------------------------------------------------
# Essence is never manufactured, whatever the source turns out to hold
# ---------------------------------------------------------------------------

def test_a_source_that_cannot_pay_in_full_does_not_credit_the_target_in_full(pool):
    """`AD-4`'s hard half, at the one point it could be violated.

    Applying a transfer by subtracting `spent` under a `max(0.0, ...)` floor is the
    wrong shape: it silences a source that cannot pay while the target still receives
    the full `produced`, which *creates* essence. Withdrawing what is there and deriving
    what arrives from what was withdrawn closes that off by construction.

    Driven by planting an over-large transfer directly, because the planner is written
    so this cannot arise — the point is that the applier is safe regardless."""
    _set(pool, WATER=1.0, METAL=0.25)
    water_before, metal_before = pool.storage[WATER], pool.storage[METAL]

    # A transfer charging ten times the Metal the pool actually holds.
    applied = pool.apply(Transfer(ConversionPath.DEFICIT, METAL, WATER, 2.5, 2.0))

    assert pool.storage[METAL] == pytest.approx(0.0), "it can only pay what it has"
    assert pool.storage[METAL] >= 0.0
    gained = pool.storage[WATER] - water_before
    paid = metal_before - pool.storage[METAL]
    assert gained == pytest.approx(paid * CYCLE_EFFICIENCY, rel=1e-12), (
        "the target was credited for chi the source never paid for"
    )
    assert applied.spent == pytest.approx(paid)
    assert applied.produced == pytest.approx(gained)


def test_a_target_that_cannot_receive_in_full_is_recorded_as_what_arrived(pool):
    """The other side: `last_transfers` reports what moved, not what was planned.

    A log that reports intent is worse than no log — it is evidence that disagrees with
    the storage columns printed beside it."""
    _set(pool, WATER=19.9, METAL=20.0)
    applied = pool.apply(Transfer(ConversionPath.PASSIVE, METAL, WATER, 1.0, 0.8))

    assert pool.storage[WATER] == pytest.approx(20.0), "capped at capacity"
    assert applied.produced == pytest.approx(0.1), "only 0.1 fitted"


def test_every_applied_transfer_conserves_essence_over_a_long_random_walk(pool):
    """Property-style sweep over the states an eating, walking bot actually reaches.

    Each tick asserts the epic's equality on *observed* storage deltas for the one edge
    both paths share, which is where a double-spend would land."""
    import random

    rng = random.Random(20260812)
    for _ in range(2000):
        for e in ELEMENT_LIST:
            pool.storage[e] = rng.choice([0.0, rng.uniform(0.0, 20.0), 20.0])
        before = dict(pool.storage)

        pool.convert()

        for e in ELEMENT_LIST:
            assert 0.0 <= pool.storage[e] <= pool.capacity[e], e

        spent, produced = 0.0, 0.0
        for path in ConversionPath:
            s, p = pool.moved(path, METAL, WATER)
            spent += s
            produced += p
        # METAL also *receives* from EARTH, so isolate its outflow via the record.
        metal_out = before[METAL] - pool.storage[METAL]
        metal_in = pool.moved(ConversionPath.PASSIVE, ElementType.EARTH, METAL)[1]
        assert metal_out + metal_in == pytest.approx(spent, abs=1e-12, rel=1e-9)
        assert produced <= spent * CYCLE_EFFICIENCY + 1e-12, "essence was manufactured"


def test_the_demand_path_never_overdraws_metal(pool):
    """The double-conversion guard, at its tightest point.

    Both paths draw on Metal from the same pre-tick snapshot. If the demand path sized
    itself against the snapshot instead of against what the passive cycle had already
    committed, Metal would go negative here — or, once clamped at zero, would silently
    destroy essence and trip Story 1.0d's invariant."""
    for metal in (0.0, 1e-9, 1e-4, 0.01, 0.5, 1.0, 3.0, 20.0):
        pool.storage.update({e: 0.0 for e in ELEMENT_LIST})
        _set(pool, WATER=0.0, METAL=metal)
        pool.convert()

        assert pool.storage[METAL] >= 0.0, metal
        passive_spent, _ = pool.moved(ConversionPath.PASSIVE, METAL, WATER)
        demand_spent, _ = pool.moved(ConversionPath.DEFICIT, METAL, WATER)
        assert passive_spent + demand_spent <= metal + 1e-12, metal


# ---------------------------------------------------------------------------
# Row 5: Water at capacity
# ---------------------------------------------------------------------------

def test_water_at_capacity_converts_nothing_into_it(pool):
    _set(pool, WATER=20.0, METAL=10.0)
    metal_before = pool.storage[METAL]
    pool.convert()

    assert not pool.deficit_active
    assert pool.moved(ConversionPath.PASSIVE, METAL, WATER) == (0.0, 0.0)
    # The source is preserved: a suppressed transfer costs nothing.
    assert pool.storage[METAL] == pytest.approx(metal_before)


def test_a_capped_target_charges_the_source_only_for_what_arrived(pool):
    """Cap then derive (`AD-4`). The inverted order — charge full price, deliver what
    fits — is Story 1.0d's negative control, and this is the same claim at unit scale."""
    # Wood at capacity suppresses WATER->WOOD and empty Earth suppresses EARTH->METAL,
    # so METAL->WATER is the only transfer touching either pool and the whole-pool
    # deltas below *are* that pair's deltas.
    _set(pool, WATER=19.999, WOOD=20.0, FIRE=0.0, EARTH=0.0, METAL=20.0)
    water_before, metal_before = pool.storage[WATER], pool.storage[METAL]
    pool.convert()

    spent, produced = pool.moved(ConversionPath.PASSIVE, METAL, WATER)
    assert produced < CYCLE_RATE * metal_before * CYCLE_EFFICIENCY, "must have capped"
    assert spent == pytest.approx(produced / CYCLE_EFFICIENCY)
    assert pool.storage[WATER] <= pool.capacity[WATER]
    # Nothing manufactured: what Water gained is exactly what Metal paid, times the
    # efficiency — measured on storage, not on the pool's own bookkeeping.
    gained = pool.storage[WATER] - water_before
    paid = metal_before - pool.storage[METAL]
    assert gained == pytest.approx(paid * CYCLE_EFFICIENCY, rel=1e-9)


# ---------------------------------------------------------------------------
# Row 6: per-path attribution
# ---------------------------------------------------------------------------

def test_both_paths_move_metal_to_water_in_one_tick_and_stay_distinguishable(pool):
    """Acceptance: "both ran once" must not be confusable with "one ran twice".

    The whole-tick Metal delta is the sum, so it cannot tell them apart; the per-path
    record can, and the two contributions differ by more than an order of magnitude."""
    _set(pool, WATER=0.0, METAL=10.0)
    metal_before = pool.storage[METAL]
    pool.convert()

    passive_spent, passive_produced = pool.moved(ConversionPath.PASSIVE, METAL, WATER)
    demand_spent, demand_produced = pool.moved(ConversionPath.DEFICIT, METAL, WATER)

    assert passive_produced > 0.0 and demand_produced > 0.0
    assert passive_produced != demand_produced

    # The two together account for the whole tick — nothing moved unattributed.
    assert metal_before - pool.storage[METAL] == pytest.approx(
        passive_spent + demand_spent, rel=1e-9
    )
    assert pool.storage[WATER] == pytest.approx(
        passive_produced + demand_produced, rel=1e-9
    )

    paths = [t.path for t in pool.last_transfers if t.source is METAL and t.target is WATER]
    assert paths == [ConversionPath.PASSIVE, ConversionPath.DEFICIT]


def test_moved_sums_every_matching_transfer_rather_than_the_first(pool):
    """`moved` must never under-report.

    Today each path commits at most one transfer per edge, so returning the first match
    is indistinguishable from summing — until the day a path commits twice, which is
    exactly the failure per-path attribution exists to expose. Under-reporting it would
    silently break the reconciliation `Δstorage == passive + deficit` that the workshop
    CSV and every accounting test rest on. Built by hand because the current
    implementation cannot produce a duplicate, which is the whole point."""
    pool.last_transfers = (
        Transfer(ConversionPath.PASSIVE, METAL, WATER, 0.5, 0.4),
        Transfer(ConversionPath.DEFICIT, METAL, WATER, 1.0, 0.8),
        Transfer(ConversionPath.PASSIVE, METAL, WATER, 0.25, 0.2),
        Transfer(ConversionPath.PASSIVE, ElementType.EARTH, METAL, 9.0, 9.0),
    )

    assert pool.moved(ConversionPath.PASSIVE, METAL, WATER) == (0.75, 0.6000000000000001)
    assert pool.moved(ConversionPath.DEFICIT, METAL, WATER) == (1.0, 0.8)
    assert pool.moved(ConversionPath.PASSIVE, WOOD, WATER) == (0.0, 0.0)


def test_a_duplicated_transfer_is_visible_in_the_transfer_list(pool):
    """And this is what actually distinguishes "one ran twice" from "both ran once".

    Not the sums — a duplicate lands in the same sum — and not Story 1.0d's essence
    invariant, which compares `outflow x CYCLE_EFFICIENCY` against `inflow`, a ratio a
    duplicated transfer preserves exactly. The *list* is the discriminator: two
    `METAL -> WATER` entries under one path is a different list from one under each."""
    _set(pool, WATER=0.0, METAL=10.0)
    pool.convert()

    honest = [
        t.path for t in pool.last_transfers if t.source is METAL and t.target is WATER
    ]
    assert honest == [ConversionPath.PASSIVE, ConversionPath.DEFICIT]

    duplicated = pool.last_transfers + (pool.last_transfers[-1],)
    pool.last_transfers = duplicated
    doubled = [
        t.path for t in pool.last_transfers if t.source is METAL and t.target is WATER
    ]
    assert doubled != honest, "a second run of one path must change the record"


def test_attribution_is_this_tick_only_and_is_not_an_accumulator(pool):
    """Observers read it and reset nothing; the pool overwrites it every tick."""
    _set(pool, WATER=0.0, METAL=10.0)
    pool.convert()
    assert pool.moved(ConversionPath.DEFICIT, METAL, WATER)[1] > 0.0

    _set(pool, WATER=12.0)
    pool.convert()
    assert pool.moved(ConversionPath.DEFICIT, METAL, WATER) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Row 7: recovery
# ---------------------------------------------------------------------------

def test_the_elevated_rate_stops_once_water_recovers_and_passive_resumes(pool):
    _set(pool, WATER=0.0, METAL=10.0)
    pool.convert()
    assert pool.deficit_active

    _set(pool, WATER=12.0)  # eaten a Water resource
    pool.convert()

    assert not pool.deficit_active
    assert pool.moved(ConversionPath.DEFICIT, METAL, WATER) == (0.0, 0.0)
    assert pool.moved(ConversionPath.PASSIVE, METAL, WATER)[1] > 0.0


def test_a_deep_deficit_recovers_over_several_ticks_and_then_disarms(pool):
    """Driven end to end: armed, converting, then quiet once Water is back."""
    _set(pool, WATER=0.0, METAL=20.0)
    armed = []
    for _ in range(6):
        pool.convert()
        armed.append(pool.deficit_active)
        pool.storage[WATER] += 5.0  # eating faster than the legs drain

    assert armed[0] is True
    assert armed[-1] is False
    assert pool.storage[WATER] > pool.deficit_level()


# ---------------------------------------------------------------------------
# The organism holds a pool and owns no conversion of its own (`AD-4`)
# ---------------------------------------------------------------------------

def test_the_organism_has_no_conversion_method_left():
    """E3 substitutes a MeridianNetwork behind the same port. Anything that accreted
    back onto the organism would have to be moved again."""
    assert not hasattr(TaobotSimple, "_cycle_elements")


def test_the_organism_and_its_pool_share_one_storage_dict():
    """Two names, one dict — never two that can drift. The invariant harness swaps the
    dict for an observer through exactly this property."""
    bot = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    assert bot.storage is bot.chi.storage

    bot.storage[WOOD] = 4.0
    assert bot.chi.storage[WOOD] == pytest.approx(4.0)

    replacement = dict(bot.storage)
    bot.storage = replacement
    assert bot.chi.storage is replacement


def test_a_bot_built_without_a_world_still_obeys_the_shipped_laws():
    bot = TaobotSimple(x=0.0, y=0.0, entity_id=1)
    assert bot.chi.laws == default_chi_laws()


def test_a_bot_spawned_by_a_world_obeys_that_world_s_laws(small_world):
    bot = small_world.spawn_taobot(x=1.0, y=1.0)
    assert bot.chi.laws is small_world.config.chi


def test_a_world_config_can_override_the_chi_laws(tmp_path):
    """The same deliberate escape hatch `fire_arena` uses for `chemistry`."""
    from world import WorldConfig

    (tmp_path / "laws.json").write_text(
        json.dumps({"chemistry": {"degrade_rate": 0.001},
                    "chi": {"water_deficit_threshold": 0.008,
                            "deficit_conversion_rate": 0.025}})
    )
    config = tmp_path / "w.json"
    config.write_text(json.dumps({
        "name": "override", "laws": "laws.json",
        "world": {"width": 10, "height": 10},
        "resources": {"initial_count": 0, "respawn_delay_ticks": 1,
                      "spawn_weights": {e.name: 1.0 for e in ELEMENT_LIST}},
        "hazards": {"initial_count": 0,
                    "spawn_weights": {e.name: 1.0 for e in ELEMENT_LIST}},
        "taobots": {"initial_count": 0, "target_population": 0},
        "chi": {"deficit_conversion_rate": 0.5},
    }))

    loaded = WorldConfig.from_json(config)
    assert loaded.chi.deficit_conversion_rate == pytest.approx(0.5)
    assert loaded.chi.water_deficit_threshold == pytest.approx(0.008), "inherits the law"


def test_a_config_with_no_laws_file_still_gets_the_universal_chi_laws(tmp_path):
    """A law is universal by definition — a config that declares none does not get to
    run under a different physics, it gets the shipped one."""
    from world import WorldConfig

    config = tmp_path / "w.json"
    config.write_text(json.dumps({
        "name": "bare",
        "world": {"width": 10, "height": 10},
        "resources": {"initial_count": 0, "respawn_delay_ticks": 1,
                      "spawn_weights": {e.name: 1.0 for e in ELEMENT_LIST}},
        "hazards": {"initial_count": 0,
                    "spawn_weights": {e.name: 1.0 for e in ELEMENT_LIST}},
        "taobots": {"initial_count": 0, "target_population": 0},
        "chemistry": {"degrade_rate": 0.001},
    }))

    assert WorldConfig.from_json(config).chi == default_chi_laws()


# ---------------------------------------------------------------------------
# The trigger prevents the starvation it exists to prevent
# ---------------------------------------------------------------------------

def test_the_trigger_keeps_legs_fed_where_the_passive_cycle_alone_cannot():
    """The story in one test: a bot with Metal and no Water walks without starving.

    With only the passive cycle the legs receive `0.0008 x storage[METAL]` a tick
    against a cruise draw of 0.020 — an order of magnitude short — so integrity slides.
    The comparison is run twice on the same bot arrangement, once with the demand path
    disabled by a zero threshold, so the difference is the trigger and nothing else."""
    def walk(laws: ChiLaws) -> float:
        bot = TaobotSimple(x=0.0, y=0.0, entity_id=1, run_seed=7, chi_laws=laws)
        bot.storage[METAL] = 20.0
        for _ in range(400):
            for leg in bot.legs:
                leg.set_thrust(leg.max_thrust * 0.5)  # cruise
            bot._tick_body_parts()
            bot.chi.convert()
        return min(leg.structural_integrity for leg in bot.legs)

    without = walk(ChiLaws(water_deficit_threshold=0.0, deficit_conversion_rate=0.025))
    with_trigger = walk(default_chi_laws())

    assert without < 0.5, "the passive cycle alone must not keep up — that is the story"
    assert with_trigger == 1.0, "the demand path must prevent the starvation outright"


# ---------------------------------------------------------------------------
# The tick phase order is behaviour, and is pinned here
# ---------------------------------------------------------------------------
#
# `AD-1` specifies `sense -> decide -> act -> chi -> upkeep -> age`; the build runs chi
# *after* upkeep and deliberately keeps doing so, because reordering changes behaviour
# above the deficit threshold and Story 1.2's acceptance forbids that. That reorder is a
# named, near-term change that lands exactly here — so the order it is being held at has
# to be enforced by something, or "we deliberately did not reorder" is an unverified
# claim and the reorder can arrive as a silent accident instead of a decision.

#: The phases `TaobotSimple.tick` runs, in the order it runs them.
RECORDED_PHASE_ORDER = ("sense+decide", "act", "body parts", "upkeep", "chi", "age")


def _run_phases_by_hand(bot: TaobotSimple, world) -> None:
    """`RECORDED_PHASE_ORDER`, spelled out."""
    resources, hazards = bot._sense(world)
    bot._decide(resources, hazards, world)
    bot._act(world)
    bot._tick_body_parts()
    bot._metabolize()
    bot.chi.convert()
    bot.age_ticks += 1


def _observable_state(bot: TaobotSimple) -> tuple:
    return (
        tuple(bot.storage[e] for e in ELEMENT_LIST),
        tuple(bot.organ(e) for e in ELEMENT_LIST),
        (bot.x, bot.y, bot.heading, bot.age_ticks),
        tuple((p.reserve, p.structural_integrity) for p in bot.body_parts),
    )


def _seeded_pair(default_config):
    """Two independent worlds built from the same seed, each holding one bot.

    Same seed and same construction, so their per-entity RNG streams are identical and
    any divergence is the phase order and nothing else."""
    from world import World

    pair = []
    for _ in range(2):
        world = World(default_config, seed=20260812)
        world.initialize()
        bot = world.spawn_taobot(x=40.0, y=30.0)
        # Below the trigger with Metal to serve it, so the chi phase is doing real work
        # every tick — an ordering test on a bot where conversion moves nothing proves
        # nothing about where conversion sits.
        for element in ELEMENT_LIST:
            bot.storage[element] = bot.storage_capacity[element] * 0.4
        bot.storage[WATER] = 0.0
        pair.append((world, bot))
    return pair


def test_the_tick_runs_the_phases_in_the_recorded_order(default_config):
    """Digit for digit, over enough ticks that a reordering cannot hide.

    Compared tick by tick rather than only at the end: two orderings that diverge and
    reconverge would still be caught at the tick they parted."""
    (world_a, bot_a), (world_b, bot_b) = _seeded_pair(default_config)

    assert _observable_state(bot_a) == _observable_state(bot_b), "the twins start equal"

    for tick in range(120):
        bot_a.tick(world_a)
        _run_phases_by_hand(bot_b, world_b)
        assert _observable_state(bot_a) == _observable_state(bot_b), (
            f"tick {tick}: `TaobotSimple.tick` no longer runs the phases in "
            f"{RECORDED_PHASE_ORDER}. That order is deliberate — chi runs after upkeep, "
            "against AD-1, because reordering changes behaviour above the deficit "
            "threshold. If the reorder is being made on purpose, it needs its own story "
            "and its own captured baseline; see deferred-work.md."
        )


def test_the_recorded_order_is_not_vacuous_because_reordering_would_change_things(
    default_config,
):
    """The counterpart, and the reason the test above has teeth.

    Runs the phases with chi hoisted above upkeep — `AD-1`'s order — and asserts the
    state really does part company. Without this, the pin could be sitting on an
    ordering that makes no difference, and pass forever."""
    (world_a, bot_a), (world_b, bot_b) = _seeded_pair(default_config)

    def ad1_order(bot, world) -> None:
        resources, hazards = bot._sense(world)
        bot._decide(resources, hazards, world)
        bot._act(world)
        bot._tick_body_parts()
        bot.chi.convert()      # <-- hoisted above upkeep
        bot._metabolize()
        bot.age_ticks += 1

    for _ in range(120):
        bot_a.tick(world_a)
        ad1_order(bot_b, world_b)

    assert _observable_state(bot_a) != _observable_state(bot_b), (
        "reordering the phases made no observable difference — if that is genuinely "
        "true, the ordering constraint this story cites has evaporated and the "
        "deferred AD-1 restructure is free"
    )
