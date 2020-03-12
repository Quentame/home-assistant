"""Consts used by Speedtest.net."""
from datetime import timedelta

from homeassistant.const import DATA_RATE_MEGABITS_PER_SECOND, TIME_MILLISECONDS

DOMAIN = "speedtestdotnet"
DATA_UPDATED = f"{DOMAIN}_data_updated"

CONF_SERVER_ID = "server_id"
CONF_MANUAL = "manual"

DEFAULT_INTERVAL = timedelta(hours=1)
DEFAULT_MANUAL = False

SENSOR_TYPES = {
    "ping": ["Ping", TIME_MILLISECONDS],
    "download": ["Download", DATA_RATE_MEGABITS_PER_SECOND],
    "upload": ["Upload", DATA_RATE_MEGABITS_PER_SECOND],
}
