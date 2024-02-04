"""The Epic Games Store integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN, SERVICE_DATA
from .coordinator import EGSCalendarUpdateCoordinator

PLATFORMS: list[Platform] = [
    Platform.CALENDAR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Epic Games Store from a config entry."""

    coordinator = EGSCalendarUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Services
    def async_data(call: ServiceCall) -> ServiceResponse:
        """Handle data service call."""
        return {
            **__serialize_data(coordinator, "discount"),
            **__serialize_data(coordinator, "free"),
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_DATA,
        async_data,
        supports_response=SupportsResponse.ONLY,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        hass.services.async_remove(DOMAIN, SERVICE_DATA)

    return unload_ok


def __serialize_data(
    coordinator: EGSCalendarUpdateCoordinator, cal_type: str
) -> JsonObjectType:
    """Serialize data to service response."""
    return {
        cal_type: [
            {str(key): str(value) for key, value in games.items()}
            for games in coordinator.data[cal_type]
        ]
    }
