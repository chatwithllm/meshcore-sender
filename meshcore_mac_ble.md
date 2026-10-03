# MeshCore on a Mac mini over BLE — progress, ground truth, and rebuild guide

**Status:** working end to end for sending and receiving. Remaining work is §8; read §9
and §11 before promising anything.
**Last updated:** 2026-10-03 (after the inbox, roles, adverts and UI-grouping work)
**Project:** `~/dev/active/meshcore-sender/` (renamed from `meshtastic-sender`)

This file is the handoff. It records what works, what is broken, and the facts that took
hours to establish so nobody rediscovers them.

**VERIFIED** = confirmed by running something and reading its output.
**UNVERIFIED** = not confirmed. Nothing here is claimed as working without evidence.

---

## 1. The rig

| | |
|---|---|
| Radio | **Heltec V4** LoRa board |
| Its firmware | **MeshCore** `v1.17.1-d929643 (13)` |
| BLE name | `MeshCore-MacMini` |
| **BLE UUID** | **`DDE75E06-4BF2-DB42-7B69-B29FE29CB836`** ← address by this, never by name |
| Host | Mac mini, user `assistant` |
| Client | `meshcore-cli` at `~/.local/bin/meshcore-cli` (uv-installed) |
| CLI source | `~/.local/share/uv/tools/meshcore-cli/lib/python3.11/site-packages/meshcore_cli/meshcore_cli.py` — **read this when the docs and reality disagree** |
| Our app | `~/dev/active/meshcore-sender/` → `http://127.0.0.1:8788` |

Reference material: `~/dev/GPTMeshApp/meshcore-setup/` (`cli_commands.md`,
`companion_protocol.md`, firmware, `MyMesh.h`).

### Meshtastic is NOT MeshCore

Same board, different firmware, **different wire protocol**. A Heltec running MeshCore
will never answer `meshtastic`, over any transport. The first version of this app was
built for Meshtastic and could not see the radio at all.

---

## 2. Traps that cost the most time (read first)

1. **BLE allows ONE central per peripheral.** A connected device stops advertising, so an
   empty scan can mean *busy*, not *off*.
2. **Anything holding the connection blocks the CLI** — the Mac's pairing, the MeshCore One
   Mac app, or the phone app. Release it first.
3. **macOS gives a silent empty scan when the calling process lacks Bluetooth permission.**
   No error, just nothing.
4. **`meshcore-cli` exits 0 even when it never found the device.** Never trust the exit
   code. Failure strings: `Couldn't find device`, `Can't connect`, `No response from`,
   `Problem while executing`.
5. **Never use `-q`.** It hides those lines, turning a clear "Couldn't find device" into
   *no output at all with exit 0*.
6. **Address by UUID, not name.** `-a <name>` re-scans BLE on every call and is racy.
7. **Never filter CLI output by length.** Contact lines are column-padded to ~70 chars, so
   `len > 60` silently discards *every contact*. Detect prose by wording
   (`"contacts in device"`, leading `>`), never size. This bug shipped twice.
8. **The CLI emits ANSI cursor escapes** (`\x1b[34G`) to align its columns, and they can
   land inside a short contact name. Strip them (`strip_ansi()`).
9. **The contact table is a RAM cache of adverts heard**, not config. Every CLI call opens
   a fresh BLE session, and an unclean drop can leave it empty. Observed across sessions:
   **54 → 0 → 53 → 0 → 54 → 1 → 57.** Nothing is corrupt; only an advert makes the radio
   remember.
10. **`sync_msgs` CONSUMES the queue.** It hands you the messages and clears them. Never
    treat it as a non-destructive poll — accumulate server- or client-side.
11. **A flash or config reset wipes contacts and non-default channels.** Recovery:
    `add_channel <name> <key>` if you still hold the key.

---

## 3. Ground truth: exact output formats

**`get_channels`**
```
0: Public [8b3387e9c5cdea6ac9e5edbaa115cd72]
1: private [bd707c1fb3788148b0eda5fc4f57b6f0]
```
`<index>: <name> [<key>]` — the **colon** breaks a naive `isdigit()`; the name is the text
**before `[`**.

**`contacts`**
```
OptimusPrime                    CLI  beb9019e697d  11h ab,ac
DynamicRepeater                 REP  acaa59bf6959   3h Flood
```
`<name, padded> <TYPE> <key> <age> <flags>` — padded via the ANSI cursor escape.

**The TYPE column is the valuable part, and it was being thrown away:**

| TYPE | meaning |
|---|---|
| `CLI` | a node — companion app / handheld |
| `REP` | a repeater |
| `ROOM` | a room server |

On this device: **8 nodes, 44 repeaters, 2 room servers.** Classify by this column,
**never** by the name — "Death Star Repeater" must not be inferred from the word. Parse
pattern: text following the cursor escape begins at TYPE; fall back to
`<TYPE>\s+<hex key>` (8+ hex chars), which a contact name cannot fake.

Prose line to reject: `> 0 from 0 contacts in device`.

**`sync_msgs` (the inbox)**
```
public (7): KQ4EZN T-Deck: <emoji>
public (2): T-DECK PLUS: There are people using the mesh
OptimusPrime (0): Hello
OptimusPrime (D): Hi
```
`<scope> (<flag>): <text>`. For channel messages the **sender is prefixed inside the
text**, so split it out. `json_msgs on` is documented but **fails on this firmware**, so
this is deliberately a text parse — verified against 18 of 18 real lines.

**Log lines**: `INFO:meshcore:…` — always filtered out of parsed payload.

**Commands, VERIFIED in this exact form**

| command | result |
|---|---|
| `clock` | connectivity check: `Connected to <name> running on <fw>` |
| `get_channels` / `contacts` / `reload_contacts` | as above |
| `sync_msgs` | drains and returns the message queue (**consumes**) |
| `wait_msg`, `msgs_subscribe` | live receive primitives — present in the CLI source, not yet used |
| `floodadv` | **"Advert sent"** ✅ |
| `advert` | **"Advert sent"** ✅ |
| `zerohop` | ❌ `Problem while executing ['zerohop']` — documented but broken on this firmware |
| `json_msgs on` | ❌ fails on this firmware |
| `msg <name> <text> wait_ack` | direct message |
| `chan <n> <text>` | channel message (public = channel 0) |
| `add_channel <name> <key>` | restore a private channel |
| `import_contact <URI>` / `add_contact <key> <type> <name>` / `export_contact <name>` | contacts |

---

## 4. The app

```
src/server.py               stdlib-only HTTP server (no pip install needed)
src/transport_meshcore.py   CLI wrapper, parsers, roles, auto-recovery, dedupe, inbox
public/index.html           shell + client app -- ALL JS IS INLINED HERE
public/destinations.js      source of the inlined block; NOT loaded (dead file)
data/config.json            non-secret config            (gitignored)
data/auth.json              passphrase hash, mode 0600   (gitignored)
data/inbox.json             persistent message store     (written by the app)
```

**Why the JS is inlined:** the server serves the shell and the API, not arbitrary static
files, so `<script src="...">` 404s silently. Inline it, or add a static route with a
filename allowlist first.

**Run it**
```bash
cd ~/dev/active/meshcore-sender && python3 src/server.py   # → http://127.0.0.1:8788
```
Env: `PORT` (8788), `MESHCORE_ADDR` (defaults to the UUID), `MESHCORE_CLI`,
`MESHCORE_TIMEOUT` (30), `DATA_DIR`.

**Routes**
```
GET  /                    the shell
GET  /api/session         {first_run, authed, csrf}
GET  /api/health          radio reachability + radio_partial          (session)
GET  /api/nodes           destinations, ?force=1 bypasses 60s cache   (session)
GET  /api/messages        the stored inbox, instant, no radio         (session)
GET  /api/messages/fetch  drain sync_msgs, merge into the store       (session)
POST /api/setup           {passphrase} >= 8 chars, first run only
POST /api/login           {passphrase} -> httpOnly cookie ms_session + CSRF
POST /api/send            {text, targets}                             (session + CSRF)
POST /api/advert          {mode: "flood"|"zero"}                      (session + CSRF)
```
Targets are `chan:<index>` or `dm:<name>`. Session = cookie `ms_session` (12h). CSRF is
the `X-CSRF-Token` header compared against the session record.

**Auth:** the server's own passphrase (not the radio's). **The passphrase was set by the
user and must never be reset by an agent.** To deliberately return to first run, delete
`data/auth.json`.

---

## 5. How the pieces work now

**Dedupe.** The device can report the same channel twice per connection. Items are deduped
by id and tagged: `public`, `private`, `node`, `repeater`, `room`.

**Role classification.** `_contact_roles()` reads the TYPE column into a name→role map;
`_stamp_roles()` applies it. VERIFIED: 54 roles → `{node: 8, repeater: 44, room: 2}`.

**Auto-recovery.** `destinations()` wraps `_destinations_once()`. If there are **no
contacts**, it floods **one** advert, waits 5s, reloads contacts and re-reads once.
Bounded: one attempt per call plus a **90s cooldown**, because an advert is a mesh-wide
broadcast and a page refresh must not spam the air.

```
healthy      -> 56 destinations, 54 contacts, advert_fired=False
empty table  -> cli ['floodadv','reload_contacts'], 2 reads, contacts recovered
immediately  -> cli []      ("an advert was sent 0s ago, waiting 89s")
after 90s    -> advert allowed again
still empty  -> "no contacts after a flood advert - the radio may have no neighbours"
```

**Inbox.** `GET /api/messages` serves `data/inbox.json` instantly; `/fetch` drains
`sync_msgs` and merges new messages (keyed by raw line, so re-reads do not duplicate).
The UI groups by **scope** (contact or channel — never by sender, which splits a channel
into a thread per person), newest first, one line per message, and records your own sends
into the same thread as `you`.

**UI.** Sections Nodes / Repeaters / Rooms / Channels in a 2-column grid with filter chips
(All/Nodes/Repeaters/Rooms/Channels, remembered in localStorage); a Favourites section
pinned above them (★ per row); role badges; resizable message box; five message templates
(`RT (time)` stamps the clock at click time); Enter submits the passphrase; Flood advert +
Advert (0-hop) beside Refresh. The old `dm:Name` label is gone — the id survives only in
the invisible checkbox value, which is what makes Send work.

---

## 6. VERIFIED working

| Thing | Evidence |
|---|---|
| Connect over BLE by UUID | `Connected to MacMini running on a v1.17.1-d929643 (13) fw` |
| Destinations classified | 56 → `{public 1, private 1, node 8, repeater 44, room 2}` |
| **Send from the UI** | **`OptimusPrime — sent`** (user-confirmed); `channel 1 — sent` |
| **Receive** | `sync_msgs` → 18 real messages; `OptimusPrime Hi` pulled off the radio on demand |
| Inbox parser | 18 of 18 real lines, senders and emoji intact |
| Inbox store | `data/inbox.json` served instantly; UI shows it with timestamps |
| Advert route | `/api/advert` → 401 without a session (registered + gated) |
| Auto-recovery | empty table → `['floodadv','reload_contacts']` → contacts recovered; cooldown blocks repeats |
| Layout | `gridColumns: '633px 633px'` (2 columns); `starVisible: True` |
| Templates | chips present; clicking RT filled the box with `RT 13:07:32` |
| Enter to sign in | real keypress → `POST /api/login` → server answered |
| Inline JS | `node --check` on the extracted `<script>` blocks: OK |
| Device repair | private channel re-added with its key; `floodadv` → contacts 6 → 54 |
| Gates | first-run 428, no session 401, unknown path 404 JSON |

---

## 7. Known defects / rough edges

1. **The signed-in view is UNVERIFIED by the agent** — see §9. Biggest risk in this file.
2. **`zerohop` is broken on this firmware**, so the "Advert (0-hop)" button always reports
   a failure. It surfaces the device's error rather than faking success; remove it if a
   dead button is worse than the honesty.
3. **Channel order** inside the Channels section is alphabetical, so `private` can precede
   `Public channel`.
4. **~21s per healthy destinations call** — the CLI's BLE connect time, not app code. The
   60s server cache can also serve a stale payload, which produced a "56 in the header, 2
   in the list" mismatch.
5. `public/destinations.js` is dead. Delete it or re-inline.
6. Housekeeping: no `README.md`; leftover `meshtastic` strings; no `deploy/` units; no
   tests; no `.gitignore`; `notes/` symlink not created.

---

## 8. Requested, designed, NOT built

**Range test** — interval (default 15s), message prefix (default `RT`), Start/Stop,
per-target ack counters, rolling log. Each tick runs
`msg <contact> "<prefix> <time>" wait_ack`; **the ack is the delivery datum** — the thing
a shell loop can never prove. Routes `/api/range/start|stop|status`. The templates are
already the front half of this.

**Add contact** — a card taking **either** a contact URI (QR scanned on the phone) **or** a
public key, plus a name; and a per-contact "show URI". Maps to `import_contact` /
`add_contact` / `export_contact`. No QR library needed — the phone scans, the app imports.

**Deploy** — Dockerfile + launchd plist in `deploy/`, **staged only**. This user starts
services themselves. Loopback by default; wider exposure means Tailscale Serve, never a
public route.

---

## 9. The verification gap (read before promising anything)

**The agent cannot see the signed-in view.** The vault has no saved login for
`127.0.0.1:8788` and the user declined to save one. Consequence: every automated check
runs against the *sign-in* screen, where the destination list, chips, favourites and inbox
either don't exist or are empty — so UI bugs get discovered from the user's screenshots
after the fact. That is the round-robin this project suffered from, and it is a process
problem, not a coding one.

Two ways out, both legitimate:

1. **Save the login** (`browser_vault_save_login`) — the passphrase goes into a masked
   prompt, never into chat, and the agent can verify the real view directly.
2. **Work from screenshots deliberately** — treat each one as the test result, fix one
   thing per round, and never claim a UI change is verified.

What the agent *can* always verify without a session: the transport (Python),
`node --check` on the inline JS, computed styles and DOM structure on any page, and the
server log at `/tmp/meshcore-sender.log`, which logs every request with its status code —
that is how the `401` on `/api/messages` was finally diagnosed.

---

## 10. Working method that actually worked

- **Get ground truth before writing a parser.** Real captured output ended several "bugs";
  one was a length filter of my own invention.
- **Fail loudly.** Every patch asserts its anchor and compiles before writing, so a wrong
  assumption changes nothing instead of half-changing it.
- **`node --check` the extracted inline script** after every UI edit — cheap and decisive.
- **Read the server log** (`grep api/messages /tmp/meshcore-sender.log`) — it found in one
  command what three rounds of reasoning had missed.
- **Test the error path deliberately** — auto-recovery was verified with a fake radio that
  always returns no contacts.
- **Beware your own test harness.** A synthetic destination checkbox MUST have a
  `dm:`/`chan:` value or the host filter ignores it (cost two rounds); a `\u2605` inside an
  `re.sub` replacement raises `bad escape` and silently skips the write (use a lambda); a
  test subtree appended into a hidden region measures 0px.
- **Leave a debug hook** (`window.__mcDest` with `setData`/`render`) so the UI can be
  exercised with synthetic data without a session or any credential.

---

## 11. Environment notes (Hermes-specific)

- The terminal runtime **rejects shell background wrappers** (`nohup`, `&`, `disown`,
  `setsid`). Start services with `subprocess.Popen([...], start_new_session=True)`.
- **No top-level `import re`** in `transport_meshcore.py` — helpers import it locally.
- **`re.sub` processes escapes in the replacement** — use a lambda when the replacement
  contains backslashes.
- **`offsetParent` is null for `position: fixed`** elements — test visibility with
  `getBoundingClientRect()`.
- **The page's first button/field may belong to a hidden view** (the first-run card sits
  before the sign-in card), so handlers must pick the *visible* one.
- **`DATA_DIR` is not in scope inside the request handler.** Derive paths from
  `os.path.abspath(__file__)`. A `NameError` there made `/api/messages` fail on every call
  while the data sat in the store, innocent.
- **The browser caches the inline JS.** Add `no-store` (a `<meta>` is the quick fix) or you
  will debug ghost behaviour — several "I fixed it and nothing changed" rounds were this,
  not the code.
- **Adding one checkbox to the page can break the destination host.** `host()` used to take
  the common ancestor of *every* checkbox, which became `<body>` once the inbox's auto
  toggle existed — and the list re-rendered over the whole UI, wiping the cards. It now
  filters for `dm:`/`chan:` values and refuses to write into `body`.
- **A flex row where the name absorbs all shrinkage collapses names to "P."** — give the
  name a `min-width` floor and pin the badge/star/id with `flex: 0 0 auto`.

---

## 12. Rebuild from scratch — the recipe

1. Confirm the board runs **MeshCore**, not Meshtastic.
2. Get the BLE UUID (Bluetooth pane, or `meshcore-cli -l -T 10` while it advertises and
   nothing else holds it).
3. Make sure **nothing else holds the radio** (quit MeshCore One on Mac and phone;
   disconnect the Mac's pairing) and the process running the CLI has **Bluetooth
   permission**.
4. Prove connectivity: `meshcore-cli -a <UUID> clock` → expect `Connected to …`.
5. Repair device state if needed: `add_channel <name> <key>` for a missing private channel;
   `floodadv` + `reload_contacts` for an empty contact table.
6. `python3 src/server.py` → `http://127.0.0.1:8788` → set a passphrase → pick targets →
   Send. Messages you receive appear under **Messages**, grouped per conversation.
7. Never `-q`. Never trust the exit code. Never filter CLI lines by length. Strip ANSI.

---

## 13. Related pipelines on this machine

**Driving the MeshCore One app instead of the CLI.** Before the CLI worked, messages were
sent by driving the Mac app (process **`MC1`**, an iPad app wrapper) with AppleScript
clicks: a 15-second loop sent 124 messages over 35 minutes, verified. Field ≈
**(x+640, y+680)** for a 1000×700 window; **clear the field with ⌘A + Delete before
typing** or messages concatenate onto stale text. Logs:
`~/homelab-ops/artifacts/meshcore-loop-*.log`. That route cannot choose a destination.

**Muse → Cloudflare Pages watcher** (staged, not active):
`~/homelab-ops/tools/muse-deploy.sh` +
`~/homelab-ops/staged/com.assistant.musedeploy.plist`. Watches
`~/Downloads/thanksgiving-trip-app-*.zip`, deploys to the `gulftrip-2026` project. **Needs
`npx wrangler login` first** (the user's action; never handle their token). The zip wraps
content in a single subdirectory — deploy that, not the unzip root.
