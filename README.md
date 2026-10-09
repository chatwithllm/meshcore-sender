# MeshCore Sender

Web UI for a MeshCore radio connected over BLE. It sends direct messages, channel messages,
receives inbox updates, runs range tests, maps repeaters with GPS, and supports deterministic
remote command control from an allowlisted contact or channel.

## Home Assistant

The native Home Assistant integration provides an authenticated sidebar with Inbox,
Compose, Range, Contacts, Commands, Repeaters and Map. It uses HA Bluetooth or a PIN-capable
BLE bridge, without a Mac login or a separate Mac server. Remote commands can reuse
supported tool-free HA conversation agents, with approved contacts and confirmation.
The older server/App mode remains available but is not the current native deployment.
Remote repeater administration adds response-capable inspection/login/trace actions
and manually refreshed device entities, with read-only CLI defaults and explicit
mutation permission. See [remote repeater administration](REMOTE_REPEATER_ADMIN.md)
for credentials, dashboard setup, airtime safeguards and current live-test limits.

See [Home Assistant setup](homeassistant.md), [current status and pipeline](PROJECT_STATUS.md),
and [agent handover](HANDOFF_PROMPT.md). The Mac/server commands and environment
variables below apply to standalone mode, not the native HA integration.

## Run locally

```bash
python3 src/server.py
```

Then open:

```text
http://127.0.0.1:8788
```

Manual source runs bind to loopback by default. The packaged Mac app starts in LAN mode so
you can use it from another device on the same trusted home/private network. Do not expose
it to the public internet or public tunnels.

## Useful environment variables

- `PORT`: defaults to `8788`
- `MESHCORE_HOST` or `HOST`: defaults to `127.0.0.1`; use `0.0.0.0` for LAN access
- `DATA_DIR`: defaults to `./data`
- `MESHCORE_ADDR`: BLE UUID on macOS, or Bluetooth MAC address on Linux
- `MESHCORE_TIMEOUT`: radio command timeout in seconds
- `MESHCORE_SDK_SITE`: optional path override for the MeshCore SDK site-packages

## Deploy files

Deployment templates live in `deploy/` and are staged only:

- `deploy/com.meshcore.sender.plist`: launchd template for macOS
- `deploy/Dockerfile`: packaging experiment; macOS Docker generally cannot access BLE

Review and install deploy files manually. The repo does not auto-load services.

## Notes

Runtime files under `data/` are local machine state and are intentionally ignored by Git.
`data/auth.json` contains only the app passphrase hash, but still must stay local.
