"""MeshCore integration constants."""

from homeassistant.const import Platform

DOMAIN = "meshcore_sender"
CONF_URL = "url"
CONF_PASSPHRASE = "passphrase"
CONF_CONNECTION = "connection"
CONF_ADDRESS = "address"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT,
             Platform.NUMBER, Platform.BUTTON]
