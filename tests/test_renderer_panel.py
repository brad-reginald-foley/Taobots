"""The panel defect, tested where it happened: on real pixels.

`test_panel_layout.py` proves the arithmetic. This proves the renderer obeys it.
The distinction matters more than it looks: the inspector is hard-clipped now, so
a renderer that computes a position wrongly no longer paints outside the panel —
it paints *nothing*, and an assertion made against the layout's own dataclasses
would never notice. Every check here reads the surface back.

Drawing goes to an offscreen `pygame.Surface`, so no display is needed.
"""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

import panel_layout
from common import (
    ELEMENT_LIST,
    PANEL_COLOR,
    PANEL_W,
    WINDOW_H,
    WINDOW_W,
)
from panel_layout import RowKind, Variant
from renderer import LayoutMismatch, Renderer

PANEL_X = WINDOW_W
PANEL_RIGHT = WINDOW_W + PANEL_W

#: Every kind that must put ink somewhere inside its own row.
INKED_KINDS = frozenset(RowKind)


class _StubLeg:
    """Only what `Renderer` reads off a leg: the count, and dot placement."""

    def __init__(self) -> None:
        self.theta = 0.4
        self.structural_integrity = 0.951


class _StubBot:
    """A bot with deliberately long values, so labels are at their widest.

    Only the handful of attributes the renderer reads are provided; `as_bot`
    casts it at the call boundary so mypy sees the real parameter type."""

    archetype = "wanderer"

    def __init__(self, n_legs: int, entity_id: int = 12345) -> None:
        self.legs = [_StubLeg() for _ in range(n_legs)]
        self.entity_id = entity_id
        self.x = 39.94
        self.y = 30.17
        self.heading = 1.234
        self.behavior_state = "collecting"

    def organ(self, element) -> float:
        return 87.65

    def get_state(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "x": self.x,
            "y": self.y,
            "organs": {e.name: 87.65 for e in ELEMENT_LIST},
            "behavior_state": self.behavior_state,
            "storage": {e.name: 19.95 for e in ELEMENT_LIST},
            "storage_capacity": {e.name: 20.0 for e in ELEMENT_LIST},
            "fitness_score": 0.9876,
            "age_ticks": 9999,
            "heading": self.heading,
            "speed": 2.2,
            "sensing_range": 8.0,
            "affinity": {e.name: 0.2 for e in ELEMENT_LIST},
            "resources_by_element": {e.name: 1 for e in ELEMENT_LIST},
            "distance_moved": 1234.5,
            "damage_taken_total": 678.9,
            "legs": [
                {
                    "index": i,
                    "theta_deg": -114.6,
                    "phi_deg": -180.0,
                    "reserve": 3.951,
                    "capacity": 10.0,
                    "integrity": 0.951,
                    "thrust": -0.9876,
                    "max_thrust": 1.0,
                }
                for i in range(len(self.legs))
            ],
        }


class _StubWorld:
    """The minimum `Renderer.render` reads. Enough to exercise the whole frame."""

    def __init__(self, bot: _StubBot) -> None:
        self.resources: list = []
        self.dead_resources: list = []
        self.hazards: list = []
        self.taobots = [bot]
        self._taobots = {bot.entity_id: bot}
        self.tick_count = 300


def as_bot(stub: _StubBot) -> Any:
    """Hand the stub to renderer methods typed for a real taobot."""
    return cast(Any, stub)


@pytest.fixture
def surface(pygame_init):
    import pygame

    return pygame.Surface((WINDOW_W + PANEL_W, WINDOW_H))


def _clear_panel(surface) -> None:
    import pygame

    surface.fill(PANEL_COLOR, pygame.Rect(WINDOW_W, 0, PANEL_W, WINDOW_H))


def _snapshot(surface, rect: panel_layout.Rect) -> bytes:
    import pygame

    return pygame.image.tostring(surface.subsurface(pygame.Rect(*rect.as_tuple())), "RGB")


def _painted(surface, rect: panel_layout.Rect) -> bool:
    """True if any pixel inside `rect` differs from the panel background."""
    for y in range(rect.y, rect.bottom):
        for x in range(rect.x, rect.right):
            if surface.get_at((x, y))[:3] != PANEL_COLOR:
                return True
    return False


def _rightmost_painted_x(surface, rect: panel_layout.Rect) -> int | None:
    for x in range(rect.right - 1, rect.x - 1, -1):
        for y in range(rect.y, rect.bottom):
            if surface.get_at((x, y))[:3] != PANEL_COLOR:
                return x
    return None


def _draw(renderer: Renderer, surface, bot, layout, workshop: bool) -> None:
    _clear_panel(surface)
    if workshop:
        renderer._draw_workshop_inspector(as_bot(bot), 300, layout)
    else:
        renderer._draw_inspector(as_bot(bot), layout)
    renderer._draw_organ_graph(layout)


def _fill_history(renderer: Renderer, n: int = 200) -> None:
    for i in range(n):
        value = 50 + 40 * math.sin(i / 9)
        renderer.push_organ_sample(value, value - 10, value + 10)


# --- The headline defect ----------------------------------------------------


@pytest.mark.parametrize("legs", [0, 1, 2, 4, 8])
@pytest.mark.parametrize("workshop", [True, False])
def test_graph_does_not_overwrite_the_inspector(surface, legs: int, workshop: bool) -> None:
    """The panel must look the same at tick 0 and once the graph has samples.

    Before this story the graph filled an opaque rect at a fixed y computed
    independently of the inspector, and returned early while its history was
    empty — so the panel looked right until the first sample landed and then
    erased whatever the inspector had drawn there."""
    renderer = Renderer(surface, workshop=workshop)
    bot = _StubBot(legs)
    layout = renderer._panel_layout(as_bot(bot))

    _draw(renderer, surface, bot, layout, workshop)
    empty_history = _snapshot(surface, layout.inspector)
    # Comparing a region against itself is satisfied by drawing nothing at all.
    assert _painted(surface, layout.inspector), "the inspector drew nothing"

    _fill_history(renderer)
    _draw(renderer, surface, bot, layout, workshop)
    assert _snapshot(surface, layout.inspector) == empty_history


@pytest.mark.parametrize("legs", [0, 1, 2, 4, 8])
def test_nothing_is_drawn_in_the_gap_below_the_inspector(surface, legs: int) -> None:
    """The band between the inspector's bottom and the graph caption stays clean.

    Anything there is content that escaped its rect."""
    renderer = Renderer(surface, workshop=True)
    bot = _StubBot(legs)
    layout = renderer._panel_layout(as_bot(bot))
    _fill_history(renderer, 50)
    _draw(renderer, surface, bot, layout, workshop=True)

    gap = panel_layout.Rect(
        PANEL_X, layout.inspector.bottom, PANEL_W, layout.graph_label.y - layout.inspector.bottom
    )
    assert gap.h >= 0
    if gap.h:
        assert not _painted(surface, gap)


@pytest.mark.parametrize("legs", [0, 1, 2, 4, 8])
@pytest.mark.parametrize("workshop", [True, False])
def test_nothing_is_painted_past_the_panel_edge(surface, legs, workshop) -> None:
    """The panel's last two pixel columns are never painted."""
    renderer = Renderer(surface, workshop=workshop)
    bot = _StubBot(legs)
    layout = renderer._panel_layout(as_bot(bot))
    _fill_history(renderer, 50)
    _draw(renderer, surface, bot, layout, workshop)

    edge = panel_layout.Rect(PANEL_RIGHT - 2, 0, 2, WINDOW_H)
    assert not _painted(surface, edge)


# --- P1: the right-hand label, on pixels ------------------------------------


@pytest.mark.parametrize("legs", [1, 2])
def test_leg_reserve_label_is_painted_whole_and_flush_right(surface, legs: int) -> None:
    """The longest bar label must actually reach the panel's right edge.

    The pre-change code blitted it at a fixed offset past a fixed-width bar,
    which ran past the edge — and now that the inspector is clipped, that same
    arithmetic would be silently *cut* rather than visibly overflowing. So this
    reads the surface: the drawn pixels must match a reference render of the
    full label at the layout's right-aligned position, and the rightmost ink in
    the row must be the label's, not the bar's."""
    import pygame

    renderer = Renderer(surface, workshop=True)
    bot = _StubBot(legs)
    layout = renderer._panel_layout(as_bot(bot))
    assert layout.leg_detail is panel_layout.LegDetail.BARS
    _draw(renderer, surface, bot, layout, workshop=True)

    section = layout.section("legs")
    assert section is not None
    bar_rows = [r for r in section.rows if r.kind is RowKind.BAR]
    assert len(bar_rows) == legs * 2

    label = "3.951/10.0"
    for reserve_row in bar_rows[1::2]:          # second bar of each leg is reserve
        row = reserve_row.rect
        geom = panel_layout.bar_row(row, "resv", label, char_w=renderer._char_w_sm)
        assert geom.label == label, "the label was truncated to fit"
        assert geom.label_right <= PANEL_RIGHT

        from common import DIM_WHITE

        expected = pygame.Surface((geom.label_right - geom.label_x, row.h))
        expected.fill(PANEL_COLOR)
        expected.blit(renderer._font_sm.render(label, True, DIM_WHITE), (0, 0))
        actual = surface.subsurface(
            pygame.Rect(geom.label_x, row.y, expected.get_width(), row.h)
        )
        assert pygame.image.tostring(actual, "RGB") == pygame.image.tostring(expected, "RGB"), (
            "the reserve label is not painted whole at its right-aligned position"
        )

        rightmost = _rightmost_painted_x(surface, row)
        assert rightmost is not None
        assert rightmost < geom.label_right
        assert rightmost >= geom.label_x, "the rightmost ink is not the label's"


# --- P2: the renderer paints into the rows it was allotted ------------------


@pytest.mark.parametrize("legs", [0, 1, 2, 4, 8])
@pytest.mark.parametrize("workshop", [True, False])
def test_every_allotted_row_gets_ink(surface, legs: int, workshop: bool) -> None:
    """A row the layout reserved and the renderer never filled is lost content.

    `_RowCursor` turns a layout/renderer mismatch into a skipped row, so without
    this a dropped organ — the Water row Story 1.0b added, say — would leave the
    whole suite green."""
    renderer = Renderer(surface, workshop=workshop)
    bot = _StubBot(legs)
    layout = renderer._panel_layout(as_bot(bot))
    _draw(renderer, surface, bot, layout, workshop)

    for section in layout.sections:
        for row in section.rows:
            if row.kind not in INKED_KINDS:
                continue
            assert _painted(surface, row.rect), (
                f"{section.name} {row.kind.value} row {row.index} was never painted"
            )


def test_cursor_raises_when_the_renderer_outruns_the_layout(surface) -> None:
    """Running out of rows is a bug, not something to skip past quietly."""
    renderer = Renderer(surface, workshop=True)
    layout = renderer._panel_layout(as_bot(_StubBot(2)))
    section = layout.section("organs")
    assert section is not None

    from renderer import _RowCursor

    cursor = _RowCursor(section, clipped=False)
    for row in section.rows:
        cursor.next(row.kind)
    with pytest.raises(LayoutMismatch):
        cursor.next(RowKind.BAR)


def test_cursor_raises_on_a_kind_mismatch(surface) -> None:
    """Drawing text where the layout allotted a bar is a mismatch, not a nudge."""
    renderer = Renderer(surface, workshop=True)
    layout = renderer._panel_layout(as_bot(_StubBot(2)))
    section = layout.section("organs")
    assert section is not None

    from renderer import _RowCursor

    cursor = _RowCursor(section, clipped=False)
    with pytest.raises(LayoutMismatch):
        cursor.next(RowKind.BAR)          # the first row is a separator


def test_cursor_tolerates_exhaustion_only_when_the_layout_said_it_clipped(surface) -> None:
    from renderer import _RowCursor

    renderer = Renderer(surface, workshop=True)
    layout = renderer._panel_layout(as_bot(_StubBot(2)))
    section = layout.section("organs")
    assert section is not None
    cursor = _RowCursor(section, clipped=True)
    for row in section.rows:
        cursor.next(row.kind)
    assert cursor.next(RowKind.BAR) is None
    assert _RowCursor(None, clipped=False).next(RowKind.TEXT) is None


# --- P3: the truncation notice is really painted ----------------------------


def test_the_truncation_notice_is_painted(surface) -> None:
    """An 8-leg plain panel drops legs; it must say so on screen, in ink."""
    renderer = Renderer(surface, workshop=False)
    bot = _StubBot(8)
    layout = renderer._panel_layout(as_bot(bot))
    assert layout.content_clipped and layout.truncated

    notice = layout.section("notice")
    assert notice is not None
    _draw(renderer, surface, bot, layout, workshop=False)
    assert _painted(surface, notice.rows[0].rect), "the panel hid rows without saying so"


def test_no_notice_is_painted_when_nothing_was_dropped(surface) -> None:
    """The shipping body must not see a notice in either panel."""
    for workshop in (True, False):
        renderer = Renderer(surface, workshop=workshop)
        bot = _StubBot(2)
        layout = renderer._panel_layout(as_bot(bot))
        assert layout.section("notice") is None
        assert not layout.content_clipped


# --- P5: the chrome is placed by the layout ---------------------------------


def test_pause_and_slider_rects_come_from_the_layout(surface) -> None:
    renderer = Renderer(surface, workshop=True)
    chrome = renderer._chrome
    assert renderer.pause_button_rect == pytest.approx(chrome.pause_button.as_tuple())
    assert renderer.speed_slider_rect == pytest.approx(chrome.slider_hit.as_tuple())
    assert renderer.fps_from_mouse_x(chrome.slider_track.x) == 5
    assert renderer.fps_from_mouse_x(chrome.slider_track.right) == 120


def test_chrome_is_painted_below_the_graph_and_never_on_it(surface) -> None:
    """The pause button and slider used to derive their own y from window_h."""
    renderer = Renderer(surface, workshop=True)
    layout = renderer._panel_layout(as_bot(_StubBot(2)))
    _fill_history(renderer, 50)

    _clear_panel(surface)
    renderer._draw_organ_graph(layout)
    graph_only = _snapshot(surface, layout.graph)

    renderer._draw_pause_button(paused=False)
    renderer._draw_speed_slider(60, 60.0)
    assert _snapshot(surface, layout.graph) == graph_only, "chrome painted onto the graph"
    assert _painted(surface, renderer._chrome.pause_button)
    assert _painted(surface, renderer._chrome.slider_track)
    assert _painted(surface, renderer._chrome.slider_label)


# --- P7: the graph is bounded too -------------------------------------------


def _painted_bbox(surface, region: panel_layout.Rect) -> panel_layout.Rect | None:
    xs, ys = [], []
    for y in range(region.y, region.bottom):
        for x in range(region.x, region.right):
            if surface.get_at((x, y))[:3] != PANEL_COLOR:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return panel_layout.Rect(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


@pytest.mark.parametrize("legs", [0, 2, 8])
def test_the_graph_is_painted_exactly_where_the_layout_put_it(surface, legs: int) -> None:
    """The graph's ink must occupy `layout.graph` and not a pixel more or less.

    Asserting only that it clears the inspector would let it drift anywhere in
    the empty space below — which is how it came to be positioned by a constant
    of its own in the first place."""
    renderer = Renderer(surface, workshop=True)
    layout = renderer._panel_layout(as_bot(_StubBot(legs)))
    _fill_history(renderer, 200)

    _clear_panel(surface)
    renderer._draw_organ_graph(layout)

    # Everything below the caption and above the chrome should be graph, only graph.
    region = panel_layout.Rect(
        PANEL_X, layout.graph_label.bottom, PANEL_W,
        renderer._chrome.pause_button.y - layout.graph_label.bottom,
    )
    assert _painted_bbox(surface, region) == layout.graph


@pytest.mark.parametrize("bad", [1e6, -1e6, float("inf"), float("-inf"), float("nan")])
def test_an_out_of_range_sample_cannot_escape_the_graph(surface, bad: float) -> None:
    """`to_px` maps value/100 with no bound, so a wild sample used to paint upward
    over the caption and the inspector."""
    renderer = Renderer(surface, workshop=True)
    bot = _StubBot(2)
    layout = renderer._panel_layout(as_bot(bot))
    for _ in range(10):
        renderer.push_organ_sample(bad, bad, bad)
        renderer.push_organ_sample(50.0, 40.0, 60.0)

    _clear_panel(surface)
    renderer._draw_workshop_inspector(as_bot(bot), 300, layout)
    inspector_before = _snapshot(surface, layout.inspector)
    renderer._draw_organ_graph(layout)

    assert _snapshot(surface, layout.inspector) == inspector_before
    above = panel_layout.Rect(PANEL_X, layout.graph_label.bottom, PANEL_W,
                              layout.graph.y - layout.graph_label.bottom)
    if above.h:
        assert not _painted(surface, above)


def test_samples_are_clamped_at_the_door(surface) -> None:
    renderer = Renderer(surface, workshop=True)
    renderer.push_organ_sample(500.0, -20.0, float("nan"))
    assert list(renderer._organ_history) == [(100.0, 0.0, 0.0)]


@pytest.mark.parametrize("bad", [400.0, -400.0])
def test_the_graph_is_bounded_even_if_the_history_is_not(surface, bad: float) -> None:
    """Clamping at the door is the mechanism; the clip is the guarantee.

    Written past `push_organ_sample` on purpose — a door clamp makes the plot's
    own bound and clip untestable through the public path, and the graph was the
    one region of the panel with neither. Anything appended to the buffer by a
    future path must still be unable to paint over the caption or the inspector
    above it."""
    renderer = Renderer(surface, workshop=True)
    bot = _StubBot(2)
    layout = renderer._panel_layout(as_bot(bot))
    for i in range(10):
        renderer._organ_history.append((bad, bad - 1, bad + 1))
        renderer._organ_history.append((50.0, 40.0, 60.0))

    _clear_panel(surface)
    renderer._draw_workshop_inspector(as_bot(bot), 300, layout)
    inspector_before = _snapshot(surface, layout.inspector)
    renderer._draw_organ_graph(layout)

    assert _snapshot(surface, layout.inspector) == inspector_before, (
        "the graph painted over the inspector"
    )
    above = panel_layout.Rect(
        PANEL_X, layout.graph_label.bottom, PANEL_W, layout.graph.y - layout.graph_label.bottom
    )
    if above.h:
        assert not _painted(surface, above)
    below = panel_layout.Rect(PANEL_X, layout.graph.bottom, PANEL_W, 20)
    assert not _painted(surface, below)


# --- The whole frame --------------------------------------------------------


@pytest.mark.parametrize("workshop", [True, False])
def test_render_draws_a_whole_frame_within_the_panel(surface, workshop: bool) -> None:
    """`render()` is the only place the "one layout owner" claim is enacted.

    Nothing tested it at any level, so a wiring mistake between the three panel
    drawers would not have shown up."""
    renderer = Renderer(surface, workshop=workshop)
    bot = _StubBot(2)
    world = _StubWorld(bot)
    _fill_history(renderer, 200)

    surface.fill((0, 0, 0))
    renderer.render(cast(Any, world), selected_id=bot.entity_id, fps=3.0, target_fps=3)

    layout = renderer._panel_layout(as_bot(bot))
    assert _painted(surface, layout.inspector)
    assert _painted(surface, layout.graph)
    assert _painted(surface, renderer._chrome.pause_button)
    gap = panel_layout.Rect(
        PANEL_X, layout.inspector.bottom, PANEL_W, layout.graph_label.y - layout.inspector.bottom
    )
    if gap.h:
        assert not _painted(surface, gap)
    for section in layout.sections:
        for row in section.rows:
            assert _painted(surface, row.rect), f"{section.name} {row.kind.value} unpainted"


def test_workshop_panel_with_no_bot_draws(surface) -> None:
    renderer = Renderer(surface, workshop=True)
    layout = renderer._panel_layout(None)
    _clear_panel(surface)
    renderer._draw_workshop_inspector(None, 0, layout)
    renderer._draw_organ_graph(layout)
    assert layout.legs_total == 0
    for section in layout.sections:
        for row in section.rows:
            assert _painted(surface, row.rect)


def test_plain_panel_with_no_bot_draws(surface) -> None:
    renderer = Renderer(surface, workshop=False)
    layout = renderer._panel_layout(None)
    assert layout.variant is Variant.PLAIN
    _clear_panel(surface)
    renderer._draw_inspector(None, layout)
    renderer._draw_organ_graph(layout)
    for section in layout.sections:
        for row in section.rows:
            assert _painted(surface, row.rect)
