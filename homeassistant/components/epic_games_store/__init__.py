"""The Epic Games Store integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.util.json import JsonArrayType

from .const import DOMAIN, SERVICE_DATA
from .coordinator import CalendarType, EGSCalendarUpdateCoordinator

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
        search: str | None = call.data.get("search")
        games = sorted(
            [
                *coordinator.data[CalendarType.DISCOUNT],
                *coordinator.data[CalendarType.FREE],
            ],
            key=lambda game: game["discount_start_at"],
        )
        if search:
            if search in [
                CalendarType.DISCOUNT,
                CalendarType.FREE,
            ]:
                return {
                    search: __serialize_data(coordinator.data[search]),
                }

            filtered_games = list(
                filter(
                    lambda game: game.get("title") == search
                    or game.get("publisher") == search,
                    games,
                )
            )
            if filtered_games:
                return {"search": __serialize_data(filtered_games)}
        return {
            "all": __serialize_data(games),
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


def __serialize_data(games: list[dict[str, Any]]) -> JsonArrayType:
    """Serialize data to service response."""
    return [
        {
            str(key): str(value) if isinstance(value, datetime) else value
            for key, value in game.items()
        }
        for game in games
    ]
