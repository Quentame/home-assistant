"""Config flow to configure the Météo-France integration."""

from __future__ import annotations

import logging
from typing import Any

from meteofrance_api.client import MeteoFranceClient
from meteofrance_api.model import Place
import voluptuous as vol

from homeassistant.components.person import DOMAIN as PERSON_DOMAIN
from homeassistant.config_entries import SOURCE_IMPORT, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_CITY, CONF_FOLLOW, CONF_TYPE, CONF_TYPES, DOMAIN

_LOGGER = logging.getLogger(__name__)


class MeteoFranceFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a Météo-France config flow."""

    VERSION = 1
    places: list[Place] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors: dict[str, str] = {}
        _LOGGER.info("async_step_user -----------")
        _LOGGER.info(user_input)

        if user_input is None:
            user_input = {}
        elif user_input.get(CONF_CITY):
            user_input[CONF_TYPE] = CONF_CITY
        elif user_input.get(CONF_FOLLOW):
            user_input[CONF_TYPE] = CONF_FOLLOW

        if not user_input.get(CONF_TYPE):
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_TYPE, default=user_input.get(CONF_TYPE)
                        ): vol.In(CONF_TYPES)
                    }
                ),
                errors=errors or {},
            )

        # Type: static city
        if user_input[CONF_TYPE] == CONF_CITY:
            if not user_input.get(CONF_CITY):
                return await self.async_step_city(user_input, errors)

            city = user_input[CONF_CITY]  # Might be a city name or a postal code
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)

            if not latitude or not longitude:
                client = MeteoFranceClient()
                self.places = await self.hass.async_add_executor_job(
                    client.search_places, city
                )
                _LOGGER.debug("Places search result: %s", self.places)
                if not self.places:
                    errors[CONF_CITY] = "empty"
                    return await self.async_step_city(user_input, errors)

                return await self.async_step_cities()

            # Check if already configured
            await self.async_set_unique_id(f"{latitude}, {longitude}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=city,
                data={
                    CONF_TYPE: CONF_CITY,
                    CONF_LATITUDE: latitude,
                    CONF_LONGITUDE: longitude,
                },
            )

        # Type: follow a person to get weather on the nearest city
        elif user_input[CONF_TYPE] == CONF_FOLLOW:
            if user_input.get(CONF_FOLLOW) and self.hass.states.get(
                user_input[CONF_FOLLOW]
            ).attributes.get("device_trackers"):
                errors = {CONF_FOLLOW: "person with no device trackers"}

            if not user_input.get(CONF_FOLLOW):
                return await self.async_step_follow(user_input, errors)

            # Check if already configured
            await self.async_set_unique_id(
                f"{user_input[CONF_TYPE]};{user_input[CONF_FOLLOW]}"
            )
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Follow {user_input[CONF_FOLLOW]}",
                data={CONF_TYPE: CONF_FOLLOW, CONF_FOLLOW: user_input[CONF_FOLLOW]},
            )

        return await self.async_step_user(user_input, errors)

    async def async_step_city(
        self,
        user_input: dict[str, Any],
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Show the setup form to select a city."""
        _LOGGER.info("async_step_city -----------")
        _LOGGER.info(user_input)

        if user_input.get(CONF_CITY):
            return await self.async_step_user(
                {CONF_TYPE: CONF_CITY, CONF_CITY: user_input[CONF_CITY]}
            )

        return self.async_show_form(
            step_id="city",
            data_schema=vol.Schema(
                {vol.Required(CONF_CITY, default=user_input.get(CONF_CITY, "")): str}
            ),
            errors=errors or {},
        )

    async def async_step_cities(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step where the user choose the city from the API search results."""
        _LOGGER.info("async_step_cities -----------")
        _LOGGER.info(user_input)
        if not user_input:
            if len(self.places) > 1:
                places_for_form: dict[str, str] = {}
                for place in self.places:
                    places_for_form[_build_place_key(place)] = f"{place}"

                return self.async_show_form(
                    step_id="cities",
                    data_schema=vol.Schema(
                        {
                            vol.Required(CONF_CITY): vol.All(
                                vol.Coerce(str), vol.In(places_for_form)
                            )
                        }
                    ),
                )
            user_input = {CONF_CITY: _build_place_key(self.places[0])}

        city_infos = user_input[CONF_CITY].split(";")
        return await self.async_step_user(
            {
                CONF_TYPE: CONF_CITY,
                CONF_CITY: city_infos[0],
                CONF_LATITUDE: city_infos[1],
                CONF_LONGITUDE: city_infos[2],
            }
        )

    async def async_step_follow(
        self,
        user_input: dict[str, Any],
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Show the setup form to select a city."""
        _LOGGER.info("async_step_follow -----------")
        _LOGGER.info(user_input)

        if user_input.get(CONF_FOLLOW):
            return await self.async_step_user(
                {CONF_TYPE: CONF_FOLLOW, CONF_FOLLOW: user_input[CONF_FOLLOW]}
            )

        return self.async_show_form(
            step_id="follow",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FOLLOW): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=PERSON_DOMAIN)
                    ),
                }
            ),
            errors=errors or {},
        )


def _build_place_key(place: Place) -> str:
    return f"{place};{place.latitude};{place.longitude}"
