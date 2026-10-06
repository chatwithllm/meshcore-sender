# Home Assistant

## PIN-capable BLE bridge mode (0.3.0)

For a PIN-protected radio that rejects standard proxy UART writes, use a dedicated
ESPHome `ble_client` connection with `io_capability: keyboard_only` and a passkey
reply. The authenticated BLE session is exposed to HA through a TCP bridge on the
trusted LAN. This does not require a phone, Mac, or weakening radio security.

The package template is `meshcore_homeassistant/ble_bridge_package.yaml`. It pins
[meshcore-ble-bridge](https://github.com/matthew73210/meshcore-ble-bridge) v0.1.0's
source commit. Retain the ESPHome device's board, Wi-Fi, API encryption and OTA
settings, remove its `bluetooth_proxy` component, and merge the package. Set
`meshcore_radio_mac` and `meshcore_radio_pin` in ESPHome secrets. Do not expose
secrets in logs or commit the live device configuration.

Compile before flashing. After the device reports BLE authentication and a ready
TCP listener, choose **Radio through a PIN-capable BLE bridge** in MeshCore Sender.
Use the ESPHome device's LAN hostname/IP and port 5000. Setup verifies the actual
MeshCore handshake and loads contact/channel names. The existing range controls,
statistics and incoming-message events apply in bridge mode too.

The bridge TCP endpoint has no authentication or encryption. Restrict it to a
trusted LAN; never forward its port to the internet. The bridge is an experimental
third-party component, currently seeking a maintainer. Live compatibility must be
verified before treating it as an unattended service.

User approved converting ble-proxy-c3 and confirmed the default radio PIN. The
Apollo kitchen sensor is not changed. Before edits, Supervisor created and verified
an ESPHome backup, slug `7c8c8ebd`. The bridge firmware compiled and uploaded
successfully to `192.168.100.189`; its LAN listener on port 5000 is reachable.
HACS installed integration revision `b2cdff1` (0.3.0), HA's configuration check
passed, and HA was restarted. The bridge option is verified in the live setup menu.

Live BLE logs identify the radio as **MeshCore-MacMini** at
`88:56:A6:96:29:59`. Authentication initially failed with reason 81 (pairing
confirmation mismatch). A second firmware
update exposes `button.ble_proxy_c3_repair_heltec_pairing`. This button disables
the BLE client, removes only this radio's bond from the bridge, then reconnects.
It was invoked through HA, but authentication still failed afterward. The user
then updated `meshcore_radio_pin` in ESPHome Secrets. Recompiling and uploading
the firmware with that saved secret resolved authentication. The PIN was not
printed or committed. Changing that secret requires rebuilding the bridge.

Integration 0.3.1 (revision `7654531`) is installed through HACS. Its contact fetch
allows 30 seconds and rejects retrieval failures rather than exposing an empty
successful setup. Thirteen local tests pass. After HA's configuration check and
restart, config entry `01M47GQ1BN3ND5XGNKKG3V7C2B` (**MeshCore BLE bridge**) was
created and verified **loaded** using `192.168.100.189:5000`.

The live radio-connected indicator is on. The target picker exposes 94 choices;
OptimusPrime is selected and the interval is 30 seconds. The range-running
indicator is off and sent/ACK counters are zero. Setup verification sent no range
test messages; real delivery/ACK timing still needs a deliberate test. The bridge
and HA integration now run independently of the Mac. Do not use the original
direct Bluetooth flow for this PIN-protected connection.

## Direct Bluetooth mode (0.2.0)

The HACS integration can now connect directly through Home Assistant's local
Bluetooth adapters or connectable ESPHome Bluetooth proxies. A separate server
App and server passphrase are not required in this mode.

In Devices & Services > Add Integration > MeshCore Sender, choose **Radio through
Home Assistant Bluetooth**, enter the companion radio's Bluetooth MAC address,
and complete the handshake. The radio must be advertising near a proxy; close
the Mac app and phone apps holding its single Bluetooth connection first.

The integration uses the MeshCore SDK for the radio protocol and Home Assistant's
Bluetooth device selection plus bleak-retry-connector for proxy connections. It
keeps a live connection, loads contacts/channel names, and exposes the same range
target/interval controls, Start/Stop buttons and automation actions. Incoming radio
messages fire `meshcore_sender_message` events with address, sender/channel, text
and receive time. Range tests use an async scheduler independent of the browser.
Stop cancels the current task; slow transmissions skip missed ticks rather than burst.
Channel transmissions have their own success counters and never count as receiver ACKs.

Direct mode currently covers messaging and range tests. The standalone server's
conversation UI, favorites/controller settings, AI remote-command interpretation,
maps and repeater-discovery scheduling have not been migrated into direct mode.
The existing **server** connection mode retains those functions on its server.
Native range tests stop on Home Assistant restart; configured radio address and
dashboard target/interval choices persist.

Nine local tests pass, including actual scheduled second-round sends, cancellation,
failed sends followed by successful rounds, and channel ACK semantics. Live proxy
discovery and GATT connection were verified; the companion handshake is blocked
by Bluetooth authentication, so entity loading and radio delivery remain unverified.

## Verified host access (2026-10-05)

The existing Codex Home Assistant header helper provides a working long-lived token.
It authenticates as an owner/admin on `http://homeassistant.local:8123`
(`192.168.20.11:8123`). Home Assistant is version 2026.9.3, with a healthy,
supported Supervisor. Read Supervisor endpoints using the authenticated WebSocket
`supervisor/api` command; the REST proxy intentionally does not expose these paths.
Never print or commit the token; obtain headers through the configured helper.

Bluetooth currently reports two connectable **remote** scanners: `ble-proxy-c3`
and `apollo-msr-2-174b84`. No local scanner was reported. Consequently, the App
below cannot connect to the radio with the host's current Bluetooth setup.
The native integration now uses Home Assistant's proxy-capable Bluetooth APIs.
No separate server App has been installed.

## HACS installation verified (2026-10-05)

HACS 2.0.5 registered `chatwithllm/meshcore-sender` as a custom Integration
repository (ID `1403528253`) and installed revision `e0c73d3` under
`/config/custom_components/meshcore_sender`. HACS reports `installed: true`.
Home Assistant was restarted after a successful configuration check. The live
config flow now offers direct Bluetooth and existing-server connection modes.

Installation is complete, but no MeshCore Sender config entry has been created.
After quitting the Mac app to release Bluetooth, ble-proxy-c3 detected UART device
`88:56:A6:96:29:59` at approximately -83 to -89 dBm. The proxy opened a connection
and discovered services, but UART writes failed with GATT error 5, **Insufficient
authentication**. A second attempt with explicit `BleakClient.pair()` before
notifications still produced that error. Both incomplete setup flows were removed.
Do not claim this is the intended companion until its MeshCore handshake succeeds.

Next: confirm the radio's pairing/PIN requirements and bring it close to the proxy.
Check whether its required authentication is supported by that proxy's firmware;
do not disable radio security or flash a proxy without the user's approval. A local
HA Bluetooth adapter or USB radio connection is an alternative if the proxy cannot
perform the required pairing. No native range test is running. The Mac app was
left closed to keep the radio's Bluetooth connection available for setup.

This provides two parts: a Supervisor-managed App that runs the existing MeshCore
server on Home Assistant OS, and a custom integration with dashboard entities and
automation actions. The Mac is no longer needed once the radio connects to this App.

## Install the server App

1. In Home Assistant, open Settings > Apps > App store > Repositories and add
   `https://github.com/chatwithllm/meshcore-sender`.
2. Install **MeshCore Sender**. Set `bluetooth_address` to the companion radio's
   Bluetooth MAC address, for example `AA:BB:CC:DD:EE:FF`. The Mac's UUID is not valid
   on Linux. The radio must be in range of the Home Assistant host's local adapter.
3. Quit the Mac MeshCore app to release the radio's existing Bluetooth connection.
4. Start the App, enable **Start on boot** and **Watchdog**, then open its web UI.
   Complete the server's initial passphrase setup there. Keep the passphrase private.
5. Enable remote commands, favorites, controllers and optional AI in the web UI.
   This is a new server with its own persistent `/data` storage; the Mac settings
   and API keys are not copied automatically.

The App uses the host's BlueZ service via D-Bus. It does not use Home Assistant
Bluetooth proxies, and will not work if only a remote proxy is available. Bluetooth
pairing and firmware compatibility still require a live device check on your host.
No ingress is advertised: the current web UI uses absolute API paths. Use its Web UI
button or the Home Assistant host's LAN address on port 8788.

## Install dashboard controls

1. In HACS, open Custom repositories and add
   `https://github.com/chatwithllm/meshcore-sender` with type **Integration**.
   Search for **MeshCore Sender** and download it. It is a custom repository,
   not a HACS default listing. Alternatively, install the repository's
   `custom_components/meshcore_sender` folder under `/config/custom_components/`.
2. Restart Home Assistant. Open Settings > Devices & Services > Add Integration,
   search **MeshCore Sender**, and enter `http://homeassistant.local:8788` (or the
   host's LAN IP and configured port) and the server passphrase.
3. Add the MeshCore entities to a dashboard with a built-in Entities card.
   Choose **Range test target**, set **Range test interval** to 30 seconds,
   then press **Start range test**. Use **Stop range test** to stop it.

Target and interval choices persist across Home Assistant restarts. These settings
apply to the next test; changing them does not silently alter a running test.
The active test interval, starter, running state, sent count, acknowledged count,
and channel broadcast count update every ten seconds. The messages-sent sensor
also carries per-target statistics. Channels do not provide delivery ACKs; their
acknowledged count is unavailable, rather than falsely indicating delivery.
The sent count records attempts; channel broadcasts count successful transmissions,
not confirmed reception by another radio.

Actions available in Home Assistant's automation editor:

- `meshcore_sender.start_range_test`: multiple destination IDs, interval, prefix.
- `meshcore_sender.stop_range_test`: stop the current test.
- `meshcore_sender.send_message`: destination IDs and message text.

For OptimusPrime, use target `dm:OptimusPrime` with interval `30` in the start action.
For dashboard use, the picker shows actual contact/channel names from the radio.
If several servers are configured, select the appropriate config entry in actions.

Authentication uses the existing server passphrase and session/CSRF protections.
The integration renews expired sessions after server restart or expiration. It never
publishes credentials in entity states. Treat Home Assistant backups as sensitive,
since config entries contain the passphrase.

## Lifecycle and testing

The server runs independently of the browser and Mac login. It connects lazily when
the integration polls or the web UI is opened. App configuration, inbox, remote
controllers, favorites and AI settings persist under `/data`, included in App backups.
Running range tests and discovery schedules are in memory: after restarting the App,
start them again. A Home Assistant restart alone does not stop the separate App.

This initial release is experimental. The App pins server revision
`0b78351eb97c68e66b07ca4df1f8e1d48a461b89` and MeshCore SDK `2.3.14` for reproducible
builds. Updating the App requires bumping its version and pinned server revision.
The web UI in that revision includes the latest mobile conversation fix.

Development checks cover Python syntax, manifest/config parsing and the authenticated
client against a mock HTTP server, including expired sessions and rejected commands.
The HACS integration is deployed on the user's Home Assistant OS host. The separate
server App is not installed. Home Assistant entity loading and real radio delivery
must still be verified after resolving the direct-mode authentication blocker.

Live checklist:

- App starts with the Linux Bluetooth address and receives known contacts.
- Integration authenticates, displays actual names, and survives a server restart.
- OptimusPrime receives multiple pings at a 30-second interval; ACK totals increase.
- Stop stops further sends, and the starter reads Home Assistant.
- A channel broadcast never appears as a confirmed receiver delivery.
- Mac can be locked or powered off while tests continue on Home Assistant.
- Home Assistant reboot starts the App and restores dashboard target/interval choices.
