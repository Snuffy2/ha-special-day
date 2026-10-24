"""Today's special day status."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpecialDayConfigEntry
from .entity import SpecialDayEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpecialDayConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the status entity automatically."""
    async_add_entities(
        [SpecialDayBinarySensor(entry.runtime_data, entry.entry_id, "status")]
    )


class SpecialDayBinarySensor(SpecialDayEntity, BinarySensorEntity):
    """Indicate whether at least one occasion applies today."""

    _attr_name = None

    @property
    def is_on(self) -> bool:
        """Return today's status."""
        return bool(self.coordinator.data.events)
