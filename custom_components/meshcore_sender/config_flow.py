"""Configure the server and passphrase in Devices & Services."""

import voluptuous as vol
import re

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import MeshCoreAuthError, MeshCoreClient, MeshCoreError, normalize_url
from .const import (CONF_ADDRESS, CONF_CONNECTION, CONF_HOST, CONF_PORT,
                    CONF_PASSPHRASE, CONF_URL, DOMAIN)


class MeshCoreConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["bridge", "bluetooth", "server"])

    async def async_step_bridge(self, user_input=None):
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip().lower()
            port = user_input[CONF_PORT]
            if not host or any(c in host for c in "/@?# ") or "://" in host:
                errors[CONF_HOST] = "invalid_host"
            else:
                await self.async_set_unique_id(f"bridge:{host}:{port}")
                self._abort_if_unique_id_configured()
                from .bluetooth_client import NativeMeshCoreClient
                client = NativeMeshCoreClient(self.hass, f"{host}:{port}", host=host, port=port)
                try:
                    await client.request("GET", "/api/nodes")
                except MeshCoreError:
                    errors["base"] = "cannot_connect_bridge"
                else:
                    return self.async_create_entry(title="MeshCore BLE bridge", data={
                        CONF_CONNECTION: "bridge", CONF_HOST: host, CONF_PORT: port,
                    })
                finally:
                    await client.close()
        return self.async_show_form(step_id="bridge", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=5000): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        }))

    async def async_step_bluetooth(self, user_input=None):
        errors = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            if not re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", address):
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                from .bluetooth_client import NativeMeshCoreClient
                client = NativeMeshCoreClient(self.hass, address)
                try:
                    await client.request("GET", "/api/nodes")
                except MeshCoreError:
                    errors["base"] = "cannot_connect_bluetooth"
                else:
                    return self.async_create_entry(title="MeshCore radio", data={
                        CONF_CONNECTION: "bluetooth", CONF_ADDRESS: address,
                    })
                finally:
                    await client.close()
        found = [f"{info.name} ({info.address})" for info in
                 bluetooth.async_discovered_service_info(self.hass, connectable=True)
                 if "meshcore" in (info.name or "").lower() or
                 "6e400001-b5a3-f393-e0a9-e50e24dcca9e" in
                 {uuid.lower() for uuid in info.service_uuids}]
        return self.async_show_form(step_id="bluetooth", errors=errors,
                                   description_placeholders={"discovered": ", ".join(found) or "None yet"},
                                   data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}))

    async def async_step_server(self, user_input=None):
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
        return self.async_show_form(step_id="server", errors=errors, data_schema=vol.Schema({
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
