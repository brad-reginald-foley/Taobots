from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rng import derive_stream, new_seed
from world import World, WorldConfig

if TYPE_CHECKING:
    from taobot_simple import TaobotSimple

DEFAULT_CONFIG = "configs/default_world.json"
WORKSHOP_CONFIG = "configs/workshop.json"

LOG_DIR = Path("logs")

# Bumped when the manifest's key set changes, so a tool reading an old manifest can
# tell that it is old rather than mis-parsing it.
MANIFEST_VERSION = 1



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

    @staticmethod
    def path_names(world_name: str) -> list[Path]:
        """The files a `RunLogger` for `world_name` will write.

        The naming convention is spelled here and nowhere else: `main()` needs these
        paths for the manifest before the run starts, and a manifest that re-spelled
        the convention itself would drift from the logger without either side noticing."""
        return [
            LOG_DIR / f"{world_name}_deaths.csv",
            LOG_DIR / f"{world_name}_focal.csv",
        ]

    def __init__(self, world_name: str, rng: random.Random | None = None) -> None:
        """Open (and overwrite) the death and focal CSV files for this run.

        `rng` is the logger's *observer* stream, used only to pick focal individuals.
        It must not be the simulation's stream: an observer that draws from the run it
        is measuring perturbs that run, so attaching a logger would change the outcome
        (`AD-16` — observers read, never mutate). Omitted, a private stream is derived
        from a fresh seed; `main()` derives one from the run seed so focal selection
        replays with the run."""
        from common import ELEMENT_LIST

        self._elements = ELEMENT_LIST
        self._rng: random.Random = (
            derive_stream(new_seed(), "observer", "focal") if rng is None else rng
        )
        LOG_DIR.mkdir(exist_ok=True)
        death_path, focal_path = self.path_names(world_name)
        self._paths = [death_path, focal_path]

        self._death_file = open(death_path, "w", newline="")
        self._focal_file = open(focal_path, "w", newline="")
        self._death_writer = csv.DictWriter(self._death_file, fieldnames=self._DEATH_COLUMNS)
        self._focal_writer = csv.DictWriter(self._focal_file, fieldnames=self._FOCAL_COLUMNS)
        self._death_writer.writeheader()
        self._focal_writer.writeheader()

        self._focal_ids: list[int] = []  # entity_ids of currently tracked focal bots
        print(f"Run logs: {death_path}, {focal_path}")

    @property
    def paths(self) -> list[Path]:
        """The files this logger is writing (named in the manifest)."""
        return list(self._paths)

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
            chosen = self._rng.choice(non_focal)
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
                row[f"organ_{e.name}"] = round(taobot.organ(e), 2)
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
        "mean_organ_metal",
        "resources_wood", "resources_water", "resources_metal",
        "resources_fire", "resources_earth",
    ]

    def __init__(self, world_name: str, ts: str) -> None:
        """Open a new timestamped CSV file. Does not overwrite previous runs.

        `ts` is the run's shared timestamp and is required: pairing this CSV with the
        manifest recording the seed that produced it *is* the traceability guarantee,
        and a defaulted stamp would silently produce a file belonging to no manifest."""
        LOG_DIR.mkdir(exist_ok=True)
        self._path = LOG_DIR / f"{world_name}_{ts}.csv"
        self._file = open(self._path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=self.COLUMNS)
        self._writer.writeheader()
        print(f"Logging to {self._path}")

    @property
    def path(self) -> Path:
        """Where this run's population CSV is being written (named in the manifest)."""
        return self._path

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
# Workshop logger
# ---------------------------------------------------------------------------

class WorkshopLogger:
    """Writes one CSV row per tick for the single bot in workshop mode.

    Columns capture full individual state: organs, storage, behavior, position,
    per-tick resource intake per element, per-tick damage, and per-leg body part state."""

    _BASE_COLUMNS = [
        "tick", "entity_id", "archetype", "age_ticks", "behavior_state",
        "x", "y",
        "organ_WOOD", "organ_FIRE", "organ_WATER", "organ_EARTH", "organ_METAL",
        "storage_WOOD", "storage_FIRE", "storage_WATER", "storage_EARTH", "storage_METAL",
        "intake_WOOD", "intake_FIRE", "intake_WATER", "intake_EARTH", "intake_METAL",
        "tick_damage",
        "resources_collected", "distance_moved", "damage_taken_total",
        # Chi conversion, split by path. Both the passive Sheng cycle and the
        # demand-triggered path move METAL->WATER, so the change in `storage_METAL`
        # and `storage_WATER` alone cannot say whether both ran once or one ran
        # twice — these four columns are the only thing that can. `spent` is what
        # Metal paid and `produced` is what Water received; the difference is the
        # 20% lost to CYCLE_EFFICIENCY, per path, per tick.
        # `active` is "Water is below the threshold"; `served` is "the demand path
        # actually moved something". A bot in deficit with no Metal left is active and
        # unserved, and a column that could not say so would report the trigger working
        # while nothing moved.
        "chi_deficit_active", "chi_deficit_served", "chi_deficit_level",
        "chi_passive_M2W_spent", "chi_passive_M2W_produced",
        "chi_deficit_M2W_spent", "chi_deficit_M2W_produced",
    ]

    @staticmethod
    def path_name(world_name: str, ts: str) -> Path:
        """The file a `WorkshopLogger` will write — the convention, spelled once."""
        return LOG_DIR / f"{world_name}_workshop_{ts}.csv"

    def __init__(self, world_name: str, ts: str, n_legs: int = 0) -> None:
        """`ts` is the run's shared timestamp — see `MetricsLogger.__init__`."""
        from common import ELEMENT_LIST
        self._elements = ELEMENT_LIST
        self._n_legs = n_legs
        leg_cols = [
            f"leg_{i}_{field}"
            for i in range(n_legs)
            for field in ("reserve", "integrity", "thrust")
        ]
        columns = self._BASE_COLUMNS + leg_cols
        LOG_DIR.mkdir(exist_ok=True)
        self._path = self.path_name(world_name, ts)
        self._file = open(self._path, "w", newline="")
        self._writer = csv.DictWriter(self._file, fieldnames=columns)
        self._writer.writeheader()
        print(f"Workshop log: {self._path}")

    @property
    def path(self) -> Path:
        """Where this run's workshop CSV is being written (named in the manifest)."""
        return self._path

    def log_tick(self, taobot: "TaobotSimple", tick: int) -> None:
        row: dict = {
            "tick": tick,
            "entity_id": taobot.entity_id,
            "archetype": taobot.archetype,
            "age_ticks": taobot.age_ticks,
            "behavior_state": taobot.behavior_state,
            "x": round(taobot.x, 2),
            "y": round(taobot.y, 2),
            "resources_collected": round(taobot.resources_collected, 3),
            "distance_moved": round(taobot.distance_moved, 3),
            "damage_taken_total": round(taobot.damage_taken_total, 3),
            "tick_damage": round(taobot._interval_damage, 4),
        }
        # Read off the state snapshot the inspector reads, so the CSV and the panel
        # can never disagree about what the trigger did this tick.
        chi = taobot.get_state()["chi"]
        passive_spent, passive_produced = chi["passive_metal_to_water"]
        deficit_spent, deficit_produced = chi["deficit_metal_to_water"]
        row["chi_deficit_active"] = int(chi["deficit_active"])
        row["chi_deficit_served"] = int(chi["deficit_served"])
        row["chi_deficit_level"] = round(chi["deficit_level"], 4)
        row["chi_passive_M2W_spent"] = round(passive_spent, 6)
        row["chi_passive_M2W_produced"] = round(passive_produced, 6)
        row["chi_deficit_M2W_spent"] = round(deficit_spent, 6)
        row["chi_deficit_M2W_produced"] = round(deficit_produced, 6)
        for e in self._elements:
            row[f"organ_{e.name}"] = round(taobot.organ(e), 3)
            row[f"storage_{e.name}"] = round(taobot.storage[e], 3)
            row[f"intake_{e.name}"] = round(taobot._interval_resources[e], 4)
        for i, leg in enumerate(taobot.legs):
            row[f"leg_{i}_reserve"]   = round(leg.reserve, 4)
            row[f"leg_{i}_integrity"] = round(leg.structural_integrity, 4)
            row[f"leg_{i}_thrust"]    = round(leg._thrust, 4)
        self._writer.writerow(row)
        self._file.flush()
        taobot.reset_interval()

    def close(self) -> None:
        self._file.close()


# ---------------------------------------------------------------------------
# Run manifest — what produced these logs
# ---------------------------------------------------------------------------

def run_timestamp() -> str:
    """The stamp shared by every file one run writes, manifest included.

    Millisecond resolution, because it is also the *identity* of a run: at second
    resolution two runs started in the same second write the same filenames, and the
    second silently overwrites the first's manifest and population CSV."""
    return datetime.now().strftime("%Y%m%dT%H%M%S_%f")[:-3]


def config_fingerprint(config: WorldConfig) -> str:
    """A hash of the *resolved* configuration — every value the run actually used.

    The config name and path are not enough to replay a run: configs are edited, and
    laws are merged in from a second file, so the same name can mean different numbers
    a week later. Recording the resolved values makes a changed config detectable
    instead of silently producing a different run under the same seed."""
    resolved = {
        "name": config.name,
        "width": config.width,
        "height": config.height,
        "resources": {
            "initial_count": config.resources.initial_count,
            "respawn_delay_ticks": config.resources.respawn_delay_ticks,
            "spawn_weights": {e.name: v for e, v in config.resources.spawn_weights.items()},
            "cluster_affinity": {
                e.name: v for e, v in config.resources.cluster_affinity.items()
            },
        },
        "hazards": {
            "initial_count": config.hazards.initial_count,
            "spawn_weights": {e.name: v for e, v in config.hazards.spawn_weights.items()},
            "cluster_affinity": {
                e.name: v for e, v in config.hazards.cluster_affinity.items()
            },
        },
        "taobots": {
            "initial_count": config.taobots.initial_count,
            "target_population": config.taobots.target_population,
        },
        "chemistry": {"degrade_rate": config.chemistry.degrade_rate},
        # The chi laws are read every tick, so a run is not replayable without them.
        "chi": {
            "water_deficit_threshold": config.chi.water_deficit_threshold,
            "deficit_conversion_rate": config.chi.deficit_conversion_rate,
        },
    }
    canonical = json.dumps(resolved, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def git_sha(repo_root: Path | None = None) -> str | None:
    """Return the current commit SHA, or None if it cannot be determined.

    Returns None rather than raising: a manifest with an unknown commit is still worth
    having, and a run must never die because the code was unpacked outside a git
    checkout, or because `git` is not installed. `repo_root` defaults to the directory
    holding this file, not the working directory, so the SHA describes the code that
    is running rather than wherever it happened to be launched from."""
    root = Path(__file__).resolve().parent if repo_root is None else Path(repo_root)
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    return sha or None


def git_dirty(repo_root: Path | None = None) -> bool | None:
    """True if the working tree has uncommitted changes, None if unknown.

    Recorded beside the SHA because a dirty tree means the SHA does *not* identify the
    code that ran — the manifest should say so rather than imply a clean replay."""
    root = Path(__file__).resolve().parent if repo_root is None else Path(repo_root)
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return bool(proc.stdout.strip())


def write_manifest(
    *,
    seed: int,
    config: WorldConfig,
    config_path: str,
    mode: str,
    ts: str,
    log_paths: list[Path],
    log_dir: Path | None = None,
) -> Path:
    """Write this run's manifest beside its logs and return the path — `AD-12` part 3.

    Until now `--seed` was accepted and recorded nowhere, so no logged run could be
    replayed and no CSV could be attributed to the code that produced it. The manifest
    closes that: seed, config, commit, Python version and timestamp, plus the log files
    this run writes, all keyed by the same timestamp that names those files.

    Written *before* the run so a crash still leaves an attributable manifest, which is
    why `ticks` starts null — `finalize_manifest` fills it in on a clean exit."""
    directory = LOG_DIR if log_dir is None else Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{config.name}_manifest_{ts}.json"
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "seed": seed,
        "config_name": config.name,
        "config_path": str(config_path),
        "config_fingerprint": config_fingerprint(config),
        # Null until the run ends. A run stopped by `--duration` is wall-clock bound,
        # so the same seed reaches a different tick count on a busier machine; the
        # replay guarantee is "same trajectory", and this says how far this one got.
        "ticks": None,
        "mode": mode,
        "git_sha": git_sha(),
        "git_dirty": git_dirty(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        # Determinism is scoped to an environment, never to a committed golden file:
        # float summation order and libm differ across builds, so the platform is part
        # of what a replay needs to match.
        "platform": platform.platform(),
        "timestamp": ts,
        "logs": [str(p) for p in log_paths],
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Run manifest: {path}  (seed {seed})")
    return path


def finalize_manifest(path: Path, tick_count: int) -> None:
    """Record how many ticks the run actually reached.

    Best-effort: a manifest that cannot be updated is not worth failing a completed run
    over, and the pre-run manifest it leaves behind is still attributable."""
    try:
        manifest = json.loads(Path(path).read_text())
        manifest["ticks"] = tick_count
        Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError) as exc:  # pragma: no cover - defensive
        print(f"Warning: could not record final tick count in {path}: {exc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments. See README for full documentation."""
    parser = argparse.ArgumentParser(description="Taobots simulation")
    parser.add_argument("--headless", action="store_true", help="Run without display at max speed")
    parser.add_argument("--workshop", action="store_true",
                        help="Open Lao Tzu's Workshop (single-bot sandbox, tick-by-tick)")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to world config JSON")
    parser.add_argument("--duration", type=float, default=0.0,
                        help="Wall-clock seconds to run (headless only; 0 = infinite)")
    parser.add_argument("--ticks", type=int, default=0,
                        help="Stop after N ticks (headless only; 0 = no tick limit). "
                             "Unlike --duration this is reproducible: the same seed and "
                             "the same --ticks give the same run on any machine")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed (one is generated and recorded if omitted)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Visual mode
# ---------------------------------------------------------------------------

def run_visual(world: World, config: WorldConfig, run_logger: RunLogger) -> None:
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
                    earth_vals = [t.organ(ElementType.EARTH) for t in taobots]
                    renderer.push_organ_sample(
                        sum(earth_vals) / len(earth_vals), min(earth_vals), max(earth_vals)
                    )

            fps = clock.get_fps()
            renderer.render(world, selected_id, fps, target_fps=target_fps, paused=paused)
            pygame.display.flip()
            clock.tick(target_fps)
    finally:
        run_logger.close()

    pygame.quit()


# ---------------------------------------------------------------------------
# Workshop mode — Lao Tzu's Workshop
# ---------------------------------------------------------------------------

def run_workshop(  # noqa: C901
    world: World, config: WorldConfig, ws_logger: WorkshopLogger
) -> None:
    """Single-bot sandbox with tick-by-tick stepping and full state inspector.

    Controls:
      N / Right    — step one tick (stays paused)
      R            — toggle slow run (~2 ticks/sec)
      Space        — pause / unpause at target FPS
      Up / Down    — adjust target FPS
      G            — toggle grid
      Esc / Q      — quit
    """
    import pygame

    from common import PANEL_W, WINDOW_H, WINDOW_W, ElementType
    from renderer import Renderer

    _SLOW_FPS = 2

    pygame.init()
    pygame.font.init()
    screen = pygame.display.set_mode((WINDOW_W + PANEL_W, WINDOW_H))
    pygame.display.set_caption("Lao Tzu's Workshop")
    clock = pygame.time.Clock()
    renderer = Renderer(
        screen,
        world_w=config.width,
        world_h=config.height,
        workshop=True,
    )

    selected_id: int | None = next(iter(world._taobots), None)
    paused = True
    slow_run = False
    target_fps = 3
    slider_dragging = False

    running = True
    while running:
        step_once = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_SPACE:
                    paused = not paused
                    slow_run = False
                elif event.key in (pygame.K_n, pygame.K_RIGHT):
                    step_once = True
                elif event.key == pygame.K_r:
                    slow_run = not slow_run
                    paused = not slow_run
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
                    slow_run = False
                elif renderer.speed_slider_rect.collidepoint(mx, my):
                    slider_dragging = True
                    target_fps = renderer.fps_from_mouse_x(mx)
            elif event.type == pygame.MOUSEBUTTONUP:
                slider_dragging = False
            elif event.type == pygame.MOUSEMOTION:
                if slider_dragging:
                    target_fps = renderer.fps_from_mouse_x(event.pos[0])

        if step_once or (not paused):
            world.tick()
            if step_once:
                paused = True
                slow_run = False
            # Re-acquire bot if it respawned
            if selected_id not in world._taobots:
                selected_id = next(iter(world._taobots), None)
            taobots = world.taobots
            if taobots:
                earth_vals = [t.organ(ElementType.EARTH) for t in taobots]
                renderer.push_organ_sample(
                    sum(earth_vals) / len(earth_vals), min(earth_vals), max(earth_vals)
                )
                if selected_id is not None and selected_id in world._taobots:
                    ws_logger.log_tick(world._taobots[selected_id], world.tick_count)

        fps = clock.get_fps()
        effective_fps = _SLOW_FPS if slow_run else target_fps
        renderer.render(world, selected_id, fps, target_fps=effective_fps, paused=paused)
        pygame.display.flip()
        clock.tick(effective_fps)

    ws_logger.close()
    pygame.quit()


# ---------------------------------------------------------------------------
# Headless mode
# ---------------------------------------------------------------------------

def run_headless(
    world: World,
    config: WorldConfig,
    duration_secs: float,
    logger: MetricsLogger,
    run_logger: RunLogger,
    max_ticks: int = 0,
) -> None:
    """Run the simulation at maximum speed without a display.

    Logs population stats every 60 ticks and prints a progress line every 600.
    Stops after `max_ticks` ticks or `duration_secs` wall-clock seconds, whichever
    comes first; both default to 0, meaning "no limit". Prefer `max_ticks` when the run
    needs to be reproducible — a wall-clock bound reaches a different tick count on a
    machine under different load, so two same-seed runs share only a common prefix."""
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

            if max_ticks > 0 and world.tick_count >= max_ticks:
                break
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
    """Parse args, build the world, and dispatch to visual or headless mode.

    Every run is seeded: `--seed` fixes it, and omitting the flag generates one rather
    than leaving the run unseeded. Either way the seed reaches the manifest, so a run
    launched without `--seed` is still replayable afterwards (`AD-12` part 3)."""
    args = parse_args()

    seed = new_seed() if args.seed is None else args.seed
    ts = run_timestamp()

    if args.workshop:
        config_path = WORKSHOP_CONFIG
    else:
        config_path = args.config
    config = WorldConfig.from_json(config_path)

    world = World(config, seed=seed)
    world.initialize()

    mode = "workshop" if args.workshop else ("headless" if args.headless else "visual")

    # Loggers are built here, before the run, so the manifest can take its file list
    # straight off them. Nothing re-spells the naming convention: a manifest that
    # predicted paths of its own would drift from the loggers silently, and a manifest
    # naming files that were never written is worse than no manifest.
    observer = derive_stream(world.seed, "observer", "focal")
    if args.workshop:
        # The workshop writes its own single-bot CSV and no run logs.
        first_bot = next(iter(world.taobots), None)
        n_legs = len(first_bot.legs) if first_bot is not None else 0
        ws_logger = WorkshopLogger(config.name, ts=ts, n_legs=n_legs)
        log_paths = [ws_logger.path]
    else:
        run_logger = RunLogger(config.name, rng=observer)
        log_paths = run_logger.paths
        if args.headless:
            metrics = MetricsLogger(config.name, ts=ts)
            log_paths = log_paths + [metrics.path]

    # Written *before* the run: a run killed by Ctrl-C or a crash is exactly the one
    # whose logs most need attributing to a seed.
    manifest_path = write_manifest(
        seed=seed,
        config=config,
        config_path=config_path,
        mode=mode,
        ts=ts,
        log_paths=log_paths,
    )

    try:
        if args.workshop:
            run_workshop(world, config, ws_logger)
        elif args.headless:
            run_headless(
                world, config, args.duration, metrics, run_logger, max_ticks=args.ticks
            )
        else:
            run_visual(world, config, run_logger)
    finally:
        finalize_manifest(manifest_path, world.tick_count)


if __name__ == "__main__":
    main()
