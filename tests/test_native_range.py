"""Verify native range lifecycle and ACK semantics without radio hardware."""

import asyncio
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender/range_test.py"
spec = importlib.util.spec_from_file_location("native_range", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RangeTests(unittest.IsolatedAsyncioTestCase):
    async def test_channel_success_is_not_receiver_ack(self):
        async def send(target, text, timeout):
            return {"ok": True, "acked": not target.startswith("chan:")}
        runner = module.NativeRangeTest(send)
        runner.state["targets"] = ["dm:OptimusPrime", "chan:1"]
        await runner._send_round(1)
        state = runner.snapshot()
        self.assertEqual(state["sent"], 2)
        self.assertEqual(state["acked"], 1)
        self.assertEqual(state["per_target"]["chan:1"]["acked"], 0)
        self.assertEqual(state["per_target"]["chan:1"]["broadcasts_sent"], 1)

    async def test_failure_does_not_prevent_next_round(self):
        calls = 0
        async def send(target, text, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ConnectionError("Radio disconnected")
            return {"ok": True, "acked": True}
        runner = module.NativeRangeTest(send)
        runner.state["targets"] = ["dm:OptimusPrime"]
        await runner._send_round(1)
        await runner._send_round(2)
        self.assertEqual(runner.state["sent"], 2)
        self.assertEqual(runner.state["acked"], 1)

    async def test_stop_cancels_inflight_send_and_allows_restart(self):
        started = asyncio.Event()
        async def send(target, text, timeout):
            started.set()
            await asyncio.Event().wait()
        runner = module.NativeRangeTest(send)
        runner.start(["dm:OptimusPrime"], 30)
        await asyncio.wait_for(started.wait(), 1)
        with self.assertRaises(ValueError):
            runner.start(["dm:OptimusPrime"], 30)
        await runner.stop()
        self.assertFalse(runner.state["running"])
        self.assertIsNone(runner.state["next_due_at"])
        runner.start(["dm:OptimusPrime"], 30)
        await runner.stop()

    async def test_actual_scheduler_sends_next_round(self):
        sent = []
        second = asyncio.Event()
        async def send(target, text, timeout):
            sent.append((text, asyncio.get_running_loop().time()))
            if len(sent) == 2:
                second.set()
            return {"ok": True, "acked": True}
        runner = module.NativeRangeTest(send)
        runner.start(["dm:OptimusPrime"], 5)
        try:
            await asyncio.wait_for(second.wait(), 7)
            self.assertGreaterEqual(sent[1][1] - sent[0][1], 4.9)
            self.assertEqual(runner.state["acked"], 2)
        finally:
            await runner.stop()


if __name__ == "__main__":
    unittest.main()
