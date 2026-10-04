# Deploy files

These files are staged for manual use. Do not install or load them automatically.

## launchd

`com.meshcore.sender.plist` starts the local server on `127.0.0.1:8788` and stores app
data under:

`~/Library/Application Support/MeshCore Sender/data`

To use it manually, copy the plist to `~/Library/LaunchAgents/`, review the paths, then
load it with `launchctl`. Keep Bluetooth permission in mind: the process that launches the
server must be allowed to use Bluetooth.

## Docker

The Dockerfile is mostly for portability experiments and server packaging. On macOS,
Docker generally cannot talk to the BLE radio directly, so the native app or launchd path
is the practical deployment route. The container still binds the app to loopback inside
the container; do not expose it publicly.
