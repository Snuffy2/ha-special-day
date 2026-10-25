"""The date of the next special day after today."""

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SpecialDayConfigEntry
from .coordinator import format_event_names
from .entity import SpecialDayEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SpecialDayConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the next special day date entity automatically.

    Args:
        hass (HomeAssistant): Home Assistant instance.
        entry (SpecialDayConfigEntry): Integration configuration entry.
        async_add_entities (AddEntitiesCallback): Callback for registering the platform entities.
    """
    # Preserve the registered identity when changing the displayed sensor name.
    async_add_entities([SpecialDaySensor(entry.runtime_data, entry.entry_id, "next_holiday")])


class SpecialDaySensor(SpecialDayEntity, SensorEntity):
    """Show the date of the next strictly future special day."""

    _attr_name = "Next special day"
    _attr_device_class = SensorDeviceClass.DATE

    @property
    def native_value(self) -> date | None:
        """Return the date of the next special day strictly after today.

        Returns:
            date | None: Next special day date, or None when no future date is known.
        """
        data = self.coordinator.data
        if not data.next_holidays:
            return None
        return data.next_holidays[0].day

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the next special day details directly as sensor attributes.

        Returns:
            dict[str, Any]: Next special day details and calendar read errors.
        """
        data = self.coordinator.data
        events = list(dict.fromkeys(holiday.name for holiday in data.next_holidays))
        holiday = (
            data.next_holidays[0].as_dict(data.checked.date())
            if data.next_holidays
            else {"days_until": None}
        )
        holiday.pop("date", None)
        return {
            **holiday,
            "events": events,
            "name": format_event_names(events),
            "last_checked": data.checked.isoformat(),
            "calendar_errors": data.calendar_errors,
        }
