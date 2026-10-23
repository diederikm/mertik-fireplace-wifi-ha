"""Tests for select entity (operating mode)."""

import pytest

from custom_components.mertik.select import (
    MertikModeSelectEntity,
    async_setup_entry,
)
from custom_components.mertik.const import DOMAIN


class TestModeSelect:
    """Test the operating mode select entity."""

    @pytest.fixture
    def select(self, hass, mock_coordinator):
        entity = MertikModeSelectEntity(mock_coordinator, "test_entry", "My Fireplace")
        entity.hass = hass
        return entity

    def test_unique_id(self, select):
        assert select.unique_id == "test_entry-Mode"

    def test_options(self, select):
        assert select.options == ["manual", "eco", "temperature"]

    def test_current_option(self, select, mock_coordinator):
        mock_coordinator.mode = "eco"
        assert select.current_option == "eco"

    async def test_select_option(self, select, mock_coordinator):
        await select.async_select_option("eco")
        mock_coordinator.set_mode.assert_called_once_with("eco")
        mock_coordinator.async_set_updated_data.assert_called_once_with(None)


class TestSelectPlatformSetup:
    """Test select platform async_setup_entry."""

    async def test_creates_one_entity(self, hass, mock_coordinator, mock_config_entry):
        hass.data[DOMAIN] = {mock_config_entry.entry_id: mock_coordinator}
        added = []
        await async_setup_entry(hass, mock_config_entry, lambda e: added.extend(e))

        assert len(added) == 1
        assert isinstance(added[0], MertikModeSelectEntity)
