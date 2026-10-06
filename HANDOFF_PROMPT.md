TASK: continue the native MeshCore Home Assistant integration and workspace

START HERE
- 0.6.3 battery monitoring deployed (`388eccd`): one-minute local
  `get_bat()` ADC reads over HA's existing radio transport, voltage measurement
  sensor/history and workspace status. Backup `f37ba470`, config check and restart
  completed; module v=0.6.3, 142 contacts, stopped test, exact favorites/controller/
  AI retention verified. User stopped the test before deployment.
  Solar charger charges two parallel 18650 cells that directly power the battery
  connector (not USB). Fresh 4.209 V readings, Recorder history and live WebKit
  history dialog verified at 375/1366 px. Some requests briefly failed then
  recovered: correctly unavailable, not a stale value presented as current.
  No percentage/current/capacity/runtime estimates, no second radio owner.
- Previous 0.6.2 release (`24937b9`): final range-stop summaries
  with start/stop actor+HA/LoRa source, attempts, direct ACKs and channel TX
  (explicitly no channel delivery ACK). Notify tested targets; LoRa stopper's
  command reply supplies its summary without a duplicate target notification.
  HA retains the summary/failures in Range; transmitted packets persist in inbox.
  Idle/concurrent stops don't resend, cancellation isn't a stop, shutdown sends
  no broadcasts, and summaries don't increase test counts. 99 Python checks
  pass; browser fixtures include the final summary at 375/390/768/1366px.
  HA backup `f889edd7`, HACS install, config check and restart completed; module
  v=0.6.2, radio available, 142 contacts/channels, range stopped, two controllers,
  three favorites and exact saved controller/favorite/AI settings preserved.
  No agent-triggered radio test was sent. Handset receipt for HA and LoRa stops
  remains an acceptance test. Read homeassistant.md and PROJECT_STATUS.md.
- Deployed 0.6.1 (`6bb5dcd`): numbered range-target menus in `remote_commands.py`,
  wired to favorite contacts/channels in `workspace.py`. 83 Python tests pass.
  Send `range test`/`targets`/`help`, choose `1`, `1,2`, or `1 every 60s`, then
  separately confirm the full proposal with `1`. Paging: next/back, 150-byte
  UTF-8 packets, stable snapshot numbers, 2m expiry, permission/cancel/reset
  invalidation. Explicit names and AI fallback remain available. Menu scope
  defaults to favorites while the user's scope question is outstanding; this
  is not a separate target-authorization policy. No new controllers were added.
  User stopped the test before deployment. HA backup `2fa9ba3d`, HACS install,
  config check and restart completed. Verified 142 contacts/channels, range
  stopped, remote enabled, two controllers, three favorites, Google agent,
  zero pending, module URL v=0.6.1. Live handset menu acceptance remains pending.
  Initial three-minute verifier expired during startup; subsequent live checks
  verified recovery and HACS revision. No second restart was performed.
- Read `PROJECT_STATUS.md` for the authoritative completed / awaiting-validation /
  pipeline summary and the next acceptance test. Updated 2026-10-06.
- Current HA code and the BLE whole-frame firmware fix are deployed; no
  coding/build/deployment process is still running. Latest live check: remote
  control enabled, two approved controllers, range stopped after the user's
  successful OptimusPrime 30s test (Remote: OptimusPrime, initial 1 sent / 1 ACK).
- User's opened handset messages contained literal `Start O`; the earlier
  preview-clipping explanation was wrong. Old bridge revision split commands
  into 20-byte GATT writes, leaving only seven text bytes after the direct header.
  Updated to upstream `db6bfdef4681294bf6439d0d001e8dfeb430b556` with response
  writes enabled. ESPHome backup `77f4c170`, firmware job `e0a617fa16aa`, exit 0;
  settings/runtime PIN preserved, HA reconnected with 127 contacts/channels.
  Run `tests/check_bridge_frames.py` for the compiled non-radio regression.
  Post-flash correction: cached health looked connected but inbox was stale.
  Reloading ONLY the native integration entry while range was stopped restored
  a fresh handshake, queued reception and 142 contacts/channels. User's next
  `Range test OptimusPrime Every 30s` and `1` then arrived live and started the
  confirmed range test. No agent-issued start or test message was sent. Stop,
  cancel and fuzzy AI acceptance tests remain; independently viewing the full
  handset reply is still required before claiming its rendering was verified.
- Google AI preview is verified. Codex OAuth refresh is blocked by HTTP 401 and
  requires reauthorization. Live remote radio start/stop still needs user testing.
- Read `homeassistant.md` for setup/security/deployment and use the checkpoint
  below for implementation context. Older release/Mac notes are historical and
  must not be mistaken for active tasks or current runtime state.

HOME ASSISTANT REMOTE/AI CHECKPOINT (0.6.0; MENU UPDATE ABOVE IS CURRENT)
- Native remote commands now live in `remote_commands.py`, with HA credential
  reuse and tool-free agent eligibility in `ai_agent.py`. `workspace.py` attaches
  a per-entry remote Store before the radio starts fetching messages. Defaults
  are disabled; favorites are candidates, not automatic authorization. Contact
  permissions bind full public keys; ambiguous wire prefixes/channel senders
  cannot trigger commands. Names may still change between sessions.
- Commands tab: favorites/controller selection, enabled state, AI selector,
  persistent command outcomes, and AI preview without radio transmission.
  Standard commands use local parsing; AI fallback returns validated proposals.
  Status is read-only; range start/stop require `1`/`confirm` within 120 seconds.
  Cancel clears only the pending request. Pending requests expire across restart;
  enable/controllers/agent/history persist. Incoming source timestamps must be
  within 120 seconds; duplicate/future/stale messages are not acted upon.
- Existing HA Google and Codex agents have home-control permissions; do not send
  incoming radio text to them. A separate Codex conversation subentry named
  `MeshCore AI` was created through the HA config flow using the existing login,
  no tools, default gpt-5.1-codex model and low reasoning. Other agents unchanged.
- Deployment completed 2026-10-06: HACS installed `d02d846` / 0.6.0 after
  verified backup `f8aaf3f1`, core check and restart. Panel registers version
  `workspace.js?v=0.6.0`; radio available with 127 contacts/channels, 38 saved
  messages, range stopped. Latest test count: 73 Python checks, geography,
  four-width Chromium fixtures, live Chromium/WebKit Commands at 390/1366px.
  No live radio transmissions, PIN changes or remote Start/Stop tests performed.
- Codex provider preview failed because its existing OAuth refresh returns 401.
  Reauthorization is required; do not claim the subscription agent works yet.
  Original Codex/Google household agents retain their home-control permissions
  and are correctly blocked by MeshCore. Claude Terminal remains separate.
- Created a separate `MeshCore AI Google` conversation subentry using the existing
  Google credentials and no home-control APIs, through HA's supported config flow.
  Its live AI preview successfully translated "Can you keep checking OptimusPrime
  every half minute?" into start/dm:OptimusPrime/30/ping with range still stopped.
  At this original checkpoint remote control was DISABLED with no approved
  controllers; this is superseded by the live bridge-fix checkpoint above.
  Permissions have not been inferred from old Mac advertised names.
- Quick confirmation/cancellation of a pending request bypasses new-command
  throttling. AI clarify/unrelated chat never silently becomes a range proposal;
  deployed 0.6.0's explicit bare `range test` may propose the controller itself.
  The staged numbered-menu change supersedes this bare-request behavior only.
- Next deliberate test: favorite OptimusPrime, enable it in Commands and Save;
  send a fuzzy range request, confirm with 1, inspect Remote starter/ACK stats,
  then request stop and confirm. Also test cancel and permissions after HA restart
  when no range test is active. Reauthorize Codex separately before selecting it.

HISTORICAL HA RELEASE NOTES (0.5.x AND EARLIER)
- Rollout correction: user's existing Safari session did not show Sort after
  the file-only update. Once the range test was confirmed stopped, the pending
  HA restart was completed (backup `45a61ce6`). The registered module URL is
  now explicitly `workspace.js?v=0.5.3`. Fresh Safari/WebKit desktop verification
  confirms Sort and both distance orders, with 506px list height and no page
  errors. Radio reconnected; range stopped. Full browser-tab reload is required
  for an existing tab, since the data-refresh icon cannot replace loaded JS.
- Version 0.5.3 adds Map name/nearest/farthest sorting, based on unrounded
  distances with stable tie-breaking. Without a reference, distance modes are
  disabled and revert to A-Z. Filter/poll/tab changes retain the chosen mode.
  Map list height is responsive (480-700px desktop, 360-560px mobile) and the
  desktop map stretches with the sidebar. Four-width browser checks cover both.
- Latest installation: `d2e34a3` / 0.5.3 via HACS on 2026-10-06, verified HA
  backup `45a61ce6` and core check. An active range test was preserved: NO HA
  restart. Fresh local sessions loaded new JS, but the user's existing Safari
  session retained the old UI through the old registered version URL. Complete
  frontend rollouts with a safe HA restart and a full browser-tab reload, not
  the workspace's data-refresh icon. Never restart during an active test. Live 390/1366px
  nearest/farthest checks pass, with 464/506px list heights and no page errors.
  43 Python tests and four-width browser fixtures pass; no live sends/PIN changes.
- Version 0.5.2 adds straight-line km/mi distances to each Map list row. Clicking
  a marker/row changes the reference; the Distance from dropdown can choose any
  valid GPS repeater or None. Reference is independent of state/name filtering
  and persists across polling/tab changes. A missing/invalid reference is cleared.
  Uses Leaflet distanceTo; no terrain, route or coverage inference. Browser tests
  check known distances, zero, reference changes/clearing and persistence.
- Latest deployment: `510f2b1` / 0.5.2 on 2026-10-06, HA backup `f7dbac80`,
  core check and restart verified. Radio connected with 125 contacts/channels,
  92 GPS repeaters and range stopped. Live 390/1366px checks confirm distances
  in both units for all 11 Indiana rows from BlairOneW, with zero for origin
  and polling persistence. 43 Python tests, geography and four-width browser
  fixtures pass; no live sends or firmware/PIN changes.
- Version 0.5.1 adds a GPS-derived State dropdown to Map. Both markers/list and
  name search share the filter; excluded selections are cleared and matching
  locations fit automatically. Local Census 2024 boundaries and bundled Turf
  classify coordinates; no geocoder or guessed states. Non-US/unmatched points
  stay available under Outside US / unclassified. Boundary provenance/licenses
  are in `www/vendor/STATE-DATA.md`; geography tests in `tests/map_states.cjs`.
- Latest deployed revision: `3904d0d` / 0.5.1 on 2026-10-06, after HA backup
  `fbfee7f0`, core check and restart. Radio connected: 122 contacts/channels,
  89 GPS repeaters, range stopped. Live 390/1366px state-filter checks show
  Indiana's 10 markers/rows matching, with polling/search working and no
  MeshCore page errors. 43 Python tests, geography tests and four-width browser
  fixtures pass. No firmware/PIN changes or live transmissions in this update.
- Version 0.5.0 adds runtime bridge PIN updates and a native repeater map. Read
  the first section of `homeassistant.md` and `bridge.py`. PIN updates use a
  separate admin-only WebSocket command with the redacted `password` field,
  directly invoking the matching encrypted ESPHome runtime API (no HA service
  bus, PIN entity or options storage). Persisted PIN lives only on the bridge.
- Updated `ble_bridge_package.yaml` adds `update_meshcore_pin` and a restoring
  global override. Secrets supply only the initial/factory-reset fallback.
  After the one-time firmware update, the HA key-icon dialog saves/reconnects
  without rebuilding. Never print PINs or raw firmware/config/transport logs.
- Map uses bundled Leaflet 1.9.4 and OSM tiles. `_nodes()` exposes validated
  degree-valued SDK coordinates. Markers/list sync, zoom 12 on selection, popup
  close survives polling, and mobile stacks map/list. Never infer node locations.
- Read `homeassistant.md` first for the native HA migration. Current development
  is in `custom_components/meshcore_sender/`, not the Mac wrapper.
- `/meshcore` sidebar panel: Inbox, Compose, Range, Contacts/favorites, Commands and Map. The
  frontend module is `www/workspace.js`; authenticated admin-only WebSocket API
  and Store lifecycle are in `workspace.py`; bounded history in `history.py`.
- Reuses `NativeMeshCoreClient` and its single radio connection. No new server,
  TCP client or extra Bluetooth owner. Incoming/outgoing history persists in HA.
- Live host: HA OS 2026.9.3 at homeassistant.local:8123 (192.168.20.11).
  Native entry `01M47GQ1BN3ND5XGNKKG3V7C2B` connects through
  `ble-proxy-c3` / 192.168.100.189:5000 to Heltec V4 / MeshCore-MacMini.
  ESPHome Secrets provide the initial PIN fallback. Runtime overrides persist
  on the bridge after a key-dialog update. Never print PIN/API/token secrets.
- HACS custom integration repository ID 1403528253; update from `main`, run
  Supervisor's core configuration check, then restart HA. Use the configured
  Codex HA header helper for authorized API access; do not hardcode tokens.
- New native inbox starts with this version: old HA events and Mac history are
  not automatically imported. Range tests stop at restart; defaults persist.
- Channel-based controllers, contact import/export and discovery scans are still
  pending migration. Do not claim complete Mac parity or live remote-command tests.
- Tests: Python unittest suite plus `tests/workspace_browser.cjs` (Playwright).
  Browser actions use fixtures and must not secretly send live radio messages.
- Deployment completed: HACS installed `49121ff` / 0.5.0 after verified HA
  backup `d4e31a28`, core check and restart. Runtime PIN bridge firmware job
  `3b6fc4175417` succeeded; ESPHome backup `28e8af89` is available. Radio is
  connected with 98 contacts/channels and 70 GPS repeaters; range is stopped.
  43 Python checks and four-width browser fixtures pass. Live 390/1366px checks
  verified map tiles, list/marker selection, zoom, persistent popup close and
  masked PIN dialog cancellation, with no MeshCore page errors or live sends.
  Runtime PIN submission was fixture-tested, not tested by changing the live PIN.
  User-facing link: https://homeassistant.npalakurla.net/meshcore.
- Radio reconnection is now verified after the user changed the radio PIN and
  saved `meshcore_radio_pin` in ESPHome Secrets. Only ble-proxy-c3 was rebuilt
  and installed (job eeb004f5d8fa); HA reports available with 96 contacts/channels,
  zero new saved messages and range stopped. No pairing reset was needed.
- The PIN was not read, printed or committed. Apollo and other devices were
  unchanged. No live transmissions were sent: next deliberate test is a new
  OptimusPrime incoming message, reply, then Start/Stop at 30 seconds with
  starter attribution and successive transmission/ACK checks.

HISTORICAL MAC/SERVER HANDOVER
The following records the pre-native-HA app and earlier migration checkpoints.
It is not the current task list or deployment state. Read `PROJECT_STATUS.md`
and `homeassistant.md` first; use these notes only for behavior to preserve or port.

WHAT WE ARE BUILDING
A small local-only web app that sends and receives messages over a Heltec V4 LoRa
radio running MeshCore firmware, connected to this Mac mini by BLE. There is no
usable desktop client for MeshCore here (the vendor's Mac app is an iPad wrapper),
which is why this exists. The goal: message one contact, several contacts, or a
channel, and read replies in per-conversation threads. The user is a radio operator
on a mesh with ~8 nodes, ~44 repeaters and 2 room servers in range; their real uses
are one-to-one texting and signal/range testing.

WHERE EVERYTHING IS
- MAC/SERVER REFERENCE (historical, not authoritative for native HA status):
  ~/dev/active/meshcore-sender/meshcore_mac_ble.md
- App: ~/dev/active/meshcore-sender/
  Run: cd ~/dev/active/meshcore-sender && python3 src/server.py   ->  http://127.0.0.1:8788
  Files: src/server.py (stdlib HTTP server, no pip deps), src/transport_meshcore.py
  (SDK transport, roles, route metadata, repeater coordinates, inbox),
  public/index.html (shell + ALL client JS inlined), data/inbox.json (local runtime
  message store, gitignored), data/auth.json (local passphrase hash, mode 0600,
  gitignored).
- Radio CLI: meshcore-cli at ~/.local/bin/meshcore-cli.
  Device "MeshCore-MacMini", BLE UUID DDE75E06-4BF2-DB42-7B69-B29FE29CB836.
  ALWAYS address by UUID, never by name (name addressing re-scans BLE and is racy).
- Command ground truth when docs and reality disagree (they do):
  ~/.local/share/uv/tools/meshcore-cli/lib/python3.11/site-packages/meshcore_cli/meshcore_cli.py
- Server log (logs every request with its status code — a primary debugging tool):
  /tmp/meshcore-sender.log

LATEST PUSHED CHECKPOINTS
- `40fe64a` Wire AI parser as remote command fallback
- `8feba67` Add pending AI interpreter settings
- `74910fa` Convert utility drawers to tools workspace
- `dcef7fc` Polish conversation console UI
- `e6e5bd9` Allow repeated inbound command messages

WORKING TODAY (all verified; evidence in the doc's VERIFIED table)
- BLE connect by UUID; reads channels (chan:0 public, chan:1 private) and 50+ contacts.
- Destinations classified from the SDK contact type/adverts into
  node / repeater / room, deduped, shown in four sections with filter chips and a
  pinned Favourites section (star per row), plus search by contact/channel name.
- Sending to one contact, many contacts, or a channel, with send status, ACK/fail
  display, hop counts and route detail panel where route path is available.
- Receiving: sync_msgs drains the radio's queue, parsed into a persistent store and
  shown as per-conversation threads in the UI (newest first, your own sends included).
- Chat windows are bounded-height with internal scrolling; missed/unread counts show in
  the conversation sidebar. Current UI pass widened the console, added conversation
  search, moved Fetch into the inbox header, shows target type as a compact badge, and
  adds a short id only when duplicate display names need disambiguation.
- Lower utility drawers are now a single Tools workspace with tabs for Message, Range,
  Commands, Contacts, Map and Raw. The last selected tool is remembered locally, and the
  Range tab shows a live indicator while a range test is running.
- Repeater map: repeaters with advertised GPS are shown on an OpenStreetMap-backed map
  with pan, wheel zoom, marker popup, selected-row sync and "Open full map". Marker
  selection and right-panel selection are both supported; popup close is handled on
  pointer-down because map dragging can otherwise steal the click.
- Range test: one or more targets, editable while running, per-target sent/acked/missed
  stats, next-ping countdown bar, live collapsed summary, and rolling log.
- Remote Commands v1: deterministic allowlisted control from received MeshCore messages.
  The Remote commands drawer stores controller contact/channel names, shows command
  history, has persisted starred controller favorites, and supports `status`,
  `range test`, `stop range`, numbered confirmation replies and `cancel`. It
  mirrors automatic replies into the related conversation so received commands and
  app responses are visible in chat history. Repeated same-text commands are allowed
  after the short live-queue duplicate guard, so `Status` can be sent more than once.
  AI interpreter settings are visible in the Commands tool and can store provider/model/
  API key locally. When enabled, AI is parse-only: it can propose structured intents for
  messy controller text, but numbered confirmation still controls execution.
- Contacts drawer: import `meshcore://...` contact URI, manually add contact by full
  public key + display name + type, and export this node/contact URI.
- Flood-advert button; message templates, Enter-to-submit login, LAN-capable Mac app binding,
  session cookie + CSRF.

HISTORICAL MAC TEST FOLLOW-UPS (NOT THE CURRENT HA BACKLOG)
1. User needs to test the Contacts drawer later: Show URI with blank contact,
   export an existing contact URI, import a `meshcore://...` URI if available,
   then Refresh and confirm the contact appears.
2. Original note requested tests when the project grew. Superseded: native HA now
   has 73 Python tests plus geography/browser checks; see `PROJECT_STATUS.md`.

AI INTERPRETER STATUS
- Configuration UI, local secret storage and provider client are wired. The parser is
  fallback-only after deterministic commands. It converts messy controller text into
  structured intents only; the allowlist + confirmation state machine remains the safety
  boundary.
- Test flow: open Commands, save provider/model/API key, enable AI parser, then from an
  allowed controller such as OptimusPrime send a fuzzy request like "can you keep checking
  optimus every half minute". Expected behavior: the app replies with numbered
  confirmation choices; it must not start the range test until the controller replies `1`.
- Local fallback also treats "ping OptimusPrime in 30 sec", "ping OptimusPrime every 30 sec",
  and "check OptimusPrime every half minute" as range-test confirmation requests before calling AI.
- Command history now persists to `command_history.json`; use it for AI/remote-command failures
  after restart. AI provider calls retry once on transient network/server errors, and
  DeepSeek/OpenAI requests include JSON response-format hints.
- After rebuilding/copying the Mac app, quit and reopen MeshCore Sender before testing. If
  the old app process is still running, Safari/app UI may receive new radio messages while
  remote-command parser fixes are not active yet.
- Discovery tool added: controlled flood advert scan once, or every 5/10/30/60 minutes.
  It refreshes contacts after each scan and records newly seen repeaters. Remote controllers
  can request `scan for repeaters` / `scan for repeaters every 10 minutes`, but the app still
  requires numbered confirmation before scanning.
- Public/channel conversations now show a broadcast delivery warning plus quick actions to
  mention the last sender publicly or try direct when a matching contact exists.
- LAN mode: `src/server.py` defaults to localhost, but honors `MESHCORE_HOST`/`HOST`.
  The packaged Mac wrapper now sets `MESHCORE_HOST=0.0.0.0`, keeps local health/open-browser
  on `127.0.0.1`, and has a menu item to copy `http://<Mac-IP>:8788`.

HARD CONSTRAINTS
- Never reset, change, or ask for the user's passphrase in chat. Never handle their tokens
  or keys. The passphrase is theirs and was set by them.
- Do not expose this app to the public internet. LAN binding is allowed for the packaged
  Mac app per the user's request, but keep it on trusted home/private LANs. Never use
  Tailscale Funnel, ngrok, Cloudflare tunnels, or public port forwarding for this app.
- Auto-start / service configuration is STAGED for the user to load, never installed.
- Transport code fails loudly or not at all — never swallow an error.

METHOD THAT WORKS HERE (learned the hard way; see doc §2 and §11)
- Ground truth before parsers. Never write a parser from documentation alone — capture
  real output first. Several "bugs" in this project were invented by guessing a format.
- Never filter CLI output by length (contact lines are column-padded to ~70 chars and a
  length test silently discards every one). Never use -q (it hides "device not found" and
  the CLI still exits 0). Strip ANSI escapes — they can land inside a name.
- The contact table is a volatile cache of adverts heard, not config: it empties
  (54 → 0 → 54) and only a flood advert refills it. sync_msgs CONSUMES the message queue.
- Assert every edit anchor and compile before writing; run `node --check` on the extracted
  inline script after every UI edit; read /tmp/meshcore-sender.log when something 401s.
- Verify UI with computed styles and DOM geometry, not by eye, and test empty/error paths
  deliberately. The user judges by rendered output only.
- THE BIG ONE: your automated browser cannot see the signed-in view (no login is saved in
  the vault, and the user previously declined). Every check therefore runs against the
  sign-in screen, where the destination list, chips, favourites and inbox do not exist —
  which is exactly how this project fell into a fix-by-screenshot loop. **Ask the user
  once, politely, to save the login to the vault**: the passphrase goes into a masked
  prompt that you never see, and from then on you can verify the real screen. Until then,
  never claim a UI change is verified.

MOBILE CHAT CHECKPOINT (2026-10-05)
- Fixed the hidden desktop sidebar track remaining in the mobile chat grid.
- Selected conversations fill the phone viewport; Back returns to the inbox, and
  the reply composer stays at the bottom. Desktop retains its sidebar layout.
- Playwright checked rendered conversation fixtures at 375, 390, 430 and 980px:
  no horizontal overflow; phone chat and composer match viewport width.
- These checks use mocked API responses, not the user's authenticated radio session.
  Confirm the live iPhone view after installing the rebuilt app.

HOME ASSISTANT CHECKPOINT (2026-10-05)
- User has Home Assistant OS with Bluetooth available. Server App packaging lives
  in meshcore_homeassistant/; root repository.yaml makes the GitHub repo an App repo.
- custom_components/meshcore_sender/ provides a config flow, session renewal,
  target picker, interval number, Start/Stop buttons, running/connection indicators,
  statistics and multi-target actions. Choices persist in config entry options.
- Read homeassistant.md for installation and the deferred live test checklist.
- HACS deployment and live proxy connection attempts have been performed. Do not
  claim radio control works until the authenticated companion handshake succeeds.
- The App pins the existing published server commit, avoiding duplicate source trees.
- Follow-up verified the existing long-lived token through the configured
  /Users/assistant/.codex/helpers/home-assistant-auth.py helper. Do not display it.
  Local HA is http://homeassistant.local:8123 (192.168.20.11), version 2026.9.3.
  Token is owner/admin; Supervisor access works via WebSocket supervisor/api.
- Actual Bluetooth inventory has only remote scanners ble-proxy-c3 and
  apollo-msr-2-174b84. No local scanner was reported. The prepared App cannot use
  these proxies; do not install/start it expecting radio connectivity. Native
  proxy-aware transport is now implemented in bluetooth_client.py.
- User requested HACS installation; completed through HACS WebSocket APIs on
  live HA. Repo ID 1403528253, installed revision e0c73d3, HACS 2.0.5.
  Configuration check passed and HA restarted. Live config flow offers Bluetooth
  and server modes. Temporary validation flows removed; no meshcore_sender entry.
- Native mode loads contacts/channel names, exposes range controls/statistics,
  schedules cancellable multi-target tests, and fires incoming-message events.
  AI remote commands, server UI, favorites, maps and discovery are NOT ported.
  Nine local tests pass; native tests stop on HA restart, saved choices persist.
- Mac app was quit to release BLE and is left closed. ble-proxy-c3 discovered
  UART address 88:56:A6:96:29:59 at roughly -83 to -89 dBm. GATT connected, but
  MeshCore UART writes failed with error 5 (Insufficient authentication). Explicit
  pairing before notifications was deployed and retried, with the same error.
  Confirm the radio/PIN requirements and proxy support; do not claim the detected
  UART device is the intended companion until the handshake succeeds. User was
  asked whether phone pairing needs a PIN and to move the radio near the proxy.
  No native range test is running. Do not weaken security or flash devices blindly.
- Existing unrelated domain meshcore entry (MeshCore Node HABridge) retries a
  missing USB serial path. It was not changed; keep it separate from our integration.
- Latest follow-up: user approved converting ble-proxy-c3 and confirmed default
  PIN. ESPHome backup 7c8c8ebd verified before editing. C3 is now a dedicated
  PIN-capable BLE-to-TCP bridge at 192.168.100.189:5000, not a general proxy.
  Wi-Fi/API/OTA retained; Apollo kitchen sensor unchanged. Both bridge and repair
  button firmware compiled and uploaded successfully through ESPHome dashboard.
- Native TCP bridge mode added (0.3.0, b2cdff1 installed through HACS); HA config
  check passed and restarted. Live setup menu includes bridge mode. Twelve local
  tests pass, including transport selection, failed-handshake cleanup and range.
- Live radio name is MeshCore-MacMini, MAC 88:56:A6:96:29:59. Pairing still fails
  with confirmation mismatch reason 81. Repair Heltec pairing button was invoked
  and only cleared this radio's bond on C3; it did not resolve authentication.
  User asked to verify displayed PIN/update meshcore_radio_pin in ESPHome Secrets.
  Recompile/upload after any secret change. Do not print or commit that secret.
  No meshcore_sender config entry or native range test is running yet.
- ESPHome dashboard uses WebSocket ws commands (not legacy edit/compile REST).
  firmware/install returns the COMPILE job and queues a dependent UPLOAD job:
  verify BOTH exit codes before reporting deployment. No pending jobs at checkpoint.
- RESOLVED CHECKPOINT: user saved the current radio PIN in ESPHome Secrets.
  Recompiled (851caab9d79f) and uploaded (0d8974e42c2f), both exit 0. The SDK
  handshake returns SELF_INFO, radio name MacMini; contacts were fetched over the
  authenticated BLE bridge. Never print or commit the live PIN.
- Integration 0.3.1 (7654531) fixes the SDK's short default contact retrieval wait:
  explicit get_contacts(timeout=30), checked for errors before completing setup.
  Thirteen local tests pass. Deployed through HACS, config checked, HA restarted.
- Config entry 01M47GQ1BN3ND5XGNKKG3V7C2B, title MeshCore BLE bridge, is LOADED.
  Radio connected is ON; select.meshcore_sender_range_test_target has 94 choices
  and is set to OptimusPrime. number.meshcore_sender_range_test_interval is 30.
  Range running is OFF; sent/ACK counts 0. No test messages were sent. Next live
  check is a deliberate Start/Stop test with receiver ACK/timing verification.

HISTORICAL MAC DEFINITION OF DONE
The old add-contact implementation/test objective above is not the current HA task.
For the next round, use the acceptance test and pipeline in `PROJECT_STATUS.md`.
Any new UI change must still be checked in a rendered signed-in view or explicitly
reported as unverified.
