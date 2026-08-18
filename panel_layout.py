"""Pure layout arithmetic for the right-hand panel.

This module is the panel's single layout owner. It imports no pygame, opens no
display, and draws nothing: it takes panel geometry plus a part inventory and
returns plain rects. Everything the renderer paints into the panel — the
inspector, its sections, its individual rows, the organ graph, the graph's
caption, the pause button and the speed slider — comes out of one :func:`compute`
call, so no two of them can disagree about where the boundaries are.

Coordinates are screen pixels, because the panel is a screen-space widget; the
renderer converts these plain rects to ``pygame.Rect`` at the draw boundary, per
the house convention of converting only where drawing happens.

Vertical overflow is handled by a declared condensation ladder (see ``_LADDER``)
rather than by letting content run off the bottom, and horizontal overflow by
:func:`clip_text` and :func:`bar_row`, which right-align and truncate against
the row's own right edge. Anything the layout still could not place is reported
through ``PanelLayout.content_clipped`` and given a notice row, because content
that vanishes without saying so is worse than content that does not fit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

# --- Geometry constants -----------------------------------------------------
#
# Structural invariants of the panel widget, not tunables: they describe how the
# thing is built, not how the simulation behaves.

MARGIN = 8              # px gutter between panel edge and its content
GRAPH_H = 100           # px height of the organ history graph
GRAPH_LABEL_H = 16      # px caption row directly above the graph
INSPECTOR_GAP = 4       # px breathing room between inspector and graph caption
# Distance from the window bottom up to the graph's top edge. Everything below
# the graph (pause button, speed slider and its label) lives inside this band.
BOTTOM_SECTION_H = 192

# Panel chrome below the graph. These used to be computed independently inside
# the renderer, which is the same "two constants that must agree" defect the
# graph had; they are inputs to the one layout now.
PAUSE_BTN_W = 110
PAUSE_BTN_H = 24
PAUSE_BTN_UP = 58       # px from the window bottom to the button's top edge
SLIDER_H = 10
SLIDER_UP = 18          # px from the window bottom to the slider track's top
SLIDER_HIT_PAD = 6      # px the clickable area extends above/below the track
SLIDER_LABEL_H = 16

ORGAN_ROWS = 5          # one row per element
STORAGE_ROWS = 5
AFFINITY_ROWS = 5

LEG_INDENT = 8          # px the per-leg bar rows are inset from the inspector

# Compact bar row internals. `CHAR_W` is the advance of the 13px monospace face
# the renderer uses; callers that have a real font measure it and pass their own,
# and the bar start moves to stay clear of the name at that measured width.
CHAR_W = 8
SWATCH_W = 8
SWATCH_H = 8
ROW_INSET_Y = 3         # px from row top to swatch/bar top
NAME_X = 12             # px from row left to the name text
NAME_CHARS = 5
NAME_GAP = 3            # px minimum gap between the name and the bar
BAR_X = 51              # px from row left to the bar, when the name allows it
BAR_MAX_W = 96
BAR_MIN_W = 8
LABEL_GAP = 4           # px minimum gap between bar and its right-hand label

# Below these the panel cannot hold even a header and one bar row, and every
# rect it returned would be degenerate — an empty rect trivially satisfies every
# containment assertion, so a silently degenerate layout is a layout that cannot
# be tested. Reject instead.
MIN_INSPECTOR_H = 48
MIN_PANEL_W = 2 * MARGIN + BAR_X + BAR_MIN_W + LABEL_GAP + 4 * CHAR_W
MIN_PANEL_H = BOTTOM_SECTION_H + GRAPH_LABEL_H + INSPECTOR_GAP + MARGIN + MIN_INSPECTOR_H


class LayoutError(ValueError):
    """The panel geometry cannot hold a panel."""


# --- Value types ------------------------------------------------------------


@dataclass(frozen=True)
class Rect:
    """A plain integer rect. Converted to ``pygame.Rect`` only at the draw boundary."""

    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    @property
    def is_degenerate(self) -> bool:
        return self.w <= 0 or self.h <= 0

    def overlaps(self, other: "Rect") -> bool:
        """True if the two rects share any interior pixel. Empty rects never overlap."""
        if self.is_degenerate or other.is_degenerate:
            return False
        return (
            self.x < other.right
            and other.x < self.right
            and self.y < other.bottom
            and other.y < self.bottom
        )

    def contains(self, other: "Rect") -> bool:
        """True if `other` lies wholly inside self.

        A degenerate rect is *not* contained. Vacuous truth here would let a
        collapsed layout pass every containment assertion in the suite."""
        if self.is_degenerate or other.is_degenerate:
            return False
        return (
            other.x >= self.x
            and other.y >= self.y
            and other.right <= self.right
            and other.bottom <= self.bottom
        )

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


class RowKind(Enum):
    """What a laid-out row is for.

    The renderer names the kind it is about to draw when it asks for the row, so
    a layout that says "bar" and a renderer that draws text is a loud error
    rather than a quietly misplaced glyph."""

    TEXT = "text"
    HEADING = "heading"
    SEPARATOR = "separator"
    BAR = "bar"
    LEG_HEAD = "leg_head"
    LEG_LINE = "leg_line"
    NOTICE = "notice"


@dataclass(frozen=True)
class Row:
    kind: RowKind
    rect: Rect
    index: int = -1     # element / leg ordinal where one applies, else -1


@dataclass(frozen=True)
class Section:
    name: str
    rect: Rect
    rows: tuple[Row, ...]


class Variant(Enum):
    """Which inspector the panel is laying out.

    WORKSHOP — the tick-stepping sandbox panel: header carries a tick line.
    PLAIN    — the ordinary run panel: no tick line, plus Params and Affinities.
    """

    WORKSHOP = "workshop"
    PLAIN = "plain"


class LegDetail(Enum):
    """How much of each leg is shown, richest first.

    FULL — heading, integrity bar, reserve bar, diagnostics (thrust/max/phi)
    BARS — heading, integrity bar, reserve bar
    LINE — one text line carrying theta, integrity and reserve as numbers

    Integrity and reserve survive every level: they are what a reader watching a
    degrade/recover round trip needs. Thrust, max thrust and phi are diagnostic
    detail and are the first thing to go.
    """

    FULL = "full"
    BARS = "bars"
    LINE = "line"


_LEG_ROW_COUNT = {LegDetail.FULL: 4, LegDetail.BARS: 3, LegDetail.LINE: 1}


@dataclass(frozen=True)
class Metrics:
    """Row rhythm. The tight variant is the lower rung of the ladder.

    `line_h` must leave room for the tallest glyph the renderer puts in a row;
    the renderer picks a 13px face when `line_h` is below 16 for exactly that
    reason, since non-overlapping rects do not imply non-overlapping glyphs."""

    line_h: int
    sep_h: int
    pad_h: int


@dataclass(frozen=True)
class _Profile:
    bot_info_lines: int
    leg_detail: LegDetail
    metrics: Metrics
    affinity_rows: int
    params_heading: bool


_NORMAL = Metrics(line_h=16, sep_h=7, pad_h=3)
_TIGHT = Metrics(line_h=14, sep_h=5, pad_h=0)

# The declared condensation rule, applied in order until the content fits the
# inspector rect. Each rung gives up strictly less than the one after it:
#   1. everything
#   2. drop the per-leg diagnostics row (thrust / max thrust / phi)
#   3. condense the bot-info block from five rows to four — same facts, less air
#   4. tighten the row rhythm
#   5. drop the per-leg bars, keeping integrity and reserve as numbers
#   6. fold the plain panel's affinity block into two rows and drop its Params
#      heading — both are static genome traits, the least urgent thing on screen
# If the last rung still does not fit, rows are clipped, a notice row is reserved
# before anything else is placed, and the layout reports what went missing.
#
# Which rungs a given window reaches depends on its geometry and variant — at
# PANEL_W=240 and WINDOW_H=600 the workshop panel skips the middle rungs and the
# plain panel goes all the way to the last. They are kept because the rule, not
# the current window, is what is declared here.
_LADDER: tuple[_Profile, ...] = (
    _Profile(5, LegDetail.FULL, _NORMAL, AFFINITY_ROWS, True),
    _Profile(5, LegDetail.BARS, _NORMAL, AFFINITY_ROWS, True),
    _Profile(4, LegDetail.BARS, _NORMAL, AFFINITY_ROWS, True),
    _Profile(4, LegDetail.BARS, _TIGHT, AFFINITY_ROWS, True),
    _Profile(4, LegDetail.LINE, _TIGHT, AFFINITY_ROWS, True),
    _Profile(4, LegDetail.LINE, _TIGHT, 2, False),
)


@dataclass(frozen=True)
class PanelLayout:
    """Every rect the panel draws into, computed once from one set of inputs."""

    variant: Variant
    panel: Rect
    inspector: Rect
    graph: Rect
    graph_label: Rect
    pause_button: Rect
    slider_track: Rect
    slider_hit: Rect
    slider_label: Rect
    sections: tuple[Section, ...]
    metrics: Metrics
    bot_info_lines: int
    leg_detail: LegDetail
    affinity_rows: int
    params_heading: bool
    legs_shown: int
    legs_total: int
    content_clipped: bool
    #: True if the builder refused a row for want of space. Surfaced rather than
    #: kept private because a dropped row that nothing reports is the defect this
    #: module exists to remove; `test_dropped_rows_are_always_announced` asserts
    #: it can never be true without a notice row on screen.
    rows_dropped: bool

    def section(self, name: str) -> Section | None:
        for s in self.sections:
            if s.name == name:
                return s
        return None

    @property
    def truncated(self) -> bool:
        return self.legs_shown < self.legs_total

    @property
    def truncation_note(self) -> str:
        """On-screen wording for clipped content. Empty when nothing was dropped.

        A silently shortened list reads as a bot with fewer legs — or with less
        state — which is a meaningful and wrong claim, so it is always stated.
        The leg count is named when legs are what went; otherwise the notice is
        generic, because the header, organs or storage may be what overflowed."""
        hidden = self.legs_total - self.legs_shown
        if hidden > 0:
            return f"{hidden} of {self.legs_total} legs hidden"
        if self.content_clipped:
            return "panel full - rows hidden"
        return ""

    def all_rects(self) -> tuple[Rect, ...]:
        """Every rect this layout hands out, for containment/overlap assertions."""
        out: list[Rect] = [
            self.inspector,
            self.graph,
            self.graph_label,
            self.pause_button,
            self.slider_track,
            self.slider_hit,
            self.slider_label,
        ]
        for s in self.sections:
            out.append(s.rect)
            out.extend(r.rect for r in s.rows)
        return tuple(out)

    def rows(self) -> tuple[Row, ...]:
        return tuple(r for s in self.sections for r in s.rows)


# --- Text and bar-row fitting ----------------------------------------------


#: How wide a string is, in pixels. Injected so this module can be exact about text
#: without importing pygame: purity here means no side effects and no display, not
#: refusing inputs. `SysFont("monospace")` is **not** guaranteed to resolve to a
#: fixed-pitch face — it does on macOS and did not on the Linux CI runner, where
#: `len(text) * char_w` mispredicted every label width and the panel painted its
#: right-aligned labels somewhere the tests did not expect.
Measure = Callable[[str], int]


def _width(text: str, char_w: int, measure: "Measure | None") -> int:
    """Pixel width of `text`: measured when a measurer is supplied, else assumed."""
    return measure(text) if measure is not None else len(text) * char_w


def clip_text(
    text: str, max_w: int, char_w: int = CHAR_W, measure: "Measure | None" = None
) -> str:
    """Shorten `text` to fit `max_w` pixels.

    Pass `measure` — typically `font.size` composed to return a width — and the fit is
    exact for any face. Without it the old fixed-advance assumption applies, which is
    correct only while the font really is monospace.

    A shortened string ends in '>' so the reader can see it was cut rather than
    mistaking the fragment for the whole value."""
    if max_w <= 0 or (measure is None and char_w <= 0):
        return ""
    if _width(text, char_w, measure) <= max_w:
        return text
    # Trim a character at a time, leaving room for the marker. Character-wise rather
    # than by arithmetic because with a proportional face there is no divisor to use.
    for cut in range(len(text) - 1, 0, -1):
        candidate = text[:cut] + ">"
        if _width(candidate, char_w, measure) <= max_w:
            return candidate
    return ""


@dataclass(frozen=True)
class BarRowGeometry:
    """Placement for one ``[swatch] NAME [bar] value`` row, all inside `row`."""

    row: Rect
    swatch: Rect
    name: str
    name_x: int
    bar: Rect
    label: str
    label_x: int
    #: The label's real pixel width, carried rather than recomputed. Deriving it from
    #: `len(label) * char_w` here while `label_x` was placed from a *measured* width
    #: made the geometry disagree with itself on any face that is not fixed-pitch.
    label_w: int
    char_w: int = CHAR_W

    @property
    def label_right(self) -> int:
        return self.label_x + self.label_w

    @property
    def truncated(self) -> bool:
        return self.label.endswith(">")


def bar_row(
    row: Rect,
    name: str,
    label: str,
    char_w: int = CHAR_W,
    name_chars: int = NAME_CHARS,
    measure: "Measure | None" = None,
) -> BarRowGeometry:
    """Lay out a compact bar row so its right-hand label ends at the row's right edge.

    The label is right-aligned against `row.right` and the bar shrinks to make
    room, rather than the label being blitted at a fixed offset past a
    fixed-width bar — which is what used to push leg reserve values off the
    panel. The bar's start also yields to the name at the caller's *measured*
    character width, since a fixed `BAR_X` is only clear of a five-character
    name while the font stays narrow. If a label is too long even for the whole
    row, it is truncated with a visible marker."""
    swatch = Rect(row.x, row.y + ROW_INSET_Y, SWATCH_W, SWATCH_H)
    name_x = row.x + NAME_X
    name_text = f"{name[:name_chars]:<{name_chars}}"

    bar_x = max(row.x + BAR_X, name_x + _width(name_text, char_w, measure) + NAME_GAP)
    label_text = clip_text(label, max(0, row.right - bar_x - LABEL_GAP), char_w, measure)
    label_w = _width(label_text, char_w, measure)
    label_x = row.right - label_w
    bar_w = max(0, min(BAR_MAX_W, label_x - LABEL_GAP - bar_x))
    bar = Rect(bar_x, row.y + ROW_INSET_Y, bar_w, SWATCH_H)

    return BarRowGeometry(
        row=row,
        swatch=swatch,
        name=name_text,
        name_x=name_x,
        bar=bar,
        label=label_text,
        label_x=label_x,
        label_w=label_w,
        char_w=char_w,
    )


# --- Layout -----------------------------------------------------------------


class _Builder:
    """Appends rows top-down and refuses to place anything past `bottom`."""

    def __init__(self, x: int, y: int, w: int, bottom: int) -> None:
        self.x = x
        self.y = y
        self.w = w
        self.bottom = bottom
        self.rows: list[Row] = []
        self.overflowed = False

    def add(self, kind: RowKind, h: int, index: int = -1, indent: int = 0) -> None:
        if h <= 0:
            return
        if self.y + h > self.bottom:
            self.overflowed = True
            return
        self.rows.append(
            Row(kind, Rect(self.x + indent, self.y, self.w - indent, h), index)
        )
        self.y += h

    def pad(self, h: int) -> None:
        self.y = min(self.y + h, self.bottom)

    def open_section(self) -> tuple[int, int]:
        return self.y, len(self.rows)

    def close_section(self, name: str, mark: tuple[int, int]) -> Section | None:
        """Finish a section. Returns None if nothing fitted in it."""
        start_y, start_idx = mark
        rows = tuple(self.rows[start_idx:])
        if not rows:
            return None
        return Section(name, Rect(self.x, start_y, self.w, self.y - start_y), rows)


def _content_h(
    profile: _Profile,
    *,
    variant: Variant,
    has_bot: bool,
    legs_total: int,
    legs_shown: int,
    with_notice: bool,
    organ_rows: int,
    storage_rows: int,
) -> int:
    """Height the inspector content would occupy under `profile`.

    Kept in lockstep with the builder below by
    `test_predicted_height_matches_the_built_layout`."""
    m = profile.metrics
    h = m.line_h + m.sep_h                              # title + separator
    if variant is Variant.WORKSHOP:
        h += m.line_h                                   # tick / controls row
    if not has_bot:
        return h + m.line_h                             # "No bot" / "Click a taobot"
    h += profile.bot_info_lines * m.line_h + m.pad_h
    h += m.sep_h + m.line_h + organ_rows * m.line_h + m.pad_h
    h += m.sep_h + m.line_h + storage_rows * m.line_h + m.pad_h
    if legs_total > 0:
        h += m.sep_h + m.line_h                         # separator + "Legs" heading
        h += legs_shown * _LEG_ROW_COUNT[profile.leg_detail] * m.line_h
    if variant is Variant.PLAIN:
        h += m.sep_h + (m.line_h if profile.params_heading else 0) + m.line_h + m.pad_h
        h += m.sep_h + m.line_h + profile.affinity_rows * m.line_h
    if with_notice:
        h += m.line_h
    return h


def _choose(
    avail_h: int,
    *,
    variant: Variant,
    has_bot: bool,
    legs_total: int,
    organ_rows: int,
    storage_rows: int,
) -> tuple[_Profile, int, bool]:
    """Walk the condensation ladder.

    Returns the richest profile that fits, how many legs it can show, and whether
    a notice row must be reserved. Only the last rung ever clips."""
    for profile in _LADDER:
        if (
            _content_h(
                profile,
                variant=variant,
                has_bot=has_bot,
                legs_total=legs_total,
                legs_shown=legs_total,
                with_notice=False,
                organ_rows=organ_rows,
                storage_rows=storage_rows,
            )
            <= avail_h
        ):
            return profile, legs_total, False

    profile = _LADDER[-1]
    m = profile.metrics
    # The notice is reserved before a single leg is placed, so the one guard
    # against silent clipping can never itself be the row that does not fit.
    base = _content_h(
        profile,
        variant=variant,
        has_bot=has_bot,
        legs_total=legs_total,
        legs_shown=0,
        with_notice=True,
        organ_rows=organ_rows,
        storage_rows=storage_rows,
    )
    per_leg = _LEG_ROW_COUNT[profile.leg_detail] * m.line_h
    shown = 0 if per_leg <= 0 else max(0, (avail_h - base) // per_leg)
    # Not `legs_total - 1`: when the header, organs or storage are what overflowed,
    # every leg may still fit, and claiming one is hidden would be a false notice.
    shown = min(shown, legs_total)
    return profile, shown, True


def compute(
    panel_x: int,
    panel_w: int,
    panel_h: int,
    leg_count: int = 0,
    *,
    panel_y: int = 0,
    variant: Variant = Variant.WORKSHOP,
    has_bot: bool = True,
    organ_rows: int = ORGAN_ROWS,
    storage_rows: int = STORAGE_ROWS,
) -> PanelLayout:
    """Lay the whole panel out from its geometry and the bot's part inventory.

    `panel_x` is the panel's left edge in screen pixels (the window width, since
    the panel sits to the right of the viewport). Returns rects only — this
    function never touches pygame and needs no display surface.

    Raises `LayoutError` for geometry too small to hold a panel, rather than
    returning collapsed rects that satisfy every assertion vacuously."""
    if panel_w < MIN_PANEL_W:
        raise LayoutError(f"panel_w {panel_w} is below the minimum {MIN_PANEL_W}")
    if panel_h < MIN_PANEL_H:
        raise LayoutError(f"panel_h {panel_h} is below the minimum {MIN_PANEL_H}")

    leg_count = max(0, leg_count)
    panel = Rect(panel_x, panel_y, panel_w, panel_h)
    bottom = panel_y + panel_h

    graph = Rect(
        panel_x + MARGIN,
        bottom - BOTTOM_SECTION_H,
        panel_w - MARGIN * 2,
        GRAPH_H,
    )
    graph_label = Rect(graph.x, graph.y - GRAPH_LABEL_H, graph.w, GRAPH_LABEL_H)

    pause_button = Rect(
        panel_x + (panel_w - PAUSE_BTN_W) // 2, bottom - PAUSE_BTN_UP, PAUSE_BTN_W, PAUSE_BTN_H
    )
    slider_track = Rect(panel_x + MARGIN, bottom - SLIDER_UP, panel_w - MARGIN * 2, SLIDER_H)
    slider_hit = Rect(
        slider_track.x,
        slider_track.y - SLIDER_HIT_PAD,
        slider_track.w,
        SLIDER_H + SLIDER_HIT_PAD * 2,
    )
    slider_label = Rect(
        slider_track.x, slider_track.y - SLIDER_LABEL_H - 2, slider_track.w, SLIDER_LABEL_H
    )

    ins_x = panel_x + MARGIN
    ins_y = panel_y + MARGIN
    ins_w = panel_w - MARGIN * 2
    inspector = Rect(ins_x, ins_y, ins_w, graph_label.y - INSPECTOR_GAP - ins_y)

    legs_total = leg_count if has_bot else 0
    profile, legs_shown, needs_notice = _choose(
        inspector.h,
        variant=variant,
        has_bot=has_bot,
        legs_total=legs_total,
        organ_rows=organ_rows,
        storage_rows=storage_rows,
    )
    m = profile.metrics

    # The notice slot is carved out of the build area up front, so no section can
    # consume it and leave the panel unable to admit what it dropped.
    build_bottom = inspector.bottom - (m.line_h if needs_notice else 0)
    b = _Builder(inspector.x, inspector.y, inspector.w, build_bottom)
    sections: list[Section] = []

    def close(name: str, mark: tuple[int, int]) -> None:
        section = b.close_section(name, mark)
        if section is not None:
            sections.append(section)

    mark = b.open_section()
    b.add(RowKind.HEADING, m.line_h)                    # panel title
    if variant is Variant.WORKSHOP:
        b.add(RowKind.TEXT, m.line_h)                   # tick / controls
    b.add(RowKind.SEPARATOR, m.sep_h)
    close("header", mark)

    if has_bot:
        mark = b.open_section()
        for _ in range(profile.bot_info_lines):
            b.add(RowKind.TEXT, m.line_h)
        b.pad(m.pad_h)
        close("bot_info", mark)

        for name, count in (("organs", organ_rows), ("storage", storage_rows)):
            mark = b.open_section()
            b.add(RowKind.SEPARATOR, m.sep_h)
            b.add(RowKind.HEADING, m.line_h)
            for i in range(count):
                b.add(RowKind.BAR, m.line_h, index=i)
            b.pad(m.pad_h)
            close(name, mark)

        if legs_total > 0:
            mark = b.open_section()
            b.add(RowKind.SEPARATOR, m.sep_h)
            b.add(RowKind.HEADING, m.line_h)
            for i in range(legs_shown):
                if profile.leg_detail is LegDetail.LINE:
                    b.add(RowKind.LEG_LINE, m.line_h, index=i)
                else:
                    b.add(RowKind.LEG_HEAD, m.line_h, index=i)
                    b.add(RowKind.BAR, m.line_h, index=i, indent=LEG_INDENT)
                    b.add(RowKind.BAR, m.line_h, index=i, indent=LEG_INDENT)
                    if profile.leg_detail is LegDetail.FULL:
                        b.add(RowKind.TEXT, m.line_h, index=i)
            close("legs", mark)

        if variant is Variant.PLAIN:
            mark = b.open_section()
            b.add(RowKind.SEPARATOR, m.sep_h)
            if profile.params_heading:
                b.add(RowKind.HEADING, m.line_h)
            b.add(RowKind.TEXT, m.line_h)
            b.pad(m.pad_h)
            close("params", mark)

            mark = b.open_section()
            b.add(RowKind.SEPARATOR, m.sep_h)
            b.add(RowKind.HEADING, m.line_h)
            for i in range(profile.affinity_rows):
                kind = RowKind.BAR if profile.affinity_rows >= AFFINITY_ROWS else RowKind.TEXT
                b.add(kind, m.line_h, index=i)
            close("affinity", mark)
    else:
        mark = b.open_section()
        b.add(RowKind.TEXT, m.line_h)
        close("message", mark)

    if needs_notice:
        b.bottom = inspector.bottom          # the slot reserved above
        mark = b.open_section()
        b.add(RowKind.NOTICE, m.line_h)
        close("notice", mark)

    return PanelLayout(
        variant=variant,
        panel=panel,
        inspector=inspector,
        graph=graph,
        graph_label=graph_label,
        pause_button=pause_button,
        slider_track=slider_track,
        slider_hit=slider_hit,
        slider_label=slider_label,
        sections=tuple(sections),
        metrics=m,
        bot_info_lines=profile.bot_info_lines if has_bot else 0,
        leg_detail=profile.leg_detail,
        affinity_rows=profile.affinity_rows,
        params_heading=profile.params_heading,
        legs_shown=legs_shown,
        legs_total=legs_total,
        # `b.overflowed` is a redundant safety net: the ladder only reaches its
        # clipping branch with `needs_notice` set, and
        # `test_predicted_height_matches_the_built_layout` pins `_content_h` to
        # what the builder actually places, so a refusal without a notice would
        # already be a caught failure. Kept because the cost of the term is zero
        # and the cost of a silently dropped row is the whole story.
        content_clipped=needs_notice or b.overflowed,
        rows_dropped=b.overflowed,
    )
