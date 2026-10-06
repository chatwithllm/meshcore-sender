TASK: continue hardening a local MeshCore messaging app on macOS

You are taking over a working project mid-stream. Read this whole brief, then the
handoff doc, then the code — in that order.

WHAT WE ARE BUILDING
A small local-only web app that sends and receives messages over a Heltec V4 LoRa
radio running MeshCore firmware, connected to this Mac mini by BLE. There is no
usable desktop client for MeshCore here (the vendor's Mac app is an iPad wrapper),
which is why this exists. The goal: message one contact, several contacts, or a
channel, and read replies in per-conversation threads. The user is a radio operator
on a mesh with ~8 nodes, ~44 repeaters and 2 room servers in range; their real uses
are one-to-one texting and signal/range testing.

WHERE EVERYTHING IS
- HANDOFF DOC (authoritative — read it fully before touching anything):
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

NOT BUILT — NEXT TASKS IN ORDER
1. User needs to test the Contacts drawer later: Show URI with blank contact,
   export an existing contact URI, import a `meshcore://...` URI if available,
   then Refresh and confirm the contact appears.
2. Add tests when the project grows enough to support them.

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

DEFINITION OF DONE FOR THE NEXT ROUND
Add-contact workflow implemented and verified against real device output; any UI change
either confirmed in a rendered signed-in view or explicitly reported as unverified.
