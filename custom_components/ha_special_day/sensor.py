"""Days until the next special day after today."""

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
    """Create the next special day countdown entity automatically.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (SpecialDayConfigEntry): Integration configuration entry.
        async_add_entities (AddEntitiesCallback): Callback for registering the platform entities.
    """
    # Preserve the registered identity when changing the displayed sensor name.
    async_add_entities([SpecialDaySensor(entry.runtime_data, entry.entry_id, "next_holiday")])


class SpecialDaySensor(SpecialDayEntity, SensorEntity):
    """Count down to the next strictly future special day."""

    _attr_name = "Next special day"
    _attr_native_unit_of_measurement = UnitOfTime.DAYS

    @property
    def native_value(self) -> int | None:
        """Return the days until the next special day strictly after today.

        Returns:
            int | None: Positive number of days, or None when no special day is known.
        """
        data = self.coordinator.data
        if not data.next_holidays:
            return None
        return (data.next_holidays[0].day - data.checked.date()).days

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the next special day details directly as sensor attributes.

        Returns:
            dict[str, Any]: Next special day details and calendar read errors.
        """
        data = self.coordinator.data
        holiday = (
            data.next_holidays[0].as_dict(data.checked.date())
            if data.next_holidays
            else {"name": None, "date": None}
        )
        return {
            **holiday,
            "last_checked": data.checked.isoformat(),
            "calendar_errors": data.calendar_errors,
        }
