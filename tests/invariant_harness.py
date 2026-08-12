"""A scenario-parameterised invariant harness — Story 1.0d, Phase B.

Invariants are asserted **over runs, not examples**: a scenario ticks a world for
thousands of ticks and all six invariants are checked on every living taobot every
tick. A hand-written example test pins one arithmetic path at one moment; this pins
the whole state space a bot actually wanders through.

The harness is parameterised over starting conditions (`Scenario`). Stories 1.2 and
1.3 add an entry to `SCENARIOS` rather than writing a second harness.

**Report, do not relax.** This runs against unmodified code, so a failure here is an
existing bug in the simulation, not a bug in the harness. Record it in the spec's
Design Notes with the tick and the offending value and leave the assertion intact.

The six invariants (the epic's table):

| Storage bounded       | `0 <= storage[e] <= capacity[e]`, all five            |
| Part integrity        | `0.0 <= structural_integrity <= 1.0`, every part      |
| Organ integrity       | `0.0 <= organ(e) <= ORGAN_MAX`, all five              |
| Essence exact         | per pair across the chi phase, equality not `<=`      |
| No numeric corruption | no NaN/inf anywhere in float state                    |
| Determinism           | same seed, same tick count -> identical state         |
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from common import ELEMENT_LIST, ElementType
from taobot_simple import (
    CYCLE_EFFICIENCY,
    CYCLE_SEQUENCE,
    ORGAN_MAX,
    TaobotSimple,
)
from tests.state_snapshot import state_repr
from world import World, WorldConfig

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"

# Tolerances for the essence equality. Neither is a relaxation of the invariant — they
# are the floor of what float arithmetic can represent, and both were measured rather
# than guessed.
#
# The check compares two *observed* storage deltas, and an observed delta is a
# subtraction of two nearby storage values: reading a transfer of ~1e-2 out of a
# storage of ~4e1 cancels away roughly twelve of the sixteen significant digits before
# the harness ever sees it. That noise is unavoidable and has nothing to do with
# essence being conserved.
#
# Measured over 160,000 conversion pairs (4 scenarios x 20 seeds x 400 ticks) on
# correct code, the worst deviation observed was 4.0e-13 relative and 2.8e-15
# absolute. The values below sit ~400x above both, so they absorb float noise with
# margin while staying far tighter than anything a real leak could hide behind: the
# inversion this invariant exists to catch is wrong by ~60%, not by 1e-9.
ESSENCE_REL_TOL = 1e-9
ESSENCE_ABS_TOL = 1e-12

# Bounds are checked exactly. An epsilon was tried here on the theory that
# `storage + (capacity - storage)` could land one ULP above `capacity`, but measurement
# says it never does — so there is nothing to forgive, and an unearned epsilon is just
# a quieter assertion. If a future change makes a bound overshoot by a ULP, that is a
# finding to report, not a constant to raise.
BOUND_EPS = 0.0

# Per invariant, how many violations to record before counting the rest. A broken
# invariant fires on most ticks, and 3000 identical failures obscure rather than
# inform — but the count still tells you it is systemic, not a one-tick blip.
MAX_REPORTED_PER_INVARIANT = 5

# The five per-tick invariants, by the name they report under. Determinism is the
# sixth and is asserted across two runs rather than within one.
PER_TICK_INVARIANTS = (
    "storage bounded",
    "part integrity bounded",
    "organ bounded",
    "essence exact",
    "no numeric corruption",
)
DETERMINISM = "determinism"
ALL_INVARIANTS = PER_TICK_INVARIANTS + (DETERMINISM,)


# ---------------------------------------------------------------------------
# Scenarios — the starting conditions the harness is parameterised over
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Scenario:
    """One starting condition. Add an entry to `SCENARIOS` to cover a new regime.

    `storage` is a *fraction of capacity*, not an absolute amount, so a scenario reads
    the same for every archetype whatever its capacities are. Pass a float for all five
    elements or a `{element name: fraction}` dict for a specific mix.

    The starting condition applies to the bot the harness spawns. If that bot dies and
    the world refills the population, the replacement starts from ordinary defaults —
    which is intended: "what happens after the scenario bot dies" is also state the
    invariants must hold through.

    `exercises` declares which invariants this scenario is expected to *meaningfully*
    evaluate, and is checked in both directions: an invariant it claims must be
    exercised at least once, and one it disclaims must be exercised exactly zero times.
    Without that, a scenario can silently stop covering an invariant — `starving` holds
    no storage, so every conversion pair is skipped and the essence check racks up
    thousands of vacuous `0 == 0` passes that look exactly like coverage."""

    name: str
    storage: float | dict[str, float] = 0.0
    leg_integrity: float = 1.0
    params: dict | None = None
    resources: int = 0
    hazards: int = 0
    population: int = 1
    ticks: int = 3000
    seed: int = 20260811
    config: str = "default_world.json"
    exercises: frozenset[str] = frozenset(PER_TICK_INVARIANTS)


# At least the three the spec names, plus one that puts the conversion phase under a
# capacity cap — the only regime where the essence invariant can tell a correct cycle
# from an inverted one, and therefore the regime the negative control uses.
SCENARIOS: list[Scenario] = [
    Scenario(
        name="healthy",
        storage=0.6,
        resources=150,
        hazards=20,
    ),
    Scenario(
        name="starving",
        storage=0.0,
        resources=0,
        hazards=0,
        # Empty storage means every conversion pair hits `continue`, so this scenario
        # exercises the essence invariant zero times — declared, not silent. It earns
        # its place on the other four: it is the only scenario that drives organs to
        # zero, kills bots and exercises the respawn path.
        exercises=frozenset(PER_TICK_INVARIANTS) - {"essence exact"},
    ),
    Scenario(
        name="degraded legs",
        storage=0.5,
        leg_integrity=0.2,
        resources=20,
        hazards=0,
    ),
    Scenario(
        # Storage just below capacity, so every target's `room` is smaller than the
        # amount its source offers and all five transfers are capped. A correct cycle
        # derives `spent` from the capped `produced` and stays exact here; an inverted
        # one charges the source full price and loses essence. See `test_invariants.py`.
        name="brimming",
        storage=0.9995,
        resources=0,
        hazards=0,
    ),
]


# ---------------------------------------------------------------------------
# Observed storage — how the essence invariant sees the conversion phase
# ---------------------------------------------------------------------------

class ObservedStorage(dict):
    """The bot's `storage` dict, recording the writes made while it is armed.

    This is how the essence check gets **per-pair** deltas out of **observed storage**.
    The two constraints pull against each other: the epic's assertion is per pair
    (`Δstorage[target] == −Δstorage[source] × CYCLE_EFFICIENCY`), but a plain
    before/after snapshot of the phase cannot supply that — every element is both a
    source and a target in the cycle, so its net delta mixes an outflow and an inflow
    and the two can no longer be told apart.

    Watching the writes separates them without reading `spent` or `produced`. A write
    that lowers `storage[e]` is an outflow *observed on storage*; one that raises it is
    an inflow. Each element is a source exactly once and a target exactly once per
    cycle, so the accumulated outflow of a pair's source and inflow of its target are
    that pair's two deltas.

    It survives a second conversion path being added (Story 1.2): more writes simply
    accumulate into the same totals, and the identity still has to hold across them.
    That is the point — a whole-phase net delta could not tell a correct second path
    from the same path running twice, and this can."""

    def __init__(self, base: dict) -> None:
        super().__init__(base)
        self._armed = False
        self.outflow: dict[ElementType, float] = {}
        self.inflow: dict[ElementType, float] = {}
        self.begin_phase()
        self._armed = False

    def begin_phase(self) -> None:
        """Start recording. Called as the conversion phase is entered."""
        self.outflow = dict.fromkeys(self, 0.0)
        self.inflow = dict.fromkeys(self, 0.0)
        self._armed = True

    def end_phase(self) -> None:
        """Stop recording — eating and `_metabolize` must never be observed.

        Scope matters as much as the assertion: eating legitimately creates storage and
        `_metabolize` legitimately destroys it, so an essence check that saw either
        would fire on correct behaviour."""
        self._armed = False

    def __setitem__(self, key, value) -> None:
        if self._armed:
            delta = value - self.get(key, 0.0)
            if delta < 0.0:
                self.outflow[key] = self.outflow.get(key, 0.0) - delta
            elif delta > 0.0:
                self.inflow[key] = self.inflow.get(key, 0.0) + delta
        super().__setitem__(key, value)


def instrument(bot: TaobotSimple) -> ObservedStorage:
    """Give `bot` an observing `storage` dict, armed only during the chi phase.

    Instance-level, not class-level: the harness observes the bots it built and leaves
    the class untouched, so two scenarios in one process cannot contaminate each other."""
    existing = getattr(bot, "_harness_storage", None)
    if existing is not None:
        return existing

    observed = ObservedStorage(bot.storage)
    bot.storage = observed
    bot._harness_storage = observed  # type: ignore[attr-defined]

    inner = bot._cycle_elements

    def watched_cycle() -> None:
        observed.begin_phase()
        try:
            inner()
        finally:
            observed.end_phase()

    bot._cycle_elements = watched_cycle  # type: ignore[method-assign]
    return observed


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Violation:
    """One invariant failure, carrying the tick and the offending value."""

    invariant: str
    tick: int
    entity_id: int
    detail: str
    value: float

    def __str__(self) -> str:
        return (
            f"[{self.invariant}] tick {self.tick}, entity {self.entity_id}: "
            f"{self.detail} (offending value {self.value!r})"
        )


@dataclass
class HarnessResult:
    """What one scenario run observed."""

    scenario: Scenario
    ticks_run: int
    digest: str
    violations: list[Violation] = field(default_factory=list)
    suppressed: dict[str, int] = field(default_factory=dict)
    deaths: int = 0
    # How many times each invariant was *meaningfully* evaluated. An invariant that a
    # scenario never actually exercises reads as coverage otherwise: `starving` holds
    # no storage, so every conversion pair is skipped and the essence check would
    # report thousands of vacuous passes. Counting makes a silent no-op loud.
    evaluations: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.violations

    def report(self) -> str:
        lines = [
            f"scenario {self.scenario.name!r}: {len(self.violations)} violation(s) "
            f"over {self.ticks_run} ticks (seed {self.scenario.seed}, "
            f"{self.deaths} death(s))"
        ]
        lines += [f"  {v}" for v in self.violations]
        for invariant, count in sorted(self.suppressed.items()):
            lines.append(f"  ... and {count} further [{invariant}] violation(s) not shown")
        lines.append(
            "  evaluations: "
            + ", ".join(
                f"{name}={self.evaluations.get(name, 0)}" for name in PER_TICK_INVARIANTS
            )
        )
        return "\n".join(lines)


class _Recorder:
    """Collects violations, capping how many of each invariant are kept."""

    def __init__(self) -> None:
        self.violations: list[Violation] = []
        self.suppressed: dict[str, int] = {}
        self._seen: dict[str, int] = {}

    def __call__(
        self, invariant: str, tick: int, entity_id: int, detail: str, value: float
    ) -> None:
        seen = self._seen.get(invariant, 0) + 1
        self._seen[invariant] = seen
        if seen <= MAX_REPORTED_PER_INVARIANT:
            self.violations.append(Violation(invariant, tick, entity_id, detail, value))
        else:
            self.suppressed[invariant] = self.suppressed.get(invariant, 0) + 1


Report = Callable[[str, int, int, str, float], None]


# ---------------------------------------------------------------------------
# The six invariants
# ---------------------------------------------------------------------------

def check_storage_bounded(bot: TaobotSimple, tick: int, report: Report) -> int:
    """`0 <= storage[e] <= capacity[e]` for all five elements.

    Returns how many bounds were meaningfully evaluated, so a scenario that silently
    exercises an invariant zero times cannot masquerade as coverage."""
    for element in ELEMENT_LIST:
        value = bot.storage[element]
        capacity = bot.storage_capacity[element]
        limit = capacity + BOUND_EPS * max(1.0, abs(capacity))
        if value < -BOUND_EPS or value > limit:
            report(
                "storage bounded", tick, bot.entity_id,
                f"storage[{element.name}] = {value!r} outside [0, {capacity!r}]",
                value,
            )
    return len(ELEMENT_LIST)


def check_part_integrity_bounded(bot: TaobotSimple, tick: int, report: Report) -> int:
    """`0.0 <= structural_integrity <= 1.0` for every part.

    Nothing on `BodyPart` enforces the range today; Story 1.3's Earth-funded repair is
    the first thing that could push a part past 1.0, and this is the net that catches it."""
    for index, part in enumerate(bot.body_parts):
        value = part.structural_integrity
        if not (-BOUND_EPS <= value <= 1.0 + BOUND_EPS):
            report(
                "part integrity bounded", tick, bot.entity_id,
                f"part[{index}] {part.part_id} structural_integrity = {value!r} "
                f"outside [0.0, 1.0]",
                value,
            )
    return len(bot.body_parts)


def check_organ_bounded(bot: TaobotSimple, tick: int, report: Report) -> int:
    """`0.0 <= organ(e) <= ORGAN_MAX` for all five, read through the accessor."""
    for element in ELEMENT_LIST:
        value = bot.organ(element)
        if not (-BOUND_EPS <= value <= ORGAN_MAX + BOUND_EPS):
            report(
                "organ bounded", tick, bot.entity_id,
                f"organ({element.name}) = {value!r} outside [0.0, {ORGAN_MAX}]",
                value,
            )
    return len(ELEMENT_LIST)


def check_essence_exact(
    bot: TaobotSimple, observed: ObservedStorage, tick: int, report: Report
) -> int:
    """Per pair across the chi phase: what the target gained is exactly what the
    source lost times `CYCLE_EFFICIENCY`.

    Equality, never a one-sided bound. A bound of "the target gained no more than the
    source lost" passes the exact inversion this exists to catch, where the source pays
    full price and a capped target receives less: essence is destroyed, not created,
    and only an equality notices.

    Both sides are observed storage deltas (see `ObservedStorage`), never the
    implementation's own `spent`/`produced` bookkeeping — a conversion path that
    miscounts its own arithmetic would report itself as correct.

    Returns the number of pairs where a transfer actually moved something. A pair that
    moved nothing satisfies `0 == 0 * EFFICIENCY` trivially, and counting those as
    coverage is how a scenario that never converts at all (`starving`, whose storage is
    empty) could look like it was exercising this invariant 15,000 times."""
    evaluated = 0
    for source, target in CYCLE_SEQUENCE:
        lost = observed.outflow.get(source, 0.0)
        gained = observed.inflow.get(target, 0.0)
        if lost > 0.0 or gained > 0.0:
            evaluated += 1
        expected = lost * CYCLE_EFFICIENCY
        if not math.isclose(
            gained, expected, rel_tol=ESSENCE_REL_TOL, abs_tol=ESSENCE_ABS_TOL
        ):
            report(
                "essence exact", tick, bot.entity_id,
                f"{source.name}->{target.name}: storage[{target.name}] rose by "
                f"{gained!r} while storage[{source.name}] fell by {lost!r}; at "
                f"CYCLE_EFFICIENCY={CYCLE_EFFICIENCY} the target should have gained "
                f"{expected!r}",
                gained - expected,
            )
    return evaluated


def _float_state(bot: TaobotSimple) -> Iterator[tuple[str, float]]:
    """Every float on a taobot that a corrupted computation could reach."""
    yield "x", bot.x
    yield "y", bot.y
    yield "heading", bot.heading
    yield "desired_heading", bot._desired_heading
    yield "distance_moved", bot.distance_moved
    yield "damage_taken_total", bot.damage_taken_total
    yield "resources_collected", bot.resources_collected
    for element in ELEMENT_LIST:
        yield f"storage[{element.name}]", bot.storage[element]
        yield f"organ({element.name})", bot.organ(element)
    for index, part in enumerate(bot.body_parts):
        yield f"part[{index}].structural_integrity", part.structural_integrity
        yield f"part[{index}].reserve", part.reserve


def check_no_numeric_corruption(bot: TaobotSimple, tick: int, report: Report) -> int:
    """No NaN and no infinity anywhere in float state.

    NaN is the failure that hides: it propagates silently through arithmetic, compares
    false against every bound, and so slips past every *other* invariant here."""
    examined = 0
    for name, value in _float_state(bot):
        examined += 1
        if not math.isfinite(value):
            report(
                "no numeric corruption", tick, bot.entity_id,
                f"{name} = {value!r} is not finite",
                value,
            )
    return examined


# ---------------------------------------------------------------------------
# Determinism — the sixth invariant, which needs two runs to assert
# ---------------------------------------------------------------------------

def _fold_state(digest, world: World) -> None:
    """Fold this tick's state into a rolling digest.

    Rolling rather than final-state-only: two runs that diverge and reconverge would
    compare equal at the end, and the point is to catch the tick where they parted.

    The snapshot is the shared `state_snapshot.world_state`, not a summary of its own.
    An earlier version folded only the live-resource count and the sum of their
    amounts, which left resource *positions*, element types, hazards, respawn timers
    and `_next_id` invisible — so a loss of determinism in `_pick_position`, the world
    stream's main consumer, would not have moved the digest at all. The determinism
    invariant is only ever as strong as the state it looks at."""
    digest.update(state_repr(world).encode("utf-8"))


# ---------------------------------------------------------------------------
# Running a scenario
# ---------------------------------------------------------------------------

def build(scenario: Scenario) -> tuple[World, TaobotSimple]:
    """Build the world and the bot a scenario describes."""
    config = WorldConfig.from_json(CONFIG_DIR / scenario.config)
    config.resources.initial_count = scenario.resources
    config.hazards.initial_count = scenario.hazards
    config.taobots.initial_count = 0
    config.taobots.target_population = scenario.population

    world = World(config, seed=scenario.seed)
    world.initialize()
    bot = world.spawn_taobot(params=scenario.params)

    if isinstance(scenario.storage, dict):
        fractions = scenario.storage
    else:
        fractions = {e.name: float(scenario.storage) for e in ELEMENT_LIST}
    for element in ELEMENT_LIST:
        bot.storage[element] = bot.storage_capacity[element] * float(
            fractions.get(element.name, 0.0)
        )
    for leg in bot.legs:
        leg.structural_integrity = scenario.leg_integrity

    return world, bot


def run_scenario(scenario: Scenario) -> HarnessResult:
    """Tick `scenario` to completion, checking five invariants every tick.

    The sixth, determinism, needs two runs to compare and is asserted by
    `assert_invariants` from the digest this returns."""
    world, bot = build(scenario)

    observed: dict[int, ObservedStorage] = {}

    # Instrument at spawn rather than after the first tick, so a bot that replaces a
    # death has its very first conversion phase observed too.
    original_spawn = world.spawn_taobot

    def spawn_and_instrument(*args, **kwargs):
        spawned = original_spawn(*args, **kwargs)
        observed[spawned.entity_id] = instrument(spawned)
        return spawned

    world.spawn_taobot = spawn_and_instrument  # type: ignore[method-assign]
    observed[bot.entity_id] = instrument(bot)

    deaths = 0
    previous_death_callback = world.on_taobot_death

    def count_death(dying: TaobotSimple) -> None:
        nonlocal deaths
        deaths += 1
        if previous_death_callback is not None:
            previous_death_callback(dying)

    world.on_taobot_death = count_death

    recorder = _Recorder()
    digest = hashlib.blake2b(digest_size=16)
    evaluations = dict.fromkeys(PER_TICK_INVARIANTS, 0)

    for _ in range(scenario.ticks):
        world.tick()
        tick = world.tick_count
        for living in world.taobots:
            evaluations["storage bounded"] += check_storage_bounded(
                living, tick, recorder
            )
            evaluations["part integrity bounded"] += check_part_integrity_bounded(
                living, tick, recorder
            )
            evaluations["organ bounded"] += check_organ_bounded(living, tick, recorder)
            evaluations["no numeric corruption"] += check_no_numeric_corruption(
                living, tick, recorder
            )
            phase = observed.get(living.entity_id)
            if phase is not None:
                evaluations["essence exact"] += check_essence_exact(
                    living, phase, tick, recorder
                )
        _fold_state(digest, world)

    return HarnessResult(
        scenario=scenario,
        ticks_run=scenario.ticks,
        digest=digest.hexdigest(),
        violations=recorder.violations,
        suppressed=recorder.suppressed,
        deaths=deaths,
        evaluations=evaluations,
    )


def assert_invariants(scenario: Scenario) -> HarnessResult:
    """Run `scenario` twice and assert all six invariants.

    The second run is what makes determinism assertable: identical seed and identical
    tick count must produce an identical per-tick digest. Compared **between two runs
    in the same process and environment**, never against a committed golden digest —
    float summation order and libm differ across architectures, so a checked-in
    baseline would be a permanent false alarm rather than a regression guard."""
    first = run_scenario(scenario)
    second = run_scenario(scenario)

    problems: list[str] = []
    if not first.ok:
        problems.append(first.report())
    if not second.ok:
        problems.append(second.report())

    # Coverage is part of the assertion, not a separate nicety: an invariant that this
    # scenario never actually evaluates is not being checked here, however green the
    # run looks. Both directions, so the declaration cannot rot either way.
    for invariant in PER_TICK_INVARIANTS:
        count = first.evaluations.get(invariant, 0)
        if invariant in scenario.exercises and count == 0:
            problems.append(
                f"scenario {scenario.name!r}: claims to exercise [{invariant}] but "
                f"evaluated it 0 times — the invariant is not being checked here"
            )
        if invariant not in scenario.exercises and count > 0:
            problems.append(
                f"scenario {scenario.name!r}: does not claim [{invariant}] but "
                f"evaluated it {count} times — add it to `exercises`"
            )

    if first.digest != second.digest:
        problems.append(
            f"scenario {scenario.name!r}: [determinism] two runs at seed "
            f"{scenario.seed} for {scenario.ticks} ticks produced different state "
            f"digests ({first.digest} vs {second.digest})"
        )

    if problems:
        raise AssertionError(
            "invariant harness found existing bugs — report them in the spec's "
            "Design Notes with the tick and value; do not relax the assertion:\n"
            + "\n".join(problems)
        )
    return first
