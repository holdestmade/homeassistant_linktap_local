import logging

import voluptuous as vol
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.valve import ValveEntity, ValveEntityFeature
from homeassistant.const import (ATTR_ENTITY_ID, SERVICE_TURN_OFF,
                                 SERVICE_TURN_ON)
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (CoordinatorEntity,
                                                      DataUpdateCoordinator)
from homeassistant.util import slugify

from .const import ATTR_STATE, DOMAIN, GW_IP, MANUFACTURER, NAME, TAP_ID

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
    def switch_entity(self):
        name = self._name.replace(" ", "_")
        name = name.replace("-", "_")
        return f"switch.{DOMAIN}_{name}".lower()

    async def async_open_valve(self, **kwargs):
        """Open the valve."""
        await self.hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: self.switch_entity},
            blocking=True,
            context=self._context,
        )
        await self.coordinator.async_request_refresh()

    async def async_close_valve(self, **kwargs):
        """Close valve."""
        await self.hass.services.async_call(
            SWITCH_DOMAIN,
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: self.switch_entity},
            blocking=True,
            context=self._context,
        )
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        return {
            "data": self.coordinator.data,
            "switch": self.switch_entity,
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
        await self.coordinator.tap_api.pause_tap(gw_id, self.tap_id, hours)
        await self.coordinator.async_request_refresh()

    async def _start_watering(self, seconds=False):
        if not seconds or seconds == 0:
            seconds = 1439 * 60
        _LOGGER.debug(f"Starting watering via service call for {seconds} seconds")
        gw_id = self.coordinator.get_gw_id()
        await self.coordinator.tap_api.turn_on(gw_id, self.tap_id, seconds)
        await self.coordinator.async_request_refresh()
