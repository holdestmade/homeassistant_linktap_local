import logging

import voluptuous as vol
from homeassistant.components.valve import ValveEntity, ValveEntityFeature
from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (CoordinatorEntity,
                                                      DataUpdateCoordinator)
from homeassistant.util import slugify

from .const import (ATTR_DEFAULT_TIME, ATTR_DURATION, ATTR_STATE, ATTR_VOL,
                    ATTR_VOLUME, DEFAULT_TIME, DEFAULT_VOL, DOMAIN, GW_IP,
                    MANUFACTURER, NAME, TAP_ID)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass, config, async_add_entities, discovery_info=None
):
    """Initialize Valve """
    taps = hass.data[DOMAIN][config.entry_id]["conf"]["taps"]
    valves = []
    for tap in taps:
        coordinator = tap["coordinator"]
        _LOGGER.debug(f"Configuring valve for tap {tap}")
        valves.append(LinktapValve(coordinator, hass, tap))
    async_add_entities(valves, True)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service("pause_valve",
        {vol.Required("hours", default=1): vol.Coerce(int)},
        "_pause_tap"
        )
    platform.async_register_entity_service("start_watering",
        {vol.Required("seconds", default=9000): vol.Coerce(int)},
        "_start_watering"
        )

class LinktapValve(CoordinatorEntity, ValveEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, hass, tap):
        super().__init__(coordinator)
        self._name = tap[NAME]
        self.tap_id = tap[TAP_ID]
        self.tap_api = coordinator.tap_api
        self.platform = "valve"
        self.hass = hass
        self._attr_supported_features = ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
        self._attr_reports_position = False
        self._attr_unique_id = slugify(f"{DOMAIN}_{self.platform}_{self.tap_id}")
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, tap[TAP_ID])
            },
            name=tap[NAME],
            manufacturer=MANUFACTURER,
            configuration_url="http://" + tap[GW_IP] + "/"
        )

    @property
    def name(self):
        return f"{MANUFACTURER} {self._name}"

    @property
    def duration_entity(self) -> str:
        slug = slugify(self._name)
        return f"number.{DOMAIN}_{slug}_watering_duration"

    @property
    def volume_entity(self) -> str:
        slug = slugify(self._name)
        return f"number.{DOMAIN}_{slug}_watering_volume"

    def get_watering_duration(self):
        entity = self.hass.states.get(self.duration_entity)
        if not entity or entity.state == STATE_UNKNOWN:
            _LOGGER.debug(f"Entity {self.duration_entity} unavailable -- using default")
            return DEFAULT_TIME
        return entity.state

    def get_watering_volume(self):
        entity = self.hass.states.get(self.volume_entity)
        if not entity or entity.state == STATE_UNKNOWN:
            _LOGGER.debug(f"Entity {self.volume_entity} unavailable -- using default")
            return float(DEFAULT_VOL)
        return float(entity.state)

    async def async_open_valve(self, **kwargs):
        """Open the valve (start watering)."""
        duration = self.get_watering_duration()
        seconds = int(float(duration)) * 60
        volume = self.get_watering_volume()
        gw_id = self.coordinator.get_gw_id()
        await self.tap_api.turn_on(gw_id, self.tap_id, seconds, volume)
        await self.coordinator.async_request_refresh()

    async def async_close_valve(self, **kwargs):
        """Close the valve (stop watering)."""
        gw_id = self.coordinator.get_gw_id()
        await self.tap_api.turn_off(gw_id, self.tap_id)
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        duration_entity = self.hass.states.get(self.duration_entity)
        is_default = duration_entity is None or duration_entity.state == STATE_UNKNOWN
        volume = self.get_watering_volume()
        return {
            "data": self.coordinator.data,
            "duration_entity": self.duration_entity,
            "volume_entity": self.volume_entity,
            ATTR_DEFAULT_TIME: is_default,
            ATTR_DURATION: self.get_watering_duration(),
            ATTR_VOL: volume != 0,
            ATTR_VOLUME: volume,
        }

    @property
    def is_closed(self):
        data = self.coordinator.data
        if not data or ATTR_STATE not in data:
            return None
        return not bool(data[ATTR_STATE])

    async def _pause_tap(self, hours=None):
        if hours is None:
            hours = 1
        _LOGGER.debug(f"Pausing {self.entity_id} for {hours} hours")
        gw_id = self.coordinator.get_gw_id()
        await self.tap_api.pause_tap(gw_id, self.tap_id, hours)
        await self.coordinator.async_request_refresh()

    async def _start_watering(self, seconds=False):
        if not seconds or seconds == 0:
            seconds = 1439 * 60
        _LOGGER.debug(f"Starting watering via service call for {seconds} seconds")
        gw_id = self.coordinator.get_gw_id()
        await self.tap_api.turn_on(gw_id, self.tap_id, seconds)
        await self.coordinator.async_request_refresh()
