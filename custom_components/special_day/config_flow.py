"""Configure Special Day through the Home Assistant UI."""

from typing import Any

import probatio
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_CALENDARS, CONF_RULES_FILE, DOMAIN
from .coordinator import read_rules
from .rules import RuleError


def options_schema(options: dict[str, Any]) -> probatio.Schema:
    """Describe a personal rules path and optional calendar entities."""
    return probatio.Schema(
        {
            probatio.Optional(
                CONF_RULES_FILE, default=options.get(CONF_RULES_FILE, "")
            ): selector.TextSelector(),
            probatio.Optional(
                CONF_CALENDARS, default=options.get(CONF_CALENDARS, [])
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="calendar", multiple=True)
            ),
        }
    )


class SpecialDayConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up one shared set of Special Day entities."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate the rules before storing configuration."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(
                    read_rules, self.hass, user_input.get(CONF_RULES_FILE, "")
                )
            except (RuleError, OSError, ValueError) as err:
                errors["base"] = "invalid_rules"
                placeholders["error"] = str(err)
            else:
                return self.async_create_entry(title="Special Day", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=options_schema(user_input or {}),
            errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> SpecialDayOptionsFlow:
        """Allow changing the file and calendars after setup."""
        return SpecialDayOptionsFlow()


class SpecialDayOptionsFlow(config_entries.OptionsFlow):
    """Validate changes before replacing working configuration."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the configuration without requiring a Home Assistant restart."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(
                    read_rules, self.hass, user_input.get(CONF_RULES_FILE, "")
                )
            except (RuleError, OSError, ValueError) as err:
                errors["base"] = "invalid_rules"
                placeholders["error"] = str(err)
            else:
                return self.async_create_entry(title="", data=user_input)
        current = dict(self.config_entry.options or self.config_entry.data)
        return self.async_show_form(
            step_id="init",
            data_schema=options_schema(
                user_input if user_input is not None else current
            ),
            errors=errors,
            description_placeholders=placeholders,
        )
