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
                "legacy_week": "1/2+1w@mon",
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
                "leap": "29/2",
                "clamped": "31/1+1m",
                "new_year_reference": "year_end+1d",
                "year_end": "31/12",
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
        ({"bad": "31/2"}, "bad.*date"),
        ({"bad": "Missing Rule+1d"}, "bad.*unknown"),
        ({"bad": "1/1+1q"}, "bad.*suffix"),
        ({"bad": "1/1+" + "9" * 200 + "d"}, "bad.*amount"),
        ({"bad": "1/1+2000d+2000d"}, "bad.*cumulative"),
        (
            {"base": "1/1+2000d", "bad": "base+2000d"},
            "bad.*reference chain cumulative",
        ),
        ({"first": "second+1d", "second": "first-1w"}, "cyclic rule reference"),
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
