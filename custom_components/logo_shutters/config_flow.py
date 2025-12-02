"""Config flow for LOGO shutters."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_CLOSE_SWITCH,
    CONF_INITIAL_POSITION,
    CONF_MOVING_DOWN_SENSOR,
    CONF_MOVING_UP_SENSOR,
    CONF_OPEN_SWITCH,
    CONF_OPEN_TIME,
    CONF_CLOSE_TIME,
    CONF_STOP_SEQUENCE,
    CONF_STOP_SEQUENCE_UP,
    CONF_STOP_SEQUENCE_DOWN,
    CONF_SHADE_POSITION,
    DOMAIN,
)


def _base_schema(defaults: dict[str, object]) -> vol.Schema:
    """Build the shared schema for user/options steps."""
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): str,
            vol.Required(CONF_OPEN_SWITCH, default=defaults.get(CONF_OPEN_SWITCH, "")): str,
            vol.Required(CONF_CLOSE_SWITCH, default=defaults.get(CONF_CLOSE_SWITCH, "")): str,
            vol.Optional(
                CONF_MOVING_UP_SENSOR,
                default=defaults.get(CONF_MOVING_UP_SENSOR, ""),
            ): str,
            vol.Optional(
                CONF_MOVING_DOWN_SENSOR,
                default=defaults.get(CONF_MOVING_DOWN_SENSOR, ""),
            ): str,
            vol.Required(
                CONF_OPEN_TIME,
                default=defaults.get(CONF_OPEN_TIME, 20.0),
            ): vol.All(vol.Coerce(float), vol.Range(min=0.1)),
            vol.Required(
                CONF_CLOSE_TIME,
                default=defaults.get(CONF_CLOSE_TIME, 20.0),
            ): vol.All(vol.Coerce(float), vol.Range(min=0.1)),
            vol.Optional(
                CONF_INITIAL_POSITION,
                default=defaults.get(CONF_INITIAL_POSITION, 0),
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            vol.Optional(
                CONF_SHADE_POSITION,
                default=defaults.get(CONF_SHADE_POSITION, 40),
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
            vol.Optional(CONF_STOP_SEQUENCE, default=defaults.get(CONF_STOP_SEQUENCE, "")): str,
            vol.Optional(
                CONF_STOP_SEQUENCE_UP, default=defaults.get(CONF_STOP_SEQUENCE_UP, "")
            ): str,
            vol.Optional(
                CONF_STOP_SEQUENCE_DOWN, default=defaults.get(CONF_STOP_SEQUENCE_DOWN, "")
            ): str,
        }
    )


class LogoShuttersFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LOGO shutters."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(step_id="user", data_schema=_base_schema({}), errors=errors)

    @callback
    def async_get_options_flow(self, config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return LogoShuttersOptionsFlow(config_entry)


class LogoShuttersOptionsFlow(config_entries.OptionsFlow):
    """Handle options for an existing entry."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.entry = entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        current = {**self.entry.data, **self.entry.options}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_base_schema(current),
            errors=errors,
        )
