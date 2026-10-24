"""Shared Special Day entity attributes."""

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SpecialDayCoordinator


class SpecialDayEntity(CoordinatorEntity[SpecialDayCoordinator]):
    """Expose consistent occasion data on both entities."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-star"

    def __init__(self, coordinator: SpecialDayCoordinator, entry_id: str, key: str) -> None:
        """Associate an entity with the singleton Special Day device.

        Args:
            coordinator (SpecialDayCoordinator): Coordinator supplying the occasion snapshot.
            entry_id (str): Stable configuration-entry identifier.
            key (str): Unique entity key within the integration.
        """
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)}, name="Special Day")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the full list even when the sensor state needs truncation.

        Returns:
            dict[str, Any]: Complete occasion data and calendar error identifiers.
        """
        data = self.coordinator.data
        return {
            "events": data.events,
            "description": data.description,
            "last_checked": data.checked.isoformat(),
            "calendar_errors": data.calendar_errors,
        }
