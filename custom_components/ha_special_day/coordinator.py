"""Refresh local holiday rules and optional calendar events."""

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_CALENDARS, CONF_RULES_FILE
from .rules import RuleError, Rules, load_rules

_LOGGER = logging.getLogger(__name__)


def rules_path(hass: HomeAssistant, filename: str) -> Path:
    """Resolve a personal rules file inside the Home Assistant config folder.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        filename (str): Personal rules path relative to the Home Assistant config folder.

    Returns:
        Path: Resolved rules path inside the config folder.

    Raises:
        RuleError: The file path lies outside the config folder.
    """
    root = Path(hass.config.config_dir).resolve()
    path = (root / filename).resolve()
    if path == root or not path.is_relative_to(root):
        raise RuleError("Rules file must be inside the Home Assistant config folder")
    return path


def read_rules(hass: HomeAssistant, filename: str) -> Rules:
    """Read defaults or the explicitly configured personal file in an executor.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        filename (str): Personal rules path relative to the Home Assistant config folder.

    Returns:
        Rules: Loaded and validated rule evaluator.
    """
    if not filename:
        return load_rules()
    return load_rules(rules_path(hass, filename))


@dataclass(frozen=True)
class SpecialDayData:
    """A complete snapshot of today's occasions."""

    events: list[str]
    checked: datetime
    calendar_errors: list[str]

    @property
    def description(self) -> str:
        """Return text suitable for 'today is ...'.

        Returns:
            str: Complete human-readable description.
        """
        if len(self.events) < 2:
            return "".join(self.events)
        return ", ".join(self.events[:-1]) + " and " + self.events[-1]


class SpecialDayCoordinator(DataUpdateCoordinator[SpecialDayData]):
    """Keep local status current and atomically replace validated rules."""

    def __init__(
        self,
        hass: HomeAssistant,
        options: dict[str, Any],
        entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the coordinator without performing file I/O.

        Args:
            hass (HomeAssistant): Home Assistant instance.
            options (dict[str, Any]): Selected personal rules file and calendars.
            entry (ConfigEntry | None): Integration configuration entry.
        """
        super().__init__(
            hass,
            _LOGGER,
            name="ha-special-day",
            config_entry=entry,
            update_interval=timedelta(minutes=15),
        )
        self.filename = options.get(CONF_RULES_FILE, "")
        self.calendars: list[str] = options.get(CONF_CALENDARS, [])
        self.rules: Rules | None = None
        self._rules_lock = asyncio.Lock()

    async def async_load_rules(self) -> None:
        """Validate the initial rules before forwarding entity platforms."""
        self.rules = await self.hass.async_add_executor_job(read_rules, self.hass, self.filename)

    async def async_reload_rules(self) -> None:
        """Apply rules and state together; leave the working rules on failure.

        Raises:
            HomeAssistantError: Rules could not be reloaded or calendar response data is invalid.
        """
        async with self._rules_lock:
            try:
                candidate = await self.hass.async_add_executor_job(
                    read_rules, self.hass, self.filename
                )
                data = await self._calculate(candidate)
            except (RuleError, OSError, ValueError) as err:
                raise HomeAssistantError(f"Cannot reload ha-special-day rules: {err}") from err
            self.rules = candidate
            self.async_set_updated_data(data)

    async def _async_update_data(self) -> SpecialDayData:
        """Calculate from the last successfully loaded rules.

        Returns:
            SpecialDayData: Current local date and merged occasions.

        Raises:
            UpdateFailed: The initial rules have not been loaded.
        """
        async with self._rules_lock:
            if self.rules is None:
                raise UpdateFailed("Initial ha-special-day rules have not been loaded")
            return await self._calculate(self.rules)

    async def _calculate(self, rules: Rules) -> SpecialDayData:
        """Merge all-day calendar events with today's calculated rules.

        Args:
            rules (Rules): Validated rule evaluator.

        Returns:
            SpecialDayData: Merged local and calendar occasion snapshot.
        """
        now = dt_util.now()
        day = now.date()
        events: list[str] = []
        errors: list[str] = []
        start = datetime.combine(day, time.min, tzinfo=now.tzinfo)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=now.tzinfo)
        for entity_id in self.calendars:
            try:
                async with asyncio.timeout(30):
                    response = await self.hass.services.async_call(
                        "calendar",
                        "get_events",
                        {
                            "entity_id": entity_id,
                            "start_date_time": start.isoformat(),
                            "end_date_time": end.isoformat(),
                        },
                        blocking=True,
                        return_response=True,
                    )
                events.extend(calendar_events(response, entity_id, day))
            except (HomeAssistantError, TimeoutError) as err:
                _LOGGER.warning("Cannot read ha-special-day calendar %s: %s", entity_id, err)
                errors.append(entity_id)
        events.extend(rules.events_on(day, include_fallback=not events))
        return SpecialDayData(list(dict.fromkeys(events)), now, errors)


def calendar_events(response: object, entity_id: str, day: date) -> list[str]:
    """Validate calendar response shapes and select overlapping all-day events.

    Args:
        response (object): Response returned by the calendar get_events action.
        entity_id (str): Calendar entity requested in the service call.
        day (date): Local date whose all-day events should be selected.

    Returns:
        list[str]: Names of overlapping all-day events.

    Raises:
        HomeAssistantError: Rules could not be reloaded or calendar response data is invalid.
    """
    if not isinstance(response, dict) or not isinstance(response.get(entity_id), dict):
        raise HomeAssistantError("Calendar response is missing the requested entity")
    raw_events = response[entity_id].get("events")
    if not isinstance(raw_events, list):
        raise HomeAssistantError("Calendar response has no event list")
    events: list[str] = []
    for event in raw_events:
        if not isinstance(event, dict):
            raise HomeAssistantError("Calendar returned an invalid event")
        start, end, summary = (event.get(key) for key in ("start", "end", "summary"))
        if not (isinstance(start, str) and isinstance(end, str) and isinstance(summary, str)):
            raise HomeAssistantError("Calendar event must contain start, end and summary strings")
        event_start = dt_util.parse_date(start)
        event_end = dt_util.parse_date(end)
        # Timed events have datetime strings rather than date-only values.
        if event_start and event_end and event_start <= day < event_end and summary:
            events.append(summary)
    return events
