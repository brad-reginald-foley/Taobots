from __future__ import annotations

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
)
from math_utils import world_to_screen

if TYPE_CHECKING:
    from entities import Hazard, Resource
    from taobot_simple import TaobotSimple
    from world import World


class Renderer:
    def __init__(
        self,
        screen: pygame.Surface,
        world_w: int = WORLD_WIDTH,
        world_h: int = WORLD_HEIGHT,
        window_w: int = WINDOW_W,
        window_h: int = WINDOW_H,
        panel_w: int = PANEL_W,
    ) -> None:
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

    def toggle_grid(self) -> None:
        self._show_grid = not self._show_grid

    def render(
        self,
        world: "World",
        selected_id: int | None = None,
        fps: float = 0.0,
    ) -> None:
        self._draw_background()
        if self._show_grid:
            self._draw_grid()
        self._draw_resources(world.resources, world.dead_resources)
        self._draw_hazards(world.hazards)
        self._draw_taobots(world.taobots, selected_id)
        selected_taobot = world._taobots.get(selected_id) if selected_id is not None else None
        self._draw_inspector(selected_taobot)
        self._draw_hud(world.tick_count, len(world.taobots), fps)

    # --- Layers ---

    def _draw_background(self) -> None:
        self._screen.fill(BACKGROUND_COLOR, pygame.Rect(0, 0, self._window_w, self._window_h))
        pygame.draw.rect(self._screen, PANEL_COLOR, self._panel_rect)

    def _draw_grid(self) -> None:
        bucket_px_x = int(8 * self._scale_x)
        bucket_px_y = int(8 * self._scale_y)
        for x in range(0, self._window_w, bucket_px_x):
            pygame.draw.line(self._screen, GRID_COLOR, (x, 0), (x, self._window_h))
        for y in range(0, self._window_h, bucket_px_y):
            pygame.draw.line(self._screen, GRID_COLOR, (0, y), (self._window_w, y))

    def _draw_resources(
        self, resources: list["Resource"], dead_resources: list["Resource"]
    ) -> None:
        for r in dead_resources:
            px, py = world_to_screen(r.x, r.y, self._scale_x, self._scale_y)
            color = ELEMENT_COLOR[r.element_type]
            dim = tuple(max(0, int(c * 0.25)) for c in color)
            pygame.draw.circle(self._screen, dim, (px, py), 4, 1)

        for r in resources:
            px, py = world_to_screen(r.x, r.y, self._scale_x, self._scale_y)
            color = ELEMENT_COLOR[r.element_type]
            brightness = max(0.3, r.amount / r.max_amount)
            scaled = tuple(min(255, int(c * brightness)) for c in color)
            pygame.draw.circle(self._screen, scaled, (px, py), 4)

    def _draw_hazards(self, hazards: list["Hazard"]) -> None:
        for h in hazards:
            px, py = world_to_screen(h.x, h.y, self._scale_x, self._scale_y)
            color = ELEMENT_COLOR[h.element_type]
            size = 5
            points = [
                (px, py - size),
                (px + size, py),
                (px, py + size),
                (px - size, py),
            ]
            pygame.draw.polygon(self._screen, color, points)

    def _draw_taobots(self, taobots: list["TaobotSimple"], selected_id: int | None) -> None:
        for t in taobots:
            px, py = world_to_screen(t.x, t.y, self._scale_x, self._scale_y)
            color = TAOBOT_FLEE_COLOR if t.behavior_state == "fleeing" else TAOBOT_COLOR
            pygame.draw.circle(self._screen, color, (px, py), 6)

            # Heading line
            hx = px + int(math.cos(t.heading) * 10)
            hy = py + int(math.sin(t.heading) * 10)
            pygame.draw.line(self._screen, WHITE, (px, py), (hx, hy), 1)

            # Health bar
            health_frac = max(0.0, t.health / t.max_health)
            bar_w = 12
            bar_x = px - bar_w // 2
            bar_y = py - 12
            red = (200, 40, 40)
            green = (40, 200, 40)
            bar_color = (
                int(red[0] + (green[0] - red[0]) * health_frac),
                int(red[1] + (green[1] - red[1]) * health_frac),
                int(red[2] + (green[2] - red[2]) * health_frac),
            )
            pygame.draw.rect(self._screen, (60, 60, 60), pygame.Rect(bar_x, bar_y, bar_w, 2))
            filled_w = int(bar_w * health_frac)
            pygame.draw.rect(self._screen, bar_color, pygame.Rect(bar_x, bar_y, filled_w, 2))

            # Selection ring
            if t.entity_id == selected_id:
                pygame.draw.circle(self._screen, WHITE, (px, py), 9, 1)

    def _draw_inspector(self, taobot: "TaobotSimple | None") -> None:
        x = self._window_w + 8
        y = 8
        line_h = 18

        def text(msg: str, color: tuple = DIM_WHITE, bold: bool = False) -> None:
            nonlocal y
            font = self._font_bold if bold else self._font_sm
            surf = font.render(msg, True, color)
            self._screen.blit(surf, (x, y))
            y += line_h

        def swatch(color: tuple, label: str) -> None:
            nonlocal y
            pygame.draw.rect(self._screen, color, pygame.Rect(x, y + 2, 8, 8))
            surf = self._font_sm.render(label, True, DIM_WHITE)
            self._screen.blit(surf, (x + 12, y))
            y += line_h

        def bar(value: float, max_val: float, width: int = 120, height: int = 8) -> None:
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
        text(f"Health: {state['health']:.1f}/{state['max_health']:.0f}")
        bar(state["health"], state["max_health"])
        text(f"Age: {state['age_ticks']} ticks")
        text(f"Fitness: {state['fitness_score']:.4f}")
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

    def _draw_hud(self, tick: int, n_taobots: int, fps: float) -> None:
        msg = f"Tick: {tick}  Pop: {n_taobots}  FPS: {fps:.0f}"
        surf = self._font_sm.render(msg, True, DIM_WHITE)
        self._screen.blit(surf, (6, 4))

    def _world_to_px(self, x: float, y: float) -> tuple[int, int]:
        return world_to_screen(x, y, self._scale_x, self._scale_y)
