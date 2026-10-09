# Remote Repeater Administration (0.7.0)

Native Home Assistant Bluetooth and BLE-bridge connections share the existing
HA-owned companion. No separate Mac process, second radio connection, automatic
discovery, or periodic LoRa polling is used. Existing HTTP server mode returns
`unsupported` for these new actions.

## Actions

All seven actions support optional HA response data (`response_variable` in an
automation; enable response data in Developer Tools). They require an HA admin
when called with a user context. Context-free HA automations are trusted local
configuration. They are **not** added to inbound LoRa controllers or AI tools.

```yaml
action: meshcore_sender.remote_status
data:
  target: "ab208ae4456d"
response_variable: repeater_status
```

```yaml
action: meshcore_sender.remote_command
data:
  target: "ab208ae4456d"
  command: "get tx"
  mode: "read_only"
response_variable: repeater_tx
```

| Action | Additional inputs | Behavior |
| --- | --- | --- |
| `remote_status` | Optional password | One binary status request: voltage, queue, uptime, RSSI/SNR, raw radio counters. |
| `remote_telemetry` | Optional password | One binary telemetry request; Cayenne LPP readings with channels. |
| `remote_neighbors` | Optional password, count 1-16 (default 8), offset 0-65535 | One bounded page, total neighbor count, returned count and truncation indicator. |
| `remote_command` | Required command, mode read_only/admin, allow_mutation false | One CLI request; normalized ver/board/get tx/get radio, other replies preserved. |
| `remote_login` | Password or saved credential, save_password false | Correlated login-success/fail by target key; saves only on success when requested. |
| `remote_logout` | forget_password false | Companion session cleanup; its local ACK is **not** proof of remote reachability or ACL revocation. |
| `trace` | None | One known outward route, target, reversed route; random tag/auth correlation. No path discovery. |

Each action accepts `target` (exact name or unambiguous 12-64-character public key
prefix), optional `entry_id`, and `timeout` 5-60 seconds (default 20). Timeout
bounds the entire transaction including an optional login. There are no retries.
Unknown/flood-only routes and unsupported three-byte hash routes return
`unsupported` for trace rather than altering the route or flooding discovery.

## Authentication And Safety

Use `/meshcore` > **Repeaters**, select BlairOneW, then the masked authentication
form. A saved credential is used for subsequent requests and a new login is sent
when the companion instance changes. The password is not returned in snapshots,
responses, inbox messages, or integration logs. Optional saved passwords live in
HA's protected integration storage and backups; **this is not encrypted secret
storage**. Protect HA admin access and backups. HA may retain action input data
in automation/script traces when a password is supplied explicitly to a service.
Prefer saving through the manual form rather than embedding secrets in scripts.
The bridge Bluetooth PIN is a different credential from the repeater password.

`read_only` is the default. Allowed inspection commands are `ver`, `board`, exact
`clock`, `get ...`, `neighbors`, `stats-core`, `stats-radio`, `stats-packets`.
Firmware documentation marks the stats CLI commands serial-only on some builds;
allowlisting them does not imply that a repeater implements them remotely.

Supported mutations (`set ...`, `reboot`, `poweroff`, `shutdown`, `erase`,
`password ...`, `neighbor.remove ...`, `clear stats`, `start ota`, `time ...`,
`clkreboot`, `advert`, `advert.zerohop`, `discover.neighbors`, `clock sync`) require
explicit `allow_mutation: true`. Selecting `mode: admin` alone does not permit a
write. Unknown commands and command separators/control characters are blocked.
The sidebar offers read-only CLI only; mutations are an explicit service choice.
No mutating command is part of status/telemetry/neighbor inspection.

CLI replies have a sender key and type, but no echoed request ID (their timestamp
comes from the remote clock). Commands are serialized, reject duplicate reply
timestamps, and use a two-minute cooldown after a CLI timeout. Very late replies
or another app issuing CLI commands through the same companion cannot be fully
disambiguated by this protocol; avoid concurrent external CLI clients. Binary
requests use exact tags; login checks the target key; trace checks random tag/auth.
The SDK's raw packet/CLI DEBUG logs are redacted, including late replies.

## Results And Entities

Responses contain `request_success`, `online`, `error`, `message` on failure,
`target_name`, `public_key_prefix`, `round_trip_ms`, per-repeater success/failure
counters and `raw_response`. Normalized optional measurements are null when not
reported. Voltage is in V and mV; uptime is seconds; RSSI/tx power are dBm and SNR
dB. Battery percentage, charging, power source, firmware/board, and radio settings
are **not** invented from hardware descriptions or voltage. Firmware/board/TX/
radio values can be populated explicitly with read-only CLI actions. Role and
outward path are labeled as companion-contact metadata, not proof of an online
repeater or a verified current path. RTT includes an optional authentication step.

Errors include `contact_not_found`, `ambiguous_target`, `not_connected`,
`no_response`, `auth_failed`, `traffic_deferred`, `unsupported`, `parse_error`,
`mutation_blocked`, `invalid_command`, and `forbidden`. Silence is `no_response`,
not an invented wrong-password diagnosis. A login-fail event can also be a
companion timeout, so it does not prove the repeater is online.

The first resolved request tracks the full public key and creates a separate
device. BlairOneW normally gets:

- `binary_sensor.meshcore_blaironew_online`
- `sensor.meshcore_blaironew_battery_voltage`, `battery_percent`, `uptime`
- `sensor.meshcore_blaironew_firmware`, `board`, `role`, `tx_power`, `radio`
- `sensor.meshcore_blaironew_out_path_len`, `last_rssi`, `last_snr`, `neighbor_count`
- `sensor.meshcore_blaironew_request_successes`, `request_failures`, `queue_length`
- `button.meshcore_blaironew_refresh_status`, `refresh_neighbors`

Each suffix listed above is prefixed with `sensor.meshcore_blaironew_`. Actual
entity IDs can have collision suffixes if HA already owns the suggested name.
Use the separate device's **Add to dashboard** action; voltage and signal sensors
support native history. Neighbor list is attached to the neighbor-count entity;
path bytes are attached to the path-length entity. No existing entity is renamed.

Only identities and request counters are restored at startup; online state and
observations restart as unknown. Measurements expire after 7200 seconds; the
coordinator updates freshness locally without transmitting LoRa. Default refresh
is manual. If an automation is added, use a conservative interval of at least
7200 seconds and avoid active range tests. Transactions defer while range tests,
stop summaries, another administration request, or the transport lock are active.
Allow three seconds between manual transactions. Preflight-only deferrals do
not count as failed radio requests.

## Verification And Deployment

Protocol, schema, safety, parsing, timeout, source/tag filtering, secret redaction,
entity freshness, persistent counters, and guest/admin separation have automated
tests. Four-width browser fixtures cover the Repeaters tab and read-only service
payloads. See `PROJECT_STATUS.md` for the actual release revision, HA backup,
deployment result, and first live BlairOneW results. Do not treat fixture replies
or a known contact as a live success.

References: [MeshCore SDK](https://github.com/meshcore-dev/meshcore_py),
[repeater firmware](https://github.com/meshcore-dev/MeshCore/blob/main/examples/simple_repeater/MyMesh.cpp),
[CLI documentation](https://github.com/meshcore-dev/MeshCore/blob/main/docs/cli_commands.md),
[HA response actions](https://developers.home-assistant.io/docs/dev_101_services/).
