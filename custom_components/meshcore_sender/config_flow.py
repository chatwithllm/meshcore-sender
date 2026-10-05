"""Configure the server and passphrase in Devices & Services."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import MeshCoreAuthError, MeshCoreClient, MeshCoreError, normalize_url
from .const import CONF_PASSPHRASE, CONF_URL, DOMAIN


class MeshCoreConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                user_input[CONF_URL] = normalize_url(user_input[CONF_URL])
                self._async_abort_entries_match({CONF_URL: user_input[CONF_URL]})
                client = MeshCoreClient(async_get_clientsession(self.hass),
                                        user_input[CONF_URL], user_input[CONF_PASSPHRASE])
                await client.login()
                await client.request("GET", "/api/range/status")
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            except MeshCoreAuthError:
                errors["base"] = "invalid_auth"
            except MeshCoreError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="MeshCore Sender", data=user_input)
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_URL, default="http://homeassistant.local:8788"): str,
            vol.Required(CONF_PASSPHRASE): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }))

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                client = MeshCoreClient(async_get_clientsession(self.hass),
                                        entry.data[CONF_URL], user_input[CONF_PASSPHRASE])
                await client.login()
            except MeshCoreAuthError:
                errors["base"] = "invalid_auth"
            except MeshCoreError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(step_id="reauth_confirm", errors=errors,
                                    data_schema=vol.Schema({
            vol.Required(CONF_PASSPHRASE): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
        }))
