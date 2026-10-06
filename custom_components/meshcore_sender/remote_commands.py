"""Bounded, confirmation-only radio control. AI never executes an action."""

import asyncio
import copy
import re
import time


class RemoteCommands:
    def __init__(self, nodes, send, execute, interpret, data=None, changed=lambda: None, menu_nodes=None):
        self.nodes = nodes
        self.menu_nodes = menu_nodes or nodes
        self.send = send
        self.execute = execute
        self.interpret = interpret
        self.data = data or {}
        self.data.setdefault("enabled", False)
        self.data.setdefault("controllers", [])
        self.data.setdefault("agent_id", "")
        self.data.setdefault("history", [])
        self.changed = changed
        self.pending = {}
        self.recent = {}
        self.revision = 0
        self.queue = asyncio.Queue(maxsize=8)
        self.worker = None
        self.closed = False

    def snapshot(self):
        return {**copy.deepcopy(self.data), "pending": len(self.pending)}

    def configure(self, enabled, controllers, agent_id):
        self.data.update(enabled=enabled, controllers=copy.deepcopy(controllers), agent_id=agent_id)
        self.revision += 1
        self.pending.clear()
        self.changed()

    def record(self, name, result):
        self.data["history"].append({"at": time.time(), "controller": name, "result": result})
        self.data["history"] = self.data["history"][-100:]
        self.changed()

    def allowed(self, key):
        return self.data["enabled"] and any(c["key"] == key for c in self.data["controllers"])

    def submit(self, key, name, text, timestamp, create_task):
        # Delayed/replayed companion inbox traffic must not become new commands.
        if not self.allowed(key) or not isinstance(timestamp, (int, float)):
            return
        if not 0 <= time.time() - timestamp <= 120 or len(text.encode()) > 150:
            return
        try:
            self.queue.put_nowait((key, name, text, timestamp))
        except asyncio.QueueFull:
            self.record(name, "Busy: command queue full")
            return
        if self.worker is None or self.worker.done():
            self.worker = create_task(self._drain())

    async def _drain(self):
        while not self.queue.empty() and not self.closed:
            key, name, text, timestamp = self.queue.get_nowait()
            try:
                if time.time() - timestamp <= 120:
                    await self.handle(key, name, text)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.record(name, "Command failed; check radio connection")
                self.pending.pop(key, None)
                try:
                    await self.reply(key, name, "Command failed. Check targets and the radio connection, then send the request again.")
                except Exception:
                    pass
            finally:
                self.queue.task_done()

    def validate(self, proposal):
        if not isinstance(proposal, dict):
            raise ValueError("Invalid AI response")
        action = proposal.get("action")
        if action not in ("status", "start", "stop", "clarify", "cancel"):
            raise ValueError("Unsupported command")
        if action != "start":
            return {"action": action}
        targets = proposal.get("targets")
        nodes = self.nodes()
        valid = {n["id"] for n in nodes if sum(other["id"] == n["id"] for other in nodes) == 1}
        interval = proposal.get("interval", 30)
        prefix = proposal.get("prefix", "ping")
        if (not isinstance(targets, list) or not 1 <= len(targets) <= 8
                or any(not isinstance(t, str) or t not in valid for t in targets)
                or len(set(targets)) != len(targets)):
            raise ValueError("Choose available targets")
        if type(interval) is not int or not 5 <= interval <= 300:
            raise ValueError("Interval must be 5-300 seconds")
        if not isinstance(prefix, str) or not prefix.strip() or len(prefix.encode()) > 40:
            raise ValueError("Invalid message prefix")
        return {"action": "start", "targets": targets, "interval": interval, "prefix": prefix.strip()}

    def parse(self, text):
        value = text.strip().lower().rstrip(".!?")
        if value in ("status", "range status", "test status"):
            return {"action": "status"}
        if value in ("cancel", "cancel command"):
            return {"action": "cancel"}
        if value in ("stop", "stop range", "stop range test", "stop test"):
            return {"action": "stop"}
        match = re.fullmatch(r"(?:start\s+)?(?:range test|ping|check)\s*(.*?)\s*(?:(?:every|in)\s+(\d+)\s*(s|sec|secs|seconds?|m|min|minutes?))?", value)
        if not match:
            return None
        target_text, count, unit = match.groups()
        interval = int(count) * (60 if unit.startswith("m") else 1) if count else 30
        if not 5 <= interval <= 300:
            raise ValueError("Interval must be 5-300 seconds")
        if not target_text:
            return {"action": "clarify", "interval": interval, "target_menu": True}
        pieces = re.split(r"\s+and\s+|\s*,\s*", target_text)
        targets = []
        for piece in pieces:
            matches = [n for n in self.nodes() if n["name"].lower() == piece]
            if len(matches) != 1:
                return None
            targets.append(matches[0]["id"])
        return self.validate({"action": "start", "targets": targets, "interval": interval})

    async def reply(self, key, name, text):
        if not self.allowed(key):
            return
        # Names may change; resolve the saved public key at transmission time.
        for packet in text if isinstance(text, list) else [text]:
            if not self.allowed(key):
                return
            result = await self.send(key, packet)
            if isinstance(result, dict) and not result.get("ok", True):
                raise ValueError("Reply was not delivered")
            self.record(name, packet)

    @staticmethod
    def menu_label(text, limit=45):
        raw = text.encode("utf-8")
        return text if len(raw) <= limit else raw[:limit - 3].decode("utf-8", errors="ignore") + "..."

    async def show_menu(self, key, name, interval=30, pending=None, page=0):
        revision = self.revision
        if pending is None:
            nodes = self.menu_nodes()
            choices = [copy.deepcopy(n) for n in nodes
                       if sum(other["id"] == n["id"] for other in nodes) == 1]
            choices.sort(key=lambda n: (n["name"].casefold(), n["id"]))
            if not choices:
                await self.reply(key, name, "No range targets in this menu. Ask the administrator to add favorite contacts or channels. Cancel to exit.")
                return
            pending = {"menu": choices, "interval": interval, "expires": time.monotonic() + 120}
        lines = [f"{i} {self.menu_label(n['name'])} ({'channel' if n['id'].startswith('chan:') else 'contact'})"
                 for i, n in enumerate(pending["menu"], 1)]
        header = f"Range targets, every {pending['interval']}s:\n"
        footer = "\nReply 1 or 1,2; 1 every 60s; next/back; cancel. Expires 2m."
        pages, current = [], []
        for line in lines:
            if current and len((header + "\n".join(current + [line]) + footer).encode()) > 150:
                pages.append(current)
                current = []
            current.append(line)
        if current:
            pages.append(current)
        page = max(0, min(page, len(pages) - 1))
        await self.reply(key, name, header + "\n".join(pages[page]) + footer)
        if self.allowed(key) and revision == self.revision:
            pending["page"] = page
            self.pending[key] = pending

    async def select_menu(self, key, name, text, pending):
        match = re.fullmatch(r"(\d+(?:\s*,\s*\d+)*)(?:\s+every\s+(\d+)\s*(s|sec|secs|seconds?|m|min|minutes?))?", text)
        if not match:
            return False
        if pending["expires"] < time.monotonic():
            self.pending.pop(key, None)
            await self.reply(key, name, "Target menu expired. Send range test for a new list.")
            return True
        numbers = [int(n.strip()) for n in match[1].split(",")]
        interval = int(match[2]) * (60 if match[3].startswith("m") else 1) if match[2] else pending["interval"]
        if (not 1 <= len(numbers) <= 8 or len(set(numbers)) != len(numbers)
                or any(not 1 <= n <= len(pending["menu"]) for n in numbers) or not 5 <= interval <= 300):
            await self.reply(key, name, "Choose 1-8 distinct numbers from the menu; interval must be 5-300s. Cancel to exit.")
            return True
        available = self.menu_nodes()
        targets = []
        for number in numbers:
            choice = pending["menu"][number - 1]
            matches = [n for n in available if
                       (n.get("public_key") == choice["public_key"] if choice.get("public_key")
                        else n["id"] == choice["id"] and n["name"] == choice["name"])]
            if len(matches) != 1:
                self.pending.pop(key, None)
                await self.reply(key, name, "A selected target changed or is unavailable. Send range test for a new list.")
                return True
            targets.append(matches[0]["id"])
        self.pending.pop(key, None)
        await self.offer(key, name, {"action": "start", "targets": targets, "interval": interval, "prefix": "ping"})
        return True

    async def offer(self, key, name, proposal):
        revision = self.revision
        if proposal["action"] == "clarify":
            if not proposal.get("target_menu"):
                await self.reply(key, name, "Specify targets: range test NAME every 30s. Multiple: NAME1 and NAME2. Cancel to exit.")
                return
            await self.show_menu(key, name, proposal.get("interval", 30))
            return
        proposal = self.validate(proposal)
        if proposal["action"] not in ("start", "stop"):
            return
        if proposal["action"] == "start":
            names = {n["id"]: n["name"] for n in self.nodes()}
            label = ", ".join(names[t] for t in proposal["targets"])
            text = f"Start {label} every {proposal['interval']}s, prefix {proposal['prefix']}? 1 confirm, cancel. Expires 2 min."
            if len(text.encode()) > 150:
                # Disclose all targets before the short confirmation packet.
                for target in proposal["targets"]:
                    await self.reply(key, name, "Target: " + names[target])
                text = f"Start {len(proposal['targets'])} targets every {proposal['interval']}s, prefix {proposal['prefix']}? 1 confirm, cancel. Expires 2 min."
        else:
            text = "Stop the current range test? 1 confirm, cancel. Expires 2 min."
        await self.reply(key, name, text)
        if self.allowed(key) and revision == self.revision:
            self.pending[key] = {"proposal": proposal, "expires": time.monotonic() + 120}

    async def handle(self, key, name, text):
        if not self.allowed(key):
            return
        now = time.monotonic()
        value = text.strip().lower()
        menu = self.pending.get(key)
        menu = menu if menu and "menu" in menu else None
        responding = key in self.pending and (value in ("1", "confirm", "cancel", "cancel command")
                     or menu and (value in ("next", "back") or value[:1].isdigit()))
        if now - self.recent.get(key, -100) < 2 and not responding:
            self.record(name, "Rate limited")
            return
        self.recent[key] = now
        if value in ("cancel", "cancel command"):
            self.pending.pop(key, None)
            await self.reply(key, name, "Command cancelled. A running test is unchanged; send stop range test to stop it.")
            return
        if menu:
            if value in ("next", "back"):
                if menu["expires"] < now:
                    self.pending.pop(key, None)
                    await self.reply(key, name, "Target menu expired. Send range test for a new list.")
                else:
                    await self.show_menu(key, name, pending=menu, page=menu["page"] + (1 if value == "next" else -1))
                return
            if await self.select_menu(key, name, value, menu):
                return
            if value[:1].isdigit():
                await self.reply(key, name, "Reply with a number, 1,2 for several, or 1 every 60s. Cancel to exit.")
                return
            if value == "confirm":
                await self.reply(key, name, "Choose a target number first. No test started.")
                return
        if value in ("1", "confirm"):
            pending = self.pending.pop(key, None)
            if not pending or pending["expires"] < now:
                await self.reply(key, name, "No pending command, or it expired. Send your request again.")
                return
            proposal = self.validate(pending["proposal"])
            result = await self.execute(proposal, name)
            await self.reply(key, name, result)
            return
        self.pending.pop(key, None)
        revision = self.revision
        try:
            proposal = ({"action": "clarify", "target_menu": True, "interval": 30}
                        if value in ("help", "targets", "range targets", "range test targets") else self.parse(text))
            if proposal is None and self.data["agent_id"]:
                proposal = self.validate(await asyncio.wait_for(
                    self.interpret(self.data["agent_id"], text, self.nodes()), timeout=25))
            if revision != self.revision or not self.allowed(key):
                return
            if proposal is None:
                await self.reply(key, name, "Commands: status; range test (numbered targets); range test NAME every 30s; stop range test; cancel.")
            elif proposal["action"] == "status":
                await self.reply(key, name, await self.execute(proposal, name))
            elif proposal["action"] == "cancel":
                await self.reply(key, name, "Command cancelled.")
            else:
                await self.offer(key, name, proposal)
        except asyncio.TimeoutError:
            await self.reply(key, name, "AI timed out. No action taken. Try: range test NAME every 30s.")
        except Exception:
            await self.reply(key, name, "Could not interpret this command safely. No action taken. Use range test NAME every 30s or status.")

    async def close(self):
        self.closed = True
        self.pending.clear()
        if self.worker and not self.worker.done():
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass
