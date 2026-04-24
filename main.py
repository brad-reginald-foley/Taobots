from __future__ import annotations

import argparse
import csv
import random
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from world import World, WorldConfig

if TYPE_CHECKING:
    from taobot_simple import TaobotSimple

DEFAULT_CONFIG = "configs/default_world.json"



# ---------------------------------------------------------------------------
# Run logger — death records + focal individual tracking
# ---------------------------------------------------------------------------

class RunLogger:
    """Writes two per-run CSV files: a death record for every taobot that dies,
    and a periodic snapshot for a small set of tracked focal individuals.

    Both files are **overwritten** when a new RunLogger is created, so each
    `make sim` or `make headless` run starts with clean logs.

    Death log columns:
      tick, entity_id, age_ticks, distance_moved, damage_taken_total,
      collected_WOOD … collected_EARTH

    Focal log columns (written every FOCAL_INTERVAL ticks per tracked bot):
      tick, entity_id, x, y, behavior_state,
      storage_WOOD … storage_EARTH, collected_total,
      interval_WOOD … interval_EARTH, interval_damage
    """

    N_FOCAL = 5           # number of individuals tracked per run
    FOCAL_INTERVAL = 10   # ticks between focal snapshots

    _DEATH_COLUMNS = [
        "tick", "entity_id", "archetype", "age_ticks", "distance_moved", "damage_taken_total",
        "collected_WOOD", "collected_WATER", "collected_METAL", "collected_FIRE", "collected_EARTH",
    ]
    _FOCAL_COLUMNS = [
        "tick", "entity_id", "archetype", "x", "y", "behavior_state",
        "organ_WOOD", "organ_FIRE", "organ_WATER", "organ_EARTH", "organ_METAL",
        "storage_WOOD", "storage_WATER", "storage_METAL", "storage_FIRE", "storage_EARTH",
        "collected_total",
        "interval_WOOD", "interval_WATER", "interval_METAL", "interval_FIRE", "interval_EARTH",
        "interval_damage",
    ]

    def __init__(self, world_name: str) -> None:
        """Open (and overwrite) the death and focal CSV files for this run."""
        from common import ELEMENT_LIST

        self._elements = ELEMENT_LIST
        Path("logs").mkdir(exist_ok=True)
        death_path = Path("logs") / f"{world_name}_deaths.csv"
        focal_path = Path("logs") / f"{world_name}_focal.csv"

        self._death_file = open(death_path, "w", newline="")
        self._focal_file = open(focal_path, "w", newline="")
        self._death_writer = csv.DictWriter(self._death_file, fieldnames=self._DEATH_COLUMNS)
        self._focal_writer = csv.DictWriter(self._focal_file, fieldnames=self._FOCAL_COLUMNS)
        self._death_writer.writeheader()
        self._focal_writer.writeheader()

        self._focal_ids: list[int] = []  # entity_ids of currently tracked focal bots
        print(f"Run logs: {death_path}, {focal_path}")

    def on_death(self, taobot: "TaobotSimple", tick: int) -> None:
        """Write a death record row and remove the bot from focal tracking if present.

        Called by the world's on_taobot_death callback just before removal."""
        row: dict = {
            "tick": tick,
            "entity_id": taobot.entity_id,
            "archetype": taobot.archetype,
            "age_ticks": taobot.age_ticks,
            "distance_moved": round(taobot.distance_moved, 3),
            "damage_taken_total": round(taobot.damage_taken_total, 3),
        }
        for e in self._elements:
            row[f"collected_{e.name}"] = round(taobot.resources_by_element[e], 3)
        self._death_writer.writerow(row)
        self._death_file.flush()

        if taobot.entity_id in self._focal_ids:
            self._focal_ids.remove(taobot.entity_id)

    def on_tick(self, world: "World") -> None:
        """Called every tick. Samples focal bots on first call, then logs every FOCAL_INTERVAL.

        Dead focal bots are replaced with a new random selection from the living population."""
        tick = world.tick_count

        # Refill focal slots from currently alive bots
        alive_ids = list(world._taobots.keys())
        if not alive_ids:
            return
        non_focal = [eid for eid in alive_ids if eid not in self._focal_ids]
        while len(self._focal_ids) < self.N_FOCAL and non_focal:
            chosen = random.choice(non_focal)
            self._focal_ids.append(chosen)
            non_focal.remove(chosen)

        if tick % self.FOCAL_INTERVAL != 0:
            return

        for eid in list(self._focal_ids):
            taobot = world._taobots.get(eid)
            if taobot is None:
                continue
            row: dict = {
                "tick": tick,
                "entity_id": eid,
                "archetype": taobot.archetype,
                "x": round(taobot.x, 2),
                "y": round(taobot.y, 2),
                "behavior_state": taobot.behavior_state,
                "collected_total": round(taobot.resources_collected, 3),
                "interval_damage": round(taobot._interval_damage, 3),
            }
            for e in self._elements:
                row[f"organ_{e.name}"] = round(taobot.organs[e], 2)
                row[f"storage_{e.name}"] = round(taobot.storage[e], 3)
                row[f"interval_{e.name}"] = round(taobot._interval_resources[e], 3)
            self._focal_writer.writerow(row)
            taobot.reset_interval()

        self._focal_file.flush()

    def close(self) -> None:
        """Flush and close both CSV files."""
        self._death_file.close()
        self._focal_file.close()


# ---------------------------------------------------------------------------
# Metrics logger
# ---------------------------------------------------------------------------

class MetricsLogger:
    """Writes a timestamped population-level CSV to logs/ during headless runs.

    One row is written every 60 ticks. The file is flushed every 600 ticks
    so progress is preserved if the run is interrupted."""

    COLUMNS = [
        "tick", "n_taobots", "n_resources_alive", "n_resources_dead",
        "mean_organ_wood", "mean_organ_fire", "mean_organ_water", "mean_organ_earth",
        "resources_wood", "resources_water", "resources_metal",
        "resources_fire", "resources_earth",
    ]

    def __init__(self, world_name: str) -> None:
        """Open a new timestamped CSV file. Does not overwrite previous runs."""
        Path("logs").mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        self._path = Path("logs") / f"{world_name}_{ts}.csv"
        self._file = open(self._path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.COLUMNS)
        self._writer.writeheader()
        print(f"Logging to {self._path}")

    def log_tick(self, stats: dict) -> None:
        """Write one row from a world.get_stats() dict."""
        self._writer.writerow({k: stats[k] for k in self.COLUMNS})

    def flush(self) -> None:
        """Flush the file buffer to disk (called periodically during long runs)."""
        self._file.flush()

    def close(self) -> None:
        """Flush and close the file."""
        self._file.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments. See README for full documentation."""
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
    """Run the pygame visual loop at a user-adjustable target FPS.

    Controls:
      Space       — pause / unpause
      Up/Down     — cycle target FPS through _FPS_STEPS
      G           — toggle spatial-hash grid overlay
      Esc / Q     — quit
      Click bot   — select for inspector panel
      Click empty — deselect
    """
    import pygame

    from common import PANEL_W, WINDOW_H, WINDOW_W
    from renderer import Renderer

    pygame.init()
    pygame.font.init()
    screen = pygame.display.set_mode((WINDOW_W + PANEL_W, WINDOW_H))
    pygame.display.set_caption("Taobots — Pangu")
    clock = pygame.time.Clock()
    renderer = Renderer(screen)

    run_logger = RunLogger(config.name)
    world.on_taobot_death = lambda t: run_logger.on_death(t, world.tick_count)

    selected_id: int | None = None
    paused = False
    target_fps: int = 60
    slider_dragging = False

    try:
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
                    elif event.key == pygame.K_UP:
                        target_fps = min(target_fps + 5, 120)
                    elif event.key == pygame.K_DOWN:
                        target_fps = max(target_fps - 5, 5)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if renderer.pause_button_rect.collidepoint(mx, my):
                        paused = not paused
                    elif renderer.speed_slider_rect.collidepoint(mx, my):
                        slider_dragging = True
                        target_fps = renderer.fps_from_mouse_x(mx)
                    elif mx < WINDOW_W:
                        from common import SCALE_X, SCALE_Y
                        vx = mx / SCALE_X
                        vy = my / SCALE_Y
                        nearby = world.query_taobots(vx, vy, radius=1.5)
                        selected_id = nearby[0].entity_id if nearby else None
                elif event.type == pygame.MOUSEBUTTONUP:
                    slider_dragging = False
                elif event.type == pygame.MOUSEMOTION:
                    if slider_dragging:
                        target_fps = renderer.fps_from_mouse_x(event.pos[0])

            if not paused:
                world.tick()
                run_logger.on_tick(world)
                taobots = world.taobots
                if taobots:
                    from common import ElementType
                    wood_vals = [t.organs[ElementType.WOOD] for t in taobots]
                    renderer.push_organ_sample(
                        sum(wood_vals) / len(wood_vals), min(wood_vals), max(wood_vals)
                    )

            fps = clock.get_fps()
            renderer.render(world, selected_id, fps, target_fps=target_fps, paused=paused)
            pygame.display.flip()
            clock.tick(target_fps)
    finally:
        run_logger.close()

    pygame.quit()


# ---------------------------------------------------------------------------
# Headless mode
# ---------------------------------------------------------------------------

def run_headless(
    world: World, config: WorldConfig, duration_secs: float, logger: MetricsLogger
) -> None:
    """Run the simulation at maximum speed without a display.

    Logs population stats every 60 ticks and prints a progress line every 600.
    Stops after duration_secs wall-clock seconds, or runs until interrupted if duration=0."""
    run_logger = RunLogger(config.name)
    world.on_taobot_death = lambda t: run_logger.on_death(t, world.tick_count)

    start_wall = time.monotonic()

    try:
        while True:
            world.tick()
            run_logger.on_tick(world)

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
        run_logger.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Parse args, build the world, and dispatch to visual or headless mode."""
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
