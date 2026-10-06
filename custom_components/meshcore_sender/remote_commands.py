"""Bounded, confirmation-only radio control. AI never executes an action."""

import asyncio
import copy
import re
import time


class RemoteCommands:
    def __init__(self, nodes, send, execute, interpret, data=None, changed=lambda: None):
        self.nodes = nodes
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
            return {"action": "clarify", "interval": interval, "default_sender": True}
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
        await self.send(key, text)
        self.record(name, text)

    async def offer(self, key, name, proposal):
        if proposal["action"] == "clarify":
            if not proposal.get("default_sender"):
                await self.reply(key, name, "Specify targets: range test NAME every 30s. Multiple: NAME1 and NAME2. Cancel to exit.")
                return
            choices = [{"action": "start", "targets": [n["id"]],
                        "interval": proposal.get("interval", 30), "prefix": "ping"}
                       for n in self.nodes() if n["name"].casefold() == name.casefold()][:1]
            if not choices:
                await self.reply(key, name, "Specify targets: range test NAME every 30s. Multiple: NAME1 and NAME2. Cancel to exit.")
                return
            proposal = choices[0]
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
        if self.allowed(key):
            self.pending[key] = {"proposal": proposal, "expires": time.monotonic() + 120}

    async def handle(self, key, name, text):
        if not self.allowed(key):
            return
        now = time.monotonic()
        value = text.strip().lower()
        responding = key in self.pending and value in ("1", "confirm", "cancel", "cancel command")
        if now - self.recent.get(key, -100) < 2 and not responding:
            self.record(name, "Rate limited")
            return
        self.recent[key] = now
        if value in ("cancel", "cancel command"):
            self.pending.pop(key, None)
            await self.reply(key, name, "Command cancelled. A running test is unchanged; send stop range test to stop it.")
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
            proposal = self.parse(text)
            if proposal is None and self.data["agent_id"]:
                proposal = self.validate(await asyncio.wait_for(
                    self.interpret(self.data["agent_id"], text, self.nodes()), timeout=25))
            if revision != self.revision or not self.allowed(key):
                return
            if proposal is None:
                await self.reply(key, name, "Commands: status; range test NAME every 30s; stop range test; cancel.")
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
