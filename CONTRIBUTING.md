# Contributing to ha-special-day

You are welcome to report a problem, correct a holiday date, improve the
instructions, or contribute code. You do not need to be a developer to help.

## Ways to help

For a bug or date correction, open an issue in the project's GitHub repository.
Describe what you expected, what happened, and how to reproduce it. Include
your Home Assistant and integration versions when relevant. Remove personal
calendar details, addresses, and other private information from examples and
logs.

If you spot unclear or incorrect documentation, you can describe the change in
an issue or submit a documentation-only pull request. You do not need to set up
Python or install development tools for either of these contributions.

## Set up for code changes

For a code change, fork the project on GitHub and clone your fork to your
computer. Create a branch from the latest `main`, then open a terminal in the
project folder (the folder containing `pyproject.toml`). Install Python and uv
versions allowed by
[`pyproject.toml`](pyproject.toml), then install the development dependencies:

```sh
uv sync --locked --group dev
```

This creates `.venv` with the dependency versions in `uv.lock`. The `dev` group
includes the Home Assistant test dependencies, pytest, and the linting and
type-checking tools. Run the tools from this environment so your local checks
use the project dependencies.

When you change dependencies, update `pyproject.toml`, run `uv lock`, and
include both `pyproject.toml` and `uv.lock` in your pull request. Keep existing
dependency constraints and overrides unless the reason for them has been
resolved.

## Find the relevant code

- `custom_components/ha_special_day/defaults.json` contains the built-in dates.
- `custom_components/ha_special_day/rules.py` checks personal JSON files and
  calculates fixed dates, Easter dates, and date expressions.
- `custom_components/ha_special_day/coordinator.py` combines date rules with
  calendar events and refreshes the current results.
- `custom_components/ha_special_day/config_flow.py` handles setup and options;
  `__init__.py` loads the integration, registers the reload action, and handles
  unloading.
- `entity.py`, `binary_sensor.py`, and `sensor.py` provide the Home Assistant
  entities and their attributes.
- `translations/en.json` contains the setup and options text;
  `services.yaml` describes the reload action.
- `tests/test_rules.py` checks date calculations and personal rule files.
  `tests/test_integration.py` exercises setup, entities, reloads, calendars,
  and unloading through Home Assistant.

These paths are inside `custom_components/ha_special_day` unless a different
directory is shown. Keep constants in `const.py`, add type annotations to new
Python functions, and follow the existing module layout.

## Run tests and checks

Run these commands before submitting a code change:

```sh
./.venv/bin/pytest -q
./.venv/bin/ruff check .
./.venv/bin/ruff format --check .
./.venv/bin/mypy custom_components tests
./.venv/bin/prek run --all-files
```

Pytest runs the test suite and prints coverage; its HTML coverage report is
written to the directory selected by `--cov-report=html`. Ruff checks and formats Python code, and mypy checks
types. Prek runs the repository's configured checks. Its Ruff hooks can update
files, so review any changes they make and rerun affected checks.

For a focused test run, use `./.venv/bin/pytest tests/test_rules.py` or add
`-k` followed by a test name. Add regression coverage for changed behavior at
the rule-loading or Home Assistant interface. Useful cases include invalid
input, leap days, offsets across a year boundary, failed rule reloads, calendar
failures, local midnight refreshes, and unloading the integration. Fixed dates
use month/day order (`M/D`); when changing a built-in expression, check the
occasion's date in the affected years. Keep the [README](README.md) examples
consistent with the integration.

For manual testing, use a separate development Home Assistant instance. Check
setup and options, entity states and attributes, the
`ha_special_day.reload_rules` action, and the logs. Keep personal rules files
outside the integration directory.

## Pull requests and releases

Keep each pull request focused. Explain the problem, the resulting behavior,
and the checks you ran. For a date or calendar issue, include a small example
that shows how to reproduce it. Update documentation and translations when
user-facing behavior changes.

Use a Conventional Commit style pull request title, such as `fix: handle a
calendar timeout` or `docs: clarify date offsets`. Automated checks validate
the title, run tests, check the dependency lockfile, and validate the
integration with Hassfest and HACS. Resolve relevant check failures before
merging.

Release Please manages version updates and releases from commits merged to
`main`; leave version changes to its release pull request. After that pull
request is merged, the release workflow creates the tag and GitHub Release and
uploads the HACS archive.
