import logging

import voluptuous as vol
from homeassistant.components.switch import SwitchEntity
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
    """Setup the switch platform."""
    taps = hass.data[DOMAIN][config.entry_id]["conf"]["taps"]
    switches = []
    for tap in taps:
        coordinator = tap["coordinator"]
        _LOGGER.debug(f"Configuring switch for tap {tap}")
        switches.append(LinktapSwitch(coordinator, hass, tap))
        switches.append(LinktapPauseSwitch(coordinator, hass, tap))
    async_add_entities(switches, True)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service("pause",
        {vol.Required("hours", default=1): vol.Coerce(int)},
        "_pause_tap"
        )

class LinktapSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, hass, tap):
        super().__init__(coordinator)
        self._name = tap[NAME]
        self._id = tap[TAP_ID]
        self.tap_id = tap[TAP_ID]
        self.tap_api = coordinator.tap_api
        self.platform = "switch"
        self.hass = hass
        self._attr_unique_id = slugify(f"{DOMAIN}_{self.platform}_{self.tap_id}")
        self._attr_icon = "mdi:water-pump"
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
        slug = slugify(self._name)  # HA-native conversion
        return f"number.{DOMAIN}_{slug}_watering_duration"

    @property
    def volume_entity(self) -> str:
        slug = slugify(self._name)
        return f"number.{DOMAIN}_{slug}_watering_volume"

    async def async_turn_on(self, **kwargs):
        duration = self.get_watering_duration()
        seconds = int(float(duration)) * 60
        gw_id = self.coordinator.get_gw_id()
        await self.tap_api.turn_on(gw_id, self.tap_id, seconds, self.get_watering_volume())
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        gw_id = self.coordinator.get_gw_id()
        await self.tap_api.turn_off(gw_id, self.tap_id)
        await self.coordinator.async_request_refresh()

    def get_watering_duration(self):
        entity = self.hass.states.get(self.duration_entity)
        if not entity:
            _LOGGER.debug(f"Entity {self.duration_entity} not found -- setting default")
            return DEFAULT_TIME
        if entity.state == STATE_UNKNOWN:
            _LOGGER.debug(f"Entity {self.duration_entity} state unknown -- setting default")
            return DEFAULT_TIME
        return entity.state

    def get_watering_volume(self):
        entity = self.hass.states.get(self.volume_entity)
        if not entity:
            _LOGGER.debug(f"Entity {self.volume_entity} not found -- setting default")
            return float(DEFAULT_VOL)
        if entity.state == STATE_UNKNOWN:
            _LOGGER.debug(f"Entity {self.volume_entity} state unknown -- setting default")
            return float(DEFAULT_VOL)
        return float(entity.state)

    @property
    def extra_state_attributes(self):
        duration_entity = self.hass.states.get(self.duration_entity)
        is_default = duration_entity is None or duration_entity.state == STATE_UNKNOWN
        volume = self.get_watering_volume()
        data = self.coordinator.data or {}
        return {
            "data": data,
            "duration_entity": self.duration_entity,
            "volume_entity": self.volume_entity,
            ATTR_DEFAULT_TIME: is_default,
            ATTR_DURATION: self.get_watering_duration(),
            ATTR_VOL: volume != 0,
            ATTR_VOLUME: volume,
            ATTR_STATE: data.get(ATTR_STATE),
        }

    @property
    def is_on(self):
        data = self.coordinator.data
        if not data or ATTR_STATE not in data:
            return None
        return bool(data[ATTR_STATE])

    async def _pause_tap(self, hours=None):
        if hours is None:
            hours = 1
        _LOGGER.debug(f"Pausing {self.entity_id} for {hours} hours")
        gw_id = self.coordinator.get_gw_id()
        await self.tap_api.pause_tap(gw_id, self.tap_id, hours)
        await self.coordinator.async_request_refresh()

class LinktapPauseSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, hass, tap):
        super().__init__(coordinator)
        self._name = f"Pause {tap[NAME]}"
        self.tap_name = tap[NAME]  # Store original tap name for correct slug
        self.tap_id = tap[TAP_ID]
        self.platform = "switch"
        self.hass = hass
        self._attr_unique_id = slugify(f"{DOMAIN}_{self.platform}_{self.tap_id}_pause")
        self._attr_icon = "mdi:pause-circle"
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
        return self._name

    @property
    def pause_duration_entity(self) -> str:
        slug = slugify(self.tap_name)  # Use original tap name, not self._name
        return f"number.{DOMAIN}_{slug}_pause_duration"

    @property
    def is_on(self):
        status = self.coordinator.data or {}
        return bool(status.get("is_paused", False))

    async def async_turn_on(self, **kwargs):
        hours = 24
        _LOGGER.debug(f"PauseSwitch: Looking for {self.pause_duration_entity}")
        entity = self.hass.states.get(self.pause_duration_entity)
        if entity and entity.state not in (None, STATE_UNKNOWN):
            _LOGGER.debug(f"PauseSwitch: Found pause duration entity {self.pause_duration_entity} with state {entity.state}")
            try:
                hours = int(float(entity.state))
            except (TypeError, ValueError) as e:
                _LOGGER.warning(f"PauseSwitch: Could not parse pause duration, using default 24: {e}")
        await self._pause_tap(hours=hours)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        await self._pause_tap(hours=0)
        await self.coordinator.async_request_refresh()

    async def _pause_tap(self, hours):
        _LOGGER.debug(f"PauseSwitch: Pausing {self.entity_id} for {hours} hours")
        gw_id = self.coordinator.get_gw_id()
        await self.coordinator.tap_api.pause_tap(gw_id, self.tap_id, hours)
