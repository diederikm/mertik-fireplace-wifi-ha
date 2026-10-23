from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from homeassistant.const import UnitOfTemperature

from .const import DOMAIN
from .mertik import (
    STATE_IGNITING,
    STATE_OFF,
    STATE_ON,
    STATE_SHUTTING_DOWN,
    STATE_STANDBY,
)


async def async_setup_entry(hass, entry, async_add_entities):
    dataservice = hass.data[DOMAIN].get(entry.entry_id)

    async_add_entities([
        MertikAmbientTemperatureSensorEntity(dataservice, entry.entry_id, entry.data["name"]),
        MertikTargetTemperatureSensorEntity(dataservice, entry.entry_id, entry.data["name"]),
        MertikStatusSensorEntity(dataservice, entry.entry_id, entry.data["name"]),
    ])


class MertikSensorEntity(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, dataservice, entry_id, device_name, unique_suffix):
        super().__init__(dataservice)
        self._dataservice = dataservice
        self._attr_unique_id = entry_id + unique_suffix
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=device_name,
            manufacturer="Mertik Maxitrol",
        )


class MertikAmbientTemperatureSensorEntity(MertikSensorEntity):
    _attr_name = "Ambient Temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, dataservice, entry_id, device_name):
        super().__init__(dataservice, entry_id, device_name, "-AmbientTemperature")

    @property
    def native_value(self):
        return self._dataservice.ambient_temperature


class MertikTargetTemperatureSensorEntity(MertikSensorEntity):
    _attr_name = "Target Temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, dataservice, entry_id, device_name):
        super().__init__(dataservice, entry_id, device_name, "-TargetTemperature")

    @property
    def native_value(self):
        return self._dataservice.target_temperature


class MertikStatusSensorEntity(MertikSensorEntity):
    _attr_translation_key = "status"
    _attr_icon = "mdi:fireplace"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [STATE_OFF, STATE_STANDBY, STATE_IGNITING, STATE_ON, STATE_SHUTTING_DOWN]

    def __init__(self, dataservice, entry_id, device_name):
        super().__init__(dataservice, entry_id, device_name, "-Status")

    @property
    def native_value(self):
        return self._dataservice.state

    @property
    def extra_state_attributes(self):
        return self._dataservice.diagnostics
