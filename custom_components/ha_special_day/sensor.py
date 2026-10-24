"""A human-readable description of today's occasions."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpecialDayConfigEntry
from .entity import SpecialDayEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpecialDayConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the description entity automatically.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (SpecialDayConfigEntry): Integration configuration entry.
        async_add_entities (AddEntitiesCallback): Callback for registering the platform entities.
    """
    async_add_entities([SpecialDaySensor(entry.runtime_data, entry.entry_id, "description")])


class SpecialDaySensor(SpecialDayEntity, SensorEntity):
    """Describe all occasions with full text retained in attributes."""

    _attr_name = "Description"

    @property
    def native_value(self) -> str:
        """Respect Home Assistant's 255-character state limit.

        Returns:
            str: Description limited to the state length supported by Home Assistant.
        """
        return self.coordinator.data.description[:255]
