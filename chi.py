"""The chi tier: the essence an organism holds, and every conversion over it.

`AD-2` designates the storage dict as the *pool* tier (parts keep their own small
`reserve` buffers). `AD-4` puts conversion on that tier rather than on the organism,
because E3 substitutes a `MeridianNetwork` behind the same port and lifts conversion
wholesale — anything that accretes on `TaobotSimple` has to be moved again.

**Exactly one conversion site.** `ChiPool.convert` is it. Both the unconditional Sheng
cycle and the demand-triggered Metal->Water path run there, from a single pre-tick
snapshot, so "both paths ran once" and "one path ran twice" are structurally different
things rather than two readings of the same whole-tick delta.

**Cap then derive.** Every path computes `produced` first, capped against what the
target can hold and what the source actually has, and only then derives
`spent = produced / CYCLE_EFFICIENCY`. Essence is lost to efficiency and never
manufactured. Story 1.0d's invariant harness asserts that equality on *observed*
storage deltas every tick; `tests/test_invariants.py` keeps a hand-copy of this
algorithm with the two lines inverted as a permanent negative control.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

from common import ELEMENT_LIST, ElementType

# ---------------------------------------------------------------------------
# The generative (Sheng) cycle
# ---------------------------------------------------------------------------
#
# Module constants rather than config: `CYCLE_SEQUENCE` is the shape of the world's
# chemistry, not a tunable, and the two rates are frozen by Story 1.2's own acceptance
# (behaviour above the deficit threshold must stay byte-identical to the pre-change
# build). They moved here from `taobot_simple` unchanged in value — conversion lives
# on the chi tier now, and so do the numbers that parameterise it.

CYCLE_RATE: float = 0.001       # fraction of source storage converted per tick
CYCLE_EFFICIENCY: float = 0.8   # fraction that arrives at target (20% lost per step)

CYCLE_SEQUENCE: list[tuple[ElementType, ElementType]] = [
    (ElementType.WATER, ElementType.WOOD),
    (ElementType.WOOD,  ElementType.FIRE),
    (ElementType.FIRE,  ElementType.EARTH),
    (ElementType.EARTH, ElementType.METAL),
    (ElementType.METAL, ElementType.WATER),
]

LAWS_PATH = Path(__file__).resolve().parent / "configs" / "laws.json"

# The largest deficit threshold `ChiLaws` will accept, as a fraction of Water capacity.
#
# Not a tuning knob — a guard against the failure the law exists to prevent. At 1.0 the
# demand path pins Water at capacity every tick, which abolishes Water starvation
# outright; that is precisely the pressure the legs organ system exists to impose and
# the reason these two numbers are laws rather than genes. The bound is placed where
# the workshop sweep (recorded in `configs/laws.json`) says the intervention stops
# being a net benefit at all: total leg integrity loss over 12 seeds x 6000 ticks is
# 35.2 at the derived 0.008, 40.0 at 0.30 and 44.5 at 0.50, against 46.9 with the path
# switched off entirely. Past 0.5 the trigger costs more than it saves.
MAX_WATER_DEFICIT_THRESHOLD: float = 0.5


class ConversionPath(Enum):
    """Which path moved a given transfer.

    Both paths move Metal->Water, so a whole-tick storage delta cannot tell one from
    the other. Every transfer carries its path so the two stay separately attributable
    in the logs and in the inspector."""

    PASSIVE = "passive"   # the unconditional Sheng cycle
    DEFICIT = "deficit"   # demand-triggered Metal->Water, below the Water threshold


@dataclass(frozen=True)
class Transfer:
    """One conversion, as it was resolved against the pre-tick snapshot.

    `produced` is what the target received and `spent` is what the source paid;
    `spent` is always derived from `produced`, never the other way round."""

    path: ConversionPath
    source: ElementType
    target: ElementType
    spent: float
    produced: float


@dataclass(frozen=True)
class ChiLaws:
    """The tunables of the demand-triggered path — laws of Pangu, not world settings.

    Both pass `AD-13`'s test ("would making this evolvable let organisms escape a
    constraint the simulation exists to impose?") in the affirmative, so they are laws
    and live in `configs/laws.json`. An evolvable deficit threshold would be driven to
    1.0 and an evolvable conversion rate to its ceiling, which together abolish Water
    starvation — the exact pressure the legs organ system exists to impose. See the
    derivation recorded beside them in `configs/laws.json`.

    Both were derived by sweeping them in workshop mode, never chosen."""

    water_deficit_threshold: float
    deficit_conversion_rate: float

    def __post_init__(self) -> None:
        # Finiteness first, and explicitly: NaN fails every ordered comparison, so a
        # range check alone silently *accepts* it. A NaN rate disables the demand path
        # for a whole run without a word — `rate * metal` is NaN, `min(NaN, ...)` is
        # NaN, `NaN > 0.0` is False, and the transfer is simply never committed.
        for name, value in (
            ("water_deficit_threshold", self.water_deficit_threshold),
            ("deficit_conversion_rate", self.deficit_conversion_rate),
        ):
            if not math.isfinite(value):
                raise ValueError(f"chi.{name} must be a finite number, got {value!r}")

        if not 0.0 <= self.water_deficit_threshold <= MAX_WATER_DEFICIT_THRESHOLD:
            raise ValueError(
                "chi.water_deficit_threshold is a fraction of Water capacity and must "
                f"lie in [0, {MAX_WATER_DEFICIT_THRESHOLD}], got "
                f"{self.water_deficit_threshold!r} — see MAX_WATER_DEFICIT_THRESHOLD "
                "for why the ceiling is well below 1.0"
            )
        # No upper bound on the rate, deliberately. It is a ceiling on the *flow*, and
        # the flow is already bounded twice over by things a law cannot raise: the
        # demand path asks only for the shortfall to the threshold, and can spend only
        # the Metal that is actually present. A rate of a million refills the deficit in
        # one tick instead of several; it cannot convert more Metal in total, and it
        # cannot lift Water above the threshold. There is nothing to escape.
        if self.deficit_conversion_rate < 0.0:
            raise ValueError(
                "chi.deficit_conversion_rate is a fraction of Metal storage converted "
                f"per tick and cannot be negative, got {self.deficit_conversion_rate!r}"
            )

    @classmethod
    def from_mapping(cls, block: dict) -> "ChiLaws":
        """Build from a parsed `chi` config block, naming a missing key loudly."""
        try:
            return cls(
                water_deficit_threshold=float(block["water_deficit_threshold"]),
                deficit_conversion_rate=float(block["deficit_conversion_rate"]),
            )
        except KeyError as exc:
            raise ValueError(f"chi config block missing required key: {exc}") from exc


@lru_cache(maxsize=1)
def default_chi_laws() -> ChiLaws:
    """The shipped laws, read from `configs/laws.json`.

    Resolved beside this module, never against the working directory — the same
    guarantee `WorldConfig` makes about its own config paths. A `TaobotSimple` built
    without a world (tests, sandboxes) still lives in the same universe as one the
    world spawned, so it inherits the same laws rather than a second copy of the
    numbers hard-coded here.

    Cached for the life of the process: the file is read once, so editing
    `configs/laws.json` while a run is in flight changes nothing until it restarts.
    That is the intended behaviour — a run's laws must not shift underneath it, and
    the manifest's `config_fingerprint` records the ones it actually used — but it does
    mean a test that rewrites the file cannot expect this to notice."""
    block = json.loads(LAWS_PATH.read_text())["chi"]
    return ChiLaws.from_mapping(block)


# ---------------------------------------------------------------------------
# Structural repair: the chi -> part crossing
# ---------------------------------------------------------------------------
#
# These live beside the chi laws rather than in `body_parts` because both are
# statements about the *pool*: one is the exchange rate at which essence leaves the
# chi tier, the other is how much of the pool repair is forbidden to touch. The part
# is handed the rate as an argument and holds no laws of its own.

# The value below which the exchange rate stops being a price at all.
#
# Not a tuning knob — the same shape of guard as `MAX_WATER_DEFICIT_THRESHOLD`, placed
# where the workshop sweep (recorded in `configs/laws.json`) says the intervention
# stops imposing anything. Repair cheap enough is repair that is free: leg integrity
# never leaves 1.0, starvation has no lasting consequence, and the pressure the legs
# organ system exists to impose is abolished by a config edit rather than by evolution.
# `tools/derive_repair_laws.py rate` measures where that happens; the bound sits an
# order of magnitude below the derived value so a deliberate retune has room and an
# accidental zero does not.
MIN_EARTH_PER_INTEGRITY_MASS: float = 1e-3


@dataclass(frozen=True)
class RepairLaws:
    """The tunables of Earth-funded structural repair — laws of Pangu, not settings.

    Both pass `AD-13`'s test in the affirmative. An evolvable exchange rate would be
    driven to zero, which makes structural damage free and removes the consequence the
    legs organ system exists to impose; an evolvable floor would be driven to zero too,
    letting a lineage spend its last Earth healing its legs while the body — the one
    death condition — starves. `mass`, by contrast, is a *trait*: it lives on the part.

    **Direction of the law, stated once.** Earth debited is
    `Δintegrity × mass × earth_per_integrity_mass` — a *multiplication*. The epic's
    prose and its acceptance line disagreed on the direction; the constant's name is
    the stronger signal ("Earth per unit of integrity×mass" means multiply), so that
    is what is implemented, and the invariant harness asserts the same expression the
    implementation uses so the two cannot drift apart.

    **Integrity is a terminal sink.** Nothing converts integrity back into chi, so
    there is no cycle for this rate to be exploited around and it is a pure balance
    knob through E4. That stops holding at Phase 5, where a defeated taobot drops chi
    a living one absorbs: if the drop derives from the corpse's mass and integrity then
    Earth -> integrity -> corpse -> chi closes a loop and this rate acquires a second
    job. Flagged for whoever designs combat.

    Both were derived by sweeping them in workshop mode — see the reasoning recorded
    beside them in `configs/laws.json` and `tools/derive_repair_laws.py`."""

    earth_per_integrity_mass: float
    earth_repair_floor: float
    max_integrity_per_tick: float

    def __post_init__(self) -> None:
        # Finiteness first and explicitly, for the reason `ChiLaws` gives: NaN fails
        # every ordered comparison, so a range check alone silently accepts it — and a
        # NaN rate would make every repair demand NaN, which `min` propagates through
        # the pro-rata split and no bound below would notice.
        for name, value in (
            ("earth_per_integrity_mass", self.earth_per_integrity_mass),
            ("earth_repair_floor", self.earth_repair_floor),
            ("max_integrity_per_tick", self.max_integrity_per_tick),
        ):
            if not math.isfinite(value):
                raise ValueError(f"repair.{name} must be a finite number, got {value!r}")

        if self.earth_per_integrity_mass < MIN_EARTH_PER_INTEGRITY_MASS:
            raise ValueError(
                "repair.earth_per_integrity_mass is the Earth cost of one unit of "
                f"integrity x mass and must be at least "
                f"{MIN_EARTH_PER_INTEGRITY_MASS}, got "
                f"{self.earth_per_integrity_mass!r} — see "
                "MIN_EARTH_PER_INTEGRITY_MASS for why free repair is the failure this "
                "bound exists to prevent"
            )
        # No upper bound, deliberately. An arbitrarily expensive rate makes repair
        # unaffordable, which is the pre-1.3 world: parts decay one way. That is a
        # worse simulation but not an *escape* — nothing is abolished, and the flow is
        # already bounded by the Earth a bot can actually hold.
        if self.earth_repair_floor < 0.0:
            raise ValueError(
                "repair.earth_repair_floor is an amount of Earth storage held back "
                f"from repair and cannot be negative, got {self.earth_repair_floor!r}"
            )
        # Strictly positive: at zero a part can never regain anything, which is the
        # pre-1.3 world with extra machinery. There is no upper bound — above 1.0 the
        # cap simply stops binding and a part rebuilds in one tick, which is where this
        # story started and why the law exists, but it abolishes nothing.
        if self.max_integrity_per_tick <= 0.0:
            raise ValueError(
                "repair.max_integrity_per_tick is how much integrity one part may "
                "regain in a single tick and must be positive — zero is a part that "
                f"can never heal, got {self.max_integrity_per_tick!r}"
            )

    @classmethod
    def from_mapping(cls, block: dict) -> "RepairLaws":
        """Build from a parsed `repair` config block, naming a missing key loudly."""
        try:
            return cls(
                earth_per_integrity_mass=float(block["earth_per_integrity_mass"]),
                earth_repair_floor=float(block["earth_repair_floor"]),
                max_integrity_per_tick=float(block["max_integrity_per_tick"]),
            )
        except KeyError as exc:
            raise ValueError(f"repair config block missing required key: {exc}") from exc


@lru_cache(maxsize=1)
def default_repair_laws() -> RepairLaws:
    """The shipped repair laws, read from `configs/laws.json`.

    Resolved beside this module and cached for the life of the process, for the same
    reasons `default_chi_laws` is: a bot built without a world lives in the same
    universe as one the world spawned, and a run's laws must not shift underneath it."""
    block = json.loads(LAWS_PATH.read_text())["repair"]
    return RepairLaws.from_mapping(block)


def pro_rata(demands: Sequence[float], supply: float) -> list[float]:
    """Split `supply` across `demands` in proportion to each demand (`AD-3`).

    Pure arithmetic, separated from the pool so the split can be asserted directly and
    so `ChiPool.allocate` reads as "work out the shares, then withdraw them".

    - Demand that fits is met in full; nobody is scaled down when there is enough.
    - Under scarcity every requester receives `demand / total_demand * supply`, so a
      requester asking for twice as much gets twice as much. Not equal shares: equal
      shares would give a barely-scratched part the same Earth as a destroyed one.
    - Non-positive demands take nothing and, importantly, contribute nothing to the
      total — a whole part must not dilute the share of a damaged one.

    The returned shares never sum above `supply`; `allocate` still meters them against
    a running allowance, because summing float shares can land a hair either side."""
    wanted = [d if d > 0.0 else 0.0 for d in demands]
    total = sum(wanted)
    if total <= 0.0 or supply <= 0.0:
        return [0.0] * len(wanted)
    if total <= supply:
        return wanted
    return [d / total * supply for d in wanted]


class ChiPool:
    """One organism's pool of elemental essence, reached through a port.

    **The port (`AD-3`).** Consumers call `request`, `allocate` and `deposit`; they do
    not mutate the dict. All three return what was actually granted or accepted, which
    may be less than asked for — *a denied request is a correct outcome*, not an error.
    `allocate` is the pro-rata split that return shape was left room for: Story 1.3
    made structural repair a second requester of Earth, so several parts now compete
    for one element in one tick and the pool is the only thing that can see all of
    them. Note `_drain_organ` still writes storage directly and so does not yet
    compete — the same deliberate partial migration described below.

    `convert` applies every transfer through that port, so it is the port's first real
    caller rather than a seam nothing uses. Note it cannot *plan* through the port: the
    passive cycle has to resolve all five transfers against one frozen snapshot, and
    depositing as it went would let each transfer see the previous one's effect and
    reintroduce exactly the directional bias the snapshot exists to remove. Planning
    reads the snapshot; applying goes through `request`/`deposit`.

    **`storage` is still public** because Story 1.2 migrates conversion only. Resource
    collection, body-part replenish and organ upkeep keep writing the dict directly and
    move behind the port when they must. That is a deliberate partial migration: the
    alternative is a large refactor inside a story that also introduces new behaviour.
    """

    def __init__(
        self,
        storage: dict[ElementType, float],
        capacity: dict[ElementType, float],
        laws: ChiLaws | None = None,
    ) -> None:
        self.storage = storage
        self.capacity = capacity
        self.laws = default_chi_laws() if laws is None else laws

        # Per-tick attribution, overwritten by every `convert`. Observers read it and
        # reset nothing: it is this tick's record, not an accumulator they own.
        self.last_transfers: tuple[Transfer, ...] = ()

        # Two flags, because they answer two different questions and a reader needs
        # both. `deficit_active` is "Water is below the threshold" — true of a bot
        # starving with an empty Metal pool, which is a real deficit that simply cannot
        # be served. `deficit_served` is "the demand path actually moved something".
        # Collapsing them would either hide the deficit or claim the trigger is working
        # when nothing has moved.
        self.deficit_active: bool = False
        self.deficit_served: bool = False

    # --- The port ------------------------------------------------------------

    def request(self, element: ElementType, amount: float) -> float:
        """Withdraw up to `amount` of `element`. Returns what was granted.

        A grant smaller than the request — zero included — is a correct answer the
        caller must handle, not a failure to raise on."""
        if amount <= 0.0:
            return 0.0
        granted = min(amount, self.storage[element])
        if granted <= 0.0:
            return 0.0
        self.storage[element] = self.storage[element] - granted
        return granted

    def allocate(
        self,
        element: ElementType,
        demands: Sequence[float],
        *,
        reserve: float = 0.0,
    ) -> list[float]:
        """Serve several requesters of one element at once. Returns what each got.

        This is `AD-3`'s pro-rata allocation, and the reason the port returns grants
        rather than raising: **a denied or partial grant is correct behaviour**, and
        every caller already had to handle one.

        The split is across *every requester of the element in this call*, not within
        organ systems — structural repair makes a leg and (from E2) a plate of armor
        compete for the same Earth in the same tick, and the pool is where that
        competition has to be resolved because it is the only thing that can see all
        of it. Callers therefore batch: one `allocate` per element per tick, never a
        `request` per part in a loop, which would serve whoever iterated first.

        `reserve` is Earth (or whatever element) this call may not touch — the floor
        that keeps a bot from repairing its legs with the essence its body needs to
        stay alive. It is a *reserve*, not a gate: below it nothing is granted, above
        it only the excess is available, so a starving bot cannot heal and a bot that
        just crossed the line cannot spend itself straight back under it.

        Grants are metered against a running allowance rather than trusted to sum
        correctly, so float error in the shares can never dip into the reserve."""
        shares = pro_rata(demands, max(0.0, self.storage[element] - max(0.0, reserve)))
        granted: list[float] = []
        remaining = max(0.0, self.storage[element] - max(0.0, reserve))
        for share in shares:
            taken = self.request(element, min(share, remaining))
            remaining -= taken
            granted.append(taken)
        return granted

    def deposit(self, element: ElementType, amount: float) -> float:
        """Add up to `amount` of `element`. Returns what was accepted.

        Accepts only what fits under capacity; the remainder is simply not created."""
        if amount <= 0.0:
            return 0.0
        accepted = min(amount, max(0.0, self.capacity[element] - self.storage[element]))
        if accepted <= 0.0:
            return 0.0
        self.storage[element] = self.storage[element] + accepted
        return accepted

    def apply(self, planned: Transfer) -> Transfer:
        """Move one planned transfer through the port. Returns what actually moved.

        The safety property of the whole tier lives here. `request` withdraws what is
        *there*, so storage can never go negative and never needs clamping after the
        fact — and if the source could not pay in full, what arrives is recomputed from
        what was withdrawn rather than left at the planned amount.

        That ordering is the point. Subtracting `spent` under a `max(0.0, ...)` floor
        while still crediting the target the full `produced` lets the source pay less
        than the target receives, which *creates* essence — the one thing `AD-4` forbids
        outright and the failure Story 1.0d's harness exists to catch. Here it is not
        caught, it is unrepresentable.

        The returned `Transfer` carries the amounts that moved, not the ones intended:
        a log or a panel that reported a plan would be evidence disagreeing with the
        storage columns printed beside it."""
        spent = self.request(planned.source, planned.spent)
        # `request` returns the amount asked for unchanged when it can be met in full,
        # so this is an exact comparison, not a tolerance — and the planned `produced`
        # is used untouched in that (overwhelmingly common) case, which is what keeps
        # the passive cycle byte-identical to the pre-chi-tier build.
        produced = planned.produced if spent == planned.spent else spent * CYCLE_EFFICIENCY
        produced = self.deposit(planned.target, produced)
        return Transfer(planned.path, planned.source, planned.target, spent, produced)

    # --- Attribution ---------------------------------------------------------

    def moved(
        self, path: ConversionPath, source: ElementType, target: ElementType
    ) -> tuple[float, float]:
        """Total `(spent, produced)` that `path` moved along `source -> target` this tick.

        **Sums every match, never just the first.** Today each path commits at most one
        transfer per edge, so there is only ever one — but returning the first would
        mean that the day a path *did* commit twice, this reported half the movement and
        said nothing. That is precisely the failure per-path attribution exists to
        expose, so it is the one thing this must not be able to hide: an under-reported
        total silently breaks the reconciliation `Δstorage == passive + deficit` that
        the logs and the tests both rest on.

        Note that summing is deliberately *not* how "one path ran twice" is detected —
        a duplicate would land in the same sum. `last_transfers` is what distinguishes
        them: two `METAL -> WATER` entries under one path is a different list from one
        entry under each. See `test_chi.py`."""
        spent = 0.0
        produced = 0.0
        for transfer in self.last_transfers:
            if (
                transfer.path is path
                and transfer.source is source
                and transfer.target is target
            ):
                spent += transfer.spent
                produced += transfer.produced
        return spent, produced

    def deficit_level(self) -> float:
        """The Water storage level at or above which the demand path stays quiet."""
        return self.laws.water_deficit_threshold * self.capacity[ElementType.WATER]

    # --- The capability ------------------------------------------------------

    def convert(self) -> None:
        """Run every conversion for this tick — the single conversion site.

        Two stages, one snapshot:

        1. **The passive Sheng cycle.** All five transfers are resolved against the
           frozen pre-tick snapshot, never against each other, so no element gets an
           advantage from its position in `CYCLE_SEQUENCE`.
        2. **The demand path.** If Water sits below the deficit threshold it asks for
           the shortfall, granted up to what the elevated rate allows on the Metal that
           is actually left after stage 1. It is resolved against the snapshot *plus*
           stage 1's commitments, which is what makes double-conversion impossible:
           stage 2 can only ever spend Metal stage 1 did not.

        Nothing is written until both stages have been resolved.
        """
        snapshot = {e: self.storage[e] for e in ELEMENT_LIST}
        committed_in = dict.fromkeys(ELEMENT_LIST, 0.0)
        committed_out = dict.fromkeys(ELEMENT_LIST, 0.0)
        transfers: list[Transfer] = []

        def commit(
            path: ConversionPath,
            source: ElementType,
            target: ElementType,
            spent: float,
            produced: float,
        ) -> None:
            committed_out[source] += spent
            committed_in[target] += produced
            transfers.append(Transfer(path, source, target, spent, produced))

        # --- Stage 1: the passive cycle, unchanged ---------------------------
        for source, target in CYCLE_SEQUENCE:
            amount_out = CYCLE_RATE * snapshot[source]
            room = self.capacity[target] - snapshot[target]
            produced = min(amount_out * CYCLE_EFFICIENCY, room)
            if produced <= 0.0:
                continue
            spent = produced / CYCLE_EFFICIENCY
            commit(ConversionPath.PASSIVE, source, target, spent, produced)

        # --- Stage 2: Water deficit -> elevated Metal->Water ------------------
        water = ElementType.WATER
        metal = ElementType.METAL
        projected_water = snapshot[water] + committed_in[water] - committed_out[water]
        trigger_level = self.deficit_level()

        # Strictly below, so the boundary has a stated side: Water sitting *exactly*
        # at the threshold is "recovered" and the demand path stays quiet. The
        # comparison is made once, on the snapshot, so it cannot flip mid-tick.
        self.deficit_active = projected_water < trigger_level
        self.deficit_served = False

        if self.deficit_active:
            projected_metal = (
                snapshot[metal] + committed_in[metal] - committed_out[metal]
            )
            # The elevated rate is a *ceiling on the flow*, not the flow itself: what
            # the deficit path asks for is the shortfall, so Water is restored to the
            # threshold and never overshoots it. Without that cap the trigger would
            # push Water above the line, switch off, let it fall back under and fire
            # again — oscillating tick to tick instead of regulating.
            demand = trigger_level - projected_water
            # Capping the source-side amount is what keeps a second withdrawal from
            # overdrawing Metal that stage 1 already committed.
            amount_out = min(
                self.laws.deficit_conversion_rate * snapshot[metal], projected_metal
            )
            # `demand <= room` for any threshold fraction in [0, 1] (validated on
            # `ChiLaws`), so the room term never binds today. It stays because the
            # storage bound is a hard invariant and this is the only line defending it
            # if the demand target is ever raised above the threshold.
            room = self.capacity[water] - projected_water
            produced = min(amount_out * CYCLE_EFFICIENCY, demand, room)
            if produced > 0.0:
                spent = produced / CYCLE_EFFICIENCY
                commit(ConversionPath.DEFICIT, metal, water, spent, produced)
                self.deficit_served = True

        # --- Apply -----------------------------------------------------------
        # Through the port (see `apply`), in `CYCLE_SEQUENCE` order first and the demand
        # path last, so an element that both receives and pays has its inflow applied
        # before its second outflow and never dips below zero on the way.
        self.last_transfers = tuple(self.apply(planned) for planned in transfers)
