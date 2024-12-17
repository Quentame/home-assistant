"""Météo-France coordinator."""

from collections.abc import Callable, Coroutine
from datetime import timedelta
import logging
from typing import Any, TypeVar

from meteofrance_api.client import MeteoFranceClient

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_CITY, CONF_FOLLOW, DOMAIN
# from .models import CityData, FollowData


_LOGGER = logging.getLogger(__name__)
_SCAN_INTERVAL = timedelta(minutes=15)
_SCAN_INTERVAL_RAIN = timedelta(minutes=5)

_T = TypeVar("_T")


class MeteoFranceDataUpdateCoordinator(DataUpdateCoordinator[_T]):
    """Coordinator to manage data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        # conf: CityData | FollowData,
        conf: any,
        entity_id: str,
        client: MeteoFranceClient,
        method: Callable[[MeteoFranceClient], Coroutine[Any, Any, _T]],
    ) -> None:
        """Initialize coordinator."""
        self._entity_id = entity_id
        self._conf = None
        # self._conf = conf
        # self._conf = hass.data[DOMAIN][entity_id]
        self._client = client
        self._method = method
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=_SCAN_INTERVAL_RAIN if "rain" in name else _SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> _T:
        """Update data."""
        self._conf = self.hass.data[DOMAIN][self._entity_id].conf
        if self._conf.type == CONF_FOLLOW:
            self._conf.latitude = self.hass.states.get(
                self._conf.entity_id
            ).attributes.get("latitude")
            self._conf.longitude = self.hass.states.get(
                self._conf.entity_id
            ).attributes.get("longitude")
        # return await self._method if self._conf.type == CONF_CITY else

        #     return await hass.async_add_executor_job(
        #         client.get_forecast, latitude, longitude
        #     )

        #     return await hass.async_add_executor_job(
        #         client.get_warning_current_phenomenoms, department, 0, True
        #     )

        # data: _T = await self.hass.async_add_executor_job(
        #     self._method,
        #     **{"latitude": self._conf.latitude, "longitude": self._conf.longitude}
        #     if self._conf.type == CONF_CITY
        #     else (),
        # )
        data: _T
        if "alert" in self.name:
            data = await self.hass.async_add_executor_job(
                self._method, self._conf.department, 0, True
            )
        else:
            data = await self.hass.async_add_executor_job(
                self._method, self._conf.latitude, self._conf.longitude
            )
            # data = await self.hass.async_add_executor_job(
            #     self._client.get_forecast, 45.73432119386687, 4.858246408765978
            # )
        print(f"data ============== {self.name}")
        if hasattr(data, "position"):
            print(data.position)
            # {'lat': 45.708324, 'lon': 4.852569, 'alti': 175, 'name': 'Saint-Fons', 'country': 'FR - France', 'dept': '69', 'rain_product_available': 1, 'timezone': 'Europe/Paris', 'insee': '691990', 'bulletin_cote': 0}
            self._conf.city = data.position["name"]
            self._conf.department = data.position.get("dept")
            self._conf.country = data.position["country"]
        else:
            print("alert")

        print(data)
        self.hass.data[DOMAIN][self._entity_id].conf = self._conf
        return data
