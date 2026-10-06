"""Cancellable range scheduler used by the native Bluetooth connection."""

import asyncio
import copy
import logging
import time

_LOGGER = logging.getLogger(__name__)


class NativeRangeTest:
    def __init__(self, send, create_task=asyncio.create_task, on_stop=None):
        self.send = send
        self.create_task = create_task
        self.task = None
        self.on_stop = on_stop
        self.stop_lock = asyncio.Lock()
        self.stopping = False
        self.state = {"running": False, "targets": [], "target": None,
                      "prefix": "ping", "interval": 30, "sent": 0, "acked": 0,
                      "per_target": {}, "log": [], "next_due_at": None,
                      "started_by": None, "started_via": None, "stopped_by": None,
                      "stopped_via": None, "summary_messages": [], "summary_delivery": [],
                      "interrupted": 0}

    def snapshot(self):
        return {**copy.deepcopy(self.state), "finishing": self.stopping, "server_now": time.time()}

    def start(self, targets, interval=30, prefix="ping", started_by="Home Assistant", started_via="HA"):
        if self.state["running"] or self.stopping:
            raise ValueError("Range test already running")
        interval = int(interval)
        if not 5 <= interval <= 300 or not targets or not prefix.strip() or len(prefix) > 40:
            raise ValueError("Choose targets, a prefix and an interval between 5 and 300 seconds")
        targets = list(dict.fromkeys(targets))
        self.state.update(running=True, targets=targets, target=targets[0],
                          interval=interval, prefix=prefix, sent=0, acked=0,
                          per_target={}, log=[], started_by=started_by, started_via=started_via,
                          stopped_by=None, stopped_via=None, summary_messages=[], summary_delivery=[], interrupted=0,
                          next_due_at=time.time())
        self.task = self.create_task(self._run())
        return {"ok": True, **self.snapshot()}

    @staticmethod
    def actor_label(name):
        name = str(name or "Unknown").removeprefix("Remote: ")
        raw = name.encode()
        return name if len(raw) <= 60 else raw[:57].decode("utf-8", errors="ignore") + "..."

    def summary(self):
        state = self.state
        direct = sum(s["sent"] for t, s in state["per_target"].items() if not t.startswith("chan:"))
        broadcasts = sum(s["broadcasts_sent"] for t, s in state["per_target"].items() if t.startswith("chan:"))
        lines = ["Range test stopped.",
                 f"Start: {self.actor_label(state['started_by'])} ({state['started_via']}).",
                 f"Stop: {self.actor_label(state['stopped_by'])} ({state['stopped_via']}).",
                 f"Attempts {state['sent']}; DM ACK {state['acked']}/{direct}; channel TX {broadcasts} (no delivery ACK)."]
        if state["interrupted"]:
            lines.append(f"{state['interrupted']} in-flight attempt(s) unconfirmed.")
        packets = []
        text = ""
        for line in lines:
            candidate = (text + "\n" if text else "") + line
            if text and len(candidate.encode()) > 150:
                packets.append(text)
                text = "Range summary:\n" + line
            else:
                text = candidate
        if text:
            packets.append(text)
        return packets

    async def stop(self, stopped_by="Home Assistant", stopped_via="HA", *, notify=False, exclude=None):
        async with self.stop_lock:
            running = self.state["running"]
            if not running:
                return {"ok": True, "was_running": False}
            self.stopping = True
            self.state.update(running=False, next_due_at=None)
            try:
                if self.task and not self.task.done():
                    self.task.cancel()
                    try:
                        await self.task
                    except asyncio.CancelledError:
                        pass
                self.task = None
                self.state.update(stopped_by=stopped_by, stopped_via=stopped_via)
                self.state["summary_messages"] = self.summary()
                if notify and self.on_stop:
                    try:
                        self.state["summary_delivery"] = await asyncio.wait_for(self.on_stop(self.snapshot(), exclude), timeout=60)
                    except Exception:
                        self.state["summary_delivery"] = [{"ok": False, "detail": "Summary delivery failed"}]
                return {"ok": True, "was_running": True,
                        "summary_messages": list(self.state["summary_messages"])}
            finally:
                self.stopping = False

    async def _send_round(self, seq):
        for target in self.state["targets"]:
            stamp = time.strftime("%H:%M:%S")
            text = f"{self.state['prefix']} {seq} [{stamp}]"
            stat = self.state["per_target"].setdefault(
                target, {"sent": 0, "acked": 0, "broadcasts_sent": 0}
            )
            self.state["sent"] += 1
            stat["sent"] += 1
            try:
                result = await self.send(target, text, min(20, self.state["interval"] - 2))
            except asyncio.CancelledError:
                self.state["interrupted"] += 1
                raise
            except Exception as error:
                _LOGGER.warning("Range transmission failed for %s: %s", target, error)
                result = {"ok": False, "acked": False, "rtt_ms": 0, "out": str(error)}
            if target.startswith("chan:"):
                stat["broadcasts_sent"] += int(bool(result.get("ok")))
            elif result.get("acked"):
                stat["acked"] += 1
                self.state["acked"] += 1
            self.state["log"].append({"seq": seq, "target": target, "ts": stamp,
                                      "acked": bool(result.get("acked")),
                                      "rtt_ms": result.get("rtt_ms", 0),
                                      "detail": result.get("out", "")})
            self.state["log"] = self.state["log"][-200:]

    async def _run(self):
        next_at = time.monotonic()
        seq = 0
        try:
            while self.state["running"]:
                seq += 1
                self.state["next_due_at"] = None
                await self._send_round(seq)
                next_at += self.state["interval"]
                now = time.monotonic()
                # Skip missed ticks rather than sending a burst after a slow ACK.
                while next_at < now:
                    next_at += self.state["interval"]
                delay = max(0, next_at - now)
                self.state["next_due_at"] = time.time() + delay
                await asyncio.sleep(delay)
        finally:
            self.state.update(running=False, next_due_at=None)
