"""Exercise configuration validation and calendar failure handling in HA."""

import json
from pathlib import Path
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

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
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data=data, title="ha-special-day")
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

    async def get_events(call: ServiceCall) -> dict[str, Any]:
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
    attrs = hass.states.get("sensor.ha_special_day_description").attributes
    assert sorted(attrs["events"]) == ["Birthday", "Test Day", "Trip"]
    assert attrs["calendar_errors"] == ["calendar.broken"]


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
    assert hass.states.get("sensor.ha_special_day_description").state == "Test Day"


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
    assert hass.states.get("binary_sensor.ha_special_day") is None


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
    state = hass.states.get("sensor.ha_special_day_description")
    assert "Lent" in state.state
    assert state.attributes["calendar_errors"] == ["calendar.family"]

    response = {
        "calendar.family": {
            "events": [{"summary": calendar_name, "start": "2026-03-07", "end": "2026-03-08"}]
        }
    }
    freezer.move_to("2026-03-07T12:15:01Z")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    state = hass.states.get("sensor.ha_special_day_description")
    assert state.state == calendar_name[:255]
    assert state.attributes["description"] == calendar_name
    assert state.attributes["events"] == [calendar_name]
    assert state.attributes["calendar_errors"] == []
