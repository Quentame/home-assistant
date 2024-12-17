"""Météo-France models."""

from dataclasses import dataclass

from meteofrance_api.client import MeteoFranceClient
from meteofrance_api.model import CurrentPhenomenons, Forecast, Rain

from .const import CONF_CITY, CONF_FOLLOW
from .coordinator import MeteoFranceDataUpdateCoordinator


@dataclass
class CityData:
    """City data for Météo-France."""

    type: str  # = CONF_CITY
    city: str | None
    department: str | None
    country: str | None
    latitude: float | None
    longitude: float | None


@dataclass
class FollowData:
    """Follow data for Météo-France."""

    type: str  # = CONF_FOLLOW
    entity_id: float
    city: str | None
    department: str | None
    country: str | None
    latitude: float | None
    longitude: float | None


@dataclass
class DomainData:
    """Domain data for Météo-France."""

    conf: CityData | FollowData

    # type: CONF_CITY | CONF_FOLLOW
    # city: str
    # latitude: float | None
    # longitude: float | None
    # entity_id: float | None

    # client: MeteoFranceClient
    forecast: MeteoFranceDataUpdateCoordinator[Forecast]
    rain: MeteoFranceDataUpdateCoordinator[Rain] | None
    alert: MeteoFranceDataUpdateCoordinator[CurrentPhenomenons] | None
