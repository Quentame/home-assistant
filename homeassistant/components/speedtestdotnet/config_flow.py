"""Config flow to configure the Speedtest.net integration."""
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL

from .const import CONF_MANUAL, CONF_SERVER_ID, DEFAULT_INTERVAL, DEFAULT_MANUAL
from .const import DOMAIN  # pylint: disable=unused-import

_LOGGER = logging.getLogger(__name__)


class SpeedtestDotNetFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def _show_setup_form(self, user_input=None, errors=None):
        """Show the setup form to the user."""

        if user_input is None:
            user_input = {}

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_MANUAL, default=user_input.get(CONF_MANUAL, CONF_MANUAL)
                    ): bool,
                }
            ),
            errors=errors or {},
        )

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""
        if user_input is None:
            return self._show_setup_form(user_input, None)

        return self.async_create_entry(
            title="Speedtest.net",
            data={
                CONF_SERVER_ID: user_input.get(CONF_SERVER_ID),
                CONF_SCAN_INTERVAL: user_input.get(
                    CONF_SCAN_INTERVAL, DEFAULT_INTERVAL
                ),
                CONF_MANUAL: user_input.get(CONF_MANUAL, DEFAULT_MANUAL),
            },
        )

    async def async_step_import(self, user_input=None):
        """Import a config entry."""
        return await self.async_step_user(user_input)
