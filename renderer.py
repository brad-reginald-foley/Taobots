from __future__ import annotations

import collections
import math
from typing import TYPE_CHECKING

import pygame

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
_GRAPH_H = 100       # px height of health history graph
_GRAPH_MARGIN = 8
_SLIDER_H = 10       # height of the speed slider track in px
_PAUSE_BTN_H = 24    # height of the pause/resume button
_PAUSE_BTN_W = 110   # width of the pause/resume button
# Bottom section from window bottom: slider(28) + button(34) + graph(110) + labels(20) = ~192px
_BOTTOM_SECTION_H = 192
_FPS_MIN = 5
_FPS_MAX = 120


class Renderer:
    """Stateless read-only renderer for the pygame window.

    The world viewport (left side) and inspector panel (right side) are drawn
    each frame. The renderer owns only display state: grid toggle and the rolling
    health history deque. It never writes to the world or taobots.

    Panel layout (top → bottom):
      Inspector    — selected taobot details, or "Click a taobot" hint
      Health graph — 200-tick rolling mean/min/max population health
      Speed slider — draggable FPS control (5–120); also responds to Up/Down keys
    """

    def __init__(
        self,
        screen: pygame.Surface,
        world_w: int = WORLD_WIDTH,
        world_h: int = WORLD_HEIGHT,
        window_w: int = WINDOW_W,
        window_h: int = WINDOW_H,
        panel_w: int = PANEL_W,
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

        self._font_sm = pygame.font.SysFont("monospace", 13)
        self._font_md = pygame.font.SysFont("monospace", 15)
        self._font_bold = pygame.font.SysFont("monospace", 15, bold=True)

        self._panel_rect = pygame.Rect(window_w, 0, panel_w, window_h)

        # Rolling Wood-organ history: (mean, min, max) per tick
        self._organ_history: collections.deque[tuple[float, float, float]] = (
            collections.deque(maxlen=200)
        )

    def toggle_grid(self) -> None:
        """Toggle the spatial-hash bucket grid overlay on/off."""
        self._show_grid = not self._show_grid

    def push_organ_sample(self, mean: float, mn: float, mx: float) -> None:
        """Append one tick's population Wood organ stats to the rolling graph buffer."""
        self._organ_history.append((mean, mn, mx))

    @property
    def pause_button_rect(self) -> pygame.Rect:
        """The clickable rect of the pause/resume button, in screen coordinates."""
        btn_x = self._window_w + (self._panel_w - _PAUSE_BTN_W) // 2
        btn_y = self._window_h - 58
        return pygame.Rect(btn_x, btn_y, _PAUSE_BTN_W, _PAUSE_BTN_H)

    @property
    def speed_slider_rect(self) -> pygame.Rect:
        """The clickable track rect of the speed slider, in screen coordinates.

        main.py uses this to hit-test mouse events against the slider."""
        track_y = self._window_h - 18
        track_x = self._window_w + _GRAPH_MARGIN
        track_w = self._panel_w - _GRAPH_MARGIN * 2
        return pygame.Rect(track_x, track_y - 6, track_w, _SLIDER_H + 12)

    def fps_from_mouse_x(self, mx: int) -> int:
        """Convert a mouse x position to a target FPS value (clamped to _FPS_MIN.._FPS_MAX)."""
        track_x = self._window_w + _GRAPH_MARGIN
        track_w = self._panel_w - _GRAPH_MARGIN * 2
        t = max(0.0, min(1.0, (mx - track_x) / track_w))
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
        self._draw_inspector(selected_taobot)
        self._draw_organ_graph()
        self._draw_pause_button(paused)
        self._draw_speed_slider(target_fps, fps)
        self._draw_hud(world.tick_count, len(world.taobots), fps)

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
        """Draw each taobot as a circle with a heading line, Wood organ bar, and optional ring."""
        for t in taobots:
            px, py = world_to_screen(t.x, t.y, self._scale_x, self._scale_y)
            color = TAOBOT_FLEE_COLOR if t.behavior_state == "fleeing" else TAOBOT_COLOR
            pygame.draw.circle(self._screen, color, (px, py), 6)

            # Heading line
            hx = px + int(math.cos(t.heading) * 10)
            hy = py + int(math.sin(t.heading) * 10)
            pygame.draw.line(self._screen, WHITE, (px, py), (hx, hy), 1)

            # Wood organ bar (structural integrity / death condition)
            wood_frac = max(0.0, t.organs[ElementType.WOOD] / 100.0)
            bar_w = 12
            bar_x = px - bar_w // 2
            bar_y = py - 12
            red = (200, 40, 40)
            green = (40, 200, 40)
            bar_color = (
                int(red[0] + (green[0] - red[0]) * wood_frac),
                int(red[1] + (green[1] - red[1]) * wood_frac),
                int(red[2] + (green[2] - red[2]) * wood_frac),
            )
            pygame.draw.rect(self._screen, (60, 60, 60), pygame.Rect(bar_x, bar_y, bar_w, 2))
            filled_w = int(bar_w * wood_frac)
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

    def _draw_inspector(self, taobot: "TaobotSimple | None") -> None:
        """Draw the inspector panel for the selected taobot, or a placeholder if none selected."""
        x = self._window_w + 8
        y = 8
        line_h = 18

        def text(msg: str, color: tuple = DIM_WHITE, bold: bool = False) -> None:
            """Render a line of text and advance y."""
            nonlocal y
            font = self._font_bold if bold else self._font_sm
            surf = font.render(msg, True, color)
            self._screen.blit(surf, (x, y))
            y += line_h

        def swatch(color: tuple, label: str) -> None:
            """Render an 8×8 color block followed by a text label."""
            nonlocal y
            pygame.draw.rect(self._screen, color, pygame.Rect(x, y + 2, 8, 8))
            surf = self._font_sm.render(label, True, DIM_WHITE)
            self._screen.blit(surf, (x + 12, y))
            y += line_h

        def bar(value: float, max_val: float, width: int = 120, height: int = 8) -> None:
            """Render a red-to-green progress bar."""
            nonlocal y
            frac = max(0.0, value / max_val) if max_val > 0 else 0.0
            red = (200, 40, 40)
            green = (40, 200, 40)
            bar_color = (
                int(red[0] + (green[0] - red[0]) * frac),
                int(red[1] + (green[1] - red[1]) * frac),
                int(red[2] + (green[2] - red[2]) * frac),
            )
            pygame.draw.rect(self._screen, (60, 60, 60), pygame.Rect(x, y, width, height))
            pygame.draw.rect(self._screen, bar_color, pygame.Rect(x, y, int(width * frac), height))
            y += height + 4

        text("Inspector", bold=True)
        pygame.draw.line(self._screen, (80, 80, 80), (x, y), (x + self._panel_w - 16, y))
        y += 6

        if taobot is None:
            text("Click a taobot")
            return

        state = taobot.get_state()
        text(f"Taobot #{state['entity_id']}", WHITE, bold=True)
        text(f"State: {state['behavior_state']}")
        text(f"Age: {state['age_ticks']} ticks")
        text(f"Fitness: {state['fitness_score']:.4f}")
        text(f"Dist: {state['distance_moved']:.1f}  Dmg: {state['damage_taken_total']:.1f}")
        y += 4

        text("Organs:", bold=True)
        for e in ELEMENT_LIST:
            organ_val = state["organs"][e.name]
            swatch(ELEMENT_COLOR[e], f"{e.name}: {organ_val:.1f}")
            bar(organ_val, 100.0)

        y += 4
        text("Storage:", bold=True)
        for e in ELEMENT_LIST:
            amount = state["storage"][e.name]
            cap = state["storage_capacity"][e.name]
            swatch(ELEMENT_COLOR[e], f"{ELEMENT_RESOURCE_NAME[e]}: {amount:.1f}/{cap:.0f}")

        y += 4
        text("Params:", bold=True)
        text(f"Speed: {state['speed']:.1f}  Sense: {state['sensing_range']:.1f}")
        text("Affinities:")
        for e in ELEMENT_LIST:
            aff = state["affinity"][e.name]
            swatch(ELEMENT_COLOR[e], f"{ELEMENT_RESOURCE_NAME[e]}: {aff:.3f}")

    def _draw_organ_graph(self) -> None:
        """Draw the rolling Wood organ graph in the lower panel.

        Wood organ is the structural integrity / death condition (0–100).
        The shaded band spans min to max across the population; the bright line
        is the mean. X axis is time (older samples left); Y axis is 0–100."""
        if not self._organ_history:
            return

        gx = self._window_w + _GRAPH_MARGIN
        gy = self._window_h - _BOTTOM_SECTION_H
        gw = self._panel_w - _GRAPH_MARGIN * 2

        pygame.draw.rect(self._screen, (10, 25, 25), pygame.Rect(gx, gy, gw, _GRAPH_H))

        surf = self._font_sm.render("Wood organ", True, DIM_WHITE)
        self._screen.blit(surf, (gx, gy - 16))

        history = list(self._organ_history)
        n = len(history)
        if n < 2:
            return

        def to_px(i: int, val: float) -> tuple[int, int]:
            """Map (sample index, organ value 0–100) to pixel coordinates."""
            px = gx + int(i / (n - 1) * (gw - 1))
            py = gy + _GRAPH_H - 1 - int(val / 100.0 * (_GRAPH_H - 1))
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
        if len(pts) >= 2:
            pygame.draw.lines(self._screen, mean_color, False, pts, 1)

        pygame.draw.rect(self._screen, (40, 60, 40), pygame.Rect(gx, gy, gw, _GRAPH_H), 1)

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

        The filled track portion and handle position both reflect target_fps.
        Live FPS is shown alongside so the user can see if the sim is hitting the target."""
        track_x = self._window_w + _GRAPH_MARGIN
        track_w = self._panel_w - _GRAPH_MARGIN * 2
        track_y = self._window_h - 18

        # Compute handle position from current target_fps
        t = (target_fps - _FPS_MIN) / (_FPS_MAX - _FPS_MIN)
        handle_x = track_x + int(t * track_w)

        # Label row
        label = f"Speed: {target_fps} fps  (live: {live_fps:.0f})"
        surf = self._font_sm.render(label, True, DIM_WHITE)
        self._screen.blit(surf, (track_x, track_y - 18))

        # Track background
        pygame.draw.rect(
            self._screen, (50, 50, 50),
            pygame.Rect(track_x, track_y, track_w, _SLIDER_H)
        )
        # Filled portion
        pygame.draw.rect(
            self._screen, (40, 140, 80),
            pygame.Rect(track_x, track_y, handle_x - track_x, _SLIDER_H)
        )
        # Handle
        handle_cy = track_y + _SLIDER_H // 2
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
