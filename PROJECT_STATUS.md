# Project Status And Agent Handover

Updated: 2026-10-06. This is the authoritative current-status summary. Older
checkpoints in `HANDOFF_PROMPT.md` describe history, not the current backlog.

## Current Checkpoint

- Prepared and being deployed: 0.6.3 battery-voltage monitoring. Native
  bridge/BLE reads `get_bat()` / BATTERY `level` (millivolts) once per minute under
  the existing transport lock; five-second timeout, invalid/stale handling, HA
  measurement sensor and workspace voltage/history control. No percent/current/
  runtime estimates. User confirmed two 18650 cells in parallel, directly powering
  the Heltec battery connection and charged by a solar charger (not USB). Test
  stopped and user authorized deployment. Live ADC verification and HA deployment
  remain pending until a subsequent verified checkpoint. Do not open a second
  radio connection. 0.6.2 below remains live until deployment completes.
  Validation: 114 Python tests passed, workspace browser fixtures passed at
  375/390/768/1366 px (voltage, stale state and history event included), geography
  tests passed and `git diff --check` passed.
- Active product: native Home Assistant integration and `/meshcore` sidebar.
- HA integration version: **0.6.2**, HACS-installed code revision **`24937b9`**.
  The later bridge transport fix below changes ESPHome firmware, not HA code;
  it does not require an HA restart.
- Deployment: HACS install, verified HA backup **`f889edd7`**, configuration check,
  restart and radio reconnection completed. Registered frontend:
  `/meshcore_sender_static/workspace.js?v=0.6.2`. Radio connection and exact saved
  controller/favorite/AI settings were verified after restart. Panel module URL
  is nested under `config._panel_custom` in get_panels.
- Latest live check: **remote control enabled**, **two approved controllers**,
  **three favorites**, **MeshCore AI Google selected**, **range test stopped**,
  radio available with **142 contacts/channels**, **zero pending requests**.
  Before this deployment, the user's command and `1` confirmation successfully
  started a 30-second OptimusPrime test with remote attribution and ACKs; the user
  stopped it before deployment. No agent-issued menu/test transmissions were sent.
  Recheck live settings before changing permissions or deploying.
- Bridge firmware: pinned upstream **`db6bfdef4681294bf6439d0d001e8dfeb430b556`**,
  installed by ESPHome job **`e0a617fa16aa`**, exit 0, after ESPHome backup
  **`77f4c170`**. Full-frame writes with response replace the old 20-byte split;
  Wi-Fi/API/OTA, pairing and persistent runtime PIN settings were preserved.
- Recovery correction: the initial post-flash cached health said connected but
  the inbox was stale. Reloaded only entry `01M47GQ1BN3ND5XGNKKG3V7C2B` while
  the range test was stopped; the fresh handshake recovered pending inbox data
  and 142 contacts/channels. Subsequent command and confirmation arrived live.
  After future bridge firmware updates, verify a fresh handshake/inbox event,
  not just cached `available` status. Never reload during an active test.
- No implementation, deployment, build or test process was left running by the agent.
- Original Mac/server implementation remains saved in the repository. Mac history,
  API keys and controller permissions were not automatically imported into HA.

## Completed

| Area | Delivered |
| --- | --- |
| Native radio | Heltec V4 through the PIN-capable ESPHome BLE bridge; one HA-owned radio connection, no Mac login dependency. |
| Inbox | Persistent incoming/outgoing conversations, replies, name resolution when a matching contact exists, delivery states and replay deduplication. |
| Compose and contacts | Multiple recipients, actual radio channel names, search/type filters, name sorting and persisted favorites. |
| Range tests | Multiple targets, 5-300-second interval, prefix, starter attribution, countdown, per-target sent/ACK/broadcast statistics and log. |
| Stop summaries | 0.6.2: start/stop actor and HA/LoRa origin, honest attempts/DM ACK/channel TX counts, final packets to tested targets, remote stopper reply deduplication and final HA display. |
| Remote commands | Commands tab, persistent public-key-bound direct controllers, local command parsing, expiring confirmation, cancellation, queue/rate limits and recent outcomes. |
| Numbered targets | 0.6.1 deployed: favorite contacts/channels, stable numbered menu, next/back pages, multiple selections and interval override; a separate confirmation still gates execution. |
| HA AI reuse | Tool-free conversation-agent selector, validated JSON proposals, fallback-only AI interpretation and non-transmitting preview. Separate Google/Codex subentries reuse their existing HA credentials. |
| AI verification | Google preview translated "Can you keep checking OptimusPrime every half minute?" to a start proposal for that contact at 30 seconds, without executing it. |
| Runtime PIN | Masked admin dialog and persistent bridge override, without rebuilding firmware for subsequent PIN changes. |
| BLE reply truncation | Updated bridge firmware preserves complete MeshCore commands instead of independent 20-byte writes. HA reconnection verified; recipient-side retry still required. |
| Repeater map | Advertised GPS, marker/list selection, persistent popup close, local state classification/filter, reference-based km/mi distances, name/distance sorting and taller responsive list. |
| Verification | 99 Python tests, compiled pinned-upstream bridge frame check, geography tests and four-width Chromium fixtures (including stop summary) pass. Earlier live Chromium/Safari-WebKit Commands checks at 390/1366px also passed. |
| Documentation | Setup, security boundaries, deployment history and agent handover are saved in GitHub. |

Confirmation applies to range start/stop. `status` is read-only and sends a reply;
`cancel` cancels a pending request, not a running test. Fast responses to a pending
confirmation bypass new-command throttling. Unclear AI responses never imply a
range test. AI cannot access household-control tools through the MeshCore adapter.

## In Progress / Awaiting Validation

- **0.6.2 stop summaries: deployed, handset acceptance pending.** Explicit HA/LoRa
  stops capture starter/stopper and sources, attempts, direct ACKs and channel
  broadcasts without claiming channel delivery. Summary goes to tested targets;
  a remote stopper receives it once as the command reply. HA shows the final
  summary/notification failures. Packets obey the 150-byte UTF-8 limit; repeated
  stops do not resend. In-flight cancellation is unconfirmed, summary messages
  do not count as pings, and shutdown/unload does not send notifications. Tests:
  99 Python checks; four-width browser summary fixture validation. Deployment
  verified stopped state, backup `f889edd7`, config check, restart/reconnect and
  exact controller/favorite/AI retention. Live radio stop-summary receipt remains
  unverified; no agent-issued start, stop or summary test was sent.

No coding work is currently in flight. These items need user participation or a
deliberate follow-up, and must not be described as verified end to end:

- **Numbered range-target menu: deployed, awaiting handset acceptance.** A bare
  `range test`, `range test every 60s`, `help`, or `targets` opens an alphabetical
  menu of favorite contacts/channels. Numbers stay bound to that menu snapshot;
  `next`/`back` page through 150-byte UTF-8 packets. Reply `1`, `1,2`, or
  `1 every 60s` to select, then a separate `1`/`confirm` approves the resulting
  full target/interval proposal. Menus expire after two minutes, are not restored
  after restart, and clear on cancel/permission changes. Removed favorites and
  changed identities cannot execute. 83 Python tests pass. The user stopped the
  live test; 0.6.1 was installed and HA reconnection verified. The menu scope question
  (favorites/all available/separate approved list) was asked; favorites is the
  conservative first-version default pending the user's answer. Favorites are
  menu candidates, NOT controller authorization or a new restriction on explicit
  named-target requests; those retain existing validation and confirmation.

- **Full reply receipt:** user's opened handset messages showed literal `Start O`,
  not a clipped preview. HA recorded the full confirmation and a delivery ACK,
  but the old bridge split its 13-byte direct-message header plus text into
  20-byte commands, leaving seven text bytes in the first write. The upstream
  fix is installed. A compiled regression harness reproduces the old symptom
  and checks intact normal, maximum-length and UTF-8 frames, plus long-write and
  oversize-no-response handling. It tests the upstream writer/queue, not actual
  GATT reassembly or handset receipt. No agent-triggered test messages were sent.
- **Live remote control:** user's new `Range test OptimusPrime Every 30s` and `1`
  arrived after connection recovery; confirmed start is verified with 1 sent /
  1 ACK and correct starter attribution. Stop/cancel, enabled-permission restore,
  and fuzzy AI fallback still need acceptance testing. Do not mistake an ACK for
  independent proof that the handset rendered the complete original text.
- **Codex login:** the existing OAuth token refresh returned HTTP 401. The separate
  `MeshCore AI` agent is tool-free but not provider-functional until reauthorization.
  Google is the verified selected agent. Do not delete/reconfigure household agents
  or claim Claude Terminal is an HA conversation agent.
- **Permissions across a user-configured restart:** Store save/restore is covered
  by tests, and the selected agent survived a live restart. An enabled real
  controller's command flow after restart still needs a live acceptance test.
- **Runtime PIN submission:** fixture submission and live dialog cancellation were
  tested. Verify live save/reconnect at the next genuine PIN change; do not change
  a working radio PIN just to test this feature.

### Next Acceptance Test

0.6.2 is now published and deployed. Test `range test` -> numbered menu -> target
number -> separate confirmation, a channel/multiple targets, `next`/`back`,
`1 every 60s`, invalid numbers and cancel. No menu-specific live transmissions
were performed by the agent.

For stop summaries, run a short deliberate test, stop from LoRa with confirmation,
and verify start/stop actors and LoRa origin on the handset and in HA. Separately
stop another test from the HA sidebar or entity button and verify the authenticated
HA user and HA origin. Repeat stop once while idle: it must not resend the summary.
For a channel target, verify TX count is labelled no delivery ACK. Final summary
packets must not inflate ping counters. HA shutdown/unload intentionally sends no
radio summaries, and the in-memory Range result clears on restart.

1. Verify OptimusPrime is one of the approved controllers in Commands. Preserve
   the user's enabled settings and tool-free agent selection.
2. Send `Range test OptimusPrime every 30s`; verify the handset receives the
   entire confirmation including `1 confirm, cancel`, not just `Start O`.
   Then send `status` and verify both the received message and the full reply.
3. Send `Can you keep checking OptimusPrime every half minute?`; verify a proposal
   appears and the range test has **not** started yet.
4. Reply `1`; verify Range shows `Remote: OptimusPrime`, a 30-second interval and
   successive transmissions with accurate ACK statistics.
5. Send `stop range test`, then `1`; verify the test stops. Separately check that
   `cancel` removes a pending request without stopping an existing test.
6. With no test running, deliberately restart HA and verify the selected controller,
   enabled flag and AI choice persist. Old pending confirmations must not execute.

Controller messages need a source timestamp within the last 120 seconds; missing,
future, stale, replayed or ambiguous-prefix messages must not execute commands.
Unapproved senders and channel messages must not invoke AI or control actions.

## Pipeline

Suggested order after acceptance testing, **not implemented or scheduled**:

1. **Codex reauthorization and preview:** renew the existing login using the
   integration's supported mechanism, then test the tool-free MeshCore agent
   before selecting it. Never copy tokens into this repo or logs.
2. **Native discovery scans:** migrate the Mac/server one-shot and 5/10/30/60-minute
   discovery schedules, new-repeater results and confirmed remote requests.
   Flood adverts need explicit traffic limits; do not silently enable a schedule.
3. **Native contact URI import/export:** migrate the existing Mac/server workflow
   into the HA workspace, with validation and duplicate handling.
4. **Map layers:** add a layer selector after deciding on suitable tile providers,
   licensing/attribution and any required credentials. Current map is OSM only.
5. **Channel controllers / further AI providers:** design authorization first.
   Channel display names do not establish individual identity; this is intentionally
   excluded from current remote control. Additional agents need a reviewed tool-free
   adapter, not a prompt-only restriction or unrestricted home-control access.

## Resume Guide

- Read this file, then `homeassistant.md`, then the current HA section of
  `HANDOFF_PROMPT.md`. Use `meshcore_mac_ble.md` for historical Mac/server behavior.
- Integration: `custom_components/meshcore_sender/`. UI: `www/workspace.js`.
- Command state machine: `remote_commands.py`; provider safety: `ai_agent.py`;
  authenticated admin API and Store attachment: `workspace.py`.
- Native transport/receive routing: `bluetooth_client.py`; range scheduler:
  `range_test.py`; inbox persistence: `history.py`; runtime PIN: `bridge.py`.
- Tests: `python3 -m unittest discover -s tests`, `node tests/map_states.cjs`, and
  `node tests/workspace_browser.cjs` with Playwright installed or
  `PLAYWRIGHT_MODULE` pointing to it. Fixtures do not use real radio/provider calls.
- Bridge regression: `python3 tests/check_bridge_frames.py` compiles the actual
  immutable upstream frame writer with a non-radio C++ harness; requires a C++
  compiler and downloads public source. `--source /path/to/meshcore_ble_bridge.cpp`
  supports offline testing. After changing the package pin, rebuild/install only
  the dedicated ESPHome bridge; HACS alone cannot update its firmware.
- Live host: HA OS at `homeassistant.local:8123` / `192.168.20.11`. Sidebar:
  `https://homeassistant.npalakurla.net/meshcore`.
- Native entry: `01M47GQ1BN3ND5XGNKKG3V7C2B`; bridge: `ble-proxy-c3` /
  `192.168.100.189:5000`; HACS repository ID: `1403528253`.
- API credentials come from the configured HA access helper. Temporary scripts,
  virtual environments and screenshots under `/tmp` are not durable handover assets;
  recreate them if missing. Do not assume another agent has the same access tools.
- Before deployment: inspect the worktree, verify backup and live range state, update
  through HACS, run HA's configuration check, restart only when safe, then verify
  radio reconnection and the versioned panel URL. Browser-tab reload replaces JS;
  the workspace refresh button only refreshes data.
- Never restart during an active test, create a second radio connection, change the
  PIN/firmware during unrelated work, touch the Apollo kitchen sensor, expose a
  bridge outside the trusted LAN, or print/commit API keys, PINs or tokens.
