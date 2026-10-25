"""Exercise user journeys through authenticated Home Assistant HTTP APIs."""

from collections.abc import Awaitable, Callable
import json
from pathlib import Path
from typing import Any

from aiohttp.test_utils import TestClient
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ha_special_day.const import DOMAIN


@pytest.fixture
def hass_config_dir(tmp_path: Path) -> str:
    """Give each user journey a writable, isolated Home Assistant config folder.

    Args:
        tmp_path (Path): Temporary directory for this test.

    Returns:
        str: Configuration folder with the storage directory used by Local Calendar.
    """
    (tmp_path / ".storage").mkdir()
    return str(tmp_path)


@pytest.fixture
async def user_client(
    hass: HomeAssistant, hass_client: Callable[[], Awaitable[TestClient]]
) -> TestClient:
    """Expose the same configuration, state, and action APIs used by clients.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        hass_client (Callable[[], Awaitable[TestClient]]): Authenticated client factory.

    Returns:
        TestClient: Client connected to the real Home Assistant HTTP application.
    """
    assert await async_setup_component(hass, "config", {})
    assert await async_setup_component(hass, "api", {})
    # Register calendar routes before aiohttp freezes the test server's router.
    assert await async_setup_component(hass, "file_upload", {})
    assert await async_setup_component(hass, "calendar", {})
    return await hass_client()


async def create_integration(client: TestClient, domain: str, data: dict[str, Any]) -> str:
    """Complete an Add integration form through its public HTTP endpoints.

    Args:
        client (TestClient): Authenticated Home Assistant client.
        domain (str): Integration to configure.
        data (dict[str, Any]): Settings submitted by the user.

    Returns:
        str: Created configuration entry ID.
    """
    response = await client.post("/api/config/config_entries/flow", json={"handler": domain})
    assert response.status == 200
    flow = await response.json()
    assert flow["type"] == "form"
    response = await client.post(f"/api/config/config_entries/flow/{flow['flow_id']}", json=data)
    assert response.status == 200
    created = await response.json()
    assert created["type"] == "create_entry", created
    return created["result"]["entry_id"]


@pytest.mark.freeze_time("2026-10-24T12:00:00Z", ignore=["aiohttp.web_log"])
async def test_personal_rules_user_journey(
    hass: HomeAssistant, user_client: TestClient, freezer: FrozenDateTimeFactory
) -> None:
    """Set up, reload, configure, and remove the integration as a user would.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        user_client (TestClient): Authenticated Home Assistant HTTP client.
        freezer (FrozenDateTimeFactory): Controlled clock.
    """
    freezer.move_to("2026-10-24T12:00:00Z")
    path = Path(hass.config.path("occasions.json"))
    settings = {
        "include_defaults": False,
        "bank_holidays": False,
        "seasonal_fallbacks": False,
        "rules": {"Our anniversary": "10/24"},
    }
    await hass.async_add_executor_job(path.write_text, json.dumps(settings))
    entry_id = await create_integration(user_client, DOMAIN, {"rules_file": path.name})
    await hass.async_block_till_done()

    response = await user_client.get("/api/states/sensor.ha_special_day_description")
    sensor = await response.json()
    assert sensor["state"] == "Our anniversary"
    assert sensor["attributes"]["events"] == ["Our anniversary"]
    response = await user_client.get("/api/states/binary_sensor.ha_special_day")
    assert (await response.json())["state"] == "on"

    await hass.async_add_executor_job(path.write_text, '{"rules": {"Bad Date": "99/99"}}')
    response = await user_client.post("/api/services/ha_special_day/reload_rules", json={})
    assert response.status == 500
    response = await user_client.get("/api/states/sensor.ha_special_day_description")
    assert (await response.json())["state"] == "Our anniversary"

    settings["rules"] = {"Family celebration": "10/24"}
    await hass.async_add_executor_job(path.write_text, json.dumps(settings))
    response = await user_client.post("/api/services/ha_special_day/reload_rules", json={})
    assert response.status == 200
    response = await user_client.get("/api/states/sensor.ha_special_day_description")
    assert (await response.json())["state"] == "Family celebration"

    # Choosing a different file from Configure must actually reload the entities.
    other_path = Path(hass.config.path("other.json"))
    settings["rules"] = {"Tomorrow": "10/25"}
    await hass.async_add_executor_job(other_path.write_text, json.dumps(settings))
    response = await user_client.post(
        "/api/config/config_entries/options/flow", json={"handler": entry_id}
    )
    flow = await response.json()
    response = await user_client.post(
        f"/api/config/config_entries/options/flow/{flow['flow_id']}",
        json={"rules_file": other_path.name, "calendars": []},
    )
    assert response.status == 200
    assert (await response.json())["type"] == "create_entry"
    await hass.async_block_till_done()
    response = await user_client.get("/api/states/binary_sensor.ha_special_day")
    assert (await response.json())["state"] == "off"
    response = await user_client.get("/api/states/sensor.ha_special_day_description")
    sensor = await response.json()
    assert sensor["state"] == ""
    assert sensor["attributes"]["events"] == []

    response = await user_client.delete(f"/api/config/config_entries/entry/{entry_id}")
    assert response.status == 200
    await hass.async_block_till_done()
    for entity_id in ("binary_sensor.ha_special_day", "sensor.ha_special_day_description"):
        response = await user_client.get(f"/api/states/{entity_id}")
        assert response.status == 404
    assert not hass.services.has_service("ha_special_day", "reload_rules")


@pytest.mark.freeze_time("2026-10-25T03:40:00Z", ignore=["aiohttp.web_log"])
async def test_local_calendar_user_journey(
    hass: HomeAssistant, user_client: TestClient, freezer: FrozenDateTimeFactory
) -> None:
    """Real calendar events appear on the next poll and expire at local midnight.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        user_client (TestClient): Authenticated Home Assistant HTTP client.
        freezer (FrozenDateTimeFactory): Controlled clock.
    """
    await hass.config.async_set_time_zone("America/New_York")
    freezer.move_to("2026-10-25T03:40:00Z")
    await create_integration(user_client, "local_calendar", {"calendar_name": "Family"})
    await hass.async_block_till_done()
    path = Path(hass.config.path("calendar_only.json"))
    await hass.async_add_executor_job(
        path.write_text,
        json.dumps(
            {"include_defaults": False, "bank_holidays": False, "seasonal_fallbacks": False}
        ),
    )
    await create_integration(
        user_client,
        DOMAIN,
        {"rules_file": path.name, "calendars": ["calendar.family"]},
    )
    await hass.async_block_till_done()
    response = await user_client.get("/api/states/binary_sensor.ha_special_day")
    assert (await response.json())["state"] == "off"

    for event in (
        {"summary": "Family trip", "start_date": "2026-10-23", "end_date": "2026-10-25"},
        {
            "summary": "Appointment",
            "start_date_time": "2026-10-24T23:00:00-04:00",
            "end_date_time": "2026-10-25T01:00:00-04:00",
        },
    ):
        response = await user_client.post(
            "/api/services/calendar/create_event", json={"entity_id": "calendar.family", **event}
        )
        assert response.status == 200, await response.text()

    # No reload or coordinator calls: the documented 15-minute poll discovers the event.
    freezer.move_to("2026-10-25T03:55:01Z")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    response = await user_client.get("/api/states/sensor.ha_special_day_description")
    sensor = await response.json()
    assert sensor["state"] == "Family trip"
    assert sensor["attributes"]["events"] == ["Family trip"]
    assert sensor["attributes"]["calendar_errors"] == []
    response = await user_client.get("/api/states/binary_sensor.ha_special_day")
    assert (await response.json())["state"] == "on"

    freezer.move_to("2026-10-25T04:00:01Z")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    response = await user_client.get("/api/states/binary_sensor.ha_special_day")
    assert (await response.json())["state"] == "off"
    response = await user_client.get("/api/states/sensor.ha_special_day_description")
    sensor = await response.json()
    assert sensor["state"] == ""
    assert sensor["attributes"]["events"] == []
    assert sensor["attributes"]["calendar_errors"] == []
