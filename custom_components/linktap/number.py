import logging

from homeassistant.components.number import RestoreNumber
from homeassistant.const import UnitOfTime, UnitOfVolume
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (CoordinatorEntity,
                                                      DataUpdateCoordinator)
from homeassistant.util import slugify

from .const import (DEFAULT_TIME, DEFAULT_VOL, DOMAIN, GW_IP, MANUFACTURER,
                    NAME, TAP_ID)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass, config, async_add_entities, discovery_info=None
):
    """Setup the number platform."""
    taps = hass.data[DOMAIN][config.entry_id]["conf"]["taps"]
    vol_unit = hass.data[DOMAIN][config.entry_id]["conf"]["vol_unit"]
    # Normalise the gateway's "L"/"Gal" onto Home Assistant's volume units.
    volume_unit = UnitOfVolume.GALLONS if str(vol_unit).lower().startswith("g") else UnitOfVolume.LITERS
    numbers = []
    for tap in taps:
        """For each tap, we set a number for duration, volume, and pause duration"""
        _LOGGER.debug(f"Configuring numbers for tap {tap}")
        coordinator = tap["coordinator"]
        numbers.append(LinktapNumber(coordinator, hass, tap, "Watering Duration", "mdi:clock", UnitOfTime.MINUTES))
        numbers.append(LinktapNumber(coordinator, hass, tap, "Watering Volume", "mdi:water", volume_unit))
        numbers.append(LinktapPauseDurationNumber(coordinator, hass, tap, "Pause Duration", "mdi:timer-pause", UnitOfTime.HOURS))

    async_add_entities(numbers, True)

class LinktapNumber(CoordinatorEntity, RestoreNumber):
    def __init__(self, coordinator: DataUpdateCoordinator, hass, tap, number_suffix, icon, unit_of_measurement):
        super().__init__(coordinator)
        self._name = tap[NAME]
        self._id = self._name
        self.tap_id = tap[TAP_ID]
        self.platform = "number"
        self._attr_unique_id = slugify(f"{DOMAIN}_{self.platform}_{self.tap_id}_{number_suffix.replace(' ', '_')}")
        self._attr_native_min_value = 0
        self._attr_native_max_value = 120
        self._attr_native_step = 5
        if number_suffix == "Watering Volume":
            self._attr_native_max_value = 2000
            self._attr_native_step = 10
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_icon = icon
        self.number_suffix = number_suffix
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, tap[TAP_ID])
            },
            name=tap[NAME],
            manufacturer=MANUFACTURER,
            model=tap[TAP_ID],
            configuration_url="http://" + tap[GW_IP] + "/"
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        restored_number = await self.async_get_last_number_data()
        if restored_number is not None and restored_number.native_value is not None:
            _LOGGER.debug(f"Restoring value to {restored_number.native_value}")
            self._attr_native_value = restored_number.native_value
        else:
            _LOGGER.debug(f"No value found to restore -- setting default")
            if self.number_suffix == "Watering Volume":
                self._attr_native_value = DEFAULT_VOL
            else:
                self._attr_native_value = DEFAULT_TIME
        self.async_write_ha_state()

    @property
    def name(self):
        return f"{MANUFACTURER} {self._name} {self.number_suffix}"

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        self._attr_native_value = value
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

class LinktapPauseDurationNumber(CoordinatorEntity, RestoreNumber):
    def __init__(self, coordinator: DataUpdateCoordinator, hass, tap, number_suffix, icon, unit_of_measurement):
        super().__init__(coordinator)
        self._name = tap[NAME]
        self.tap_id = tap[TAP_ID]
        self.platform = "number"
        self._attr_unique_id = slugify(f"{DOMAIN}_{self.platform}_{self.tap_id}_pause_duration")
        self._attr_native_min_value = 1
        self._attr_native_max_value = 240
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_icon = icon
        self.number_suffix = number_suffix
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, tap[TAP_ID])
            },
            name=tap[NAME],
            manufacturer=MANUFACTURER,
            model=tap[TAP_ID],
            configuration_url="http://" + tap[GW_IP] + "/"
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        restored_number = await self.async_get_last_number_data()
        if restored_number is not None and restored_number.native_value is not None:
            _LOGGER.debug(f"Restoring pause duration value to {restored_number.native_value}")
            self._attr_native_value = restored_number.native_value
        else:
            _LOGGER.debug(f"No pause duration value found to restore -- setting default to 24")
            self._attr_native_value = 24
        self.async_write_ha_state()

    @property
    def name(self):
        return f"{MANUFACTURER} {self._name} Pause Duration"

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
