---
title: 'Story 1.0e — Make the workshop inspector legible'
type: 'bugfix'
created: '2026-08-11'
status: 'done'
review_loop_iteration: 0
baseline_commit: '9ab1c86a2b374810473bcd8600827af6054084a6'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The workshop is this epic's verification instrument, and its panel destroys its own
output. Two independent layout systems write the same region: `_draw_workshop_inspector` flows
top-down from `y=8` with an unbounded running `y` and no clip, then `_draw_organ_graph` runs *after*
it and fills an **opaque** rect at a fixed `y=408`, erasing whatever was beneath. The graph returns
early while its history is empty, so the panel looks correct at tick 0 and breaks the moment the
first sample lands. Measured today: the inspector overruns the graph at **one leg** (by 62px), and a
leg's reserve label runs 25px past the panel edge. Stories 1.1, 1.3 and 1.4 all read evidence off
this panel and 1.3 adds to it.

**Approach:** Give the panel **one layout owner**. Extract the arithmetic into a pure function that
returns rects and imports no pygame, so it is testable with no display surface. The inspector claims
a bounded rect ending above the graph and clips to it; the graph's position derives from the same
layout rather than an independent constant. Content that does not fit is condensed, then clipped —
never drawn outside. Fix the right-label overflow against the panel width.

## Boundaries & Constraints

**Always:**
- The layout function is **pure**: inputs in, rects out, no pygame import, no drawing, no display
  surface. That seam is what makes the panel verifiable rather than eyeballed.
- The graph's position is **derived from the same layout** as the inspector. Two constants that must
  agree is the defect being fixed, not the fix.
- Nothing is drawn outside the rect it was allotted. Overflow is condensed or clipped, never spilled.
- Right-hand value labels stay inside `PANEL_W` at the longest values the bars actually produce.
- Follow the house convention of converting at the render boundary — the layout speaks in plain
  rects, the renderer converts to `pygame.Rect` when it draws.

**Ask First:**
- Changing `PANEL_W`, `WINDOW_W`, `WINDOW_H`, or the window layout.
- Removing any row the inspector currently shows, as opposed to condensing it.
- Any change to what the organ graph plots or how it is sampled.

**Never:**
- No tabs, no scrolling, no per-organ grouping. Those are deferred to E2, when armor makes 32 parts
  real; sizing navigation now means guessing at four part types that cannot yet be seen.
- Do not change simulation behaviour. This story touches presentation only.
- Do not alter the organ values, storage values or leg values themselves — only where they are drawn.
- Do not remove the Water organ row that Story 1.0b added.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| One leg | inventory of 1 leg | No rect overlaps the graph rect; all within `PANEL_W` | N/A |
| Eight legs | inventory of 8 legs | Same — condensed as needed, nothing outside its rect | N/A |
| Zero legs | legless bot | Layout still valid; leg section empty or absent | N/A |
| Graph derives | any inventory | Graph rect begins at or below the inspector rect's bottom, never overlapping | N/A |
| No display surface | layout called in a bare process | Returns rects; imports and runs without pygame display | N/A |
| Longest labels | reserve `3.951/4.0`, storage `20.0/20` | Label right edge ≤ panel right edge | Truncate or right-align |
| Empty history | graph with no samples yet | Panel is correct at tick 0 *and* after the first sample | N/A |
| Content overflow | more rows than fit | Condensed, then clipped, with the truncation visible to the reader | N/A |

</frozen-after-approval>

## Code Map

Line anchors verified against `9ab1c86` on 2026-08-11.

**Measured defect** (probe run headlessly at `PANEL_W=240`, `WINDOW_H=600`, graph top `408`):

| legs | inspector ends at | result |
|---|---|---|
| 1 | 429 | overlaps graph by **21px** |
| 2 | 493 | overlaps by 85px |
| 4 | 621 | overlaps by 213px |
| 8 | 877 | overlaps by 469px |

*(Corrected during review. The first draft of this table read 470/534/662/918 — a hand-count of the
section rows that over-counted spacing by a constant 41px. Re-measured by instrumenting the real
`_draw_workshop_inspector` arithmetic at `9ab1c86`. The conclusion is unchanged: it fails at one leg.)*

The epic predicted failure at two legs; Story 1.0b's Water organ row moved it to one. Horizontally,
the leg reserve label spans `x=967..1065` against a panel right edge of `1040` — **25px over**. Organ
(`959..994`) and storage (`959..1008`) labels currently fit.

- `renderer.py` -- `_GRAPH_H = 100` `:35`, `_BOTTOM_SECTION_H = 192` `:41`. `render()` `:124` draws the
  inspector *then* `_draw_organ_graph()`, which is the overwrite order. `_draw_organ_graph` `:527`
  computes `gy = self._window_h - _BOTTOM_SECTION_H` `:537` — the independent constant — fills an
  opaque rect `:540`, and returns early on empty history, which is why tick 0 looks fine.
- `renderer.py` -- `_draw_workshop_inspector` `:443`: `x = window_w + 8`, `y = 8`, `lh = 16`,
  `pw = panel_w - 16`; nested `sep()`/`txt()` closures advance `y` with no bound. Sections in order:
  title, bot info, Organs (5 rows since 1.0b), Storage (5 rows), Legs (**4 rows per leg** `:508-525`).
- `renderer.py` -- `_draw_compact_bar_row` `:421`: `bar_x = x + 51`, `bar_w = 96`, right label blitted
  at `bar_x + bar_w + 4` `:441` with no regard for `PANEL_W`. Leg rows call it at `x + 8`, which is
  what pushes their labels over.
- `renderer.py` -- `_draw_inspector` `:337` is the non-workshop panel, same overwrite exposure.
- `common.py` -- `PANEL_W = 240`, `WINDOW_W = 800`, `WINDOW_H = 600`.
- `tests/` -- **`renderer.py` has no test coverage at all.** This story's pure function is the seam
  that changes that; it is already recorded in `deferred-work.md` as 1.0e's natural scope.

**Read-only evidence:** epic Story 1.0e — "one layout owner", "a pure function returning rects", and
the unit test over 1–8 legs as the regression guard. Tabs and scrolling deferred to E2.

## Tasks & Acceptance

**Execution:**
- [x] `panel_layout.py` (new) -- a pure layout module importing no pygame: given panel geometry and a part inventory, return a frozen structure holding the inspector rect, the graph rect and per-section rects. This is the seam the whole story exists to create.
- [x] `panel_layout.py` -- the graph rect is computed from the same layout as the inspector rect, so the two cannot disagree. Sections that do not fit are condensed by a declared rule, and the result reports what was truncated so the renderer can show it.
- [x] `renderer.py` -- `_draw_organ_graph` takes its rect from the layout instead of `self._window_h - _BOTTOM_SECTION_H`; delete the independent constant or reduce it to a layout input.
- [x] `renderer.py` -- `_draw_workshop_inspector` draws inside its allotted rect and clips to it, replacing the unbounded running `y`. Apply the same bound to `_draw_inspector`.
- [x] `renderer.py` -- `_draw_compact_bar_row` keeps its right label inside the panel: right-align or truncate against the panel edge rather than blitting at a fixed offset.
- [x] `renderer.py` -- when the leg list will not fit, condense it and make the truncation visible to the reader rather than silently dropping rows.
- [x] `tests/test_panel_layout.py` (new) -- the regression guard: for inventories of 1 through 8 legs, no returned rect overlaps the graph rect and none extends beyond `PANEL_W`. Current code fails this at one leg -- verify the test fails against the old arithmetic before the fix lands.
- [x] `tests/test_panel_layout.py` -- cover the rest of the matrix: zero legs, graph-derives-from-layout, callable with no display surface, and longest-label containment.

**Acceptance Criteria:**
- Given any part inventory from 0 to 8 legs, when the layout is computed, then no rect overlaps the graph rect and no rect extends beyond `PANEL_W`.
- Given a bare Python process with no display surface, when the layout function is imported and called, then it returns rects without initialising pygame.
- Given the pre-change arithmetic, when the new regression test is run against it, then it fails at one leg — proving the test has teeth.
- Given a workshop run past tick 0 with the graph populated, when the panel is drawn, then the inspector is not overwritten and no content appears outside the panel.
- Given the longest values the bars produce, when a row is drawn, then its right label's right edge is within the panel.
- Given `make check`, then ruff, mypy and the full suite pass, and a seeded run's trajectory is unchanged — this story touches presentation only.

## Spec Change Log

## Design Notes

**Why a pure function and not just a clip call.** A clip would stop the bleeding, but the panel would
still be unverifiable — the only way to know it fits would be to look at it, which is how it broke
without anyone noticing. Rects computed by a function that needs no display are assertable in a unit
test, and `renderer.py` currently has no tests at all. That is the seam, and the epic names it as the
surface a tabbed inspector would later sit on.

**Water appears twice, and that is intended.** Since 1.0b the Organs block shows the Water organ (the
mean of leg integrity) while the Legs block shows each leg's own integrity. They are an aggregate and
its parts, not a duplication — but the headings should make that legible rather than leaving a reader
to infer it.

**Condense before clipping.** Each leg currently occupies four rows. The reader's priority under
pressure is integrity and reserve; thrust, max thrust and phi are diagnostic detail. Condensing that
detail first keeps more legs visible than clipping whole legs would, and the truncation must be
stated on screen — a silently shortened list reads as a bot with fewer legs, which in this epic is a
meaningful and wrong claim.

**This is presentation-only.** The seeded trajectory must be identical before and after. If it is
not, something in the layout work reached into simulation state.

## Verification

**Commands:**
- `source .venv/bin/activate && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy make check` -- expected: ruff, mypy, full suite clean.
- `python -c "import panel_layout; print(panel_layout.compute(...))"` -- expected: returns rects in a process that never imports pygame display.
- `python main.py --headless --seed 42 --ticks 300` before and after -- expected: byte-identical logs. Presentation-only. **Do not run from the repo root without backing up `logs/default_focal.csv` and `logs/default_deaths.csv` first** — both are overwritten every run.

**Manual checks:**
- `python main.py --workshop`, step past tick 0 so the graph populates, with a 4-leg body: the inspector is intact, the graph sits below it, every value label is inside the panel, and any truncation is visible rather than silent.

## Suggested Review Order

**The layout owner**

- Entry point: the pure function. Everything the panel draws is placed here, with no pygame.
  [`panel_layout.py:528`](../../panel_layout.py#L528)

- The condensation ladder — the declared rule for what gives way first, and why.
  [`panel_layout.py:240`](../../panel_layout.py#L240)

- Picks a rung, and reserves the truncation notice *before* any section so the guard cannot be clipped.
  [`panel_layout.py:477`](../../panel_layout.py#L477)

- Bar geometry derives from the measured character width; a fixed offset already overlapped at 8px.
  [`panel_layout.py:363`](../../panel_layout.py#L363)

- Rejects geometry too small to lay out, rather than returning rects that pass containment vacuously.
  [`panel_layout.py:81`](../../panel_layout.py#L81)

**The renderer obeying it**

- One layout per frame, handed to every panel drawer — the single place the "one owner" claim is enacted.
  [`renderer.py:189`](../../renderer.py#L189)

- Raises on a layout/renderer mismatch instead of silently dropping content.
  [`renderer.py:46`](../../renderer.py#L46)

- Takes its rect from the layout. The independent constant that caused the overwrite is gone.
  [`renderer.py:747`](../../renderer.py#L747)

**Tests — the pixel-level ones exist because rect-level ones passed while the defect was restorable**

- Reads pixels back: the label must be painted whole and flush right, not merely computed so.
  [`test_renderer_panel.py:229`](../../tests/test_renderer_panel.py#L229)

- Every allotted row must hold ink. Blanking the Water organ row fails 12 tests.
  [`test_renderer_panel.py:281`](../../tests/test_renderer_panel.py#L281)

- Keeps the original defect on record: the old arithmetic overruns the graph at one leg.
  [`test_panel_layout.py:134`](../../tests/test_panel_layout.py#L134)

- Degeneracy guard, so containment is asserted against something real.
  [`test_panel_layout.py:101`](../../tests/test_panel_layout.py#L101)
