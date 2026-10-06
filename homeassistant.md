# Home Assistant

## Range Stop Summaries (0.6.2, Awaiting Deployment)

Explicit stops from a LoRa controller or HA sidebar/button/service produce a
final summary: starter and origin (HA/LoRa), stopper and origin, total transmission
attempts, direct-message ACKs/attempts and successful channel broadcasts. Channels
remain labelled no delivery ACK; a cancelled in-flight ping is unconfirmed. The
summary is sent to each tested target/channel and displayed in Range. For LoRa
stops, the requesting controller receives it as the command reply and is excluded
from duplicate target notifications. Long summaries use UTF-8-safe packets of at
most 150 bytes. Summary packets do not increase range counters.

The first explicit stop owns the result; repeated or concurrent stops do not
resend it or overwrite its actor. A new test clears the old summary and cannot
start while final notifications are finishing. Failed notifications do not undo
the stop, and HA retains their delivery results. Shutdown/unload does not broadcast
summaries; the in-memory Range result resets on restart, while transmitted summary
messages remain in the persistent inbox history. A cancelled or expired remote
stop proposal does not stop or summarize anything.

99 Python tests pass, including service/button actor attribution, mixed channel
and DM counts, interrupted sends, simultaneous stops, notification failure and
controller deduplication. Browser fixtures cover the final summary at four widths.
Live radio stop-summary receipt still requires user acceptance after deployment.

## Current Status (0.6.1)

### Numbered target menus (0.6.1)

A bare `range test` or `targets` will reply with an alphabetical numbered menu
of favorite contacts and channels. Select `1` or `1,2`; use `1 every 60s` to
override the displayed interval. `next`/`back` browse longer lists and `cancel`
exits. Selecting does not start a test: the full target/interval proposal still
requires a separate `1`/`confirm`. Each packet fits the 150-byte UTF-8 limit and
the menu expires after two minutes. Numbers are bound to the original list;
removed targets or changed permissions cannot silently redirect a command.

Favorites control this first-version menu's contents, not who may send commands.
Only approved direct controllers may open/use it; channels are destinations,
not newly authorized command sources. Existing explicit-name and natural-language
requests retain their existing validation and confirmation boundaries. The user
was asked to choose favorites/all available/a separate approved target list;
favorites is the current implementation default pending that answer.

83 Python tests, the compiled bridge frame check, geography checks and four-width
Chromium fixtures pass. Published `6bb5dcd` and installed through HACS after HA
backup `2fa9ba3d`, configuration check and restart. Verified module URL v=0.6.1,
142 contacts/channels, remote enabled, two controllers, three favorites, Google
agent retained, range stopped and no pending requests. HA startup outlasted the
initial verifier; later live checks verified recovery without another restart.
No live menu message was sent by the agent; handset acceptance remains pending.
Read `PROJECT_STATUS.md` for the latest state and resume instructions.

The native HA workspace is deployed with Inbox, Compose, Range, Contacts,
Commands and Map. Remote commands and tool-free HA AI interpretation are built;
the separate **MeshCore AI Google** agent is selected and preview-verified.
Remote control is enabled with two user-approved controllers. The user stopped
the successful remotely started OptimusPrime test before this deployment.
The separate Codex agent still needs login reauthorization (OAuth refresh 401).

No build/deployment process remains running. Numbered menus are deployed above;
confirmed remote start is verified, while stop/cancel, fuzzy AI interpretation
and enabled-controller restart testing still await acceptance checks.
Contact URI import/export, discovery schedules and additional map layers remain
in the pipeline, not implemented in native HA. Channel-based controllers are
deferred pending an authorization design.

See [Project status and handover](PROJECT_STATUS.md) for completed features,
acceptance steps, prioritized pipeline and agent resumption instructions. The
version-specific sections below include historical deployment details; the current
deployed version is 0.6.1, not the older map releases.

## Map Sorting And Height (0.5.3)

Map **Sort** offers Name A-Z, Name Z-A, Nearest first and Farthest first.
Distance sorting uses unrounded geodesic metres from **Distance from**, with
deterministic name/ID tie-breaking. Selecting a new reference recalculates the
order. Sorting survives state/name filtering, polling and tab changes. With no
valid reference, distance modes are disabled and revert to Name A-Z.

The repeater list is now viewport-responsive: 480-700px on desktop and 360-560px
on phones, instead of 320/240px. The desktop map expands to match the taller
sidebar; phones retain the compact 340px map and stack the taller list below it.
Four-width browser checks verify ordering, reference clearing, persistence and
minimum list heights alongside existing map/distance checks.

Installed on 2026-10-06 through HACS revision `d2e34a3`, after verified backup
`45a61ce6` and a passing configuration check. A range test was active, so HA was
not restarted and the test remained running. Fresh local browser sessions loaded
the new static files, but the in-memory panel still registered the previous
version URL. The user's existing Safari session subsequently kept the old UI.
Do not treat a static-file-only installation as a completed frontend rollout:
when it is safe to restart HA, update the registered version URL, then reload
the browser tab. MeshCore's refresh icon only refreshes data, not frontend code.
Live 390/1366px checks verify ascending/descending distance order and polling
persistence, with list heights 464/506px. All 43 Python tests and four-width
browser fixtures pass, with zero MeshCore page errors. No radio messages were
sent by the verification, and no firmware/PIN changes were made.

Rollout correction on 2026-10-06: after confirming the user's range test had
stopped, the pending HA restart was completed using verified backup `45a61ce6`.
The registered panel now points to `workspace.js?v=0.5.3`, rather than 0.5.2.
Fresh Safari/WebKit checks confirm Sort is visible below Distance from and
nearest/farthest modes work; desktop list height is 506px. The radio reconnected
with 125 contacts/channels and 92 GPS repeaters, and range remains stopped.
Existing browser tabs must reload the page to replace the old custom element.

## Repeater Distances (0.5.2)

Selecting a repeater marker or list row sets **Distance from** to that repeater.
Each visible list row then shows straight-line distances in kilometres and miles
to one decimal place, including zero for the reference. The dropdown also accepts
any GPS repeater, independently of state/name filters; **None** hides distances.
The reference survives filtering, polling and switching workspace tabs, even if
its marker is filtered out. If the reference disappears or loses valid GPS, the
distances are cleared rather than using stale coordinates.

Distances use Leaflet's geodesic `LatLng.distanceTo`, with metres converted using
1,000 metres/km and 1,609.344 metres/mile. They are approximate spherical-Earth
distances from advertised coordinates, not terrain-adjusted/radio-route distances
or coverage predictions. No radio transmissions or external lookups are needed.
Browser fixtures verify the known BlairOneW/Bethpage pair (369.7 km / 229.7 mi),
zero distance, reference changes/clearing, filter/poll/tab persistence and layout
at 375/390/768/1366px.

Deployed on 2026-10-06: HACS installed `510f2b1` (0.5.2), after verified HA
backup `f7dbac80`, a passing configuration check and restart. Radio connected
with 125 contacts/channels and 92 GPS repeaters; range stopped. Live checks at
390/1366px verify all 11 Indiana rows show km/mi from BlairOneW, with zero at
the reference and persistence through polling. Death Star Repeater shows
8.3 km / 5.2 mi. Existing map selection, state/search filtering, popup close
and PIN-dialog cancellation also pass with zero MeshCore page errors. All 43
Python tests, geography checks and four-width browser fixtures pass. No live
radio messages, firmware updates or PIN changes were made.

## Map State Filter (0.5.1)

The Map sidebar has a **State** dropdown above repeater search. It lists states
represented by GPS repeaters, with counts, and defaults to **All states**.
State and name search filter both markers and list rows; changing either fits
the matching locations. Hidden selections/popups are cleared, and the selected
state survives background refreshes and switching workspace tabs. Counts in the
dropdown reflect all GPS repeaters, independently of the name search.

Locations are classified locally with bundled U.S. Census 2024 cartographic
state boundaries and Turf booleanPointInPolygon. No external geocoding call or
repeater-name guessing is used. Outside-US and unmatched coordinates appear
under **Outside US / unclassified**. Generalized borders and advertised GPS can
be approximate, especially near coasts/state lines; this is not survey data.
See `www/vendor/STATE-DATA.md` for provenance, reproduction and library licenses.

Verification includes `node tests/map_states.cjs` (known locations, non-US
locations, multi-part island states and polygon holes) and four-width browser
fixtures (filter synchronization, search intersections, empty results, polling,
tab re-entry, selection clearing and phone layout).

Deployed on 2026-10-06: HACS installed `3904d0d` (0.5.1) after HA backup
`fbfee7f0`, a passing configuration check and restart. The live radio reports
122 contacts/channels and 89 GPS repeaters, with no running range test.
Live browser checks at 390/1366px confirm Indiana filters to 10 matching rows
and markers, retains its selection during polling and combines with search.
Map selection/zoom/popup close and PIN-dialog cancellation still pass; no
MeshCore page errors or live radio transmissions occurred. All 43 Python tests,
the geography checks and browser fixtures at 375/390/768/1366px pass. The bridge
firmware and PIN were not changed for this update.

## Runtime PIN And Repeater Map (0.5.0)

The sidebar now includes **Map**, showing native-radio repeaters with valid
advertised GPS. Select a marker or its list row: both selections stay in sync,
the map centers at zoom 12, and the name/coordinates/full-map link appear in a
popup. Closing the popup does not clear selection or reopen it on polling.
Fit All restores the overview. The phone layout stacks the map above its list.
Only advertised locations are shown; they are not inferred from radio paths.
Leaflet 1.9.4 and its license are bundled locally; OpenStreetMap bitmap tiles
require internet and retain their attribution.

For PIN-capable ESPHome bridges, the header's **key icon** opens **Update radio
PIN**. Enter the current six-digit Heltec PIN, then **Save & reconnect**. This
does not change the Heltec's own PIN; it updates the bridge to match it.
Runtime support requires one firmware installation using the updated
`meshcore_homeassistant/ble_bridge_package.yaml`. Later PIN changes do not
require changing Secrets or rebuilding firmware.

The bridge saves the runtime PIN in ESP32 preferences and flushes the change
before confirming success. It then clears only that radio's bond and reconnects.
The saved value overrides `meshcore_radio_pin` in Secrets; the Secret remains a
fallback for a newly installed/factory-cleared bridge. Do not factory-reset or
erase preferences unless you intend to remove this saved override.

The HA dialog is admin-only, masked, and does not retain the PIN after submission
or cancellation. It uses HA's already-connected, encrypted ESPHome API directly,
not a HA service call or entity: no PIN is stored in config-entry options, message
history, entities, recorder state or automation traces by this integration.
Only the ESPHome entry matching the configured bridge address is eligible.
Active range tests must be stopped before updating. Sensitive transport errors
are not echoed. Avoid enabling verbose API/protocol debugging when submitting
credentials. ESP32 preference storage is not a hardware vault; physical access
to an unencrypted device can expose stored secrets.

Deployed and verified on 2026-10-05: HACS installed revision `49121ff` (0.5.0)
after verified HA backup `d4e31a28`, a successful core configuration check and
restart. Only ble-proxy-c3 firmware was updated (successful job `3b6fc4175417`),
with ESPHome backup `28e8af89`; Apollo and other devices were untouched.
The authenticated workspace reports the radio connected, 98 contacts/channels,
70 GPS repeaters and no running range test. The matching encrypted bridge
advertises the runtime PIN action and the key dialog is available.

All 43 Python tests pass, including PIN validation, leading zeros, encrypted
bridge matching, active-test protection and sensitive-error redaction. Browser
fixtures pass at 375/390/768/1366px. Live HA browser checks at 390/1366px verify
rendered OSM tiles, list/marker selection, zoom 12, popup close surviving polling,
no control overflow, and masked PIN dialog cancellation, with zero MeshCore page
errors. No PIN was read or changed, and no live messages or range tests were sent.
Actual submission of a newly changed radio PIN remains a deliberate user test;
do not change the working radio PIN merely to test it.

## Native sidebar workspace (0.4.0)

Open **MeshCore** in the Home Assistant sidebar (`/meshcore`). This is an
authenticated, admin-only custom panel hosted by the integration, not an iframe,
Mac server or second radio connection. It reuses the configured native Bluetooth
or PIN-capable BLE bridge connection.

- **Inbox:** incoming and outgoing conversations, replies and explicit delivered,
  unconfirmed, failed and channel-broadcast states. Phones switch between the
  inbox list and a full-width conversation with a Back control.
- **Compose:** multi-recipient messaging, search, contact-type filters, A–Z/Z–A
  sorting, UTF-8 byte validation and actual radio-provided channel names.
- **Range:** multiple targets, editable 5–300-second interval and prefix, Start/Stop,
  live countdown/progress, authenticated starter's name, per-target sent/ACK
  statistics and a transmission log. The Range tab signals an active test even
  when another view is open. Channel broadcasts never count as receiver ACKs.
- **Contacts:** searchable contacts/channels and persisted favorites. Favorites
  do not authorize remote commands until selected and saved in Commands.
- **Commands (0.6.0):** persistent approved direct-contact controllers, optional
  HA conversation-agent interpretation, confirmation/cancellation, command history
  and a non-transmitting AI preview.

History is retained in Home Assistant's native Store, independently for each config
entry, capped at 1,000 messages. Replayed queued messages are deduplicated by sender,
conversation, source timestamp and text. Unknown direct senders can be displayed;
reply becomes available when the radio has a matching contact. Saved history stays
accessible when a previously configured native radio is offline at startup.
Messages received before this version are not recoverable from the old event-only
integration. Mac history and API keys are **not** copied automatically.

Range tests stop on HA restart and are not automatically resumed. Last-used
workspace test targets, prefix and interval persist. The native inbox and favorites
are not implemented for **Existing MeshCore server** entries; their server UI
remains the interface for conversation history.

Contact import/export and discovery scans have **not** yet been migrated into this
native workspace. The original Mac/server implementation remains available in the repo.

### Remote commands and existing HA AI (0.6.0)

1. In Contacts, favorite a direct contact such as OptimusPrime.
2. In Commands, select that controller, enable remote control, choose an optional
   AI interpreter, then Save. A favorite alone never grants permission.
3. From that contact, send `range test OptimusPrime every 30s`. The radio replies
   with the proposal. Send `1` or `confirm` within two minutes to start it.
4. `status` reports the current test without changing it. `stop range test` also
   requires confirmation. `cancel` clears a pending request but does not stop a
   running test. Multiple targets: `range test OptimusPrime and Family every 30s`
   (Family must exactly match an available channel/contact name).

Permissions bind to full radio contact public keys, not advertised names. Controller
permissions, enabled state, agent choice and the last 100 command outcomes persist
in a per-entry HA Store; pending confirmations never survive restart. Queued inbox
messages need a source timestamp within the last 120 seconds. Keep controller clocks
correct; older/future/missing-timestamp messages remain in Inbox but cannot control
the node. Incoming duplicate messages, ambiguous key prefixes and channel messages
cannot trigger commands. **Channel-based controllers are intentionally not enabled:**
a channel sender's displayed name is not individually authenticated. Controllers may
still choose channels as range-test targets; broadcasts never imply delivery ACKs.

Standard commands are handled locally. AI is fallback-only and returns JSON proposals
limited to status/start/stop/clarify/cancel; targets and 5-300-second intervals are
validated again before execution. Requests are rate-limited, bounded to eight queued
commands, and provider waits time out after 25 seconds. Provider errors never cause
an automatic range test. Starter attribution is `Remote: <contact name>`.

The AI selector reuses HA-managed credentials, **not** Mac API keys. Supported
adapters currently include tool-free Codex Conversation, Google, OpenAI and Anthropic
conversation subentries. Agents with home-control APIs or unknown implementations
are blocked, with the check repeated before each provider call. Create a separate
conversation subentry with no Home Assistant control APIs; do not turn off controls
on an existing household assistant. Claude Terminal is not a conversation agent.
Each request uses a new conversation so radio senders cannot share AI chat context.
AI preview consumes a provider request but neither sends a radio message nor creates
a pending command. Radio message text and available target names are sent to the
selected provider; the ordinary HA agent's own prompt also applies.

Live radio confirmation/start/stop must be tested deliberately by the user after
enabling a controller. Browser fixtures and AI preview are safe checks, not a claim
that remote delivery or execution has been field-tested.

Deployment verified 2026-10-06: HACS revision `d02d846`, version 0.6.0, HA backup
`f8aaf3f1`, core check and restart. Radio reconnected, range stopped. 73 Python
checks, geography tests, four-width browser fixtures and live Chromium/WebKit
Commands checks at 390/1366px passed. The separate tool-free **MeshCore AI Google**
agent is selected, using existing HA credentials. Its live preview converted
"Can you keep checking OptimusPrime every half minute?" to a 30-second test
proposal without sending radio traffic. Remote control remains disabled with no
approved controllers until the user opts in. The separate **MeshCore AI** Codex
agent is available but its existing login cannot refresh (HTTP 401); renew that
login before using it. Household assistants, radio PIN and bridge firmware were
not changed.

Verification: local Python tests cover incoming messages during connection startup,
history bounds/replay handling, delivery semantics, authenticated starter attribution,
read-only snapshots and offline history access. `tests/workspace_browser.cjs` checks
375/390/768/1366px layouts, escaped received content, draft preservation, target
selection and interval-controlled Start/Stop using fixture actions only. Run it
with an installed Playwright package (or `PLAYWRIGHT_MODULE` set to its path).
Deployment verified on 2026-10-05: Supervisor HA backup `0bbd3a85` was created
and checked. HACS installed revision `eb32027` (0.4.0), the core configuration
check passed and HA restarted. Live `get_panels` reports `/meshcore` visible in
the sidebar and admin-only; the module returns HTTP 200 and the authenticated
workspace snapshot succeeds. Live browser checks opened Inbox and Range at
390px and 1366px with HA's actual menu/icons and no MeshCore page errors.
Thirty-five Python checks and browser fixture checks at four widths pass.

The radio was unavailable before and immediately after workspace deployment.
The entry remained loaded and the offline workspace was accessible. The user then
changed the radio PIN and saved the matching `meshcore_radio_pin` in ESPHome
Secrets. Rebuilding and installing **only ble-proxy-c3** (job `eeb004f5d8fa`)
resolved the connection: the authenticated HA workspace now reports the radio
available with **96 contacts/channels**, zero new saved messages and no running
range test. No pairing reset was needed; the PIN was not read, displayed or
committed. Apollo and other Bluetooth devices were unchanged.

No live messages or range tests were sent during verification. There is no
automatic Mac history migration. Next deliberate live test: send a new message from
OptimusPrime, confirm the inbox/name, reply, then run/stop a 30-second test and
verify starter attribution, successive transmissions and ACK counts.

## PIN-capable BLE bridge mode (0.3.0)

### Whole-frame reply fix (2026-10-06)

The dedicated bridge now pins upstream
`db6bfdef4681294bf6439d0d001e8dfeb430b556`, including its
[outgoing-message truncation fix](https://github.com/matthew73210/meshcore-ble-bridge/pull/6).
The previous revision split each companion command into independent 20-byte BLE
writes. MeshCore treats each write as a complete command; a direct-message
header consumes 13 bytes, explaining why the recipient got only `Start O` even
though HA recorded the full confirmation and an ACK. This was not an AI failure
or a phone preview issue. The fix queues whole command frames and explicitly
uses writes with response, allowing the GATT stack to handle long writes.

ESPHome backup `77f4c170` preceded firmware installation job `e0a617fa16aa`
(exit 0). Only `ble-proxy-c3` was updated. Wi-Fi, encrypted API, OTA, runtime PIN
and pairing settings were preserved; HA reconnected with 127 contacts/channels,
two approved controllers, remote control enabled and range stopped. No HA
restart, PIN change or agent-triggered radio test was performed.

Post-flash recovery: the initial cached connection status was not sufficient;
the inbox remained stale. Reloading only the native MeshCore config entry while
the test was stopped completed a fresh handshake and retrieved pending messages.
The user's next range command and `1` confirmation arrived in HA and started an
OptimusPrime test at 30s, attributed to `Remote: OptimusPrime`, with its first
ping acknowledged. After bridge updates, verify a fresh handshake and incoming
message rather than relying only on cached health. Do not reload during a test.

`python3 tests/check_bridge_frames.py` tests the actual pinned upstream writer in
a compiled non-radio harness. All 73 existing Python tests also passed.
Handset receipt remains an acceptance check: retry
`Range test OptimusPrime every 30s`, verify the entire confirmation and then
reply `1`. Package/HACS updates alone do not replace bridge firmware; compile
and install the dedicated bridge after changing its external-component pin.

### Setup

For a PIN-protected radio that rejects standard proxy UART writes, use a dedicated
ESPHome `ble_client` connection with `io_capability: keyboard_only` and a passkey
reply. The authenticated BLE session is exposed to HA through a TCP bridge on the
trusted LAN. This does not require a phone, Mac, or weakening radio security.

The package template is `meshcore_homeassistant/ble_bridge_package.yaml`. It pins
[meshcore-ble-bridge](https://github.com/matthew73210/meshcore-ble-bridge) to the
immutable whole-frame-fix revision above. Retain the ESPHome device's board,
Wi-Fi, API encryption and OTA
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

At 0.2.0, direct mode covered messaging and range tests. Version 0.4.0 adds the
sidebar conversation UI and favorites described above. Controller settings, AI
remote-command interpretation, maps and repeater-discovery scheduling remain pending.
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
