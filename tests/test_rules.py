"""Focused calendar and configuration behavior tests for the pure rule engine."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

from custom_components.ha_special_day.rules import RuleError, Rules, load_rules


def _load(tmp_path: Path, config: dict[str, object]) -> Rules:
    """Write temporary JSON configuration and compile its rules.

    Args:
        tmp_path (Path): Temporary directory for the configuration file.
        config (dict[str, object]): External configuration values.

    Returns:
        Rules: Compiled rules loaded from the temporary file.
    """
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return load_rules(path)


def test_defaults_calculate_easter_and_correct_black_friday() -> None:
    """Check Easter calculations and the corrected Black Friday rule."""
    rules = load_rules()

    assert "Good Friday" in rules.events_on(date(2024, 3, 29))
    assert "Easter Day" in rules.events_on(date(2024, 3, 31))
    assert "Black Friday" in rules.events_on(date(2024, 11, 29))
    assert "Black Friday" not in rules.events_on(date(2024, 11, 22))


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        pytest.param(
            2020,
            {26: {"Boxing Day"}, 27: set(), 28: {"Boxing Day Bank Holiday"}},
            id="friday-christmas",
        ),
        pytest.param(
            2021,
            {
                26: {"Boxing Day"},
                27: {"Christmas Day Bank Holiday"},
                28: {"Boxing Day Bank Holiday"},
            },
            id="saturday-christmas",
        ),
        pytest.param(
            2022,
            {26: {"Boxing Day"}, 27: {"Christmas Day Bank Holiday"}, 28: set()},
            id="sunday-christmas-2022",
        ),
        pytest.param(
            2033,
            {26: {"Boxing Day"}, 27: {"Christmas Day Bank Holiday"}, 28: set()},
            id="sunday-christmas-2033",
        ),
    ],
)
def test_christmas_bank_holidays_follow_substitute_days(
    year: int, expected: dict[int, set[str]]
) -> None:
    """Keep the named Christmas holidays on their correct substitute dates.

    Args:
        year (int): Calendar year being checked.
        expected (dict[int, set[str]]): Expected holidays by December day.
    """
    rules = load_rules()
    holiday_names = {"Boxing Day", "Christmas Day Bank Holiday", "Boxing Day Bank Holiday"}

    for day_of_month, expected_names in expected.items():
        actual_names = set(rules.events_on(date(year, 12, day_of_month))) & holiday_names
        assert actual_names == expected_names


def test_sunday_christmas_substitute_can_be_excluded(tmp_path: Path) -> None:
    """Allow the corrected Christmas substitute holiday to be excluded.

    Args:
        tmp_path (Path): Temporary directory for the JSON configuration.
    """
    rules = _load(tmp_path, {"exclude": ["Christmas Day Bank Holiday"]})

    assert "Boxing Day" in rules.events_on(date(2022, 12, 26))
    assert "Christmas Day Bank Holiday" not in rules.events_on(date(2022, 12, 27))
    assert "Boxing Day Bank Holiday" not in rules.events_on(date(2022, 12, 27))


def test_inclusive_and_legacy_week_weekday_offsets(tmp_path: Path) -> None:
    """Check inclusive nth weekday and legacy week-based weekday offsets.

    Args:
        tmp_path (Path): Temporary directory for the JSON configuration.
    """
    rules = _load(
        tmp_path,
        {
            "include_defaults": False,
            "seasonal_fallbacks": False,
            "bank_holidays": False,
            "rules": {
                "inclusive": "1/1+1@Mon",
                "legacy_week": "2/1+1w@mon",
            },
        },
    )

    assert "inclusive" in rules.events_on(date(2024, 1, 1))
    # In February 2024 the first legacy calendar week starts on Monday Jan 29.
    assert "legacy_week" in rules.events_on(date(2024, 1, 29))


def test_leap_day_month_clamping_and_cross_year_offsets(tmp_path: Path) -> None:
    """Check leap-day rules, end-of-month clamping, and New Year crossings.

    Args:
        tmp_path (Path): Temporary directory for the JSON configuration.
    """
    rules = _load(
        tmp_path,
        {
            "include_defaults": False,
            "seasonal_fallbacks": False,
            "bank_holidays": False,
            "rules": {
                "leap": "2/29",
                "clamped": "1/31+1m",
                "new_year_reference": "year_end+1d",
                "year_end": "12/31",
            },
        },
    )

    assert "leap" in rules.events_on(date(2024, 2, 29))
    assert "leap" not in rules.events_on(date(2023, 2, 28))
    assert "clamped" in rules.events_on(date(2024, 2, 29))
    assert "clamped" in rules.events_on(date(2023, 2, 28))
    assert "new_year_reference" in rules.events_on(date(2025, 1, 1))


def test_overrides_exclusions_and_bank_holiday_switch(tmp_path: Path) -> None:
    """Check external overrides, exclusions, and UK bank holiday controls.

    Args:
        tmp_path (Path): Temporary directory for the JSON configuration.
    """
    rules = _load(
        tmp_path,
        {
            "rules": {"Pancake Day": "1/1"},
            "exclude": ["New Year's Day Bank Holiday"],
        },
    )

    assert "Pancake Day" in rules.events_on(date(2025, 1, 1))
    assert "New Year's Day Bank Holiday" not in rules.events_on(date(2023, 1, 2))
    disabled = _load(
        tmp_path,
        {"include_defaults": False, "bank_holidays": False, "rules": {}},
    )
    assert disabled.events_on(date(2023, 1, 2)) == []


def test_lent_and_advent_fallbacks_can_be_disabled_or_excluded(tmp_path: Path) -> None:
    """Check seasonal fallbacks and their caller and configuration controls.

    Args:
        tmp_path (Path): Temporary directory for the JSON configuration.
    """
    rules = load_rules()
    assert rules.events_on(date(2024, 3, 7)) == ["the 20th day of Lent"]
    assert rules.events_on(date(2024, 12, 2)) == ["the 2nd day of Advent"]
    assert rules.events_on(date(2024, 3, 7), include_fallback=False) == []

    disabled = _load(tmp_path, {"include_defaults": False, "seasonal_fallbacks": False})
    assert disabled.events_on(date(2024, 3, 7)) == []
    excluded = _load(
        tmp_path,
        {"include_defaults": False, "exclude": ["the 20th day of Lent"]},
    )
    assert excluded.events_on(date(2024, 3, 7)) == []


@pytest.mark.parametrize(
    ("rules", "message"),
    [
        pytest.param({"bad": "2/31"}, "bad", id="invalid-day"),
        pytest.param({"bad": "25/12"}, "bad", id="reversed-month-day"),
        pytest.param({"bad": "Missing Rule+1d"}, "bad", id="unknown-reference"),
        pytest.param({"bad": "1/1+1q"}, "bad", id="invalid-offset-unit"),
        pytest.param({"bad": "1/1+" + "9" * 200 + "d"}, "bad", id="oversized-offset"),
        pytest.param({"bad": "1/1+2000d+2000d"}, "bad", id="cumulative-offset"),
        pytest.param(
            {"base": "1/1+2000d", "bad": "base+2000d"}, "bad", id="reference-chain-offset"
        ),
        pytest.param({"first": "second+1d", "second": "first-1w"}, "cycl", id="cyclic-reference"),
    ],
)
def test_invalid_rules_raise_entry_specific_errors(
    tmp_path: Path, rules: dict[str, str], message: str
) -> None:
    """Reject malformed expressions, references, cycles, and large offsets.

    Args:
        tmp_path (Path): Temporary directory for the JSON configuration.
        rules (dict[str, str]): Invalid rule set to load.
        message (str): Expected text in the resulting error.
    """
    with pytest.raises(RuleError, match=message):
        _load(
            tmp_path,
            {"include_defaults": False, "seasonal_fallbacks": False, "rules": rules},
        )


def test_configuration_types_and_unknown_keys_are_rejected(tmp_path: Path) -> None:
    """Reject invalid config values and unsupported configuration keys.

    Args:
        tmp_path (Path): Temporary directory for the JSON configuration.
    """
    with pytest.raises(RuleError, match=r"bank_holidays.*boolean"):
        _load(tmp_path, {"bank_holidays": "yes"})
    with pytest.raises(RuleError, match="unknown key"):
        _load(tmp_path, {"surprise": True})


def test_custom_dates_use_month_day(tmp_path: Path) -> None:
    """Interpret custom dates in month/day order.

    Args:
        tmp_path (Path): Temporary directory for the JSON configuration.
    """
    rules = _load(
        tmp_path,
        {
            "include_defaults": False,
            "bank_holidays": False,
            "seasonal_fallbacks": False,
            "rules": {"Custom Day": "7/4"},
        },
    )
    assert rules.events_on(date(2024, 7, 4)) == ["Custom Day"]
    assert rules.events_on(date(2024, 4, 7)) == []


def test_numeric_and_easter_prefixed_named_references(tmp_path: Path) -> None:
    """Resolve date- and Easter-prefixed names before interpreting literals.

    Args:
        tmp_path (Path): Temporary directory for the JSON configuration.
    """
    config: dict[str, object] = {
        "include_defaults": False,
        "bank_holidays": False,
        "seasonal_fallbacks": False,
        "rules": {
            "7/14 anniversary": "7/14",
            "Anniversary alias": "7/14 anniversary",
            "Day after": "7/14 anniversary+1d",
            "Easter+1d event": "easter+2d",
            "Easter+1d event plus": "Easter+1d event+1d",
            "Following Easter event": "Easter+1d event plus+1d",
            "7/14+1d": "7/14+1d",
            "Easter+1d": "Easter+1d",
        },
    }
    rules = _load(tmp_path, config)

    assert "7/14 anniversary" in rules.events_on(date(2024, 7, 14))
    assert "Anniversary alias" in rules.events_on(date(2024, 7, 14))
    assert "Day after" in rules.events_on(date(2024, 7, 15))
    assert "Easter+1d event" in rules.events_on(date(2024, 4, 2))
    assert "Easter+1d event plus" in rules.events_on(date(2024, 4, 3))
    assert "Following Easter event" in rules.events_on(date(2024, 4, 4))
    assert "7/14+1d" in rules.events_on(date(2024, 7, 15))
    assert "Easter+1d" in rules.events_on(date(2024, 4, 1))

    excluded = _load(
        tmp_path,
        {**config, "exclude": ["Day after", "Following Easter event"]},
    )
    assert "Day after" not in excluded.events_on(date(2024, 7, 15))
    assert "Following Easter event" not in excluded.events_on(date(2024, 4, 4))
