"""Exercise configuration validation and calendar failure handling in HA."""

import json
from pathlib import Path
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
import voluptuous as vol

from custom_components.ha_special_day.const import DOMAIN


@pytest.fixture
def rules_file(hass: HomeAssistant) -> Path:
    """Create a personal file with deterministic occasions.

    Args:
        hass (HomeAssistant): Home Assistant instance.

    Returns:
        Path: Path to the prepared personal rules file.
    """
    path = Path(hass.config.path("personal.json"))
    path.write_text(
        json.dumps(
            {
                "include_defaults": False,
                "bank_holidays": False,
                "seasonal_fallbacks": False,
                "rules": {"Test Day": "10/24"},
            }
        )
    )
    return path


async def setup_entry(hass: HomeAssistant, **data: object) -> MockConfigEntry:
    """Load entities through the actual config-entry/platform lifecycle.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        data (object): Configuration settings passed to the entry.

    Returns:
        MockConfigEntry: Loaded configuration entry.
    """
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=data, title="Special Day")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_calendar_merge(
    hass: HomeAssistant, rules_file: Path, freezer: FrozenDateTimeFactory
) -> None:
    """Read all overlapping all-day events, dedupe and retain local rules on failure.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        rules_file (Path): Personal rules file prepared by the fixture.
        freezer (FrozenDateTimeFactory): Clock used to control the date during the test.
    """
    freezer.move_to("2026-10-24T12:00:00Z")
    calendar_ranges: list[tuple[str, str]] = []

    async def get_events(call: ServiceCall) -> dict[str, Any]:
        calendar_ranges.append((call.data["start_date_time"], call.data["end_date_time"]))
        if call.data["entity_id"] == "calendar.broken":
            raise HomeAssistantError("offline")
        return {
            "calendar.family": {
                "events": [
                    {"summary": "Birthday", "start": "2026-10-24", "end": "2026-10-25"},
                    {"summary": "Trip", "start": "2026-10-22", "end": "2026-10-26"},
                    {"summary": "Test Day", "start": "2026-10-24", "end": "2026-10-25"},
                    {
                        "summary": "Yesterday",
                        "start": "2026-10-23",
                        "end": "2026-10-24",
                    },
                    {
                        "summary": "Appointment",
                        "start": "2026-10-24T12:00:00+00:00",
                        "end": "2026-10-24T13:00:00+00:00",
                    },
                ]
            }
        }

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    await setup_entry(
        hass,
        rules_file=rules_file.name,
        calendars=["calendar.family", "calendar.broken"],
    )
    attrs = hass.states.get("binary_sensor.special_day").attributes
    assert sorted(attrs["events"]) == ["Birthday", "Test Day", "Trip"]
    assert attrs["calendar_errors"] == ["calendar.broken"]
    assert [
        (
            dt_util.parse_datetime(start).date().isoformat(),
            dt_util.parse_datetime(end).date().isoformat(),
            dt_util.parse_datetime(start).time().isoformat(),
            dt_util.parse_datetime(end).time().isoformat(),
        )
        for start, end in calendar_ranges
    ] == [("2026-10-24", "2027-10-26", "00:00:00", "00:00:00")] * 2
    next_holiday = hass.states.get("sensor.special_day_next_special_day")
    assert next_holiday.state == "365"
    assert next_holiday.attributes["friendly_name"] == "Special Day Next special day"
    assert next_holiday.attributes["name"] == "Test Day"
    assert next_holiday.attributes["date"] == "October 24, 2027"
    assert next_holiday.attributes["source"] == "rule"
    # A multi-day calendar event that started before today stays on the binary
    # sensor, but it is not a future holiday for the countdown sensor.
    assert "holidays" not in next_holiday.attributes


@pytest.mark.freeze_time("2026-10-24T12:00:00Z")
async def test_flow_and_options(hass: HomeAssistant, rules_file: Path) -> None:
    """Reject bad files before saving config and prevent duplicate setup.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        rules_file (Path): Personal rules file prepared by the fixture.
    """
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow["type"] == FlowResultType.FORM
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(flow["flow_id"], {"rules_file": 42})
    failed = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"rules_file": "missing.json"}
    )
    assert failed["errors"] == {"base": "invalid_rules"}
    assert "missing.json" in failed["description_placeholders"]["error"]
    created = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"rules_file": rules_file.name}
    )
    assert created["type"] == FlowResultType.CREATE_ENTRY
    assert created["title"] == "Special Day"
    await hass.async_block_till_done()
    entry = created["result"]
    duplicate = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert duplicate["reason"] == "already_configured"

    options = await hass.config_entries.options.async_init(entry.entry_id)
    invalid = await hass.config_entries.options.async_configure(
        options["flow_id"], {"rules_file": "../outside.json"}
    )
    assert invalid["errors"] == {"base": "invalid_rules"}
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.special_day").state == "on"
    assert hass.states.get("binary_sensor.special_day").attributes["events"] == ["Test Day"]


async def test_invalid_initial_file(hass: HomeAssistant) -> None:
    """Fail setup clearly without leaving entities or a reload service.

    Args:
        hass (HomeAssistant): Home Assistant instance.
    """
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={"rules_file": "missing.json"})
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state == ConfigEntryState.SETUP_ERROR
    assert not hass.services.has_service(DOMAIN, "reload_rules")
    assert hass.states.get("binary_sensor.special_day") is None
    assert hass.states.get("sensor.special_day_next_special_day") is None


async def test_calendar_recovery_and_full_description(
    hass: HomeAssistant, rules_file: Path, freezer: FrozenDateTimeFactory
) -> None:
    """A calendar failure recovers and calendar occasions suppress seasonal text.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        rules_file (Path): Personal rules file prepared by the fixture.
        freezer (FrozenDateTimeFactory): Clock used to control the date during the test.
    """
    freezer.move_to("2026-03-07T12:00:00Z")
    await hass.async_add_executor_job(
        rules_file.write_text, json.dumps({"include_defaults": False})
    )
    calendar_name = "A" * 280
    response: dict[str, object] | None = None

    async def get_events(call: ServiceCall) -> dict[str, object] | None:
        return response

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    await setup_entry(hass, rules_file=rules_file.name, calendars=["calendar.family"])
    state = hass.states.get("binary_sensor.special_day")
    assert "Lent" in state.attributes["description"]
    assert state.attributes["calendar_errors"] == ["calendar.family"]

    response = {
        "calendar.family": {
            "events": [{"summary": calendar_name, "start": "2026-03-07", "end": "2026-03-08"}]
        }
    }
    freezer.move_to("2026-03-07T12:15:01Z")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    state = hass.states.get("binary_sensor.special_day")
    assert state.attributes["description"] == calendar_name
    assert state.attributes["events"] == [calendar_name]
    assert state.attributes["calendar_errors"] == []


@pytest.mark.parametrize("timezone", ["America/New_York", "UTC", "Pacific/Kiritimati"])
async def test_next_holiday_selects_first_tied_holiday(
    hass: HomeAssistant,
    rules_file: Path,
    freezer: FrozenDateTimeFactory,
    timezone: str,
) -> None:
    """Expose individual details for the first holiday on the earliest future date.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        rules_file (Path): Personal rules file prepared by the fixture.
        freezer (FrozenDateTimeFactory): Clock used to control the date during the test.
        timezone (str): Home Assistant timezone used to check date presentation.
    """
    freezer.move_to("2026-10-24T05:00:00Z")
    await hass.config.async_set_time_zone(timezone)
    await hass.async_add_executor_job(
        rules_file.write_text,
        json.dumps(
            {
                "include_defaults": False,
                "bank_holidays": False,
                "seasonal_fallbacks": False,
                "rules": {"Rule party": "10/25"},
            }
        ),
    )

    async def get_events(call: ServiceCall) -> dict[str, Any]:
        return {
            "calendar.family": {
                "events": [
                    {"summary": "Calendar party", "start": "2026-10-25", "end": "2026-10-26"}
                ]
            }
        }

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    await setup_entry(hass, rules_file=rules_file.name, calendars=["calendar.family"])

    next_holiday = hass.states.get("sensor.special_day_next_special_day")
    assert next_holiday.state == "1"
    assert next_holiday.attributes["date"] == "October 25, 2026"
    assert next_holiday.attributes["days_until"] == 1
    assert next_holiday.attributes["weekday"] == "Sunday"
    assert next_holiday.attributes["source"] == "calendar"
    assert next_holiday.attributes["calendar_entity_id"] == "calendar.family"
    assert next_holiday.attributes["name"] == "Calendar party"
    assert next_holiday.attributes["end_date"] == "October 26, 2026"
    assert "holidays" not in next_holiday.attributes

    # Sensor dates are calendar text for the frontend; action dates stay ISO.
    result = await hass.services.async_call(
        DOMAIN,
        "get_holiday",
        {"name": "Calendar party"},
        blocking=True,
        return_response=True,
    )
    assert result["date"] == "2026-10-25"
    assert result["end_date"] == "2026-10-26"
    assert result["days_until"] == 1


async def test_next_holiday_unknown_when_rules_are_empty(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Represent a schedule with no upcoming dates as unknown.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        freezer (FrozenDateTimeFactory): Clock used to control the date during the test.
    """
    freezer.move_to("2026-10-24T12:00:00Z")
    empty_path = Path(hass.config.path("empty.json"))
    await hass.async_add_executor_job(
        empty_path.write_text,
        json.dumps(
            {
                "include_defaults": False,
                "bank_holidays": False,
                "seasonal_fallbacks": False,
            }
        ),
    )
    await setup_entry(hass, rules_file=empty_path.name)

    empty_sensor = hass.states.get("sensor.special_day_next_special_day")
    assert empty_sensor.state == "unknown"
    assert empty_sensor.attributes["name"] is None
    assert empty_sensor.attributes["date"] is None
    assert "holidays" not in empty_sensor.attributes
    assert empty_sensor.attributes["calendar_errors"] == []


async def test_get_holiday_service_matches_and_validates_names(
    hass: HomeAssistant, rules_file: Path, freezer: FrozenDateTimeFactory
) -> None:
    """Return same-day and future holidays with stripped Unicode casefold matching.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        rules_file (Path): Personal rules file prepared by the fixture.
        freezer (FrozenDateTimeFactory): Clock used to control the date during the test.
    """
    freezer.move_to("2026-10-24T12:00:00Z")
    await hass.async_add_executor_job(
        rules_file.write_text,
        json.dumps(
            {
                "include_defaults": False,
                "bank_holidays": False,
                "seasonal_fallbacks": False,
                "rules": {"Straße Festival": "10/25", "Today": "10/24"},
            }
        ),
    )
    entry = await setup_entry(hass, rules_file=rules_file.name)

    future = await hass.services.async_call(
        DOMAIN,
        "get_holiday",
        {"name": "  STRASSE FESTIVAL  "},
        blocking=True,
        return_response=True,
    )
    assert future == {
        "name": "Straße Festival",
        "date": "2026-10-25",
        "days_until": 1,
        "weekday": "Sunday",
        "source": "rule",
    }
    same_day = await hass.services.async_call(
        DOMAIN,
        "get_holiday",
        {"name": "today"},
        blocking=True,
        return_response=True,
    )
    assert same_day["date"] == "2026-10-24"
    assert same_day["days_until"] == 0

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "get_holiday", {"name": "Missing"}, blocking=True, return_response=True
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "get_holiday", {"name": "   "}, blocking=True, return_response=True
        )
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "get_holiday", {"name": ""}, blocking=True, return_response=True
        )
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "get_holiday", {"name": 42}, blocking=True, return_response=True
        )
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "get_holiday", {}, blocking=True, return_response=True
        )

    assert hass.services.has_service(DOMAIN, "get_holiday")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, "get_holiday")


async def test_get_holiday_service_matches_calendar_names_with_outer_whitespace(
    hass: HomeAssistant, rules_file: Path, freezer: FrozenDateTimeFactory
) -> None:
    """Match a padded calendar summary while preserving its display name.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        rules_file (Path): Personal rules file prepared by the fixture.
        freezer (FrozenDateTimeFactory): Clock used to control the date during the test.
    """
    freezer.move_to("2026-10-24T12:00:00Z")

    async def get_events(call: ServiceCall) -> dict[str, Any]:
        return {
            "calendar.family": {
                "events": [
                    {
                        "summary": "  Calendar party  ",
                        "start": "2026-10-25",
                        "end": "2026-10-26",
                    }
                ]
            }
        }

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    await setup_entry(hass, rules_file=rules_file.name, calendars=["calendar.family"])

    result = await hass.services.async_call(
        DOMAIN,
        "get_holiday",
        {"name": "Calendar party"},
        blocking=True,
        return_response=True,
    )

    assert result == {
        "name": "  Calendar party  ",
        "date": "2026-10-25",
        "days_until": 1,
        "weekday": "Sunday",
        "source": "calendar",
        "end_date": "2026-10-26",
        "calendar_entity_id": "calendar.family",
    }


async def test_next_holiday_leap_day_rollover(
    hass: HomeAssistant, rules_file: Path, freezer: FrozenDateTimeFactory
) -> None:
    """Count across leap day, then skip today's holiday instead of returning zero.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        rules_file (Path): Personal rules file prepared by the fixture.
        freezer (FrozenDateTimeFactory): Clock used to control the date during the test.
    """
    freezer.move_to("2028-02-28T12:00:00Z")
    await hass.async_add_executor_job(
        rules_file.write_text,
        json.dumps(
            {
                "include_defaults": False,
                "bank_holidays": False,
                "seasonal_fallbacks": False,
                "rules": {"Leap Day": "2/29"},
            }
        ),
    )
    await setup_entry(hass, rules_file=rules_file.name)
    state = hass.states.get("sensor.special_day_next_special_day")
    assert state.state == "1"
    assert state.attributes["date"] == "February 29, 2028"

    freezer.move_to("2028-02-29T12:00:00Z")
    response = await hass.services.async_call(
        DOMAIN,
        "get_holiday",
        {"name": "Leap Day"},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    assert response["days_until"] == 0
    state = hass.states.get("sensor.special_day_next_special_day")
    assert state.state == "1461"
    assert state.attributes["date"] == "February 29, 2032"


async def test_setup_removes_customized_legacy_description_entity(hass: HomeAssistant) -> None:
    """Remove the retired description registry entity even after a user renamed it.

    Args:
        hass (HomeAssistant): Home Assistant instance.
    """
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={}, title="Special Day")
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    legacy = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_description",
        suggested_object_id="customized_legacy_description",
        config_entry=entry,
    )
    assert legacy.entity_id == "sensor.customized_legacy_description"
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get(legacy.entity_id) is None
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_description") is None
    assert hass.states.get("sensor.special_day_next_special_day") is not None
