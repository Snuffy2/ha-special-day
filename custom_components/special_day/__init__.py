"""Native entities for calculated special days."""

from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.event import async_track_time_change
import probatio

from .const import DOMAIN
from .coordinator import SpecialDayCoordinator
from .rules import RuleError

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]
type SpecialDayConfigEntry = ConfigEntry[SpecialDayCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SpecialDayConfigEntry) -> bool:
    """Load rules, create entities, and schedule local midnight refreshes.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (SpecialDayConfigEntry): Integration configuration entry.

    Returns:
        bool: True when setup completes.

    Raises:
        ConfigEntryError: The configured rules cannot be loaded.
    """
    coordinator = SpecialDayCoordinator(hass, dict(entry.options or entry.data), entry)
    try:
        await coordinator.async_load_rules()
    except (RuleError, OSError, ValueError) as err:
        raise ConfigEntryError(f"Cannot load Special Day rules: {err}") from err
    entry.runtime_data = coordinator
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def refresh_at_midnight(now: datetime) -> None:
        """Refresh at midnight in the configured Home Assistant timezone.

        Args:
            now (datetime): Time of the local midnight callback.
        """
        await coordinator.async_request_refresh()

    async def reload_rules(call: ServiceCall) -> None:
        """Reload the editable file without unloading entities.

        Args:
            call (ServiceCall): Service call requesting a refresh.
        """
        await coordinator.async_reload_rules()

    entry.async_on_unload(
        async_track_time_change(hass, refresh_at_midnight, hour=0, minute=0, second=0)
    )
    entry.async_on_unload(entry.add_update_listener(async_options_updated))
    hass.services.async_register(DOMAIN, "reload_rules", reload_rules, schema=probatio.Schema({}))
    return True


async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply validated configuration changes.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (ConfigEntry): Integration configuration entry.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SpecialDayConfigEntry) -> bool:
    """Unload platforms; Home Assistant then removes registered callbacks.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (SpecialDayConfigEntry): Integration configuration entry.

    Returns:
        bool: Whether all platforms unloaded successfully.
    """
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.services.async_remove(DOMAIN, "reload_rules")
    return True
