"""Exercise config flows, entities, reload, calendars, and unload in HA."""

import json
from pathlib import Path
from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.special_day.const import DOMAIN


@pytest.fixture
def rules_file(hass: HomeAssistant) -> Path:
    """Create a personal file with deterministic occasions."""
    path = Path(hass.config.path("personal.json"))
    path.write_text(
        json.dumps(
            {
                "include_defaults": False,
                "bank_holidays": False,
                "seasonal_fallbacks": False,
                "rules": {"Test Day": "24/10"},
            }
        )
    )
    return path


async def setup_entry(hass: HomeAssistant, **data: object) -> MockConfigEntry:
    """Load entities through the actual config-entry/platform lifecycle."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data=data, title="Special Day"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities_reload_and_unload(
    hass: HomeAssistant, rules_file: Path, freezer: FrozenDateTimeFactory
) -> None:
    """Reload is atomic, updates entities, and stops publishing after unload."""
    freezer.move_to("2026-10-24T12:00:00Z")
    entry = await setup_entry(hass, rules_file=rules_file.name)
    assert hass.states.get("binary_sensor.special_day").state == "on"
    sensor = hass.states.get("sensor.special_day_description")
    assert sensor.state == "Test Day"
    assert sensor.attributes["events"] == ["Test Day"]

    rules_file.write_text('{"rules": {"Bad Date": "99/99"}}')
    with pytest.raises(HomeAssistantError, match="Bad Date"):
        await hass.services.async_call(DOMAIN, "reload_rules", {}, blocking=True)
    assert hass.states.get("sensor.special_day_description").state == "Test Day"
    await entry.runtime_data.async_refresh()
    assert hass.states.get("binary_sensor.special_day").state == "on"

    rules_file.write_text(
        json.dumps(
            {
                "include_defaults": False,
                "bank_holidays": False,
                "seasonal_fallbacks": False,
                "rules": {},
            }
        )
    )
    await hass.services.async_call(DOMAIN, "reload_rules", {}, blocking=True)
    assert hass.states.get("binary_sensor.special_day").state == "off"
    assert hass.states.get("sensor.special_day_description").state == ""
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not hass.services.has_service(DOMAIN, "reload_rules")
    previous = hass.states.get("sensor.special_day_description")
    async_fire_time_changed(
        hass, dt_util.utcnow().replace(day=25, hour=0, minute=0, second=0)
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.special_day_description") == previous


async def test_local_midnight(
    hass: HomeAssistant, rules_file: Path, freezer: FrozenDateTimeFactory
) -> None:
    """A day changes at local midnight rather than UTC midnight."""
    await hass.config.async_set_time_zone("America/New_York")
    freezer.move_to("2026-10-25T03:59:50Z")
    await setup_entry(hass, rules_file=rules_file.name)
    assert hass.states.get("binary_sensor.special_day").state == "on"
    freezer.move_to("2026-10-25T04:00:01Z")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.special_day").state == "off"


async def test_calendar_merge(
    hass: HomeAssistant, rules_file: Path, freezer: FrozenDateTimeFactory
) -> None:
    """Read all overlapping all-day events, dedupe and retain local rules on failure."""
    freezer.move_to("2026-10-24T12:00:00Z")
    calls: list[dict[str, Any]] = []

    async def get_events(call: ServiceCall) -> dict[str, Any]:
        calls.append(dict(call.data))
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
    attrs = hass.states.get("sensor.special_day_description").attributes
    assert attrs["events"] == ["Birthday", "Trip", "Test Day"]
    assert attrs["calendar_errors"] == ["calendar.broken"]
    assert dt_util.parse_datetime(calls[0]["start_date_time"]).hour == 0
    assert calls[0]["end_date_time"].startswith("2026-10-25")


async def test_flow_and_options(hass: HomeAssistant, rules_file: Path) -> None:
    """Reject bad files before saving config and prevent duplicate setup."""
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow["type"] == FlowResultType.FORM
    failed = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"rules_file": "missing.json"}
    )
    assert failed["errors"] == {"base": "invalid_rules"}
    assert "missing.json" in failed["description_placeholders"]["error"]
    created = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"rules_file": rules_file.name}
    )
    assert created["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    entry = created["result"]
    duplicate = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert duplicate["reason"] == "already_configured"

    options = await hass.config_entries.options.async_init(entry.entry_id)
    invalid = await hass.config_entries.options.async_configure(
        options["flow_id"], {"rules_file": "../outside.json"}
    )
    assert invalid["errors"] == {"base": "invalid_rules"}
    assert not entry.options
    saved = await hass.config_entries.options.async_configure(
        options["flow_id"], {"rules_file": "", "calendars": []}
    )
    assert saved["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.LOADED
    assert entry.options == {"rules_file": "", "calendars": []}


async def test_invalid_initial_file(hass: HomeAssistant) -> None:
    """Fail setup clearly without leaving entities or a reload service."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={"rules_file": "missing.json"}
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state == ConfigEntryState.SETUP_ERROR
    assert not hass.services.has_service(DOMAIN, "reload_rules")
    assert hass.states.get("binary_sensor.special_day") is None


async def test_calendar_recovery_and_full_description(
    hass: HomeAssistant, rules_file: Path, freezer: FrozenDateTimeFactory
) -> None:
    """A calendar failure recovers and calendar occasions suppress seasonal text."""
    freezer.move_to("2026-03-07T12:00:00Z")
    rules_file.write_text(json.dumps({"include_defaults": False}))
    calendar_name = "A" * 280
    response: object = None

    async def get_events(call: ServiceCall) -> Any:
        return response

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    entry = await setup_entry(
        hass, rules_file=rules_file.name, calendars=["calendar.family"]
    )
    state = hass.states.get("sensor.special_day_description")
    assert "Lent" in state.state
    assert state.attributes["calendar_errors"] == ["calendar.family"]

    response = {
        "calendar.family": {
            "events": [
                {"summary": calendar_name, "start": "2026-03-07", "end": "2026-03-08"}
            ]
        }
    }
    await entry.runtime_data.async_refresh()
    state = hass.states.get("sensor.special_day_description")
    assert state.state == calendar_name[:255]
    assert state.attributes["description"] == calendar_name
    assert state.attributes["events"] == [calendar_name]
    assert state.attributes["calendar_errors"] == []
