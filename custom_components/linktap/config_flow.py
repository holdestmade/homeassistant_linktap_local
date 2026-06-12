"""Config flow to configure."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries

from .const import DEFAULT_NAME, DOMAIN, GW_IP
from .linktap_local import LinktapLocal

_LOGGER = logging.getLogger(__name__)


class LinktapFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle a flow start."""
        _LOGGER.debug(f"Starting async_step_user of {DEFAULT_NAME}")

        errors = {}

        if user_input is not None:
            gw_ip = user_input[GW_IP]
            linker = LinktapLocal(self.hass)
            linker.set_ip(gw_ip)
            try:
                gw_id = await linker.fetch_gw_id()
            except Exception as err:  # noqa: BLE001 - surface any connection issue to the user
                _LOGGER.debug(f"Unable to connect to gateway at {gw_ip}: {err}")
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(gw_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_NAME, data=user_input)

        schema = vol.Schema({
            vol.Required(GW_IP): str,
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
