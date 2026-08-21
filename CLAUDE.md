# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal meal planning and nutrition tracking REPL application. Users log meals via terse food codes (e.g. `B.1 *1.5, S2.4`), and the app tracks nutrients, glycemic load, and generates recommendations. It is being refactored from a single 2000-line monolithic script (`mealplan_logger.py.old`) into a modular `meal_planner/` package — the old file is kept only for reference and is not executed.

## Running the app

```
pip install -r requirements.txt
python main.py
```

The app is an interactive REPL (`> ` prompt); type `help` for commands, `quit`/`exit`/`q` to leave.

## Dev vs. production data — READ BEFORE TOUCHING DATA FILES

`config.py` selects a `MODE` of `"DEVELOPMENT"` or `"PRODUCTION"`:
- `DEVELOPMENT` (default) points at `./data/` — safe, disposable test copies.
- `PRODUCTION` points at `C:\data\mealplan\` — the user's **real** nutrition/meal data.

`config_local.py` (gitignored) can override `MODE` and always wins over the default in `config.py`. Never edit data files under `C:\data\mealplan\` directly, and never flip the app into `PRODUCTION` mode as a side effect of testing something — the app prints a `⚠️ WARNING` banner when it does. `data/` is tracked in git for the dev copies except for CSV/JSON files matching `.gitignore` patterns and `data/backups/`.

## Tests

```
pytest
python -m pytest tests/test_parser.py -q       # single file
python -m pytest tests/test_parser.py::test_parse_selection_group  # single test
```

Tests live in `tests/` and currently cover column resolution, the code parser, and data models only — most of `meal_planner/` (commands, scorers, generators, filters) has no test coverage yet, so be extra careful with manual verification when changing those areas.

## Architecture

### Entry point and command dispatch
`main.py` builds a single `CommandContext` (`meal_planner/commands/base.py`) — the shared state object holding every data manager, the scorer set, workspace, and session state — then runs a REPL loop. User input is split into `cmd_name` + `args`; `cmd_name` is looked up in the global `CommandRegistry` (`meal_planner/commands/__init__.py` imports every `*_command.py`/`*_commands.py` module, which self-register via the `@register_command` decorator at import time). Each `Command` subclass implements `execute(self, args: str)`. `CommandContext` also does hard validation at startup (thresholds config, food codes) and calls `sys.exit(1)` on invalid config rather than degrading gracefully — this is intentional, not a bug to "fix" with a fallback.

`ModeManager` (`meal_planner/commands/mode_manager.py`) lets the REPL enter a "mode" (prompt prefix like `[plan]>`) where subsequent input is auto-prefixed with a command name; `.` escapes back to a global command for one line.

### Layered structure inside `meal_planner/`
- `parsers/` — turns terse food-code strings into structured items. `code_parser.py` is the core DSL: simple codes (`B.1`), multipliers (`L.3x2`, `FI.9 x5.7/4`), groups (`(FR.1, FR.2) *.5`), subtractions (`D.10-VE.T1`), and time markers (`@11:30 (DINNER)`). Treat this as a small parser/grammar, not string munging — extend the regexes and the `parse_*` functions together, not ad hoc.
- `models/` — plain data classes (`MealItem`, `DailyTotals`, `PendingDay`, etc.), no I/O.
- `data/` — one manager class per persisted file (`MasterLoader`, `LogManager`, `PendingManager`, `ThresholdsManager`, `AliasManager`, `WorkspaceManager`, `UserPreferencesManager`, `StagingBufferManager`, `EmailManager`). Managers own load/save/reload for their file; commands never touch pandas/JSON I/O directly.
- `commands/` — one file per command (or command family), each registering one or more `Command` subclasses. `base.py` also defines `CommandHistoryMixin` used by commands (`threshold`, `analyze`, `recommend`) that support `--history`/`--use` replay of prior invocations, stored per-meal in the workspace.
- `filters/`, `scorers/`, `generators/` — the recommendation engine. `scorers/` score a *complete meal* (not a single food) 0–1 against one concern (`nutrient_gap`, `daily_count`, `intraday`, `interday`); scorers are registered in `SCORER_REGISTRY` and only instantiated if their weight in `recommendation_weights` (from thresholds config) is non-zero. `filters/` prune candidate meals/pools before scoring (mutual exclusion, conditional requirements, nutrient constraints, pre-score cutoffs). `generators/genetic.py`'s `GeneticAlgorithm` is the orchestrator tying filters + scoring + breeding (`ga_breeding.py`, `ga_population.py`, `ga_member.py`) together for the GA-based recommender — it is the *only* generator module `recommend_command.py` should import from directly.
- `glucose/` — glycemic response calculation/classification, driven by the `glucose_scoring`/`curve_classification` sections of the thresholds config.
- `reports/` — report and chart rendering (`chart_builder.py` produces the trend JPG via matplotlib).
- `analyzers/` — meal analysis logic used by `analyze`/`explain` commands.
- `utils/` — cross-cutting helpers: `columns.py` (canonical column-name resolution — use this, don't re-derive column names), `time_utils.py` (meal boundary/name normalization), `usage_tracker.py`, `docs_renderer.py`, `affinity.py`, `search.py`.

### Config-driven behavior — don't hardcode what belongs in JSON
Most tunable numeric behavior (daily nutrient targets, glucose risk scoring weights/ranges, curve classification rules, recommendation scorer weights, explain-command message thresholds) lives in `meal_plan_config.json` (loaded via `ThresholdsManager`), not in Python. See `THRESHOLDS_REFERENCE.md` for the full schema, including the range-array pattern (`[{"max": N, "score": X}, ..., {"max": null, "score": Y}]`, ascending, last entry `max: null`) used throughout. `ThresholdsManager.load()` validates structure/food-code references at startup and fails hard (see above) rather than falling back to defaults — when adding a new tunable, add it to this file's schema and validation, don't hardcode a constant in the scorer/analyzer.

User-specific preferences (frozen portions, staple foods, unavailable items used by the preference-aware scoring paths) live separately in `meal_plan_user_preferences.json` via `UserPreferencesManager`, and are optional (missing file degrades gracefully, unlike thresholds).

### Docs worth reading before touching these areas
- `THRESHOLDS_REFERENCE.md` — full `meal_plan_config.json` schema and validation rules.
- `PREFERENCE_SCORER_TESTING.md` — manual test scenarios and scoring formula for preference-aware recommendation.
- `docs/templates/` — glycemic-index / curve-type / risk-scoring reference content, some of it rendered back to users at runtime via `utils/docs_renderer.py`.
