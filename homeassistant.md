# Home Assistant

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
Deployment is pending either a local Bluetooth adapter or a transport that uses
Home Assistant's proxy-capable Bluetooth APIs. No App has been installed.

## HACS installation verified (2026-10-05)

HACS 2.0.5 registered `chatwithllm/meshcore-sender` as a custom Integration
repository (ID `1403528253`) and installed revision `30ac14c` under
`/config/custom_components/meshcore_sender`. HACS reports `installed: true`.
The live Home Assistant config-flow endpoint loaded the integration and returned
the user form with `url` and `passphrase` fields. The temporary validation flow
was removed. No Home Assistant restart was required for this validation.

Installation is complete, but no MeshCore config entry has been created and no
radio has been connected on Home Assistant. Proxy support is still pending.

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
Deployment, Home Assistant entity loading and real Bluetooth/radio delivery must still
be verified on Home Assistant OS. No live Home Assistant installation has been modified.

Live checklist:

- App starts with the Linux Bluetooth address and receives known contacts.
- Integration authenticates, displays actual names, and survives a server restart.
- OptimusPrime receives multiple pings at a 30-second interval; ACK totals increase.
- Stop stops further sends, and the starter reads Home Assistant.
- A channel broadcast never appears as a confirmed receiver delivery.
- Mac can be locked or powered off while tests continue on Home Assistant.
- Home Assistant reboot starts the App and restores dashboard target/interval choices.
