"""Story 1.0d, Phase B — the six invariants, run over the harness's scenarios.

Two things are asserted here, and the second matters as much as the first:

1. All six invariants hold on **unmodified** code, across every starting condition in
   `invariant_harness.SCENARIOS`. This is a regression net for Stories 1.2 and 1.3, so
   a failure is an existing bug to report in the spec's Design Notes — never a bound to
   soften or a scenario to skip.
2. The invariants have **teeth**. An assertion that cannot fail is worse than no
   assertion, because it reads as coverage. Every check here is shown firing on a
   deliberately broken input, and the essence invariant — the one Story 1.2 depends on
   — gets a full negative control that runs the real harness against an inverted cycle.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from body_parts import LegPart
from chi import (
    CYCLE_EFFICIENCY,
    CYCLE_RATE,
    CYCLE_SEQUENCE,
    ChiPool,
    ConversionPath,
    Transfer,
)
from common import ELEMENT_LIST, ElementType
from taobot_simple import DERIVED_ORGANS, ORGAN_MAX, TaobotSimple

# `tests/` carries an `__init__.py`, so the harness is a submodule of the `tests`
# package rather than a top-level module — import it as one, or it resolves only when
# pytest happens to be run from inside `tests/`.
from tests.invariant_harness import (
    PER_TICK_INVARIANTS,
    SCENARIOS,
    Scenario,
    Violation,
    assert_invariants,
    build,
    check_no_numeric_corruption,
    check_organ_bounded,
    check_part_integrity_bounded,
    check_storage_bounded,
    instrument,
    run_scenario,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# The harness on current code
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_all_six_invariants_hold_on_current_code(scenario: Scenario):
    """Every invariant, every tick, across every starting condition.

    `assert_invariants` runs the scenario twice: once to check the five per-tick
    invariants, and a second time so the sixth — determinism — has something to compare
    against. Two runs in the same process and environment, never a committed digest."""
    result = assert_invariants(scenario)
    assert result.ticks_run == scenario.ticks


def test_the_scenarios_cover_the_conditions_the_story_names():
    """At least healthy, starving and degraded legs, per the task list."""
    names = {s.name for s in SCENARIOS}
    assert {"healthy", "starving", "degraded legs"} <= names


def test_adding_a_scenario_is_a_data_change():
    """Stories 1.2 and 1.3 must be able to add a starting condition without writing a
    second harness. Proven by running one the harness has never seen."""
    hoarder_in_a_hazard_field = Scenario(
        name="hoarder under fire",
        storage={"WOOD": 0.9, "WATER": 0.1, "METAL": 0.0, "FIRE": 0.5, "EARTH": 0.75},
        leg_integrity=0.6,
        params={"speed": 0.8, "collect_rate": 5.0},
        resources=40,
        hazards=30,
        ticks=400,
        seed=7,
    )
    result = assert_invariants(hoarder_in_a_hazard_field)
    assert result.ticks_run == 400


def test_the_essence_check_is_not_vacuous():
    """A scenario where nothing converts would pass the essence invariant by doing
    nothing at all. Assert the harness actually observes conversion happening."""
    scenario = next(s for s in SCENARIOS if s.name == "healthy")
    world, bot = build(scenario)
    observed = instrument(bot)
    world.tick()

    assert any(v > 0 for v in observed.outflow.values()), "no storage left any element"
    assert any(v > 0 for v in observed.inflow.values()), "no storage reached any element"
    for source, target in CYCLE_SEQUENCE:
        assert observed.outflow[source] > 0.0, f"{source.name} never paid anything"
        assert observed.inflow[target] > 0.0, f"{target.name} never received anything"


def test_the_essence_check_never_sees_eating_or_metabolism():
    """Scope is the conversion phase only. Eating legitimately creates storage and
    `_metabolize` legitimately destroys it, so an essence check that observed either
    would fire on correct behaviour."""
    scenario = next(s for s in SCENARIOS if s.name == "healthy")
    world, bot = build(scenario)
    observed = instrument(bot)
    world.tick()

    # Outside the conversion phase the recorder is disarmed: a large deposit and a
    # large withdrawal in the shape of eating and metabolism must leave it unmoved.
    before_in = dict(observed.inflow)
    before_out = dict(observed.outflow)
    bot.storage[ElementType.WOOD] = bot.storage_capacity[ElementType.WOOD]
    bot.storage[ElementType.WOOD] = 0.0
    assert dict(observed.inflow) == before_in
    assert dict(observed.outflow) == before_out


# ---------------------------------------------------------------------------
# The negative control — proving the essence invariant has teeth
# ---------------------------------------------------------------------------

def inverted_convert(self) -> None:
    """`ChiPool.convert` with `spent` derived **before** capping — the bug.

    A hand-copy of the real algorithm whose only change is the order of two lines, in
    *both* paths. Correct code caps `produced` against the target's room and then
    derives what the source pays; this charges the source the full pre-cap amount and
    lets the target receive whatever fits. Essence is destroyed: the source pays for
    chi that never arrives.

    **Re-derived for Story 1.2.** The previous version copied `_cycle_elements`, which
    no longer exists — conversion moved to the chi tier and grew a second, demand-
    triggered Metal->Water path. That drift was logged as a known consequence of this
    story, and the control was re-derived against the new implementation rather than
    relaxed. `test_the_negative_control_still_mirrors_the_real_algorithm` below is what
    keeps it honest next time.

    This is a deliberate, permanent negative control, not scaffolding: the essence
    invariant is the net that catches the two paths double-converting, and a net nobody
    has watched fail is an assumption."""
    snapshot = {e: self.storage[e] for e in ELEMENT_LIST}
    committed_in = dict.fromkeys(ELEMENT_LIST, 0.0)
    committed_out = dict.fromkeys(ELEMENT_LIST, 0.0)
    transfers: list[tuple[ConversionPath, ElementType, ElementType, float, float]] = []

    def commit(path, source, target, spent, produced):
        committed_out[source] += spent
        committed_in[target] += produced
        transfers.append((path, source, target, spent, produced))

    for source, target in CYCLE_SEQUENCE:
        amount_out = CYCLE_RATE * snapshot[source]
        spent = amount_out  # <-- derived before the cap; the real code derives it after
        room = self.capacity[target] - snapshot[target]
        produced = min(amount_out * CYCLE_EFFICIENCY, room)
        if produced <= 0.0:
            continue
        commit(ConversionPath.PASSIVE, source, target, spent, produced)

    water = ElementType.WATER
    metal = ElementType.METAL
    projected_water = snapshot[water] + committed_in[water] - committed_out[water]
    trigger_level = self.deficit_level()
    self.deficit_active = projected_water < trigger_level
    if self.deficit_active:
        projected_metal = snapshot[metal] + committed_in[metal] - committed_out[metal]
        demand = trigger_level - projected_water
        amount_out = min(
            self.laws.deficit_conversion_rate * snapshot[metal], projected_metal
        )
        spent = amount_out  # <-- the same inversion, on the demand path
        room = self.capacity[water] - projected_water
        produced = min(amount_out * CYCLE_EFFICIENCY, demand, room)
        if produced > 0.0:
            commit(ConversionPath.DEFICIT, metal, water, spent, produced)

    # Applied and recorded the same way the real one does, so the control mirrors
    # attribution too and not only storage. (Wiping `last_transfers` here would let the
    # per-path record drift arbitrarily while the mirror test below still passed.)
    self.last_transfers = tuple(
        self.apply(Transfer(path, source, target, spent, produced))
        for path, source, target, spent, produced in transfers
    )


# The inversion is only *observable* where a target is partially capped. Uncapped,
# `produced` is `amount_out * CYCLE_EFFICIENCY` either way and the two implementations
# agree exactly — so a negative control run on a roomy scenario would prove nothing.
# `brimming` is the scenario that puts every transfer under a cap.
_CAPPED_SCENARIO = next(s for s in SCENARIOS if s.name == "brimming")

# The demand path's own inversion needs a scenario where that path is capped by
# `demand` rather than by the Metal available — which is exactly the deficit regime.
_DEFICIT_SCENARIO = next(s for s in SCENARIOS if s.name == "water deficit")


def test_inverted_cycle_makes_the_essence_assertion_fail(monkeypatch):
    """Acceptance: with `spent` computed before capping, the harness fails."""
    monkeypatch.setattr(ChiPool, "convert", inverted_convert)

    with pytest.raises(AssertionError) as excinfo:
        assert_invariants(replace(_CAPPED_SCENARIO, ticks=50))

    message = str(excinfo.value)
    assert "essence exact" in message
    # The failure must name the tick and the offending value, not merely say "failed".
    # Word-bounded: a plain `"tick 1" in message` also matches "tick 10".
    assert re.search(r"\btick 1\b", message), message
    assert "should have gained" in message


def test_the_inverted_cycle_is_caught_by_essence_and_nothing_else(monkeypatch):
    """The negative control must fail for the *right reason*.

    If the inversion also tripped a bounds check, the test above would pass without the
    essence invariant contributing anything."""
    monkeypatch.setattr(ChiPool, "convert", inverted_convert)
    result = run_scenario(replace(_CAPPED_SCENARIO, ticks=50))

    kinds = {v.invariant for v in result.violations}
    assert kinds == {"essence exact"}, f"expected only essence failures, got {kinds}"

    worst = max(result.violations, key=lambda v: abs(v.value))
    assert abs(worst.value) > 1e-4, (
        "the inversion should lose a visible amount of essence, not a rounding error"
    )


def test_the_inverted_demand_path_is_caught_too(monkeypatch):
    """Story 1.2's half of the control.

    `brimming` never enters a deficit, so it exercises only the passive path's
    inversion. Run the control where the *demand* path is the one under a cap and the
    essence invariant must catch that inversion as well — otherwise the second
    conversion path would be riding on a net that only ever watched the first."""
    monkeypatch.setattr(ChiPool, "convert", inverted_convert)
    result = run_scenario(replace(_DEFICIT_SCENARIO, ticks=50))

    kinds = {v.invariant for v in result.violations}
    assert kinds == {"essence exact"}, f"expected only essence failures, got {kinds}"
    assert any(
        "METAL->WATER" in v.detail for v in result.violations
    ), "the demand path's own edge must be among the failures"


def test_the_negative_control_still_mirrors_the_real_algorithm():
    """The control is only a control while it is a *copy* of the real thing.

    It is kept in sync by hand, so it drifts silently the moment conversion changes —
    which is exactly what Story 1.2 did to the previous version. Pin the property that
    matters: away from any cap the two implementations must agree exactly, because the
    inversion is the *only* difference between them. If a third conversion path is
    added and this control is not updated, the numbers part company and this fails."""
    _, bot = build(replace(next(s for s in SCENARIOS if s.name == "healthy"), ticks=0))
    # Room everywhere, so no `room` cap binds on the passive cycle; Water empty so the
    # demand path runs too, and Metal low enough that the *rate* is what limits it
    # rather than the shortfall. With nothing capped, the inversion is invisible and the
    # two implementations must agree digit for digit — so any disagreement here is
    # drift, which is exactly what this test is for.
    for element in ELEMENT_LIST:
        bot.storage[element] = bot.storage_capacity[element] * 0.5
    bot.storage[ElementType.WATER] = 0.0
    bot.storage[ElementType.METAL] = 0.4

    before = dict(bot.storage)
    bot.chi.convert()
    after_real = dict(bot.storage)
    real_record = [
        (t.path, t.source, t.target) for t in bot.chi.last_transfers
    ]

    bot.storage.update(before)
    inverted_convert(bot.chi)
    after_inverted = dict(bot.storage)
    inverted_record = [
        (t.path, t.source, t.target) for t in bot.chi.last_transfers
    ]

    drifted = (
        "the negative control has drifted from the real algorithm — re-derive it "
        "against the current `ChiPool.convert` rather than relaxing anything"
    )
    # A relative tolerance, not `==`: the inversion's one intended difference is
    # `spent = amount_out` where the real code writes `produced / CYCLE_EFFICIENCY`,
    # and `(x * 0.8) / 0.8` does not always round-trip to `x`. So the two can differ by
    # an ULP with nothing wrong at all. Real drift — a whole conversion path missing —
    # moves storage by ~0.15 here, twelve orders of magnitude above this bound.
    for element in ELEMENT_LIST:
        assert after_real[element] == pytest.approx(
            after_inverted[element], rel=1e-9, abs=1e-12
        ), f"{drifted} ({element.name})"

    # Storage agreement alone would not notice a control that stopped recording which
    # path moved what, which is half of what it is mirroring.
    assert real_record == inverted_record, drifted


def test_the_inversion_is_invisible_without_a_cap_which_is_why_brimming_exists():
    """Documents the scenario requirement rather than leaving it as folklore.

    With room to spare, the inverted and correct cycles compute identical numbers, so
    the negative control genuinely needs a capped starting condition. If someone later
    'simplifies' `brimming` away, this test explains what was lost."""
    roomy = replace(next(s for s in SCENARIOS if s.name == "healthy"), ticks=50)

    baseline = run_scenario(roomy)
    original = ChiPool.convert
    ChiPool.convert = inverted_convert
    try:
        inverted = run_scenario(roomy)
    finally:
        ChiPool.convert = original

    assert baseline.ok and inverted.ok
    assert baseline.digest == inverted.digest, (
        "uncapped, the two implementations must be numerically identical"
    )


# ---------------------------------------------------------------------------
# Every invariant is wired into the harness loop
# ---------------------------------------------------------------------------
#
# These are the important tests in this file. The unit-level teeth tests further down
# call the check functions directly, which proves the *checks* work but says nothing
# about whether `run_scenario` still calls them: deleting all four calls from the
# harness loop once left the whole suite green, leaving a net that advertised six
# invariants and enforced two.
#
# Each test below breaks one arithmetic site in the simulation so that *simulated*
# state goes out of range, then asserts `assert_invariants` raises naming that
# invariant — reaching the check only through the harness, exactly as 1.2 and 1.3 will.


def _mutated_scenario(name: str, ticks: int = 60) -> Scenario:
    return replace(next(s for s in SCENARIOS if s.name == name), ticks=ticks)


def test_storage_bound_is_wired_into_the_harness(monkeypatch):
    """Drop `_drain_organ`'s "can I afford it?" guard and storage goes negative."""
    def unguarded_drain(self, element, drain):
        if element in DERIVED_ORGANS:
            raise ValueError(element)
        self.storage[element] -= drain  # no floor, no affordability check

    monkeypatch.setattr(TaobotSimple, "_drain_organ", unguarded_drain)

    with pytest.raises(AssertionError, match=r"storage bounded"):
        assert_invariants(_mutated_scenario("starving"))


def test_part_integrity_bound_is_wired_into_the_harness(monkeypatch):
    """A repair that forgets to clamp — the shape Story 1.3 is about to add."""
    original_tick = LegPart.tick

    def overshooting_repair(self):
        original_tick(self)
        self.structural_integrity += 0.05  # no `min(1.0, ...)`

    monkeypatch.setattr(LegPart, "tick", overshooting_repair)

    with pytest.raises(AssertionError, match=r"part integrity bounded"):
        assert_invariants(_mutated_scenario("degraded legs"))


def test_organ_bound_is_wired_into_the_harness(monkeypatch):
    """Regeneration without its `min(ORGAN_MAX, ...)` clamp."""
    def unclamped_regen(self, element, drain):
        if element in DERIVED_ORGANS:
            raise ValueError(element)
        if self.storage[element] >= drain:
            self.storage[element] -= drain
            self._organs[element] = self._organs[element] + 1.0  # no ceiling
        else:
            self.storage[element] = 0.0
            self._organs[element] = max(0.0, self._organs[element] - 1.0)

    monkeypatch.setattr(TaobotSimple, "_drain_organ", unclamped_regen)

    with pytest.raises(AssertionError, match=r"organ bounded"):
        assert_invariants(_mutated_scenario("healthy"))


def test_numeric_corruption_is_wired_into_the_harness(monkeypatch):
    """An accumulator with a compounding bug, overflowing to infinity.

    Float overflow is silent in Python — `1e308 * 10` is `inf`, not an exception — so
    this is a realistic route to non-finite state rather than an injected sentinel.
    `_act` runs every tick, so the overflow is reached in three, not left to depend on
    whether the bot happened to bump into a hazard."""
    original_act = TaobotSimple._act

    def compounding_odometer(self, world):
        original_act(self, world)
        self.distance_moved = self.distance_moved * 1e200 + 1.0  # should be `+=`

    monkeypatch.setattr(TaobotSimple, "_act", compounding_odometer)

    with pytest.raises(AssertionError, match=r"no numeric corruption"):
        assert_invariants(_mutated_scenario("starving", ticks=20))


def test_every_invariant_is_exercised_by_the_scenario_set():
    """Suite-level coverage: no invariant is unexercised by every scenario at once.

    Per-scenario coverage is enforced inside `assert_invariants` via `Scenario.exercises`;
    this catches the case where every scenario legitimately disclaims the same one."""
    totals = dict.fromkeys(PER_TICK_INVARIANTS, 0)
    for scenario in SCENARIOS:
        result = run_scenario(replace(scenario, ticks=50))
        for invariant, count in result.evaluations.items():
            totals[invariant] += count

    unexercised = [name for name, count in totals.items() if count == 0]
    assert not unexercised, f"no scenario exercises: {unexercised}"


def test_the_water_deficit_scenario_really_crosses_the_deficit_repeatedly():
    """Story 1.2's scenario has to earn its place, not merely exist.

    A scenario that started below the threshold and stayed there would exercise the
    demand path but never the *transition*, and one that never dipped under it would
    exercise neither. Assert both directions actually happen, and that there are ticks
    where both paths move METAL->WATER at once — the regime the essence invariant is
    there to police."""
    world, _ = build(_DEFICIT_SCENARIO)

    was_armed: dict[int, bool] = {}
    crossings = armed_ticks = quiet_ticks = both_paths = 0
    # Every living bot, exactly as the harness itself checks — the scenario bot enters
    # the deficit on tick one and the bots that replace it start from empty storage, so
    # the transition is exercised more than once per run.
    for _ in range(_DEFICIT_SCENARIO.ticks):
        world.tick()
        for bot in world.taobots:
            armed = bot.chi.deficit_active
            if was_armed.get(bot.entity_id, armed) != armed:
                crossings += 1
            was_armed[bot.entity_id] = armed
            armed_ticks += int(armed)
            quiet_ticks += int(not armed)
            passive = bot.chi.moved(
                ConversionPath.PASSIVE, ElementType.METAL, ElementType.WATER
            )
            demand = bot.chi.moved(
                ConversionPath.DEFICIT, ElementType.METAL, ElementType.WATER
            )
            if passive[1] > 0.0 and demand[1] > 0.0:
                both_paths += 1

    assert armed_ticks > 0 and quiet_ticks > 0, "only one side of the threshold was seen"
    # Measured 4-6 across seeds 20260811, 7 and 99; asserted below that with margin.
    assert crossings >= 3, f"the threshold was crossed only {crossings} time(s)"
    assert both_paths >= 100, (
        f"only {both_paths} tick(s) had both paths moving METAL->WATER — this scenario "
        "exists to put the essence invariant in the regime where they overlap"
    )


def test_starving_exercises_no_conversion_and_says_so():
    """Pins the one declared coverage hole, so it stays deliberate.

    `starving` holds no storage, so every conversion pair is skipped. That is a real
    gap in what this scenario proves, and it is declared on the scenario rather than
    left to be discovered."""
    starving = next(s for s in SCENARIOS if s.name == "starving")
    assert "essence exact" not in starving.exercises

    result = run_scenario(replace(starving, ticks=100))
    assert result.evaluations["essence exact"] == 0
    # And it is pulling its weight on everything else.
    for invariant in starving.exercises:
        assert result.evaluations[invariant] > 0


# ---------------------------------------------------------------------------
# The other five invariants have teeth too
# ---------------------------------------------------------------------------

@pytest.fixture
def broken_bot() -> TaobotSimple:
    _, bot = build(replace(SCENARIOS[0], ticks=0))
    return bot


def _collect(check, bot) -> list[Violation]:
    found: list[Violation] = []
    check(bot, 1, lambda *args: found.append(Violation(*args)))
    return found


def test_storage_bound_check_fires_above_capacity(broken_bot):
    broken_bot.storage[ElementType.WOOD] = broken_bot.storage_capacity[ElementType.WOOD] + 1.0
    found = _collect(check_storage_bounded, broken_bot)
    assert len(found) == 1
    assert found[0].value == pytest.approx(broken_bot.storage[ElementType.WOOD])


def test_storage_bound_check_fires_below_zero(broken_bot):
    broken_bot.storage[ElementType.FIRE] = -0.5
    assert _collect(check_storage_bounded, broken_bot)


def test_storage_bound_check_accepts_the_endpoints(broken_bot):
    """Exactly empty and exactly full are legal states, not violations."""
    for element in ELEMENT_LIST:
        broken_bot.storage[element] = broken_bot.storage_capacity[element]
    assert _collect(check_storage_bounded, broken_bot) == []
    for element in ELEMENT_LIST:
        broken_bot.storage[element] = 0.0
    assert _collect(check_storage_bounded, broken_bot) == []


def test_part_integrity_check_fires_above_one(broken_bot):
    """The bound Story 1.3's Earth-funded repair is the first thing able to overshoot."""
    broken_bot.body_parts[0].structural_integrity = 1.5
    found = _collect(check_part_integrity_bounded, broken_bot)
    assert len(found) == 1
    assert found[0].value == 1.5


def test_organ_bound_check_fires_above_organ_max(broken_bot):
    broken_bot._organs[ElementType.FIRE] = ORGAN_MAX + 50.0
    found = _collect(check_organ_bounded, broken_bot)
    assert len(found) == 1
    assert found[0].value == ORGAN_MAX + 50.0


def test_organ_bound_check_reads_derived_organs_through_the_accessor(broken_bot):
    """Water is derived from its parts, so a part out of range is what pushes it out."""
    for leg in broken_bot.legs:
        leg.structural_integrity = 3.0
    # `_derive_organ` clamps, so the organ itself stays in range — the *part* check is
    # what catches this. Pin that division of labour so neither check is assumed to
    # cover the other.
    assert _collect(check_organ_bounded, broken_bot) == []
    assert _collect(check_part_integrity_bounded, broken_bot)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_numeric_corruption_check_fires(broken_bot, bad):
    broken_bot.storage[ElementType.EARTH] = bad
    found = _collect(check_no_numeric_corruption, broken_bot)
    assert found
    assert "storage[EARTH]" in found[0].detail


def test_nan_is_why_the_corruption_check_is_not_redundant(broken_bot):
    """NaN compares false against every bound, so it slips past the bounds checks and
    only the finiteness check catches it. The infinities do trip the bounds checks —
    it is specifically NaN that would otherwise travel silently."""
    broken_bot.storage[ElementType.EARTH] = float("nan")
    assert _collect(check_storage_bounded, broken_bot) == []
    assert _collect(check_no_numeric_corruption, broken_bot)

    broken_bot.storage[ElementType.EARTH] = float("inf")
    assert _collect(check_storage_bounded, broken_bot)


def test_determinism_check_fires_when_a_bot_reaches_for_a_global_stream(monkeypatch):
    """The sixth invariant, and a direct regression guard on Phase A.

    A bot drawing from module-level `random` again is exactly the failure `AD-12`
    removed; two runs at the same seed must stop matching."""
    import random as global_random

    original_decide = TaobotSimple._decide

    def leaky_decide(self, nearby_resources, nearby_hazards, world):
        self._desired_heading += global_random.uniform(-1e-3, 1e-3)
        return original_decide(self, nearby_resources, nearby_hazards, world)

    monkeypatch.setattr(TaobotSimple, "_decide", leaky_decide)

    with pytest.raises(AssertionError, match="determinism"):
        assert_invariants(replace(SCENARIOS[0], ticks=30))


# ---------------------------------------------------------------------------
# The suite is not tied to the working directory
# ---------------------------------------------------------------------------

_FOREIGN_CWD_CHILD = "TAOBOTS_FOREIGN_CWD_CHILD"


@pytest.mark.skipif(
    os.environ.get(_FOREIGN_CWD_CHILD) == "1",
    reason="this is the child run; recursing would not terminate",
)
def test_the_full_suite_passes_from_a_foreign_working_directory(tmp_path):
    """Acceptance: `pytest` from a directory other than the repo root passes.

    Run as a real subprocess from `tmp_path`, because the failure this guards against
    is a module resolving a path against the working directory — which an in-process
    `chdir` inside an already-imported test session would not reproduce faithfully."""
    env = {
        **os.environ,
        _FOREIGN_CWD_CHILD: "1",
        "SDL_VIDEODRIVER": "dummy",
        "SDL_AUDIODRIVER": "dummy",
    }
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(REPO_ROOT / "tests"),
         "-q", "-p", "no:cacheprovider"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, (
        f"suite failed when run from {tmp_path}:\n{proc.stdout[-4000:]}\n{proc.stderr[-2000:]}"
    )
