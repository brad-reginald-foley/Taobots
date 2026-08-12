"""Regression guard for the panel's layout arithmetic.

`panel_layout` is deliberately free of pygame, so everything here runs with no
display surface and no window. That is the point of the module: the panel used
to be verifiable only by looking at it, which is how it came to overwrite its
own output without anyone noticing.

What this file cannot prove is that the *renderer* obeys the rects it is given —
that is `test_renderer_panel.py`, on real pixels.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import panel_layout
from common import PANEL_W, WINDOW_H, WINDOW_W
from panel_layout import LayoutError, LegDetail, Rect, RowKind, Variant, compute

REPO_ROOT = Path(__file__).resolve().parent.parent

# The real window geometry, so the guard is about the panel that actually ships.
PANEL_X = WINDOW_W
PANEL_RIGHT = WINDOW_W + PANEL_W

ALL_LEG_COUNTS = list(range(0, 9))
VARIANTS = list(Variant)

#: Row kinds that put ink on the panel. Every one of them is checked for pixels
#: in `test_renderer_panel.py`; here they are checked for space.
DRAWN_KINDS = frozenset(RowKind)


def layout_for(legs: int, variant: Variant = Variant.WORKSHOP):
    return compute(PANEL_X, PANEL_W, WINDOW_H, legs, variant=variant)


def every_layout():
    for variant in VARIANTS:
        for legs in ALL_LEG_COUNTS:
            yield variant, legs, layout_for(legs, variant)


# --- The regression guard ---------------------------------------------------


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("legs", ALL_LEG_COUNTS)
def test_no_rect_overlaps_the_graph(legs: int, variant: Variant) -> None:
    """No rect the layout hands out may intrude on the organ graph.

    The original defect: the inspector flowed past the graph's top edge and the
    graph — drawn afterwards with an opaque fill — erased it."""
    layout = layout_for(legs, variant)
    for rect in layout.all_rects():
        if rect is layout.graph:
            continue
        assert not rect.overlaps(layout.graph), f"{rect} overlaps graph {layout.graph}"


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("legs", ALL_LEG_COUNTS)
def test_no_rect_extends_beyond_the_panel(legs: int, variant: Variant) -> None:
    """Every rect stays inside PANEL_W, horizontally and vertically."""
    layout = layout_for(legs, variant)
    for rect in layout.all_rects():
        assert rect.x >= PANEL_X, f"{rect} starts left of the panel"
        assert rect.right <= PANEL_RIGHT, f"{rect} runs past the panel's right edge"
        assert rect.y >= 0
        assert rect.bottom <= WINDOW_H


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("legs", ALL_LEG_COUNTS)
def test_every_section_row_is_inside_the_inspector(legs: int, variant: Variant) -> None:
    """Content is condensed or clipped within the inspector rect, never spilled."""
    layout = layout_for(legs, variant)
    for section in layout.sections:
        assert layout.inspector.contains(section.rect), f"{section.name} escapes the inspector"
        for row in section.rows:
            assert layout.inspector.contains(row.rect), f"{section.name} row escapes"


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("legs", ALL_LEG_COUNTS)
def test_rows_do_not_overlap_each_other(legs: int, variant: Variant) -> None:
    """Two rows sharing pixels means one is painting over the other."""
    layout = layout_for(legs, variant)
    rows = [row.rect for section in layout.sections for row in section.rows]
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            assert not a.overlaps(b), f"{a} overlaps {b}"


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("legs", ALL_LEG_COUNTS)
def test_nothing_the_layout_returns_is_degenerate(legs: int, variant: Variant) -> None:
    """Containment assertions are worthless against zero-sized rects.

    Every rect must be real, and every section must hold at least one row, or
    the guards above pass while nothing at all is laid out."""
    layout = layout_for(legs, variant)
    for rect in layout.all_rects():
        assert not rect.is_degenerate, f"{rect} is degenerate"
    assert layout.inspector.h > 0
    assert layout.sections, "no sections at shipping geometry"
    for section in layout.sections:
        assert section.rows, f"{section.name} has no rows"


# --- The test has teeth: the pre-change arithmetic fails it -----------------


def _legacy_inspector_bottom(legs: int) -> int:
    """Reproduce the pre-1.0e top-down flow of `_draw_workshop_inspector`.

    y starts at 8; `txt()` advances 16, `sep()` advances 7, and each section
    adds a 3px pad. Organs and Storage are five rows each (Water included, since
    Story 1.0b). Every leg costs four rows. Nothing bounds the running y."""
    y = 8
    y += 16 * 2 + 7                     # title, tick line, separator
    y += 16 * 5 + 3                     # bot info block
    y += 7 + 16 + 16 * 5 + 3            # Organs
    y += 7 + 16 + 16 * 5 + 3            # Storage
    y += 7 + 16                         # Legs heading
    y += legs * 4 * 16
    return y


def test_legacy_arithmetic_overruns_the_graph_at_one_leg() -> None:
    """The guard above is only meaningful if the old code fails it.

    One leg is enough — Story 1.0b's Water organ row moved the failure point
    down from two legs to one."""
    graph_top = layout_for(1).graph.y
    assert _legacy_inspector_bottom(0) <= graph_top, "the header alone should have fitted"
    assert _legacy_inspector_bottom(1) > graph_top, (
        "the pre-change arithmetic is supposed to overrun the graph at one leg"
    )
    for legs in range(1, 9):
        assert _legacy_inspector_bottom(legs) > graph_top


def test_legacy_reserve_label_overruns_the_panel() -> None:
    """The pre-change right label was blitted at a fixed offset past a fixed bar.

    Leg rows were indented 8px, which pushed the longest reserve labels past the
    panel's right edge."""
    row_x = PANEL_X + panel_layout.MARGIN + panel_layout.LEG_INDENT
    legacy_label_x = row_x + panel_layout.BAR_X + panel_layout.BAR_MAX_W + panel_layout.LABEL_GAP
    longest = "3.951/10.0"
    assert legacy_label_x + len(longest) * panel_layout.CHAR_W > PANEL_RIGHT


# --- The rest of the matrix -------------------------------------------------


def test_zero_legs_is_valid_and_has_no_leg_section() -> None:
    layout = layout_for(0)
    assert layout.section("legs") is None
    assert layout.legs_total == 0
    assert not layout.truncated
    assert not layout.content_clipped
    # A legless bot has room for everything else at full detail.
    assert layout.leg_detail is LegDetail.FULL
    assert layout.bot_info_lines == 5


def test_graph_derives_from_the_same_layout() -> None:
    """The graph sits at or below the inspector's bottom for every inventory."""
    for _variant, _legs, layout in every_layout():
        assert layout.graph_label.bottom <= layout.graph.y
        assert layout.inspector.bottom <= layout.graph_label.y
        assert layout.graph.y >= layout.inspector.bottom
        assert layout.graph.bottom <= WINDOW_H


def test_graph_rect_is_stable_across_inventories_and_variants() -> None:
    """The graph does not move when legs are added; only the inspector's content
    condenses. Two constants that must agree is the defect, not the fix."""
    rects = {layout.graph for _v, _n, layout in every_layout()}
    assert len(rects) == 1


def test_chrome_is_placed_by_the_layout_and_clears_everything_above_it() -> None:
    """The pause button and slider used to compute their own y from window_h.

    That is the same "two constants that must agree" shape the graph had, so
    they come out of `compute` now and are asserted against it."""
    for _variant, _legs, layout in every_layout():
        for rect in (
            layout.pause_button,
            layout.slider_track,
            layout.slider_hit,
            layout.slider_label,
        ):
            assert not rect.overlaps(layout.graph), f"{rect} overlaps the graph"
            assert not rect.overlaps(layout.graph_label)
            assert not rect.overlaps(layout.inspector)
            assert rect.y >= layout.graph.bottom, f"{rect} is above the graph's bottom"
            assert rect.x >= PANEL_X and rect.right <= PANEL_RIGHT
            assert rect.bottom <= WINDOW_H
        # The clickable area must cover the track it is a proxy for.
        assert layout.slider_hit.contains(layout.slider_track)


def test_no_display_surface_needed() -> None:
    """Importing and calling the layout must not pull in pygame at all."""
    script = (
        "import sys; import panel_layout;"
        "L = panel_layout.compute(800, 240, 600, 4);"
        "assert 'pygame' not in sys.modules, sorted(m for m in sys.modules if 'pygame' in m);"
        "assert L.graph.h > 0 and L.inspector.h > 0;"
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_panel_layout_module_imports_no_pygame() -> None:
    """Belt and braces on the seam: the source itself must not name pygame."""
    source = (REPO_ROOT / "panel_layout.py").read_text()
    assert "import pygame" not in source


@pytest.mark.parametrize(
    "label",
    ["3.951/4.0", "3.951/10.0", "20.0/20", "100.0", "0.000/0.0", "999.9/1000"],
)
@pytest.mark.parametrize("indent", [0, panel_layout.LEG_INDENT])
@pytest.mark.parametrize("char_w", [7, 8, 9, 10])
def test_longest_labels_stay_inside_the_panel(label: str, indent: int, char_w: int) -> None:
    """Right labels end at the row's right edge, never past the panel.

    Swept across plausible font advances, because the renderer measures its own
    face rather than trusting the module default."""
    layout = layout_for(4)
    row = Rect(
        layout.inspector.x + indent,
        layout.inspector.y,
        layout.inspector.w - indent,
        layout.metrics.line_h,
    )
    geom = panel_layout.bar_row(row, "resv", label, char_w=char_w)
    assert geom.label_right <= row.right <= PANEL_RIGHT
    assert geom.bar.right <= geom.label_x - panel_layout.LABEL_GAP
    assert geom.bar.w > 0
    assert geom.swatch.x >= row.x


@pytest.mark.parametrize("char_w", [7, 8, 9, 10, 12])
def test_bar_starts_clear_of_the_name(char_w: int) -> None:
    """`BAR_X` is fixed but the name's width is not.

    At a wide enough face the five-character name would run under the bar, so
    the bar start yields to the measured advance."""
    row = Rect(PANEL_X + 8, 0, 224, 16)
    geom = panel_layout.bar_row(row, "integr", "0.951", char_w=char_w)
    name_right = geom.name_x + len(geom.name) * char_w
    assert geom.bar.x >= name_right, "the name overruns the bar"


def test_bar_row_truncates_a_label_it_cannot_fit() -> None:
    """An absurd label is cut with a visible marker rather than drawn off-panel."""
    row = Rect(PANEL_X + 8, 0, 100, 16)
    geom = panel_layout.bar_row(row, "resv", "1234567890123456789012345")
    assert geom.label_right <= row.right
    assert geom.truncated and geom.label.endswith(">")


def test_clip_text_marks_what_it_cut() -> None:
    assert panel_layout.clip_text("abcdef", 6 * 8) == "abcdef"
    assert panel_layout.clip_text("abcdef", 4 * 8) == "abc>"
    assert panel_layout.clip_text("abcdef", 0) == ""


# --- Condensation and truncation -------------------------------------------


@pytest.mark.parametrize("variant", VARIANTS)
def test_condensation_ladder_is_monotonic(variant: Variant) -> None:
    """More legs never yields a richer presentation than fewer legs did."""
    rank = {LegDetail.FULL: 0, LegDetail.BARS: 1, LegDetail.LINE: 2}
    previous = -1
    for legs in ALL_LEG_COUNTS:
        current = rank[layout_for(legs, variant).leg_detail]
        assert current >= previous
        previous = current


def test_legs_are_condensed_before_they_are_clipped() -> None:
    """The four-leg target body plan shows every leg — condensed, not truncated."""
    layout = layout_for(4)
    assert layout.legs_shown == 4
    assert not layout.truncated
    assert not layout.content_clipped


def test_the_shipping_body_fits_in_both_panels() -> None:
    """Two legs is the body every taobot is built with today.

    Neither panel may need a "rows hidden" notice for it — a panel that always
    says it is full is not legible."""
    for variant in VARIANTS:
        layout = layout_for(2, variant)
        assert not layout.content_clipped, f"{variant.value} panel is full at the default body"
        assert layout.section("notice") is None
        assert layout.truncation_note == ""
        assert layout.legs_shown == 2


def test_the_plain_panel_keeps_every_block_at_the_shipping_body() -> None:
    """Params and Affinities must survive; they used to be erased by the graph."""
    layout = layout_for(2, Variant.PLAIN)
    names = [s.name for s in layout.sections]
    assert names == ["header", "bot_info", "organs", "storage", "legs", "params", "affinity"]


def test_clipping_is_reported_not_silent() -> None:
    """When rows must be dropped, the layout says so — unconditionally asserted.

    An eight-leg plain panel cannot fit at shipping geometry, so this is not
    guarded by an `if` that could pass vacuously."""
    layout = layout_for(8, Variant.PLAIN)
    assert layout.content_clipped
    assert layout.truncated
    assert layout.legs_shown < 8
    assert str(8 - layout.legs_shown) in layout.truncation_note
    assert "hidden" in layout.truncation_note
    notice = layout.section("notice")
    assert notice is not None
    assert [r.kind for r in notice.rows] == [RowKind.NOTICE]


def test_the_notice_row_is_reserved_before_anything_else() -> None:
    """The one guard against silent clipping must not itself be clippable.

    Swept down to the smallest legal panel: whenever content is clipped there is
    always a notice row, and it is the last thing on the panel."""
    for panel_h in range(panel_layout.MIN_PANEL_H, WINDOW_H + 1, 7):
        for variant in VARIANTS:
            for legs in ALL_LEG_COUNTS:
                layout = compute(PANEL_X, PANEL_W, panel_h, legs, variant=variant)
                if not layout.content_clipped:
                    continue
                notice = layout.section("notice")
                assert notice is not None, f"clipped with no notice: {panel_h=} {legs=}"
                assert notice.rows
                assert layout.inspector.contains(notice.rows[0].rect)
                assert layout.sections[-1] is notice
                assert layout.truncation_note != ""


def test_dropped_rows_are_always_announced() -> None:
    """The builder's refusal flag must never be true behind a silent panel.

    `_Builder.overflowed` used to be set on every dropped row and read by
    nothing, so on a short panel organ or storage rows vanished while the panel
    claimed all was well. Swept across every legal geometry."""
    for panel_h in range(panel_layout.MIN_PANEL_H, WINDOW_H + 1, 11):
        for variant in VARIANTS:
            for legs in ALL_LEG_COUNTS:
                layout = compute(PANEL_X, PANEL_W, panel_h, legs, variant=variant)
                if not layout.rows_dropped:
                    continue
                assert layout.content_clipped, f"rows dropped in silence: {panel_h=} {legs=}"
                assert layout.section("notice") is not None
                assert layout.truncation_note != ""


def test_no_rows_are_dropped_at_shipping_geometry() -> None:
    """At 240x600 the ladder must place everything it planned to place."""
    for _variant, _legs, layout in every_layout():
        assert not layout.rows_dropped


def test_the_notice_does_not_claim_legs_are_hidden_when_they_are_not() -> None:
    """A legless bot on a panel too small for its organs must not blame legs."""
    layout = compute(PANEL_X, PANEL_W, panel_layout.MIN_PANEL_H, 0)
    assert layout.content_clipped
    assert layout.legs_total == 0
    assert "legs" not in layout.truncation_note
    assert layout.truncation_note == "panel full - rows hidden"


def test_water_organ_row_is_still_there() -> None:
    """Story 1.0b's Water organ row must survive the relayout: five organ rows."""
    for variant in VARIANTS:
        layout = layout_for(2, variant)
        organs = layout.section("organs")
        assert organs is not None
        assert len([r for r in organs.rows if r.kind is RowKind.BAR]) == 5
        storage = layout.section("storage")
        assert storage is not None
        assert len([r for r in storage.rows if r.kind is RowKind.BAR]) == 5


def test_leg_row_counts_match_the_detail_level() -> None:
    for variant in VARIANTS:
        for legs in range(1, 9):
            layout = layout_for(legs, variant)
            section = layout.section("legs")
            assert section is not None
            leg_rows = [r for r in section.rows if r.kind is not RowKind.SEPARATOR
                        and r.kind is not RowKind.HEADING]
            per_leg = {LegDetail.FULL: 4, LegDetail.BARS: 3, LegDetail.LINE: 1}
            assert len(leg_rows) == layout.legs_shown * per_leg[layout.leg_detail]


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("legs", ALL_LEG_COUNTS)
def test_predicted_height_matches_the_built_layout(legs: int, variant: Variant) -> None:
    """`_content_h` drives the ladder; the builder places the rows.

    If they disagree the ladder picks a rung that does not actually fit and the
    builder silently drops the difference."""
    layout = layout_for(legs, variant)
    if layout.content_clipped:
        pytest.skip("clipped layouts intentionally place less than predicted")
    profile = panel_layout._Profile(
        layout.bot_info_lines,
        layout.leg_detail,
        layout.metrics,
        layout.affinity_rows,
        layout.params_heading,
    )
    predicted = panel_layout._content_h(
        profile,
        variant=variant,
        has_bot=True,
        legs_total=layout.legs_total,
        legs_shown=layout.legs_shown,
        with_notice=False,
        organ_rows=5,
        storage_rows=5,
    )
    built = layout.sections[-1].rect.bottom - layout.inspector.y
    assert built == predicted


def test_no_bot_still_lays_out() -> None:
    for variant in VARIANTS:
        layout = compute(PANEL_X, PANEL_W, WINDOW_H, 0, variant=variant, has_bot=False)
        assert [s.name for s in layout.sections] == ["header", "message"]
        for rect in layout.all_rects():
            assert rect is layout.graph or not rect.overlaps(layout.graph)
            assert rect.right <= PANEL_RIGHT
            assert not rect.is_degenerate


def test_negative_leg_count_is_clamped() -> None:
    layout = compute(PANEL_X, PANEL_W, WINDOW_H, -3)
    assert layout.legs_total == 0


# --- Degenerate geometry ----------------------------------------------------


@pytest.mark.parametrize("panel_h", [0, 50, 150, panel_layout.MIN_PANEL_H - 1])
def test_a_panel_too_short_is_rejected(panel_h: int) -> None:
    """A 150px panel used to yield a graph at y=-42 and a zero-height inspector.

    Every containment assertion then passes vacuously while nothing is drawn, so
    the geometry is refused instead."""
    with pytest.raises(LayoutError):
        compute(PANEL_X, PANEL_W, panel_h, 2)


@pytest.mark.parametrize("panel_w", [0, 10, panel_layout.MIN_PANEL_W - 1])
def test_a_panel_too_narrow_is_rejected(panel_w: int) -> None:
    """Below this the rects come out with `right` to the left of `x`."""
    with pytest.raises(LayoutError):
        compute(PANEL_X, panel_w, WINDOW_H, 2)


def test_the_smallest_legal_panel_is_still_a_real_panel() -> None:
    layout = compute(PANEL_X, panel_layout.MIN_PANEL_W, panel_layout.MIN_PANEL_H, 8)
    assert layout.inspector.h >= panel_layout.MIN_INSPECTOR_H
    for rect in layout.all_rects():
        assert not rect.is_degenerate
        assert rect.right <= PANEL_X + panel_layout.MIN_PANEL_W
    for section in layout.sections:
        assert layout.inspector.contains(section.rect)
        for row in section.rows:
            assert layout.inspector.contains(row.rect)
        assert not section.rect.overlaps(layout.graph)


def test_a_cramped_but_legal_panel_reports_what_it_dropped() -> None:
    layout = compute(PANEL_X, PANEL_W, 300, 8)
    assert layout.content_clipped
    assert layout.section("notice") is not None
    for section in layout.sections:
        assert layout.inspector.contains(section.rect)
        assert not section.rect.overlaps(layout.graph)


# --- Rect algebra used by the assertions above ------------------------------


def test_rect_overlap_and_containment() -> None:
    a = Rect(0, 0, 10, 10)
    assert a.overlaps(Rect(9, 9, 5, 5))
    assert not a.overlaps(Rect(10, 0, 5, 5))     # edge-adjacent is not overlap
    assert not a.overlaps(Rect(0, 0, 0, 10))     # empty rects never overlap
    assert a.contains(Rect(1, 1, 8, 8))
    assert not a.contains(Rect(1, 1, 20, 8))


def test_containment_is_not_vacuously_true_for_empty_rects() -> None:
    """A collapsed rect must not pass every containment check in the suite."""
    a = Rect(0, 0, 10, 10)
    assert not a.contains(Rect(2, 2, 0, 0))
    assert not Rect(0, 0, 0, 0).contains(Rect(0, 0, 0, 0))
    assert Rect(0, 0, 0, 5).is_degenerate
