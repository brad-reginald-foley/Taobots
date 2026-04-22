from __future__ import annotations

import argparse
import csv
import random
import time
from datetime import datetime
from pathlib import Path

from world import World, WorldConfig

DEFAULT_CONFIG = "configs/default_world.json"


# ---------------------------------------------------------------------------
# Metrics logger
# ---------------------------------------------------------------------------

class MetricsLogger:
    COLUMNS = [
        "tick", "n_taobots", "n_resources_alive", "n_resources_dead",
        "mean_health", "min_health", "max_health",
        "resources_wood", "resources_water", "resources_metal",
        "resources_fire", "resources_earth",
    ]

    def __init__(self, world_name: str) -> None:
        Path("logs").mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        self._path = Path("logs") / f"{world_name}_{ts}.csv"
        self._file = open(self._path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.COLUMNS)
        self._writer.writeheader()
        print(f"Logging to {self._path}")

    def log_tick(self, stats: dict) -> None:
        self._writer.writerow({k: stats[k] for k in self.COLUMNS})

    def flush(self) -> None:
        self._file.flush()

    def close(self) -> None:
        self._file.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Taobots simulation")
    parser.add_argument("--headless", action="store_true", help="Run without display at max speed")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to world config JSON")
    parser.add_argument("--duration", type=float, default=0.0,
                        help="Wall-clock seconds to run (headless only; 0 = infinite)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Visual mode
# ---------------------------------------------------------------------------

def run_visual(world: World, config: WorldConfig) -> None:
    import pygame

    from common import PANEL_W, WINDOW_H, WINDOW_W
    from renderer import Renderer

    pygame.init()
    pygame.font.init()
    screen = pygame.display.set_mode((WINDOW_W + PANEL_W, WINDOW_H))
    pygame.display.set_caption("Taobots — Pangu")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    selected_id: int | None = None
    paused = False

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_g:
                    renderer.toggle_grid()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if mx < WINDOW_W:
                    from common import SCALE_X, SCALE_Y
                    vx = mx / SCALE_X
                    vy = my / SCALE_Y
                    nearby = world.query_taobots(vx, vy, radius=1.5)
                    selected_id = nearby[0].entity_id if nearby else None

        if not paused:
            world.tick()

        fps = clock.get_fps()
        renderer.render(world, selected_id, fps)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


# ---------------------------------------------------------------------------
# Headless mode
# ---------------------------------------------------------------------------

def run_headless(
    world: World, config: WorldConfig, duration_secs: float, logger: MetricsLogger
) -> None:
    start_wall = time.monotonic()

    try:
        while True:
            world.tick()

            if world.tick_count % 60 == 0:
                logger.log_tick(world.get_stats())

            if world.tick_count % 600 == 0:
                elapsed = time.monotonic() - start_wall
                rate = world.tick_count / elapsed if elapsed > 0 else 0
                print(
                    f"Tick {world.tick_count:>8}  |  {rate:>6.0f} ticks/sec  |  "
                    f"Pop: {len(world.taobots)}"
                )
                logger.flush()

            if duration_secs > 0 and time.monotonic() - start_wall >= duration_secs:
                break
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        logger.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        # Phase 3+: also seed numpy when introduced

    config = WorldConfig.from_json(args.config)
    world = World(config)
    world.initialize()

    if args.headless:
        logger = MetricsLogger(config.name)
        run_headless(world, config, args.duration, logger)
    else:
        run_visual(world, config)


if __name__ == "__main__":
    main()
