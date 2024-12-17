"""Support for Météo-France weather data."""

from datetime import timedelta
import logging

from meteofrance_api.client import MeteoFranceClient
from meteofrance_api.helpers import is_valid_warning_department
from meteofrance_api.model import CurrentPhenomenons, Forecast, Rain
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_CITY,
    CONF_FOLLOW,
    CONF_TYPE,
    COORDINATOR_ALERT,
    COORDINATOR_FORECAST,
    COORDINATOR_RAIN,
    DOMAIN,
    PLATFORMS,
    UNDO_UPDATE_LISTENER,
)
from .coordinator import MeteoFranceDataUpdateCoordinator
from .models import DomainData, CityData, FollowData

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=15)
SCAN_INTERVAL_RAIN = timedelta(minutes=5)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an Météo-France account from a config entry."""
    print("test_get_state --------------")
    test = hass.states.get("test")
    print(test)
    test = hass.states.get("person.dev")
    print(test)
    print(test.attributes.get("device_trackers"))

    # backward compatibility
    # if entry.data.get(CONF_LATITUDE) and entry.data.get(CONF_LONGITUDE):
    #     entry.data[CONF_TYPE] = CONF_CITY # TypeError: 'mappingproxy' object does not support item assignment

    client = MeteoFranceClient()
    conf: CityData | FollowData
    if entry.data.get(CONF_TYPE) == CONF_CITY or (
        # backward compatibility
        entry.data.get(CONF_LATITUDE) and entry.data.get(CONF_LONGITUDE)
    ):
        # latitude = entry.data[CONF_LATITUDE]
        # longitude = entry.data[CONF_LONGITUDE]
        conf = CityData(
            type=CONF_CITY,
            # city=entry.data[CONF_CITY], # KeyError
            city=None,
            department=None,
            country=None,
            latitude=entry.data[CONF_LATITUDE],
            longitude=entry.data[CONF_LONGITUDE],
        )
    elif entry.data[CONF_TYPE] == CONF_FOLLOW:
        # latitude = hass.config.latitude
        # longitude = hass.config.longitude
        conf = FollowData(
            type=CONF_FOLLOW,
            entity_id=entry.data[CONF_FOLLOW],
            city=None,
            department=None,
            country=None,
            latitude=hass.states.get("person.dev").attributes.get("latitude"),
            longitude=hass.states.get("person.dev").attributes.get("longitude"),
        )

    data = DomainData(
        conf=conf,
        # client=client,
        forecast=None,
        rain=None,
        alert=None,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data

    data = DomainData(
        conf=conf,
        # client=client,
        forecast=MeteoFranceDataUpdateCoordinator(
            hass,
            "forecast",
            conf,
            entry.entry_id,
            client,
            client.get_forecast,
        ),
        rain=MeteoFranceDataUpdateCoordinator(
            hass,
            "rain",
            conf,
            entry.entry_id,
            client,
            client.get_rain,
        ),
        alert=MeteoFranceDataUpdateCoordinator(
            hass,
            "alert",
            conf,
            entry.entry_id,
            client,
            client.get_warning_current_phenomenoms,
        ),
    )

    # Fetch initial data so we have data when entities subscribe
    await data.forecast.async_config_entry_first_refresh()
    forecast_info = data.forecast.data

    # async def _async_update_data_forecast_forecast() -> Forecast:
    #     """Fetch data from API endpoint."""
    #     return await hass.async_add_executor_job(
    #         client.get_forecast, latitude, longitude
    #     )

    # async def _async_update_data_rain() -> Rain:
    #     """Fetch data from API endpoint."""
    #     return await hass.async_add_executor_job(client.get_rain, latitude, longitude)

    # async def _async_update_data_alert() -> CurrentPhenomenons:
    #     """Fetch data from API endpoint."""
    #     return await hass.async_add_executor_job(
    #         client.get_warning_current_phenomenoms, department, 0, True
    #     )

    # coordinator_forecast = DataUpdateCoordinator(
    #     hass,
    #     _LOGGER,
    #     name=f"Météo-France forecast for city {entry.title}",
    #     update_method=_async_update_data_forecast_forecast,
    #     update_interval=SCAN_INTERVAL,
    # )
    # coordinator_rain = None
    # coordinator_alert = None

    # Fetch initial data so we have data when entities subscribe
    # await coordinator_forecast.async_refresh()

    # if not coordinator_forecast.last_update_success:
    #     raise ConfigEntryNotReady


    # Check if rain forecast is available.
    if forecast_info.position.get("rain_product_available") == 1:
        await data.rain.async_config_entry_first_refresh()
    else:
        data.rain = None
        _LOGGER.warning(
            "1 hour rain forecast not available. %s is not in covered zone",
            entry.title,
        )

    department = forecast_info.position.get("dept")
    _LOGGER.debug(
        "Department corresponding to %s is %s",
        entry.title,
        department,
    )
    if department is not None and is_valid_warning_department(department):
        if not hass.data[DOMAIN].get(department):
            await data.alert.async_config_entry_first_refresh()

            if data.alert.last_update_success:
                hass.data[DOMAIN][department] = True
        else:
            data.alert = None
            _LOGGER.warning(
                (
                    "Weather alert for department %s won't be added with city %s, as it"
                    " has already been added within another city"
                ),
                department,
                entry.title,
            )
    else:
        data.alert = None
        _LOGGER.warning(
            (
                "Weather alert not available: The city %s is not in metropolitan France"
                " or Andorre"
            ),
            entry.title,
        )

    undo_listener = entry.add_update_listener(_async_update_listener)

    hass.data[DOMAIN][entry.entry_id] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if hass.data[DOMAIN][entry.entry_id].data.alert:
        department = hass.data[DOMAIN][entry.entry_id].data.forecast.data.position.get(
            "dept"
        )
        hass.data[DOMAIN][department] = False
        _LOGGER.debug(
            (
                "Weather alert for depatment %s unloaded and released. It can be added"
                " now by another city"
            ),
            department,
        )

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # hass.data[DOMAIN][entry.entry_id][UNDO_UPDATE_LISTENER]()
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
