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
- Flood-advert button; message templates, Enter-to-submit login, loopback-only binding,
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

HARD CONSTRAINTS
- Never reset, change, or ask for the user's passphrase in chat. Never handle their tokens
  or keys. The passphrase is theirs and was set by them.
- Loopback only. Never bind 0.0.0.0. Never Tailscale Funnel, ngrok or Cloudflare. Remote
  access = `tailscale serve`, tailnet-only.
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

DEFINITION OF DONE FOR THE NEXT ROUND
Add-contact workflow implemented and verified against real device output; any UI change
either confirmed in a rendered signed-in view or explicitly reported as unverified.
