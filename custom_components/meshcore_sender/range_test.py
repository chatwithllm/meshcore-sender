"""Cancellable range scheduler used by the native Bluetooth connection."""

import asyncio
import copy
import logging
import time

_LOGGER = logging.getLogger(__name__)


class NativeRangeTest:
    def __init__(self, send, create_task=asyncio.create_task):
        self.send = send
        self.create_task = create_task
        self.task = None
        self.state = {"running": False, "targets": [], "target": None,
                      "prefix": "ping", "interval": 30, "sent": 0, "acked": 0,
                      "per_target": {}, "log": [], "next_due_at": None,
                      "started_by": None}

    def snapshot(self):
        return {**copy.deepcopy(self.state), "server_now": time.time()}

    def start(self, targets, interval=30, prefix="ping"):
        if self.state["running"]:
            raise ValueError("Range test already running")
        interval = int(interval)
        if not 5 <= interval <= 300 or not targets or not prefix.strip() or len(prefix) > 40:
            raise ValueError("Choose targets, a prefix and an interval between 5 and 300 seconds")
        targets = list(dict.fromkeys(targets))
        self.state.update(running=True, targets=targets, target=targets[0],
                          interval=interval, prefix=prefix, sent=0, acked=0,
                          per_target={}, log=[], started_by="Home Assistant",
                          next_due_at=time.time())
        self.task = self.create_task(self._run())
        return {"ok": True, **self.snapshot()}

    async def stop(self):
        running = self.state["running"]
        self.state.update(running=False, next_due_at=None)
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None
        return {"ok": True, "was_running": running}

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
