from __future__ import annotations

import collections
import contextlib
import math
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pygame

import panel_layout
from common import (
    BACKGROUND_COLOR,
    DIM_WHITE,
    ELEMENT_COLOR,
    ELEMENT_LIST,
    ELEMENT_RESOURCE_NAME,
    GRID_COLOR,
    PANEL_COLOR,
    PANEL_W,
    TAOBOT_COLOR,
    TAOBOT_FLEE_COLOR,
    WHITE,
    WINDOW_H,
    WINDOW_W,
    WORLD_HEIGHT,
    WORLD_WIDTH,
    ElementType,
)
from math_utils import world_to_screen

if TYPE_CHECKING:
    from entities import Hazard, Resource
    from taobot_simple import TaobotSimple
    from world import World

_ANIM_TICKS = 8      # world ticks per animation frame step
# Every panel measurement — gutter, graph height, the band below it, the pause
# button and the slider — lives in panel_layout, which is the single owner of the
# panel's arithmetic. The renderer holds none of its own.
_FPS_MIN = 5
_FPS_MAX = 120
_ORGAN_MAX = 100.0   # organ values are 0-100; the graph's y axis is this range


class LayoutMismatch(RuntimeError):
    """The renderer asked for a row the layout did not lay out.

    Raised rather than skipped: a cursor that quietly returns ``None`` turns a
    layout/renderer disagreement into content that silently disappears, which is
    the failure mode this whole story exists to remove."""


class _RowCursor:
    """Walks a section's pre-computed row rects in order.

    The caller names the kind it is about to draw, so a layout that says "bar"
    where the renderer draws text is a loud error. Running out of rows is only
    tolerated when the layout has already reported that it clipped content (and
    the panel therefore says so on screen) or when the section is absent
    entirely; otherwise it is a bug and raises."""

    def __init__(self, section: "panel_layout.Section | None", clipped: bool) -> None:
        self._section = section
        self._rows: list[panel_layout.Row] = list(section.rows) if section else []
        self._name = section.name if section else "<absent>"
        self._clipped = clipped
        self._i = 0

    def next(self, kind: panel_layout.RowKind) -> "panel_layout.Rect | None":
        if self._i >= len(self._rows):
            if self._clipped or self._section is None:
                return None
            raise LayoutMismatch(
                f"section {self._name!r} ran out of rows while drawing {kind.value}"
            )
        row = self._rows[self._i]
        self._i += 1
        if row.kind is not kind:
            raise LayoutMismatch(
                f"section {self._name!r} row {self._i - 1} is {row.kind.value}, "
                f"renderer drew {kind.value}"
            )
        return row.rect


class Renderer:
    """Stateless read-only renderer for the pygame window.

    The world viewport (left side) and inspector panel (right side) are drawn
    each frame. The renderer owns only display state: grid toggle and the rolling
    health history deque. It never writes to the world or taobots.

    Panel layout (top → bottom):
      Inspector    — selected taobot details, or "Click a taobot" hint
      Organ graph  — 200-tick rolling mean/min/max population Earth organ
      Pause button — click to pause/resume
      Speed slider — draggable FPS control (5–120); also responds to Up/Down keys

    None of those four compute their own position. `panel_layout` owns the whole
    panel's arithmetic and hands back rects, which is why they cannot overlap;
    the renderer converts those to `pygame.Rect` as it draws.
    """

    def __init__(
        self,
        screen: pygame.Surface,
        world_w: int = WORLD_WIDTH,
        world_h: int = WORLD_HEIGHT,
        window_w: int = WINDOW_W,
        window_h: int = WINDOW_H,
        panel_w: int = PANEL_W,
        workshop: bool = False,
    ) -> None:
        """Set up fonts, scale factors, and panel geometry."""
        self._screen = screen
        self._world_w = world_w
        self._world_h = world_h
        self._window_w = window_w
        self._window_h = window_h
        self._panel_w = panel_w
        self._scale_x = window_w / world_w
        self._scale_y = window_h / world_h
        self._show_grid = False
        self._workshop = workshop

        self._font_sm = pygame.font.SysFont("monospace", 13)
        self._font_md = pygame.font.SysFont("monospace", 15)
        self._font_bold = pygame.font.SysFont("monospace", 15, bold=True)
        # A 15px bold heading in a 14px row overlaps the row below it: rects that
        # do not overlap do not imply glyphs that do not overlap. The tight rungs
        # of the ladder get a 13px bold face instead.
        self._font_bold_sm = pygame.font.SysFont("monospace", 13, bold=True)

        # Measured, not assumed: the layout fits text by character count, so it
        # needs each face's real advance rather than panel_layout's default.
        self._char_w_sm = max(1, self._font_sm.size("M")[0])
        self._char_w_bold = max(1, self._font_bold.size("M")[0])
        self._char_w_bold_sm = max(1, self._font_bold_sm.size("M")[0])

        self._panel_rect = pygame.Rect(window_w, 0, panel_w, window_h)

        # Panel chrome (graph, pause button, slider) is independent of which bot
        # is selected, so one layout computed here serves the hit-test properties
        # that main.py calls outside a frame.
        self._chrome = panel_layout.compute(window_w, panel_w, window_h, 0)

        # Rolling Earth-organ history: (mean, min, max) per tick
        self._organ_history: collections.deque[tuple[float, float, float]] = (
            collections.deque(maxlen=200)
        )

    def toggle_grid(self) -> None:
        """Toggle the spatial-hash bucket grid overlay on/off."""
        self._show_grid = not self._show_grid

    def push_organ_sample(self, mean: float, mn: float, mx: float) -> None:
        """Append one tick's population Earth organ stats to the rolling graph buffer.

        Values are clamped to the graph's 0–100 axis at the door. An out-of-range
        sample would otherwise map to a y outside the graph rect and paint over
        the caption and the inspector above it — the same defect as the graph's
        old independent position, arriving from the other direction."""
        def bounded(v: float) -> float:
            if v != v:                      # NaN: no sensible place on the axis
                return 0.0
            return max(0.0, min(_ORGAN_MAX, v))

        self._organ_history.append((bounded(mean), bounded(mn), bounded(mx)))

    @property
    def pause_button_rect(self) -> pygame.Rect:
        """The clickable rect of the pause/resume button, in screen coordinates."""
        return pygame.Rect(*self._chrome.pause_button.as_tuple())

    @property
    def speed_slider_rect(self) -> pygame.Rect:
        """The clickable track rect of the speed slider, in screen coordinates.

        main.py uses this to hit-test mouse events against the slider."""
        return pygame.Rect(*self._chrome.slider_hit.as_tuple())

    def fps_from_mouse_x(self, mx: int) -> int:
        """Convert a mouse x position to a target FPS value (clamped to _FPS_MIN.._FPS_MAX)."""
        track = self._chrome.slider_track
        t = max(0.0, min(1.0, (mx - track.x) / track.w))
        return max(_FPS_MIN, min(_FPS_MAX, int(_FPS_MIN + t * (_FPS_MAX - _FPS_MIN))))

    def render(
        self,
        world: "World",
        selected_id: int | None = None,
        fps: float = 0.0,
        target_fps: int = 60,
        paused: bool = False,
    ) -> None:
        """Draw a complete frame: world viewport, paused overlay (if paused), and panel."""
        self._draw_background()
        if self._show_grid:
            self._draw_grid()
        self._draw_resources(world.resources, world.dead_resources, world.tick_count)
        self._draw_hazards(world.hazards, world.tick_count)
        self._draw_taobots(world.taobots, selected_id)
        if paused:
            self._draw_paused_overlay()
        selected_taobot = world._taobots.get(selected_id) if selected_id is not None else None
        # One layout owner: the inspector and the graph are both placed by this
        # single call, so they cannot disagree about where the boundary is.
        layout = self._panel_layout(selected_taobot)
        if self._workshop:
            self._draw_workshop_inspector(selected_taobot, world.tick_count, layout)
        else:
            self._draw_inspector(selected_taobot, layout)
        self._draw_organ_graph(layout)
        self._draw_pause_button(paused)
        self._draw_speed_slider(target_fps, fps)
        self._draw_hud(world.tick_count, len(world.taobots), fps)

    # --- Panel layout ---

    def _panel_layout(self, taobot: "TaobotSimple | None") -> panel_layout.PanelLayout:
        """Compute this frame's panel layout from the selected bot's inventory."""
        legs = len(taobot.legs) if taobot is not None else 0
        return panel_layout.compute(
            self._window_w,
            self._panel_w,
            self._window_h,
            legs,
            variant=(
                panel_layout.Variant.WORKSHOP if self._workshop else panel_layout.Variant.PLAIN
            ),
            has_bot=taobot is not None,
            organ_rows=len(ELEMENT_LIST),
            storage_rows=len(ELEMENT_LIST),
        )

    def _heading_font(self, line_h: int) -> tuple[pygame.font.Font, int]:
        """Pick a bold face whose glyphs fit inside a row of `line_h` pixels."""
        if line_h >= self._font_bold.get_height() + 1:
            return self._font_bold, self._char_w_bold
        return self._font_bold_sm, self._char_w_bold_sm

    def _blit_row_text(
        self,
        rect: "panel_layout.Rect | None",
        msg: str,
        color: tuple = DIM_WHITE,
        bold: bool = False,
    ) -> None:
        """Draw one line of text inside its allotted row, truncating to the row width."""
        if rect is None:
            return
        if bold:
            font, char_w = self._heading_font(rect.h)
        else:
            font, char_w = self._font_sm, self._char_w_sm
        text = panel_layout.clip_text(msg, rect.w, char_w)
        if not text:
            return
        self._screen.blit(font.render(text, True, color), (rect.x, rect.y))

    @contextlib.contextmanager
    def _clip_to(self, rect: "panel_layout.Rect") -> Iterator[None]:
        """Hard-clip all drawing to `rect` for the duration of the block.

        The layout already guarantees content fits; this is the backstop that
        makes "nothing is drawn outside the rect it was allotted" true even if a
        caller miscounts."""
        previous = self._screen.get_clip()
        self._screen.set_clip(pygame.Rect(*rect.as_tuple()))
        try:
            yield
        finally:
            self._screen.set_clip(previous)

    def _blit_separator(self, rect: "panel_layout.Rect | None") -> None:
        """Draw a section rule across the width of its allotted row."""
        if rect is None:
            return
        pygame.draw.line(
            self._screen, (70, 70, 70), (rect.x, rect.y), (rect.right - 1, rect.y)
        )

    # --- Layers ---

    def _draw_background(self) -> None:
        """Fill the world viewport and panel with their background colors."""
        self._screen.fill(BACKGROUND_COLOR, pygame.Rect(0, 0, self._window_w, self._window_h))
        pygame.draw.rect(self._screen, PANEL_COLOR, self._panel_rect)

    def _draw_grid(self) -> None:
        """Draw the spatial-hash bucket grid lines over the world viewport."""
        bucket_px_x = int(8 * self._scale_x)
        bucket_px_y = int(8 * self._scale_y)
        for x in range(0, self._window_w, bucket_px_x):
            pygame.draw.line(self._screen, GRID_COLOR, (x, 0), (x, self._window_h))
        for y in range(0, self._window_h, bucket_px_y):
            pygame.draw.line(self._screen, GRID_COLOR, (0, y), (self._window_w, y))

    def _draw_resources(
        self,
        resources: list["Resource"],
        dead_resources: list["Resource"],
        tick_count: int,
    ) -> None:
        """Draw live resources with per-element animation and dead ones as dim outlines."""
        frame = tick_count // _ANIM_TICKS

        for r in dead_resources:
            px, py = world_to_screen(r.x, r.y, self._scale_x, self._scale_y)
            color = ELEMENT_COLOR[r.element_type]
            dim = tuple(max(0, int(c * 0.25)) for c in color)
            pygame.draw.circle(self._screen, dim, (px, py), 4, 1)

        for r in resources:
            px, py = world_to_screen(r.x, r.y, self._scale_x, self._scale_y)
            color = ELEMENT_COLOR[r.element_type]
            brightness = max(0.3, r.amount / r.max_amount)
            c = tuple(min(255, int(ch * brightness)) for ch in color)
            self._draw_resource_anim(px, py, r.element_type, c, frame)

    def _draw_resource_anim(
        self,
        px: int,
        py: int,
        element_type: ElementType,
        color: tuple,
        frame: int,
    ) -> None:
        s = self._screen
        e = element_type
        if e == ElementType.FIRE:
            # Flickering flame: base + alternating tip size
            pygame.draw.circle(s, color, (px, py), 4)
            tip_r, tip_dy = (2, -6) if frame % 2 == 0 else (1, -5)
            pygame.draw.circle(s, color, (px, py + tip_dy), tip_r)
        elif e == ElementType.WATER:
            # Ripple: filled shrinks while outer ring expands
            if frame % 2 == 0:
                pygame.draw.circle(s, color, (px, py), 4)
            else:
                pygame.draw.circle(s, color, (px, py), 3)
                pygame.draw.circle(s, color, (px, py), 6, 1)
        elif e == ElementType.WOOD:
            # Flower: centre disc ± 4 petals on alternating frames
            pygame.draw.circle(s, color, (px, py), 3)
            if frame % 2 == 1:
                for dx, dy in ((0, -5), (5, 0), (0, 5), (-5, 0)):
                    pygame.draw.circle(s, color, (px + dx, py + dy), 2)
        elif e == ElementType.EARTH:
            # Pulse: radius alternates 4 ↔ 5
            pygame.draw.circle(s, color, (px, py), 5 if frame % 2 == 0 else 4)
        elif e == ElementType.METAL:
            # Glint: plain circle with a brief white flash every 3rd frame
            pygame.draw.circle(s, color, (px, py), 4)
            if frame % 3 == 1:
                pygame.draw.circle(s, (255, 255, 255), (px + 3, py - 3), 1)

    def _draw_hazards(self, hazards: list["Hazard"], tick_count: int) -> None:
        """Draw hazards with per-element animation."""
        frame = tick_count // _ANIM_TICKS
        for h in hazards:
            px, py = world_to_screen(h.x, h.y, self._scale_x, self._scale_y)
            color = ELEMENT_COLOR[h.element_type]
            self._draw_hazard_anim(px, py, h.element_type, color, frame)

    @staticmethod
    def _diamond(px: int, py: int, sz: int) -> list[tuple[int, int]]:
        return [(px, py - sz), (px + sz, py), (px, py + sz), (px - sz, py)]

    def _draw_hazard_anim(
        self,
        px: int,
        py: int,
        element_type: ElementType,
        color: tuple,
        frame: int,
    ) -> None:
        s = self._screen
        e = element_type
        if e == ElementType.FIRE:
            # Breathing pyre: diamond expands on alternate frames
            sz = 7 if frame % 2 == 0 else 5
            pygame.draw.polygon(s, color, self._diamond(px, py, sz))
        elif e == ElementType.WATER:
            # Sinkhole: concentric rings cycling outward (3-frame loop)
            phase = frame % 3
            for i, r in enumerate((4, 7)):
                ring_r = r + phase
                pygame.draw.circle(s, color, (px, py), ring_r, 1)
        elif e == ElementType.WOOD:
            # Thornwall: diamond with spikes extending on alternate frames
            sz = 5
            pygame.draw.polygon(s, color, self._diamond(px, py, sz))
            if frame % 2 == 1:
                sp = 3
                pygame.draw.line(s, color, (px, py - sz), (px, py - sz - sp))
                pygame.draw.line(s, color, (px + sz, py), (px + sz + sp, py))
                pygame.draw.line(s, color, (px, py + sz), (px, py + sz + sp))
                pygame.draw.line(s, color, (px - sz, py), (px - sz - sp, py))
        elif e == ElementType.EARTH:
            # Mudpit: filled circle breathing 5 ↔ 6
            pygame.draw.circle(s, color, (px, py), 6 if frame % 2 == 0 else 5)
        elif e == ElementType.METAL:
            # Shardfield: diamond ↔ square orientation
            if frame % 2 == 0:
                pygame.draw.polygon(s, color, self._diamond(px, py, 5))
            else:
                sz = 4
                pygame.draw.polygon(s, color, [(px - sz, py - sz), (px + sz, py - sz),
                                               (px + sz, py + sz), (px - sz, py + sz)])

    def _draw_taobots(self, taobots: list["TaobotSimple"], selected_id: int | None) -> None:
        """Draw each taobot as a circle with a heading line, Earth organ bar, and optional ring."""
        for t in taobots:
            px, py = world_to_screen(t.x, t.y, self._scale_x, self._scale_y)
            color = TAOBOT_FLEE_COLOR if t.behavior_state == "fleeing" else TAOBOT_COLOR
            pygame.draw.circle(self._screen, color, (px, py), 6)

            # Legs — small dots at polar offset (heading + theta), dimmed by structural integrity
            _LEG_OFFSET_PX = 9  # pixels from body centre to leg dot
            _WATER_COLOR = ELEMENT_COLOR[ElementType.WATER]
            for leg in getattr(t, "legs", []):
                direction = t.heading + leg.theta
                lx = px + int(math.cos(direction) * _LEG_OFFSET_PX)
                ly = py + int(math.sin(direction) * _LEG_OFFSET_PX)
                brightness = leg.structural_integrity
                leg_color = (
                    int(_WATER_COLOR[0] * brightness),
                    int(_WATER_COLOR[1] * brightness),
                    int(_WATER_COLOR[2] * brightness),
                )
                pygame.draw.circle(self._screen, leg_color, (lx, ly), 2)

            # Heading line
            hx = px + int(math.cos(t.heading) * 10)
            hy = py + int(math.sin(t.heading) * 10)
            pygame.draw.line(self._screen, WHITE, (px, py), (hx, hy), 1)

            # Earth organ bar (structural integrity / death condition)
            earth_frac = max(0.0, t.organ(ElementType.EARTH) / 100.0)
            bar_w = 12
            bar_x = px - bar_w // 2
            bar_y = py - 12
            red = (200, 40, 40)
            green = (40, 200, 40)
            bar_color = (
                int(red[0] + (green[0] - red[0]) * earth_frac),
                int(red[1] + (green[1] - red[1]) * earth_frac),
                int(red[2] + (green[2] - red[2]) * earth_frac),
            )
            pygame.draw.rect(self._screen, (60, 60, 60), pygame.Rect(bar_x, bar_y, bar_w, 2))
            filled_w = int(bar_w * earth_frac)
            pygame.draw.rect(self._screen, bar_color, pygame.Rect(bar_x, bar_y, filled_w, 2))

            # Selection ring
            if t.entity_id == selected_id:
                pygame.draw.circle(self._screen, WHITE, (px, py), 9, 1)

    def _draw_paused_overlay(self) -> None:
        """Draw a semi-transparent dark overlay and centred PAUSED text over the viewport."""
        overlay = pygame.Surface((self._window_w, self._window_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        self._screen.blit(overlay, (0, 0))
        surf = self._font_bold.render("PAUSED", True, WHITE)
        cx = self._window_w // 2 - surf.get_width() // 2
        cy = self._window_h // 2 - surf.get_height() // 2
        self._screen.blit(surf, (cx, cy))

    def _draw_inspector(
        self, taobot: "TaobotSimple | None", layout: panel_layout.PanelLayout
    ) -> None:
        """Draw the inspector panel for the selected taobot, or a placeholder if none selected.

        This is the non-workshop panel — the one `python main.py` opens. It draws
        into the same layout-allotted rows as the workshop panel and rides the
        same condensation ladder, which is what lets it fit at 800×600 instead of
        permanently announcing that it is full. It carries two sections the
        workshop panel does not: Params and Affinities."""
        with self._clip_to(layout.inspector):
            header = _RowCursor(layout.section("header"), layout.content_clipped)
            self._blit_row_text(
                header.next(panel_layout.RowKind.HEADING), "Inspector", WHITE, bold=True
            )
            self._blit_separator(header.next(panel_layout.RowKind.SEPARATOR))

            if taobot is None:
                self._blit_row_text(
                    _RowCursor(layout.section("message"), layout.content_clipped).next(
                        panel_layout.RowKind.TEXT
                    ),
                    "Click a taobot",
                )
            else:
                state = taobot.get_state()
                self._draw_bot_info(state, taobot, layout, title=f"Taobot #{state['entity_id']}")
                self._draw_organ_and_storage(state, layout)
                self._draw_legs(state, layout)
                self._draw_params_and_affinity(state, layout)
            self._draw_notice(layout)

    def _draw_params_and_affinity(
        self, state: dict, layout: panel_layout.PanelLayout
    ) -> None:
        """Draw the plain panel's genome-trait blocks: speed/sense, then affinities."""
        params = _RowCursor(layout.section("params"), layout.content_clipped)
        self._blit_separator(params.next(panel_layout.RowKind.SEPARATOR))
        if layout.params_heading:
            self._blit_row_text(params.next(panel_layout.RowKind.HEADING), "Params", bold=True)
        self._blit_row_text(
            params.next(panel_layout.RowKind.TEXT),
            f"Speed {state['speed']:.1f}  Sense {state['sensing_range']:.1f}",
        )

        aff = _RowCursor(layout.section("affinity"), layout.content_clipped)
        self._blit_separator(aff.next(panel_layout.RowKind.SEPARATOR))
        self._blit_row_text(aff.next(panel_layout.RowKind.HEADING), "Affinities", bold=True)
        if layout.affinity_rows >= len(ELEMENT_LIST):
            for e in ELEMENT_LIST:
                value = state["affinity"][e.name]
                self._draw_compact_bar_row(
                    aff.next(panel_layout.RowKind.BAR),
                    ELEMENT_COLOR[e],
                    e.name,
                    value,
                    1.0,
                    f"{value:.3f}",
                )
        else:
            # Condensed: five bar rows folded into two text rows. Affinities are
            # static genome traits, so they are the least urgent thing on the panel
            # and the last block the ladder touches — but every value is still here.
            parts = [
                f"{ELEMENT_RESOURCE_NAME[e][:2]}{state['affinity'][e.name]:.2f}"
                for e in ELEMENT_LIST
            ]
            half = (len(parts) + 1) // 2
            for chunk in (parts[:half], parts[half:]):
                self._blit_row_text(aff.next(panel_layout.RowKind.TEXT), " ".join(chunk))

    def _draw_notice(self, layout: panel_layout.PanelLayout) -> None:
        """Say what the layout had to drop. Nothing is ever shortened in silence."""
        section = layout.section("notice")
        if section is None:
            return
        note = layout.truncation_note or "panel full - rows hidden"
        self._blit_row_text(
            _RowCursor(section, layout.content_clipped).next(panel_layout.RowKind.NOTICE),
            note,
            (230, 180, 60),
        )

    def _draw_compact_bar_row(
        self,
        row: "panel_layout.Rect | None",
        color: tuple,
        name: str,
        value: float,
        max_val: float,
        right_label: str,
    ) -> None:
        """Draw [swatch] NAME [bar] right_label inside `row`, all on one line.

        The geometry — including the right-aligned label and the bar width that
        yields to it — comes from `panel_layout.bar_row`, so the label can never
        run past the panel edge the way a fixed offset did."""
        if row is None:
            return
        g = panel_layout.bar_row(row, name, right_label, char_w=self._char_w_sm)
        s = self._screen
        pygame.draw.rect(s, color, pygame.Rect(*g.swatch.as_tuple()))
        s.blit(self._font_sm.render(g.name, True, DIM_WHITE), (g.name_x, row.y))
        frac = max(0.0, min(1.0, value / max_val)) if max_val > 0 else 0.0
        fill = tuple(min(255, int(c * (0.35 + 0.65 * frac))) for c in color)
        pygame.draw.rect(s, (50, 50, 50), pygame.Rect(*g.bar.as_tuple()))
        pygame.draw.rect(
            s, fill, pygame.Rect(g.bar.x, g.bar.y, int(g.bar.w * frac), g.bar.h)
        )
        s.blit(self._font_sm.render(g.label, True, DIM_WHITE), (g.label_x, row.y))

    def _draw_workshop_inspector(
        self,
        taobot: "TaobotSimple | None",
        tick_count: int,
        layout: panel_layout.PanelLayout,
    ) -> None:
        """Full-state inspector for Lao Tzu's Workshop — organs, storage, motion, behavior.

        Every row is drawn into a rect the layout allotted it, so the panel can
        neither run into the organ graph below nor past the panel edge to the
        right. Where the content will not fit, the layout has already condensed
        it; what it had to drop is stated on screen."""
        with self._clip_to(layout.inspector):
            self._draw_workshop_inspector_body(taobot, tick_count, layout)

    def _draw_workshop_inspector_body(
        self,
        taobot: "TaobotSimple | None",
        tick_count: int,
        layout: panel_layout.PanelLayout,
    ) -> None:
        header = _RowCursor(layout.section("header"), layout.content_clipped)
        self._blit_row_text(
            header.next(panel_layout.RowKind.HEADING),
            "Lao Tzu's Workshop",
            (210, 180, 30),
            bold=True,
        )
        # Wording sized to the row: "Tick: n   [N]=step  [R]=slow" was 30 characters
        # against a 28-character panel and lost its last two to the truncation marker.
        self._blit_row_text(
            header.next(panel_layout.RowKind.TEXT), f"Tick {tick_count}  [N]step [R]slow"
        )
        self._blit_separator(header.next(panel_layout.RowKind.SEPARATOR))

        if taobot is None:
            self._blit_row_text(
                _RowCursor(layout.section("message"), layout.content_clipped).next(
                    panel_layout.RowKind.TEXT
                ),
                "No bot in world",
            )
        else:
            state = taobot.get_state()
            self._draw_bot_info(
                state, taobot, layout, title=f"Bot #{state['entity_id']}  ({taobot.archetype})"
            )
            self._draw_organ_and_storage(state, layout)
            self._draw_legs(state, layout)
        self._draw_notice(layout)

    # --- Sections both inspectors share ---

    def _draw_bot_info(
        self,
        state: dict,
        taobot: "TaobotSimple",
        layout: panel_layout.PanelLayout,
        title: str,
    ) -> None:
        hdg_deg = math.degrees(state["heading"]) % 360
        state_colors = {
            "seeking": (0, 220, 80), "collecting": (0, 255, 60),
            "fleeing": (220, 220, 0), "searching": (100, 150, 200),
        }
        state_color = state_colors.get(state["behavior_state"], DIM_WHITE)

        info = _RowCursor(layout.section("bot_info"), layout.content_clipped)
        text = panel_layout.RowKind.TEXT
        self._blit_row_text(info.next(text), title, WHITE, bold=True)
        if layout.bot_info_lines >= 5:
            self._blit_row_text(info.next(text), f"State:  {state['behavior_state']}", state_color)
            self._blit_row_text(
                info.next(text), f"Age: {state['age_ticks']}   Fit: {state['fitness_score']:.4f}"
            )
            self._blit_row_text(
                info.next(text), f"Pos: ({state['x']:.1f}, {state['y']:.1f})   Hdg: {hdg_deg:.0f}°"
            )
            self._blit_row_text(
                info.next(text),
                f"Dist: {state['distance_moved']:.1f}   Dmg: {state['damage_taken_total']:.1f}",
            )
        else:
            # Condensed: the same five rows' facts folded into four. Nothing the
            # reader could see before has gone away, only the whitespace.
            self._blit_row_text(info.next(text), state["behavior_state"], state_color)
            self._blit_row_text(
                info.next(text), f"Age {state['age_ticks']}  Fit {state['fitness_score']:.4f}"
            )
            self._blit_row_text(
                info.next(text),
                f"({state['x']:.0f},{state['y']:.0f}) {hdg_deg:.0f}° "
                f"D{state['distance_moved']:.0f} Dmg{state['damage_taken_total']:.0f}",
            )

    # Warning amber for a Water pool the demand path is holding up. Distinct from the
    # element colours so "this element is in deficit" never reads as "this element".
    _DEFICIT_COLOR = (240, 170, 40)

    # Healing green for Earth being spent on structural repair, and for a leg gaining
    # integrity. Distinct from both the element colours and the deficit amber: amber
    # means "a pool is in trouble", green means "essence is crossing into structure".
    _REPAIR_COLOR = (80, 220, 120)

    def _draw_organ_and_storage(
        self, state: dict, layout: panel_layout.PanelLayout
    ) -> None:
        organs = _RowCursor(layout.section("organs"), layout.content_clipped)
        self._blit_separator(organs.next(panel_layout.RowKind.SEPARATOR))
        # "aggregate" because the Water organ here is the mean of the leg integrities
        # listed below — an aggregate and its parts, not the same number twice.
        self._blit_row_text(
            organs.next(panel_layout.RowKind.HEADING), "Organs (aggregate)", bold=True
        )
        derived = set(state.get("derived_organs", ()))
        for e in ELEMENT_LIST:
            val = state["organs"][e.name]
            self._draw_compact_bar_row(
                organs.next(panel_layout.RowKind.BAR),
                ELEMENT_COLOR[e], e.name, val, 100.0,
                self._organ_label(val, e.name in derived),
            )

        # The Water-deficit trigger is shown inside the Storage section rather than in a
        # row of its own: the panel is already at its vertical ceiling (see
        # deferred-work.md), and the deficit *is* a fact about Water storage — the place
        # a reader already looks. Nothing new is allotted, so no leg slot is spent, which
        # is also why both inspectors show it rather than only the workshop one.
        chi = state.get("chi", {})
        deficit = bool(chi.get("deficit_active"))

        storage = _RowCursor(layout.section("storage"), layout.content_clipped)
        self._blit_separator(storage.next(panel_layout.RowKind.SEPARATOR))
        self._blit_row_text(
            storage.next(panel_layout.RowKind.HEADING),
            "Storage  H2O DEFICIT" if deficit else "Storage",
            self._DEFICIT_COLOR if deficit else DIM_WHITE,
            bold=True,
        )
        # Structural repair rides the Earth storage row for the same reason the Water
        # deficit rides the Water row: the panel is at its vertical ceiling, the
        # condensation ladder is what fits new content rather than new rows, and the
        # Earth *is* what repair spends — the place a reader already looks. Nothing new
        # is allotted, so no leg slot is spent and repair stays visible at every rung
        # of the ladder, including the one that folds each leg onto a single line.
        repair = state.get("repair", {})
        repairing = float(repair.get("earth_spent", 0.0)) > 0.0

        deltas = state.get("storage_delta", {})
        for e in ELEMENT_LIST:
            val = state["storage"][e.name]
            cap = state["storage_capacity"][e.name]
            color = ELEMENT_COLOR[e]
            label = self._storage_label(val, cap, deltas.get(e.name, 0.0))
            if deficit and e is ElementType.WATER:
                color = self._DEFICIT_COLOR
                label = self._deficit_label(chi)
            elif e is ElementType.EARTH:
                label = self._earth_label(val, cap, repair)
                if repairing:
                    color = self._REPAIR_COLOR
            self._draw_compact_bar_row(
                storage.next(panel_layout.RowKind.BAR), color, e.name, val, cap, label,
            )

    @staticmethod
    def _organ_label(value: float, is_derived: bool) -> str:
        """The right-hand label for an organ row, marking a derived organ as such.

        A derived organ is a **gauge, not a tank** (`AD-5`): it is the mean integrity of
        that element's parts, nothing can draw from it, and it does not fall when the
        parts consume their fuel. A reader who takes it for a reservoir looks in the
        wrong row for a part's supply — which is exactly what happened when the Water
        organ sat at 100 while `storage_WATER` quietly drained from 9.9 to 8.9.

        The stored organs get a bare number, so the marked ones read as the exception.
        Pure function so it can be asserted as a string, like `_deficit_label`."""
        return f"{value:.1f}=parts" if is_derived else f"{value:.1f}"

    @staticmethod
    def _storage_label(value: float, capacity: float, delta: float) -> str:
        """The right-hand label for a storage row: the level, and the last tick's change.

        The level alone moves too slowly to read. Two legs at cruise draw about
        0.012/tick out of a pool of twenty, so a bar barely stirs and the digits change
        every few seconds — a pool visibly draining looks static, and the flow has to be
        inferred rather than seen. The delta is the *netted* movement over the whole
        tick: collection, leg draw, organ upkeep, repair and both conversion paths.

        Rendered without a leading zero (`-.03`) to stay narrow, and suppressed entirely
        when nothing moved, so a still pool is visibly still rather than reading `+.00`."""
        level = f"{value:.1f}/{capacity:.0f}"
        # Suppressed below what two decimals can show, rather than below some smaller
        # epsilon: a delta of 0.0006 renders as "+.00", which reads as "nothing moved"
        # while claiming otherwise. Anything displayed is movement the reader can see.
        if abs(delta) < 0.005:
            return level
        moved = f"{delta:+.2f}"
        # Drop the leading zero on the *delta only* — "+0.03" -> "+.03". Doing this by
        # replacing "0." across the whole label rewrote the level too, turning a pool of
        # 20.0 into 2.0: a narrower label is not worth misreporting the number it labels.
        if moved[1] == "0" and moved[2:3] == ".":
            moved = moved[0] + moved[2:]
        return f"{level} {moved}"

    @staticmethod
    def _deficit_label(chi: dict) -> str:
        """The Water row's right-hand label while the trigger is armed.

        Says the level Water is being held to, and then what is actually happening:
        the Water the *demand* path produced this tick, or that there is no Metal to
        produce it from. Armed-but-unserved has to be distinguishable from armed-and-
        working — a panel that reads the same either way tells a reader the trigger is
        holding the line while a bot starves next to an empty Metal pool.

        The figure is the demand path's `produced`, not its `spent` and not the passive
        path's: what a reader is watching for is the Water this trigger made, and the
        three differ. Pure function so it can be asserted as a string."""
        level = chi["deficit_level"]
        if not chi.get("deficit_served"):
            return f"<{level:.2f} no Metal"
        return f"<{level:.2f} +{chi['deficit_metal_to_water'][1]:.3f}"

    @staticmethod
    def _earth_label(value: float, capacity: float, repair: dict) -> str:
        """The Earth storage row's right-hand label.

        Three states a reader has to be able to tell apart, because they look
        identical in the bar alone:

        - repair spent Earth this tick     -> the amount, as a debit
        - a part is damaged and Earth is at or under the floor -> `FLOOR`, which is
          the bot correctly refusing to heal itself to death, not a broken repair path
        - nothing to repair                -> the plain `value/capacity`

        The debit figure is what actually left storage, not what the parts asked for:
        under a partial grant the two differ, and the number beside a falling bar has
        to be the one the bar is falling by. Pure function so it can be asserted as a
        string, exactly like `_deficit_label`."""
        spent = float(repair.get("earth_spent", 0.0))
        if spent > 0.0:
            return f"{value:.1f} -{spent:.4f}"
        floor = float(repair.get("earth_floor", 0.0))
        if repair.get("damaged") and value <= floor:
            return f"{value:.2f} FLOOR"
        return f"{value:.1f}/{capacity:.0f}"

    @staticmethod
    def _integrity_label(leg: dict) -> str:
        """A leg's integrity, plus what repair added to it this tick.

        Four decimals on the gain against three on the integrity, deliberately: one
        tick of repair moves ~1e-4, so at the integrity's own precision every gain
        would print as `+0.000` and the row would say a leg was healing by nothing.
        Widest form is `0.850 +0.0004`, which the bar row's right-aligned label fits
        at the shipped panel width and truncates visibly if a narrower one ever
        cannot. Pure function so it can be asserted as a string."""
        gain = leg.get("repair_gain", 0.0)
        if gain > 0.0:
            return f"{leg['integrity']:.3f} +{gain:.4f}"
        return f"{leg['integrity']:.3f}"

    def _draw_legs(self, state: dict, layout: panel_layout.PanelLayout) -> None:
        legs_section = layout.section("legs")
        if legs_section is None:
            return
        legs = _RowCursor(legs_section, layout.content_clipped)
        _wc = ELEMENT_COLOR[ElementType.WATER]
        self._blit_separator(legs.next(panel_layout.RowKind.SEPARATOR))
        self._blit_row_text(
            legs.next(panel_layout.RowKind.HEADING), "Legs (Water parts)", bold=True
        )
        for leg in state["legs"][: layout.legs_shown]:
            sign = "+" if leg["theta_deg"] >= 0 else ""
            repairing = leg.get("repair_gain", 0.0) > 0.0
            if layout.leg_detail is panel_layout.LegDetail.LINE:
                # Condensed to one row: integrity and reserve survive as numbers,
                # which is what a degrade/recover round trip is read from.
                self._blit_row_text(
                    legs.next(panel_layout.RowKind.LEG_LINE),
                    f"L{leg['index']} {sign}{leg['theta_deg']:.0f}° "
                    f"i{leg['integrity']:.3f} r{leg['reserve']:.2f}/{leg['capacity']:.0f}",
                    _wc,
                )
                continue
            # "ang" rather than a theta glyph: the panel's monospace face has no
            # theta and drew it as a missing-glyph box.
            self._blit_row_text(
                legs.next(panel_layout.RowKind.LEG_HEAD),
                f"leg {leg['index']}  ang {sign}{leg['theta_deg']:.0f}°",
                _wc,
            )
            self._draw_compact_bar_row(
                legs.next(panel_layout.RowKind.BAR),
                self._REPAIR_COLOR if repairing else _wc,
                "integr", leg["integrity"], 1.0, self._integrity_label(leg),
            )
            self._draw_compact_bar_row(
                legs.next(panel_layout.RowKind.BAR),
                _wc, "resv", leg["reserve"], leg["capacity"],
                f"{leg['reserve']:.3f}/{leg['capacity']:.1f}",
            )
            if layout.leg_detail is panel_layout.LegDetail.FULL:
                self._blit_row_text(
                    legs.next(panel_layout.RowKind.TEXT),
                    f"  thr {leg['thrust']:+.4f}  max {leg['max_thrust']:.2f}"
                    f"  phi {leg['phi_deg']:.0f}deg",
                )

    def _draw_organ_graph(self, layout: panel_layout.PanelLayout) -> None:
        """Draw the rolling Earth organ graph into the rect the layout gave it.

        The rect comes from the same layout call that placed the inspector, so
        the graph can no longer paint over inspector content the way an
        independently-computed y did. Earth organ is the structural integrity /
        death condition (0–100). The shaded band spans min to max across the
        population; the bright line is the mean. X axis is time (older samples
        left); Y axis is 0–100."""
        g = layout.graph
        gx, gy, gw, gh = g.as_tuple()

        # Caption sits above the graph rect, so it is drawn outside the clip.
        self._blit_row_text(layout.graph_label, "Earth organ")

        # Clipped like both inspectors: the plot was the one region of the panel
        # with neither a clip nor a bound, so a stray sample could paint upward
        # over the caption and the inspector.
        with self._clip_to(g):
            # Frame and background are drawn even with no samples yet, so the panel
            # looks the same at tick 0 as once the first sample lands.
            pygame.draw.rect(self._screen, (10, 25, 25), pygame.Rect(gx, gy, gw, gh))

            history = list(self._organ_history)
            n = len(history)
            if n >= 2:
                def to_px(i: int, val: float) -> tuple[int, int]:
                    """Map (sample index, organ value 0–100) to pixel coordinates."""
                    frac = max(0.0, min(1.0, val / _ORGAN_MAX))
                    px = gx + int(i / (n - 1) * (gw - 1))
                    py = gy + gh - 1 - int(frac * (gh - 1))
                    return px, py

                band_color = (20, 80, 40)
                for i in range(n - 1):
                    _, mn0, mx0 = history[i]
                    _, mn1, mx1 = history[i + 1]
                    p1 = to_px(i, mx0)
                    p2 = to_px(i + 1, mx1)
                    p3 = to_px(i + 1, mn1)
                    p4 = to_px(i, mn0)
                    pygame.draw.polygon(self._screen, band_color, [p1, p2, p3, p4])

                mean_color = (60, 220, 100)
                pts = [to_px(i, history[i][0]) for i in range(n)]
                pygame.draw.lines(self._screen, mean_color, False, pts, 1)

            pygame.draw.rect(self._screen, (40, 60, 40), pygame.Rect(gx, gy, gw, gh), 1)

    def _draw_pause_button(self, paused: bool) -> None:
        """Draw a pause or resume button in the panel. Highlighted yellow when paused."""
        rect = self.pause_button_rect
        if paused:
            fill = (160, 140, 0)
            label = "RESUME"
        else:
            fill = (30, 110, 60)
            label = "PAUSE"
        pygame.draw.rect(self._screen, fill, rect, border_radius=4)
        pygame.draw.rect(self._screen, WHITE, rect, width=1, border_radius=4)
        surf = self._font_bold.render(label, True, WHITE)
        cx = rect.x + (rect.width - surf.get_width()) // 2
        cy = rect.y + (rect.height - surf.get_height()) // 2
        self._screen.blit(surf, (cx, cy))

    def _draw_speed_slider(self, target_fps: int, live_fps: float) -> None:
        """Draw the draggable speed slider at the bottom of the panel.

        Track, label and hit area all come from the layout, so the slider cannot
        drift into the graph the way an independently-computed y could.
        The filled track portion and handle position both reflect target_fps.
        Live FPS is shown alongside so the user can see if the sim is hitting the target."""
        track = self._chrome.slider_track

        # Compute handle position from current target_fps
        t = (target_fps - _FPS_MIN) / (_FPS_MAX - _FPS_MIN)
        handle_x = track.x + int(t * track.w)

        self._blit_row_text(
            self._chrome.slider_label, f"Speed: {target_fps} fps  (live: {live_fps:.0f})"
        )

        # Track background
        pygame.draw.rect(self._screen, (50, 50, 50), pygame.Rect(*track.as_tuple()))
        # Filled portion
        pygame.draw.rect(
            self._screen, (40, 140, 80),
            pygame.Rect(track.x, track.y, handle_x - track.x, track.h)
        )
        # Handle
        handle_cy = track.y + track.h // 2
        pygame.draw.circle(self._screen, WHITE, (handle_x, handle_cy), 7)
        pygame.draw.circle(self._screen, (40, 140, 80), (handle_x, handle_cy), 5)

    def _draw_hud(self, tick: int, n_taobots: int, fps: float) -> None:
        """Draw the top-left HUD showing tick count, population, and live FPS."""
        msg = f"Tick: {tick}  Pop: {n_taobots}  FPS: {fps:.0f}"
        surf = self._font_sm.render(msg, True, DIM_WHITE)
        self._screen.blit(surf, (6, 4))

    def _world_to_px(self, x: float, y: float) -> tuple[int, int]:
        """Convert a world-space position to screen pixels."""
        return world_to_screen(x, y, self._scale_x, self._scale_y)
