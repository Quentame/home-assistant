"""Support for testing internet speed via Speedtest.net."""
import logging

from speedtest import Speedtest
import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import CONF_MONITORED_CONDITIONS, CONF_SCAN_INTERVAL
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.dispatcher import dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import HomeAssistantType

from .const import (
    CONF_MANUAL,
    CONF_SERVER_ID,
    DATA_UPDATED,
    DEFAULT_INTERVAL,
    DEFAULT_MANUAL,
    DOMAIN,
    SENSOR_TYPES,
)

_LOGGER = logging.getLogger(__name__)


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_SERVER_ID): cv.positive_int,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_INTERVAL): vol.All(
                    cv.time_period, cv.positive_timedelta
                ),
                vol.Optional(CONF_MANUAL, default=DEFAULT_MANUAL): cv.boolean,
                vol.Optional(
                    CONF_MONITORED_CONDITIONS, default=list(SENSOR_TYPES)
                ): vol.All(cv.ensure_list, [vol.In(list(SENSOR_TYPES))]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass, config):
    """Set up the Speedtest.net component."""

    conf = config.get(DOMAIN)
    if conf is None:
        return True

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=conf
        )
    )

    return True


async def async_setup_entry(hass: HomeAssistantType, entry: ConfigEntry):
    """Set up a config entry."""

    hass.data[DOMAIN] = speedtest = SpeedtestData(
        hass,
        entry.data.get(CONF_SERVER_ID),
        entry.data.get(CONF_MANUAL, DEFAULT_MANUAL),
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_INTERVAL),
    )

    await speedtest.setup()

    # Services
    def update(call):
        """Service call to manually update the data."""
        speedtest.update()

    hass.services.async_register(DOMAIN, "speedtest", update)

    return True


async def async_unload_entry(hass: HomeAssistantType, entry: ConfigEntry):
    """Unload a config entry."""
    return await hass.config_entries.async_forward_entry_unload(entry, SENSOR_DOMAIN)


class SpeedtestData:
    """Get the latest data from speedtest.net."""

    def __init__(self, hass, server_id, manual, scan_interval):
        """Initialize the data object."""
        self.hass = hass
        self._servers = [] if server_id is None else [server_id]
        self._manual = manual
        self._scan_interval = scan_interval
        self.data = None

    async def setup(self):
        """Set up the fetch."""
        if not self._manual:
            async_track_time_interval(self.hass, self.update, self._scan_interval)

    def update(self, now=None):
        """Get the latest data from speedtest.net."""

        _LOGGER.debug("Executing speedtest.net speed test")
        speed = Speedtest()
        speed.get_servers(self._servers)
        speed.get_best_server()
        speed.download()
        speed.upload()
        self.data = speed.results.dict()
        dispatcher_send(self.hass, DATA_UPDATED)
