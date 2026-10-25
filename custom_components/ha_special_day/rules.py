"""Pure Python calendar rule evaluation for the special day integration."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import re
from typing import Any


class RuleError(ValueError):
    """Raised when a rule file is malformed or contains invalid expressions."""


_DEFAULTS_PATH = Path(__file__).with_name("defaults.json")
_WEEKDAYS = {"mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7}
_DATE_BASE = re.compile(r"^(\d{1,2})/(\d{1,2})")
_OFFSET = re.compile(r"([+-])(\d+)?(d|w|m(?!on))?@?(mon|tue|wed|thu|fri|sat|sun)?", re.IGNORECASE)
_MAX_CUMULATIVE_OFFSET_DAYS = 3660


@dataclass(frozen=True)
class _Offset:
    direction: int
    amount: int
    unit: str
    weekday: str | None


@dataclass(frozen=True)
class _Expression:
    kind: str
    value: int | str | tuple[int, int]
    offsets: tuple[_Offset, ...]


class Rules:
    """Compiled annual rules and their optional UK and seasonal fallbacks."""

    def __init__(
        self,
        expressions: dict[str, _Expression],
        excluded: frozenset[str],
        bank_holidays: bool,
        seasonal_fallbacks: bool,
        anchor_radius: int,
    ) -> None:
        """Initialize compiled calendar rules.

        Args:
            expressions (dict[str, _Expression]): Parsed annual rule expressions.
            excluded (frozenset[str]): Event names omitted from results.
            bank_holidays (bool): Whether UK substitute bank holidays are enabled.
            seasonal_fallbacks (bool): Whether Lent and Advent labels are enabled.
            anchor_radius (int): Number of adjacent anchor years to evaluate.
        """
        self._expressions = expressions
        self._excluded = excluded
        self._bank_holidays = bank_holidays
        self._seasonal_fallbacks = seasonal_fallbacks
        self._anchor_radius = anchor_radius

    def events_on(self, day: date, *, include_fallback: bool = True) -> list[str]:
        """Return event names for ``day``, including configured fallbacks.

        Annual rules are evaluated across the anchor years needed by the
        largest configured offset. Seasonal fallback names are added only
        when there are no other events and ``include_fallback`` is true.
        Callers with an external calendar event can pass false to preserve
        the legacy fallback suppression behavior.

        Args:
            day (date): Calendar date to evaluate.
            include_fallback (bool): Whether to include a seasonal fallback when
                no bank holiday or named rule matches.

        Returns:
            list[str]: Event names for the requested date.
        """
        events: list[str] = []
        if self._bank_holidays:
            events.extend(name for name in _bank_holidays_on(day) if name not in self._excluded)

        cache: dict[tuple[str, int], date | None] = {}
        for name in self._expressions:
            if name in self._excluded:
                continue
            if any(
                _evaluate(name, year, self._expressions, cache) == day
                for year in range(
                    max(1, day.year - self._anchor_radius),
                    min(9999, day.year + self._anchor_radius) + 1,
                )
            ):
                events.append(name)

        if not events and self._seasonal_fallbacks and include_fallback:
            fallback = _seasonal_fallback(day)
            if fallback is not None and fallback not in self._excluded:
                events.append(fallback)
        return events


def load_rules(path: Path | None = None) -> Rules:
    """Load bundled rules, optionally overlaid by an external JSON file.

    The external object accepts ``include_defaults``, ``rules``, ``exclude``,
    ``bank_holidays`` and ``seasonal_fallbacks``. Rule expressions support
    fixed ``M/D`` dates, Easter, named rule references, and chained offsets.

    Args:
        path (Path | None): Optional JSON configuration path.

    Returns:
        Rules: Compiled bundled and external calendar rules.

    Raises:
        RuleError: The file cannot be read or contains invalid configuration.
    """
    defaults = _read_json(_DEFAULTS_PATH, "bundled defaults")
    if not isinstance(defaults, dict) or not all(
        isinstance(name, str) and isinstance(expression, str)
        for name, expression in defaults.items()
    ):
        raise RuleError("bundled defaults must be an object of rule name to expression strings")

    config: dict[str, Any] = {}
    if path is not None:
        config = _read_json(path, f"configuration {path}")
        if not isinstance(config, dict):
            raise RuleError(f"configuration {path} must contain a JSON object")

    allowed = {
        "include_defaults",
        "rules",
        "exclude",
        "bank_holidays",
        "seasonal_fallbacks",
    }
    unknown_keys = set(config) - allowed
    if unknown_keys:
        raise RuleError(f"configuration has unknown key(s): {', '.join(sorted(unknown_keys))}")

    include_defaults = _boolean(config, "include_defaults", True)
    bank_holidays = _boolean(config, "bank_holidays", True)
    seasonal_fallbacks = _boolean(config, "seasonal_fallbacks", True)
    external_rules = config.get("rules", {})
    if not isinstance(external_rules, dict):
        raise RuleError("configuration entry 'rules' must be an object")
    for name, expression in external_rules.items():
        _validate_rule_entry(name, expression, "configuration")

    exclusions = config.get("exclude", [])
    if not isinstance(exclusions, list) or any(not isinstance(name, str) for name in exclusions):
        raise RuleError("configuration entry 'exclude' must be a list of names")
    if any(not name.strip() for name in exclusions):
        raise RuleError("configuration entry 'exclude' contains an empty name")

    raw_rules = dict(defaults) if include_defaults else {}
    raw_rules.update(external_rules)
    expressions: dict[str, _Expression] = {}
    for name, expression in raw_rules.items():
        _validate_rule_entry(name, expression, "rules")
        expressions[name] = _parse_expression(name, expression, raw_rules)
    _validate_cycles(expressions)

    bound_cache: dict[str, int] = {}

    def cumulative_bound(name: str) -> int:
        if name in bound_cache:
            return bound_cache[name]
        expression = expressions[name]
        bound = sum(_offset_bound(offset) for offset in expression.offsets)
        if expression.kind == "reference":
            bound += cumulative_bound(str(expression.value))
        if bound > _MAX_CUMULATIVE_OFFSET_DAYS:
            raise RuleError(
                f"rule {name!r} named reference chain cumulative offset exceeds "
                f"{_MAX_CUMULATIVE_OFFSET_DAYS} days"
            )
        bound_cache[name] = bound
        return bound

    max_offset = max((cumulative_bound(name) for name in expressions), default=0)
    # Derive the anchor range so bounded offsets crossing multiple New Years
    # still match the requested calendar date.
    anchor_radius = max(1, max_offset // 365 + 1)
    return Rules(
        expressions,
        frozenset(exclusions),
        bank_holidays,
        seasonal_fallbacks,
        anchor_radius,
    )


def _read_json(path: Path, description: str) -> Any:
    try:
        with path.open(encoding="utf-8") as source:
            return json.load(source)
    except OSError as error:
        raise RuleError(f"could not read {description}: {error}") from error
    except json.JSONDecodeError as error:
        raise RuleError(
            f"invalid JSON in {description}: {error.msg} at line {error.lineno}"
        ) from error


def _boolean(config: dict[str, Any], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if not isinstance(value, bool):
        raise RuleError(f"configuration entry '{key}' must be a boolean")
    return value


def _validate_rule_entry(name: object, expression: object, source: str) -> None:
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise RuleError(f"{source} rule name must be a non-empty string without outer whitespace")
    if name.casefold() == "easter":
        raise RuleError(f"{source} rule 'Easter' conflicts with the built-in Easter base")
    if not isinstance(expression, str) or not expression.strip():
        raise RuleError(f"{source} rule {name!r} expression must be a non-empty string")


def _parse_expression(name: str, expression: str, rules: dict[str, str]) -> _Expression:
    value = expression.strip()
    kind: str
    base: int | str | tuple[int, int]
    suffix = ""

    fixed = _DATE_BASE.match(value)
    if fixed:
        month, day = int(fixed.group(1)), int(fixed.group(2))
        try:
            date(2000, month, day)  # Leap-day expressions are valid in leap anchor years.
        except ValueError as error:
            raise RuleError(f"rule {name!r} has invalid fixed date {fixed.group(0)!r}") from error
        kind, base, suffix = "fixed", (month, day), value[fixed.end() :]
    elif (
        value.casefold() == "easter"
        or value.casefold().startswith("easter+")
        or value.casefold().startswith("easter-")
    ):
        kind, base, suffix = "easter", 0, value[6:]
    else:
        references = sorted(rules, key=len, reverse=True)
        reference = next(
            (
                candidate
                for candidate in references
                if value.startswith(candidate)
                and (
                    len(value) == len(candidate)
                    or value[len(candidate) :].lstrip().startswith(("+", "-"))
                )
            ),
            None,
        )
        if reference is None:
            raise RuleError(
                f"rule {name!r} has unknown base or named rule reference in {expression!r}"
            )
        kind, base, suffix = "reference", reference, value[len(reference) :]

    offsets = _parse_offsets(name, suffix)
    return _Expression(kind, base, offsets)


def _parse_offsets(name: str, suffix: str) -> tuple[_Offset, ...]:
    offsets: list[_Offset] = []
    position = 0
    while position < len(suffix):
        while position < len(suffix) and suffix[position].isspace():
            position += 1
        if position == len(suffix):
            break
        match = _OFFSET.match(suffix, position)
        if match is None or match.end() == position:
            raise RuleError(f"rule {name!r} has invalid suffix near {suffix[position:]!r}")
        sign, amount_text, unit, weekday = match.groups()
        unit = unit.lower() if unit else None
        weekday = weekday.lower() if weekday else None
        if amount_text is None and unit is None and weekday is None:
            raise RuleError(f"rule {name!r} has incomplete offset {match.group(0)!r}")
        if amount_text is not None and len(amount_text) > 4:
            raise RuleError(f"rule {name!r} offset amounts cannot exceed 3660")
        amount = int(amount_text) if amount_text is not None else 1
        if amount > _MAX_CUMULATIVE_OFFSET_DAYS:
            raise RuleError(f"rule {name!r} offset amounts cannot exceed 3660")
        if amount == 0 and weekday is not None:
            amount = 1  # The legacy template treated an omitted/zero weekday ordinal as one.
        if amount <= 0:
            raise RuleError(f"rule {name!r} offset amounts must be positive")
        if unit in {"d", "m"} and weekday is not None:
            raise RuleError(f"rule {name!r} cannot combine a {unit!r} offset with a weekday")
        offsets.append(_Offset(1 if sign == "+" else -1, amount, unit or "d", weekday))
        position = match.end()
    if sum(_offset_bound(offset) for offset in offsets) > _MAX_CUMULATIVE_OFFSET_DAYS:
        raise RuleError(
            f"rule {name!r} cumulative offset exceeds {_MAX_CUMULATIVE_OFFSET_DAYS} days"
        )
    return tuple(offsets)


def _offset_bound(offset: _Offset) -> int:
    """Return a conservative calendar-day bound for one offset.

    Args:
        offset (_Offset): Parsed offset to bound.

    Returns:
        int: Maximum estimated day movement caused by the offset.
    """
    if offset.weekday is not None and offset.unit == "w":
        return 31 + 7 * offset.amount
    if offset.weekday is not None or offset.unit == "w":
        return 7 * offset.amount
    if offset.unit == "m":
        return 31 * offset.amount
    return offset.amount


def _validate_cycles(expressions: dict[str, _Expression]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str, chain: list[str]) -> None:
        if name in visiting:
            start = chain.index(name)
            raise RuleError(f"cyclic rule reference: {' -> '.join([*chain[start:], name])}")
        if name in visited:
            return
        visiting.add(name)
        expression = expressions[name]
        if expression.kind == "reference":
            target = str(expression.value)
            visit(target, [*chain, target])
        visiting.remove(name)
        visited.add(name)

    for rule_name in expressions:
        visit(rule_name, [rule_name])


def _evaluate(
    name: str,
    year: int,
    expressions: dict[str, _Expression],
    cache: dict[tuple[str, int], date | None],
) -> date | None:
    key = (name, year)
    if key in cache:
        return cache[key]
    if not 1 <= year <= 9999:
        cache[key] = None
        return None
    expression = expressions[name]
    if expression.kind == "easter":
        result: date | None = _easter(year)
    elif expression.kind == "fixed":
        if not isinstance(expression.value, tuple):
            raise RuleError(f"compiled fixed rule {name!r} has an invalid date")
        month, fixed_day = expression.value
        try:
            result = date(year, month, fixed_day)
        except ValueError:
            result = None
    else:
        result = _evaluate(str(expression.value), year, expressions, cache)
    if result is not None:
        try:
            for offset in expression.offsets:
                result = _apply_offset(result, offset)
        except OverflowError, ValueError:
            result = None
    cache[key] = result
    return result


def _apply_offset(day: date, offset: _Offset) -> date:
    amount = offset.direction * offset.amount
    if offset.weekday is None:
        if offset.unit == "m":
            month_index = day.year * 12 + day.month - 1 + amount
            year, month_zero = divmod(month_index, 12)
            month = month_zero + 1
            return day.replace(
                year=year,
                month=month,
                day=min(day.day, calendar.monthrange(year, month)[1]),
            )
        return day + timedelta(days=amount * (7 if offset.unit == "w" else 1))

    target = _WEEKDAYS[offset.weekday]
    if offset.unit == "w":
        month_start = day.replace(day=1)
        month_end = day.replace(day=calendar.monthrange(day.year, day.month)[1])
        if offset.direction > 0:
            week_one_monday = month_start - timedelta(days=month_start.isoweekday() - 1)
            return week_one_monday + timedelta(days=target - 1 + 7 * (offset.amount - 1))
        days_to_last = (month_end.isoweekday() - target) % 7
        last_occurrence = month_end - timedelta(days=days_to_last)
        return last_occurrence - timedelta(days=7 * (offset.amount - 1))

    current = day.isoweekday()
    if offset.direction > 0:
        return day + timedelta(days=(target - current) % 7 + 7 * (offset.amount - 1))
    return day - timedelta(days=(current - target) % 7 + 7 * (offset.amount - 1))


def _easter(year: int) -> date:
    """Return Gregorian Easter Sunday using the Meeus/Jones/Butcher algorithm.

    Args:
        year (int): Gregorian calendar year.

    Returns:
        date: Easter Sunday in the given year.
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    weekday_correction = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday_correction) // 451
    month, day = divmod(h + weekday_correction - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _bank_holidays_on(day: date) -> list[str]:
    events: list[str] = []
    if day.month == 12 and day.day in (26, 27, 28):
        christmas = date(day.year, 12, 25)
        if (christmas.weekday() == 5 and day.day == 27) or (
            christmas.weekday() == 6 and day.day == 26
        ):
            events.append("Christmas Day Bank Holiday")
        if (
            (christmas.weekday() == 5 and day.day == 28)
            or (christmas.weekday() == 6 and day.day == 27)
            or (christmas.weekday() == 4 and day.day == 28)
        ):
            events.append("Boxing Day Bank Holiday")
    if day.month == 1:
        new_year = date(day.year, 1, 1)
        if (new_year.weekday() == 5 and day.day == 3) or (new_year.weekday() == 6 and day.day == 2):
            events.append("New Year's Day Bank Holiday")
    return events


def _seasonal_fallback(day: date) -> str | None:
    easter = _easter(day.year)
    ash_wednesday = easter - timedelta(days=46)
    if ash_wednesday < day < easter:
        days_since_ash = (day - ash_wednesday).days + 1
        sundays_since_ash = (days_since_ash + 2) // 7
        lent_day = days_since_ash - sundays_since_ash
        return f"the {_ordinal(lent_day)} day of Lent"

    christmas_day = date(day.year, 12, 25)
    christmas_eve = date(day.year, 12, 24)
    first_advent = christmas_day - timedelta(days=21 + christmas_day.isoweekday())
    if first_advent < day < christmas_eve:
        advent_day = (day - first_advent).days + 1
        return f"the {_ordinal(advent_day)} day of Advent"
    return None


def _ordinal(value: int) -> str:
    suffix = "th" if 10 <= value % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"
