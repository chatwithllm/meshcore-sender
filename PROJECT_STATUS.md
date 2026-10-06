# Project Status And Agent Handover

Updated: 2026-10-06. This is the authoritative current-status summary. Older
checkpoints in `HANDOFF_PROMPT.md` describe history, not the current backlog.

## Current Checkpoint

- Active product: native Home Assistant integration and `/meshcore` sidebar.
- Version: **0.6.0**, deployed code revision **`d02d846`**. Later commits update
  documentation only; they do not require another HA restart.
- Deployment: HACS install, verified HA backup **`f8aaf3f1`**, configuration check,
  restart and radio reconnection completed. Registered frontend:
  `/meshcore_sender_static/workspace.js?v=0.6.0`.
- Last verified settings: **remote control disabled**, **zero approved controllers**,
  **MeshCore AI Google selected**, **range test stopped**. Agent selection survived
  restart. Recheck live state before changing settings or deploying.
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
| Remote commands | Commands tab, persistent public-key-bound direct controllers, local command parsing, expiring confirmation, cancellation, queue/rate limits and recent outcomes. |
| HA AI reuse | Tool-free conversation-agent selector, validated JSON proposals, fallback-only AI interpretation and non-transmitting preview. Separate Google/Codex subentries reuse their existing HA credentials. |
| AI verification | Google preview translated "Can you keep checking OptimusPrime every half minute?" to a start proposal for that contact at 30 seconds, without executing it. |
| Runtime PIN | Masked admin dialog and persistent bridge override, without rebuilding firmware for subsequent PIN changes. |
| Repeater map | Advertised GPS, marker/list selection, persistent popup close, local state classification/filter, reference-based km/mi distances, name/distance sorting and taller responsive list. |
| Verification | 73 Python tests, geography tests, four-width Chromium fixtures and live Chromium/Safari-WebKit Commands checks at 390/1366px passed. |
| Documentation | Setup, security boundaries, deployment history and agent handover are saved in GitHub. |

Confirmation applies to range start/stop. `status` is read-only and sends a reply;
`cancel` cancels a pending request, not a running test. Fast responses to a pending
confirmation bypass new-command throttling. Unclear AI responses never imply a
range test. AI cannot access household-control tools through the MeshCore adapter.

## In Progress / Awaiting Validation

No coding work is currently in flight. These items need user participation or a
deliberate follow-up, and must not be described as verified end to end:

- **Live remote control:** user must favorite/select a controller and enable it.
  Automated fixtures tested execution boundaries; no live remote start/stop or
  radio transmissions were performed during this migration's verification.
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

1. In Contacts, favorite OptimusPrime. In Commands, select it, enable remote
   control, retain MeshCore AI Google, and Save.
2. From OptimusPrime, send `status`; verify both the received message and reply.
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
