from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.components.select import SelectEntity

from .const import DOMAIN
from .mertik import MODE_ECO, MODE_MANUAL, MODE_TEMPERATURE


async def async_setup_entry(hass, entry, async_add_entities):
    dataservice = hass.data[DOMAIN].get(entry.entry_id)

    async_add_entities([
        MertikModeSelectEntity(dataservice, entry.entry_id, entry.data["name"]),
    ])


class MertikModeSelectEntity(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "mode"
    _attr_icon = "mdi:fire-circle"
    _attr_options = [MODE_MANUAL, MODE_ECO, MODE_TEMPERATURE]

    def __init__(self, dataservice, entry_id, device_name):
        super().__init__(dataservice)
        self._dataservice = dataservice
        self._attr_unique_id = entry_id + "-Mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=device_name,
            manufacturer="Mertik Maxitrol",
        )

    @property
    def current_option(self):
        return self._dataservice.mode

    async def async_select_option(self, option: str) -> None:
        await self.hass.async_add_executor_job(self._dataservice.set_mode, option)
        self._dataservice.async_set_updated_data(None)
