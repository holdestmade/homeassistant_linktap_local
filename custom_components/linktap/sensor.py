import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (PERCENTAGE, UnitOfTime, UnitOfVolume,
                                 UnitOfVolumeFlowRate)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (CoordinatorEntity,
                                                      DataUpdateCoordinator)
from homeassistant.util import slugify

from .const import DOMAIN, GW_IP, MANUFACTURER, NAME, TAP_ID

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass, config, async_add_entities, discovery_info=None
):
    """Setup the sensor platform."""
    taps = hass.data[DOMAIN][config.entry_id]["conf"]["taps"]
    vol_unit = hass.data[DOMAIN][config.entry_id]["conf"]["vol_unit"]
    # The gateway reports its volume unit as "L" or "Gal"; map these onto the
    # units Home Assistant accepts for the water / volume_flow_rate device classes.
    if str(vol_unit).lower().startswith("g"):
        volume_unit = UnitOfVolume.GALLONS  # "gal"
        flow_unit = UnitOfVolumeFlowRate.GALLONS_PER_MINUTE  # "gal/min"
    else:
        volume_unit = UnitOfVolume.LITERS  # "L"
        flow_unit = UnitOfVolumeFlowRate.LITERS_PER_MINUTE  # "L/min"
    sensors = []
    for tap in taps:
        _LOGGER.debug(f"Configuring sensors for tap {tap}")
        coordinator = tap["coordinator"]
        sensors.append(LinktapSensor(coordinator, hass, tap, data_attribute="signal", unit=PERCENTAGE, state_class="measurement", icon="mdi:percent-circle"))
        sensors.append(LinktapSensor(coordinator, hass, tap, data_attribute="battery", unit=PERCENTAGE, device_class="battery", state_class="measurement"))
        sensors.append(LinktapSensor(coordinator, hass, tap, data_attribute="total_duration", unit=UnitOfTime.SECONDS, device_class="duration", state_class="measurement", icon="mdi:clock"))
        sensors.append(LinktapSensor(coordinator, hass, tap, data_attribute="remain_duration", unit=UnitOfTime.SECONDS, device_class="duration", state_class="measurement", icon="mdi:clock"))
        sensors.append(LinktapSensor(coordinator, hass, tap, data_attribute="speed", unit=flow_unit, device_class="volume_flow_rate", state_class="measurement", icon="mdi:speedometer"))
        sensors.append(LinktapSensor(coordinator, hass, tap, data_attribute="volume", unit=volume_unit, device_class="water", state_class="total_increasing", icon="mdi:water"))
        sensors.append(LinktapSensor(coordinator, hass, tap, data_attribute="volume_limit", unit=volume_unit, icon="mdi:water"))
        sensors.append(LinktapSensor(coordinator, hass, tap, data_attribute="failsafe_duration", unit=UnitOfTime.SECONDS, device_class="duration", state_class="measurement", icon="mdi:clock"))
        sensors.append(LinktapSensor(coordinator, hass, tap, data_attribute="plan_mode", unit=None, precision=None, icon="mdi:note"))
        sensors.append(LinktapSensor(coordinator, hass, tap, data_attribute="plan_sn", name="Plan Serial Number", unit=None, precision=None, icon="mdi:note"))
        sensors.append(LinktapSensor(coordinator, hass, tap, data_attribute="plan_mode_string", unit=None, precision=None, icon="mdi:note"))
    async_add_entities(sensors, True)

class LinktapSensor(CoordinatorEntity, SensorEntity):

    def __init__(self, coordinator: DataUpdateCoordinator, hass, tap, data_attribute, unit, name=False, device_class=False, state_class=False, precision=1, icon=False):
        super().__init__(coordinator)
        display_name = name if name else data_attribute.replace("_", " ").title()
        self._name = tap[NAME] + " " + display_name
        self._id = self._name
        self.attribute = data_attribute
        self.tap_id = tap[TAP_ID]
        self.tap_name = tap[NAME]
        self.platform = "sensor"
        self._attr_unique_id = slugify(f"{DOMAIN}_{self.platform}_{data_attribute}_{self.tap_id}")
        if unit is not None:
            self._attr_native_unit_of_measurement = unit
        if precision is not None:
            self._attr_suggested_display_precision = precision
        if icon:
            self._attr_icon = icon
        if device_class:
            self._attr_device_class = device_class
        if state_class:
            # The volume sensor resets to 0 at the end of each watering job, so
            # total_increasing lets HA handle the resets natively for stats.
            self._attr_state_class = state_class

        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, tap[TAP_ID])
            },
            name=tap[NAME],
            manufacturer=MANUFACTURER,
            model=tap[TAP_ID],
            configuration_url="http://" + tap[GW_IP] + "/"
        )

    #Modemode: watering mode (1 - Instant Mode, 2 - Calendar mode, 3 - 7 day mode, 4 - Odd-even mode, 5 -Interval mode, 6 - Month mode).
    def translate_plan_mode(self, mode):
        modes = ['NA', 'Instant', 'Calendar', '7-Day', 'Odd-Even', 'Interval', 'Month']
        return modes[mode]

    @property
    def name(self):
        return f"{MANUFACTURER} {self._id}"

    @property
    def native_value(self):
        attributes = self.coordinator.data
        _LOGGER.debug(f"Sensor state: {attributes}")
        if not attributes:
            return None
        if self.attribute == "plan_mode_string":
            return self.translate_plan_mode(attributes["plan_mode"])
        return attributes.get(self.attribute)
