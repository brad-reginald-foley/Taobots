<!-- bmad:context -->
<!-- Verified 2026-08-10 against 9da079b. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

## taobots

Evolutionary life simulation set in the 5-element Taoist world of Pangu: creatures with genetically-encoded bodies sense, move, metabolize, and evolve on a toroidal map. Python + pygame, no framework. Phase 2 of 6 is **in progress, not complete** — the organ layer is built, the chi layer is not; check the status table in `PLAN.md` before assuming a subsystem exists. `docs/domain-spec.md` holds subsystem requirements with stable IDs and the open-questions register; `PLAN.md` holds phase order, exit criteria, and design-team roles; `README.md` documents world mechanics, CLI flags, and log formats.

## Where things are

- Requirements change in `docs/domain-spec.md`, not in `PLAN.md` or `README.md` — those cite requirement IDs (`NEU-3`, `MER-7`) rather than restating them
- Entry point `main.py`; simulation state in `world.py`, agent behavior in `taobot_simple.py`, all pygame drawing in `renderer.py`
- World tunables are JSON in `configs/`, selected with `--config` — not module constants
- In `logs/`, the fixed-name `*_deaths.csv` and `*_focal.csv` are **overwritten on every run**; copy them out before re-running. Timestamped files accumulate.
- `--workshop` is a single-bot tick-by-tick sandbox that always loads `configs/workshop.json` and ignores `--config`; it is the only source of complete per-tick individual state
- Notebooks read `logs/` CSVs and depend on `requirements-notebooks.txt`, which is separate from `requirements-dev.txt` — installing dev deps alone leaves notebooks broken

## Running and verifying

- Activate `.venv` first. The `Makefile` calls bare `python` and `pytest`, which resolve to system Python without it — `make test` then fails with `make: pytest: No such file or directory`.

## Conventions that differ from defaults

- Distance and direction between entities go through `math_utils.torus_*`. The world wraps at all edges, so plain Euclidean math is silently wrong near the boundaries.
- Positions are virtual units (80 × 60 world), never pixels. Convert only at the render boundary, via `math_utils.world_to_screen`.
- A new organ or body part must be added to the workshop inspector and to `WorkshopLogger` in the same change. Systems here are accepted by tick-stepping in `--workshop`, not by unit tests alone — an organ that cannot be watched cannot be verified.

<!-- /bmad:context -->
