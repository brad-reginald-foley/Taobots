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
    DIM_WHITE,
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


# --- Story 1.2: the Water-deficit trigger is watchable on the panel ---------
#
# Colour alone is not coverage here. The Water row's label carries three numbers that
# are easy to confuse and mean different things — the level Water is held to, the Water
# the *demand* path produced, and the Metal it spent — and the passive path's figure sits
# right beside them. Showing any of the wrong ones still paints amber pixels, so these
# assert the rendered *string*, reference-rendered and pixel-compared, the same way
# `test_leg_reserve_label_is_painted_whole_and_flush_right` does.

# Deliberately far apart, and none of them a round number: swapping produced for spent,
# or the deficit path's figure for the passive path's, or the level for zero, must each
# change the label rather than landing on the same text by luck.
_DEFICIT_LEVEL = 0.16
_DEFICIT_PRODUCED = 0.152
_DEFICIT_SPENT = 0.19
_PASSIVE_PRODUCED = 0.008
_PASSIVE_SPENT = 0.01


def _with_chi(
    bot: _StubBot, *, active: bool, served: bool = True, produced: float = _DEFICIT_PRODUCED
) -> _StubBot:
    """Give a stub bot the chi block `get_state` now carries."""
    original = bot.get_state

    def get_state() -> dict:
        state = original()
        state["chi"] = {
            "deficit_active": active,
            "deficit_served": served,
            "deficit_level": _DEFICIT_LEVEL,
            "passive_metal_to_water": (_PASSIVE_SPENT, _PASSIVE_PRODUCED),
            "deficit_metal_to_water": (_DEFICIT_SPENT, produced),
        }
        return state

    bot.get_state = get_state  # type: ignore[method-assign]
    return bot


def _storage_rows(layout: panel_layout.PanelLayout) -> list[panel_layout.Row]:
    section = layout.section("storage")
    assert section is not None
    return list(section.rows)


def _water_row(layout: panel_layout.PanelLayout) -> panel_layout.Row:
    bars = [r for r in _storage_rows(layout) if r.kind is RowKind.BAR]
    return bars[[e.name for e in ELEMENT_LIST].index("WATER")]


def _colors(surface, rect: panel_layout.Rect) -> set[tuple[int, int, int]]:
    return {
        surface.get_at((x, y))[:3]
        for y in range(rect.y, rect.bottom)
        for x in range(rect.x, rect.right)
    }


def _assert_label_painted(surface, renderer: Renderer, row: panel_layout.Rect, label: str):
    """The row's right-hand label must be exactly `label`, on the pixels.

    Rendered in `DIM_WHITE` because that is what `_draw_compact_bar_row` uses for every
    label — the deficit colour marks the swatch and the bar, not the text."""
    import pygame

    geom = panel_layout.bar_row(row, "WATER", label, char_w=renderer._char_w_sm)
    assert geom.label == label, f"the label was truncated to {geom.label!r}"

    expected = pygame.Surface((geom.label_right - geom.label_x, row.h))
    expected.fill(PANEL_COLOR)
    expected.blit(renderer._font_sm.render(label, True, DIM_WHITE), (0, 0))
    actual = surface.subsurface(
        pygame.Rect(geom.label_x, row.y, expected.get_width(), row.h)
    )
    assert pygame.image.tostring(actual, "RGB") == pygame.image.tostring(expected, "RGB"), (
        f"the Water row does not read {label!r}"
    )


@pytest.mark.parametrize("workshop", [True, False])
def test_the_deficit_trigger_is_visible_in_the_storage_section(surface, workshop) -> None:
    """The trigger firing has to be watchable, not only readable from a CSV.

    It is shown inside Storage rather than in a row of its own because the panel is at
    its vertical ceiling — see deferred-work.md — and because a Water deficit is a fact
    about Water storage, where a reader already looks. Costing no rows is also why
    *both* inspectors get it: `python main.py` is the mode a user opens first, and a bot
    starving there should not be the one case the panel stays silent about."""
    renderer = Renderer(surface, workshop=workshop)
    bot = _with_chi(_StubBot(2), active=True)
    layout = renderer._panel_layout(as_bot(bot))
    _draw(renderer, surface, bot, layout, workshop)

    heading = next(r for r in _storage_rows(layout) if r.kind is RowKind.HEADING)
    assert Renderer._DEFICIT_COLOR in _colors(surface, heading.rect), (
        "the Storage heading must call out the deficit"
    )
    assert Renderer._DEFICIT_COLOR in _colors(surface, _water_row(layout).rect), (
        "the Water row must be marked while the trigger is armed"
    )


@pytest.mark.parametrize("workshop", [True, False])
def test_the_water_row_reads_the_demand_paths_own_production(surface, workshop) -> None:
    """The label says what *this* trigger did — not what it spent, and not what the
    passive cycle did.

    All three numbers are on the same row's data and all three paint amber, so a colour
    assertion passes on any of them. This is the exact confusion the story exists to
    prevent: reporting the passive path's contribution under the deficit trigger would
    make "both ran once" and "one ran twice" indistinguishable on the panel."""
    renderer = Renderer(surface, workshop=workshop)
    bot = _with_chi(_StubBot(2), active=True)
    layout = renderer._panel_layout(as_bot(bot))
    _draw(renderer, surface, bot, layout, workshop)

    _assert_label_painted(
        surface, renderer, _water_row(layout).rect, f"<{_DEFICIT_LEVEL:.2f} +0.152"
    )


def test_the_deficit_label_is_a_pure_function_of_the_chi_block() -> None:
    """Pinned as a string too, so the three confusions are named rather than implied."""
    chi = {
        "deficit_active": True,
        "deficit_served": True,
        "deficit_level": _DEFICIT_LEVEL,
        "passive_metal_to_water": (_PASSIVE_SPENT, _PASSIVE_PRODUCED),
        "deficit_metal_to_water": (_DEFICIT_SPENT, _DEFICIT_PRODUCED),
    }
    label = Renderer._deficit_label(chi)

    assert label == "<0.16 +0.152"
    assert f"{_DEFICIT_SPENT:.3f}" not in label, "that is the Metal spent, not Water made"
    assert f"{_PASSIVE_PRODUCED:.3f}" not in label, "that is the passive path's figure"
    assert "0.00" not in label, "the held level must be the real one"


@pytest.mark.parametrize("workshop", [True, False])
def test_an_unserved_deficit_says_so_rather_than_reading_as_working(
    surface, workshop
) -> None:
    """A bot in deficit with no Metal left is armed and helpless.

    The panel must not read the same as armed-and-working: `+0.000` beside a level is
    easy to skim past as "the trigger is holding the line", when in fact nothing is
    moving and the legs are about to start degrading."""
    renderer = Renderer(surface, workshop=workshop)
    bot = _with_chi(_StubBot(2), active=True, served=False, produced=0.0)
    layout = renderer._panel_layout(as_bot(bot))
    _draw(renderer, surface, bot, layout, workshop)

    _assert_label_painted(
        surface, renderer, _water_row(layout).rect, f"<{_DEFICIT_LEVEL:.2f} no Metal"
    )


def test_no_deficit_colour_appears_when_the_trigger_is_quiet(surface) -> None:
    """The counterpart: an always-amber panel would be no signal at all."""
    renderer = Renderer(surface, workshop=True)
    bot = _with_chi(_StubBot(2), active=False)
    layout = renderer._panel_layout(as_bot(bot))
    _draw(renderer, surface, bot, layout, True)

    for row in _storage_rows(layout):
        assert Renderer._DEFICIT_COLOR not in _colors(surface, row.rect)


def test_a_quiet_water_row_still_reads_as_a_normal_storage_row(surface) -> None:
    """And the ordinary label is not disturbed by the deficit branch existing."""
    renderer = Renderer(surface, workshop=True)
    bot = _with_chi(_StubBot(2), active=False)
    layout = renderer._panel_layout(as_bot(bot))
    _draw(renderer, surface, bot, layout, True)

    # The stub holds 19.95 of a 20.0 pool — the plain `value/capacity` form.
    _assert_label_painted(surface, renderer, _water_row(layout).rect, "19.9/20")


def test_a_bot_state_without_a_chi_block_still_draws(surface) -> None:
    """The panel must not require the block: `_draw_organ_and_storage` is shared with
    the plain inspector and with any caller that predates Story 1.2."""
    renderer = Renderer(surface, workshop=True)
    bot = _StubBot(2)  # no chi block at all
    layout = renderer._panel_layout(as_bot(bot))
    _draw(renderer, surface, bot, layout, True)

    for row in _storage_rows(layout):
        if row.kind in INKED_KINDS:
            assert _painted(surface, row.rect)


# --- gauge vs tank, and visible movement ------------------------------------
#
# Both exist because a real session went looking for a leg's fuel in the Organs
# WATER row — a derived gauge pinned at 100 — while storage_WATER quietly drained
# from 9.9 to 8.9 one section below. Two rows, same name, opposite meanings.


def test_a_derived_organ_is_marked_and_a_stored_one_is_not():
    """`AD-5`: a derived organ is the mean integrity of its parts. Nothing can draw
    from it, so a reader must be able to tell it from a pool at a glance."""
    assert Renderer._organ_label(100.0, True) == "100.0=parts"
    assert Renderer._organ_label(93.4, False) == "93.4"


def test_the_storage_label_shows_the_last_tick_s_movement():
    """The level alone moves too slowly to read — two legs at cruise draw ~0.012/tick
    out of twenty — so a draining pool looks static."""
    assert Renderer._storage_label(9.9, 20, -0.026) == "9.9/20 -.03"
    assert Renderer._storage_label(10.0, 40, -1.25) == "10.0/40 -1.25"


def test_a_still_pool_reads_as_still():
    """Suppressed below what two decimals can show, so nothing ever renders `+.00` —
    which would read as "nothing moved" while claiming movement."""
    assert Renderer._storage_label(9.9, 20, 0.0) == "9.9/20"
    assert Renderer._storage_label(9.9, 20, 0.0006) == "9.9/20"


def test_stripping_the_delta_s_leading_zero_never_touches_the_level():
    """Doing this with a blanket `.replace("0.", ".")` rewrote the level too, turning a
    pool of 20.0 into 2.0. A narrower label is not worth misreporting the number."""
    assert Renderer._storage_label(20.0, 20, 2.0) == "20.0/20 +2.00"
    assert Renderer._storage_label(0.0, 20, -0.5) == "0.0/20 -.50"
    assert Renderer._storage_label(20.0, 20, 0.008) == "20.0/20 +.01"


def test_the_organism_reports_what_the_whole_tick_did_to_each_pool(default_config):
    """`AD-16`: the organism accumulates its own deltas and observers read them. A panel
    that differenced successive frames would report frame-to-frame change, which is not
    the same thing when the renderer and the simulation run at different rates."""
    from common import ELEMENT_LIST, ElementType
    from world import World

    world = World(default_config, seed=20260817)
    world.initialize()
    bot = world.spawn_taobot(x=40.0, y=30.0)
    for element in ELEMENT_LIST:
        bot.storage[element] = bot.storage_capacity[element] * 0.5

    assert bot.get_state()["storage_delta"][ElementType.WATER.name] == 0.0  # before any tick

    before = dict(bot.storage)
    world.tick()
    delta = bot.get_state()["storage_delta"]

    for element in ELEMENT_LIST:
        assert delta[element.name] == pytest.approx(bot.storage[element] - before[element])
    assert delta[ElementType.WATER.name] < 0.0, "a thrusting bot must be spending Water"
