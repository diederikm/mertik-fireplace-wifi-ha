"""Tests for sensor entity (ambient temperature)."""

from unittest.mock import MagicMock

import pytest

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature

from custom_components.mertik.sensor import (
    MertikAmbientTemperatureSensorEntity,
    MertikStatusSensorEntity,
    MertikTargetTemperatureSensorEntity,
    async_setup_entry,
)
from custom_components.mertik.const import DOMAIN


class TestTemperatureSensor:
    """Test the ambient temperature sensor entity."""

    @pytest.fixture
    def sensor(self, hass, mock_coordinator):
        entity = MertikAmbientTemperatureSensorEntity(
            mock_coordinator, "test_entry", "My Fireplace"
        )
        entity.hass = hass
        return entity

    def test_unique_id(self, sensor):
        assert sensor.unique_id == "test_entry-AmbientTemperature"

    def test_name(self, sensor):
        assert sensor.translation_key == "ambient_temperature"

    def test_has_entity_name(self, sensor):
        assert sensor.has_entity_name is True

    def test_device_class(self, sensor):
        assert sensor.device_class == SensorDeviceClass.TEMPERATURE

    def test_unit(self, sensor):
        assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS

    def test_device_info(self, sensor):
        info = sensor.device_info
        assert info["identifiers"] == {(DOMAIN, "test_entry")}
        assert info["name"] == "My Fireplace"
        assert info["manufacturer"] == "Mertik Maxitrol"

    def test_native_value(self, sensor, mock_coordinator):
        mock_coordinator.ambient_temperature = 21.5
        assert sensor.native_value == 21.5

    def test_native_value_cold(self, sensor, mock_coordinator):
        mock_coordinator.ambient_temperature = 5.0
        assert sensor.native_value == 5.0


class TestSensorPlatformSetup:
    """Test sensor platform async_setup_entry."""

    async def test_creates_entities(self, hass, mock_coordinator, mock_config_entry):
        hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_coordinator}
        added = []
        await async_setup_entry(hass, mock_config_entry, lambda e: added.extend(e))

        assert [type(e) for e in added] == [
            MertikAmbientTemperatureSensorEntity,
            MertikTargetTemperatureSensorEntity,
            MertikStatusSensorEntity,
        ]


class TestTargetTemperatureSensor:
    """Test the target temperature sensor entity."""

    def test_value(self, hass, mock_coordinator):
        mock_coordinator.target_temperature = 20.0
        sensor = MertikTargetTemperatureSensorEntity(mock_coordinator, "test_entry", "My Fireplace")
        assert sensor.unique_id == "test_entry-TargetTemperature"
        assert sensor.native_value == 20.0


class TestStatusSensor:
    """Test the status (off/standby/igniting/on/shutting_down) sensor entity."""

    def test_value_and_options(self, hass, mock_coordinator):
        mock_coordinator.state = "standby"
        sensor = MertikStatusSensorEntity(mock_coordinator, "test_entry", "My Fireplace")
        assert sensor.unique_id == "test_entry-Status"
        assert sensor.device_class == SensorDeviceClass.ENUM
        assert sensor.options == ["off", "standby", "igniting", "on", "shutting_down"]
        assert sensor.native_value == "standby"
