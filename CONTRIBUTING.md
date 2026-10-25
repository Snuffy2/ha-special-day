# Contributing to ha-special-day

Bug reports, holiday corrections, documentation improvements, and code changes
are welcome. For a bug report, include the integration and Home Assistant versions,
steps to reproduce, the expected result, and relevant logs. Remove personal
calendar details and other private information from examples and logs.

## Development setup

Start from the latest `main` branch and create a branch for your changes. Install
Python and uv versions that satisfy `requires-python` and `tool.uv.required-version`
in [pyproject.toml](pyproject.toml), then run these commands from the repository root:

```sh
uv sync --locked --group dev
```

This creates `.venv` with the dependencies pinned in `uv.lock`. The `ha`, `lint`,
`pytest`, and `dev` dependency groups share the same lockfile; `dev` includes the
linting and testing tools. Run tools through this environment so local checks
use the same dependencies as CI.

When changing dependencies, update `pyproject.toml`, run `uv lock`, and commit both
files. Keep any dependency constraints and overrides in place unless the reason
for them has been resolved.

## Finding the relevant code

- `custom_components/ha_special_day/rules.py` evaluates date expressions and loads
  personal rules; `defaults.json` contains the bundled occasions.
- `coordinator.py` combines local rules with calendar events and refreshes state.
- `config_flow.py` handles setup and options; `__init__.py` manages integration
  setup, the reload action, and unload.
- `entity.py`, `binary_sensor.py`, and `sensor.py` expose the results as entities.
- `translations/en.json` supplies the setup and options text; `services.yaml`
  describes the reload action.
- `tests/test_rules.py` covers the date evaluator, and `tests/test_integration.py`
  exercises the real Home Assistant integration and entity platforms.

The files listed above are inside `custom_components/ha_special_day` unless a
different directory is shown. Keep new constants in `const.py` and follow the
existing module layout and typed Python conventions.

## Testing and checks

Run the following before submitting a pull request:

```sh
./.venv/bin/pytest -q
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/mypy custom_components tests
./.venv/bin/prek run --all-files
```

Ruff and some prek hooks apply fixes. Review those changes and rerun any affected
checks. Hook definitions live in [prek.toml](prek.toml); Python tool settings live
in [pyproject.toml](pyproject.toml). Pytest prints coverage and writes an HTML
report under the configured `--cov-report=html` output directory.

For a focused test run, use `./.venv/bin/pytest tests/test_rules.py` or select a
test with `-k`. Add regression coverage for changed behavior at the rule-loading
or Home Assistant interface. Relevant cases include invalid input, leap days,
offsets crossing a year boundary, failed rule reloads, calendar failures, local
midnight refreshes, and unloading the integration. Fixed dates use `M/D`; when
changing bundled expressions, verify that their intended holiday dates remain
correct. Keep the [README](README.md) examples consistent with behavior.

Use a separate development Home Assistant instance for manual testing. Check
setup and options, entity states and attributes, the `ha_special_day.reload_rules`
action, and logs. Keep personal rule files outside the integration directory.

## Pull requests

Keep changes focused and explain the problem, resulting behavior, and validation
performed. Include a small reproducing example for date or calendar bugs, and
update documentation and translations when the user-facing behavior changes.

Use a Conventional Commit style PR title, such as `fix: handle a calendar timeout`
or `docs: clarify date offsets`. GitHub workflows validate PR titles, run tests
and coverage, check the lockfile, run lint and formatting checks, and validate
the integration with Hassfest and HACS. Resolve relevant failures before merging.

Release Please manages version updates and releases from commits merged to
`main`. Leave version changes to its release PR. After that PR is merged, the
release workflow creates the tag and GitHub Release and uploads the HACS archive.
