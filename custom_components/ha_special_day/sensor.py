"""Days until the next holiday after today."""

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpecialDayConfigEntry
from .entity import SpecialDayEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpecialDayConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the next-holiday countdown entity automatically.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (SpecialDayConfigEntry): Integration configuration entry.
        async_add_entities (AddEntitiesCallback): Callback for registering the platform entities.
    """
    async_add_entities([SpecialDaySensor(entry.runtime_data, entry.entry_id, "next_holiday")])


class SpecialDaySensor(SpecialDayEntity, SensorEntity):
    """Count down to the next strictly future holiday."""

    _attr_name = "Next holiday"
    _attr_native_unit_of_measurement = UnitOfTime.DAYS

    @property
    def native_value(self) -> int | None:
        """Return the days until the next holiday strictly after today.

        Returns:
            int | None: Positive number of days, or None when no holiday is known.
        """
        data = self.coordinator.data
        if not data.next_holidays:
            return None
        return (data.next_holidays[0].day - data.checked.date()).days

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose details for every holiday tied for the next date.

        Returns:
            dict[str, Any]: Next holiday details and calendar read errors.
        """
        data = self.coordinator.data
        holidays = [holiday.as_dict(data.checked.date()) for holiday in data.next_holidays]
        return {
            **(holidays[0] if holidays else {"name": None, "date": None}),
            "holidays": holidays,
            "last_checked": data.checked.isoformat(),
            "calendar_errors": data.calendar_errors,
        }
