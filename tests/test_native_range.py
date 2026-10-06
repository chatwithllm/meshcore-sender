"""Verify native range lifecycle and ACK semantics without radio hardware."""

import asyncio
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

path = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender/range_test.py"
spec = importlib.util.spec_from_file_location("native_range", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RangeTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_summary_has_actors_sources_and_honest_counts(self):
        notify = AsyncMock(return_value=[{"ok": True}])
        runner = module.NativeRangeTest(AsyncMock(), on_stop=notify)
        runner.state.update(running=True, targets=["dm:OptimusPrime", "chan:1"],
            started_by="Remote: OptimusPrime", started_via="LoRa", sent=5, acked=2,
            per_target={"dm:OptimusPrime": {"sent": 3,"acked":2,"broadcasts_sent":0},
                        "chan:1": {"sent":2,"acked":0,"broadcasts_sent":2}})
        result = await runner.stop("Alice", "HA", notify=True)
        text = "\n".join(result["summary_messages"])
        self.assertIn("Start: OptimusPrime (LoRa)", text)
        self.assertIn("Stop: Alice (HA)", text)
        self.assertIn("Attempts 5; DM ACK 2/3; channel TX 2 (no delivery ACK)", text)
        notify.assert_awaited_once()
        self.assertEqual(runner.state["acked"], 2)

    async def test_duplicate_concurrent_stops_notify_once_and_preserve_first_actor(self):
        notify = AsyncMock(return_value=[])
        runner = module.NativeRangeTest(AsyncMock(), on_stop=notify)
        runner.state.update(running=True, started_by="Alice", started_via="HA")
        results = await asyncio.gather(runner.stop("Bob", "LoRa", notify=True),
                                       runner.stop("Carol", "HA", notify=True))
        self.assertEqual(sum(r["was_running"] for r in results), 1)
        self.assertEqual(runner.state["stopped_by"], "Bob")
        notify.assert_awaited_once()

    async def test_shutdown_does_not_send_summary_and_idle_stop_sends_nothing(self):
        notify = AsyncMock()
        runner = module.NativeRangeTest(AsyncMock(), on_stop=notify)
        runner.state.update(running=True, started_by="Alice", started_via="HA")
        await runner.stop()
        await runner.stop(notify=True)
        notify.assert_not_awaited()

    async def test_failed_summary_does_not_undo_stop(self):
        notify = AsyncMock(side_effect=ConnectionError())
        runner = module.NativeRangeTest(AsyncMock(), on_stop=notify)
        runner.state.update(running=True, started_by="Alice", started_via="HA")
        result = await runner.stop(notify=True)
        self.assertTrue(result["ok"])
        self.assertFalse(runner.state["running"])
        self.assertFalse(runner.state["summary_delivery"][0]["ok"])

    async def test_summary_packets_fit_utf8_and_new_start_resets_previous_result(self):
        runner = module.NativeRangeTest(AsyncMock())
        runner.state.update(running=True, started_by="\u00e9" * 70, started_via="HA")
        result = await runner.stop("\u00e9" * 70, "LoRa")
        for text in result["summary_messages"]:
            self.assertLessEqual(len(text.encode()), 150)
        runner.start(["chan:1"])
        self.assertIsNone(runner.state["stopped_by"])
        self.assertFalse(runner.state["summary_messages"])
        await runner.stop()

    async def test_restart_is_blocked_while_final_summary_is_sending(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        async def notify(*args):
            entered.set()
            await release.wait()
            return []
        runner = module.NativeRangeTest(AsyncMock(), on_stop=notify)
        runner.state.update(running=True)
        stopping = asyncio.create_task(runner.stop(notify=True))
        await entered.wait()
        with self.assertRaises(ValueError):
            runner.start(["chan:1"])
        release.set()
        await stopping

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
        self.assertEqual(runner.state["interrupted"], 1)
        self.assertIn("unconfirmed", "\n".join(runner.state["summary_messages"]))
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
