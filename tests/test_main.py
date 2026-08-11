"""Tests for the CSV loggers in main.py.

These exist because the row-writing code was previously unreachable from the suite:
nothing constructed a logger, so the per-bot `organ_*` columns were never exercised
and could have kept reporting a stale constant undetected. Each test writes a real
row into a tmp_path `logs/` and parses it back.
"""

import csv

import pytest

from common import ElementType
from main import RunLogger, WorkshopLogger
from world import World


@pytest.fixture
def one_bot_world(default_config):
    """A world holding exactly one taobot, with one leg degraded to 0.5 integrity.

    Mean leg integrity is then 0.75, so a correctly derived Water organ reads 75.0
    and a stale constant still reads 100.0 — the two are distinguishable in the CSV."""
    world = World(default_config)
    bot = world.spawn_taobot(x=5.0, y=5.0)
    assert len(bot.legs) == 2, "the derived value below assumes the two-leg default body"
    bot.legs[0].structural_integrity = 0.5
    return world, bot


def _read_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_workshop_logger_writes_derived_water_organ(one_bot_world, monkeypatch, tmp_path):
    """The workshop CSV is this epic's verification instrument: if `organ_WATER`
    there is a constant, every downstream story reads a dead gauge."""
    world, bot = one_bot_world
    monkeypatch.chdir(tmp_path)

    logger = WorkshopLogger("t", n_legs=len(bot.legs))
    logger.log_tick(bot, tick=1)
    logger.close()

    rows = _read_rows(logger._path)
    assert len(rows) == 1
    row = rows[0]
    assert float(row["organ_WATER"]) == pytest.approx(75.0)
    assert float(row["organ_METAL"]) == pytest.approx(100.0)
    # The organ column must agree with the per-leg columns beside it in the same row.
    leg_mean = (float(row["leg_0_integrity"]) + float(row["leg_1_integrity"])) / 2
    assert float(row["organ_WATER"]) == pytest.approx(leg_mean * 100.0)


def test_run_logger_focal_row_writes_derived_water_organ(one_bot_world, monkeypatch, tmp_path):
    """The focal log takes the same path through `taobot.organ()`; cover it too."""
    world, bot = one_bot_world
    monkeypatch.chdir(tmp_path)

    logger = RunLogger("t")
    logger.on_tick(world)  # tick 0 is a multiple of FOCAL_INTERVAL, so a row is written
    logger.close()

    rows = _read_rows(tmp_path / "logs" / "t_focal.csv")
    assert len(rows) == 1
    assert int(rows[0]["entity_id"]) == bot.entity_id
    assert float(rows[0]["organ_WATER"]) == pytest.approx(75.0)
    assert float(rows[0]["organ_METAL"]) == pytest.approx(100.0)


def test_loggers_emit_a_column_for_every_organ(one_bot_world, monkeypatch, tmp_path):
    """AGENTS.md: adding an organ means adding it to WorkshopLogger in the same change.
    Pin that both per-bot loggers carry all five, so a sixth cannot land half-wired."""
    world, bot = one_bot_world
    monkeypatch.chdir(tmp_path)

    expected = {f"organ_{e.name}" for e in ElementType}

    ws = WorkshopLogger("t", n_legs=len(bot.legs))
    ws.log_tick(bot, tick=1)
    ws.close()
    assert expected <= set(_read_rows(ws._path)[0])

    run = RunLogger("t")
    run.on_tick(world)
    run.close()
    assert expected <= set(_read_rows(tmp_path / "logs" / "t_focal.csv")[0])
