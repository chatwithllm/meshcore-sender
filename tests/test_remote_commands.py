"""No radio or provider requests: exercise the production control boundary."""

import asyncio
import importlib.util
from pathlib import Path
import time
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender"
spec = importlib.util.spec_from_file_location("remote_commands", ROOT / "remote_commands.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RemoteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.nodes = [{"id": "dm:OptimusPrime", "name": "OptimusPrime", "kind": "node"},
                      {"id": "chan:1", "name": "Family", "kind": "private"}]
        self.send = AsyncMock()
        self.execute = AsyncMock(return_value="Done")
        self.ai = AsyncMock(return_value={"action": "start", "targets": ["dm:OptimusPrime"], "interval": 30})
        self.engine = module.RemoteCommands(lambda: self.nodes, self.send, self.execute, self.ai)
        self.engine.configure(True, [{"key": "a" * 64, "name": "OptimusPrime"}], "conversation.safe")
        self.key = "a" * 64

    async def handle(self, text, key=None):
        self.engine.recent.clear()
        await self.engine.handle(key or self.key, "OptimusPrime", text)

    async def test_unknown_sender_cannot_invoke_ai_or_actions(self):
        await self.handle("do things", "b" * 64)
        self.ai.assert_not_awaited(); self.execute.assert_not_awaited(); self.send.assert_not_awaited()

    async def test_start_requires_sender_confirmation(self):
        await self.handle("Start range test OptimusPrime every 30s")
        self.execute.assert_not_awaited(); self.ai.assert_not_awaited()
        self.assertEqual(self.engine.pending[self.key]["proposal"]["interval"], 30)
        await self.handle("1", "b" * 64)
        self.execute.assert_not_awaited()
        await self.handle("1")
        self.execute.assert_awaited_once()
        await self.handle("1")
        self.assertEqual(self.execute.await_count, 1)

    async def test_ai_fallback_requires_confirmation(self):
        await self.handle("keep checking optimus every half minute")
        self.ai.assert_awaited_once(); self.execute.assert_not_awaited()
        await self.handle("confirm")
        self.execute.assert_awaited_once()

    async def test_cancel_does_not_stop_running_test(self):
        await self.handle("stop range test")
        self.execute.assert_not_awaited()
        await self.handle("cancel")
        await self.handle("1")
        self.execute.assert_not_awaited()

    async def test_expired_confirmation_cannot_execute(self):
        await self.handle("ping OptimusPrime in 30 sec")
        self.engine.pending[self.key]["expires"] = 0
        await self.handle("1")
        self.execute.assert_not_awaited()

    async def test_permissions_edit_cancels_pending(self):
        await self.handle("stop")
        self.engine.configure(True, [{"key": self.key, "name": "OptimusPrime"}], "")
        await self.handle("1")
        self.execute.assert_not_awaited()

    async def test_permission_revoked_during_ai_call(self):
        async def revoke(*args):
            self.engine.configure(False, [], "")
            return {"action": "stop"}
        self.ai.side_effect = revoke
        await self.handle("finish that test")
        self.assertFalse(self.engine.pending)
        self.send.assert_not_awaited(); self.execute.assert_not_awaited()

    async def test_malformed_ai_or_unknown_targets_fail_closed(self):
        for proposal in ({"action": "turn_on"}, {"action": "start", "targets": ["dm:Missing"]},
                         {"action": "start", "targets": ["dm:OptimusPrime"], "interval": True},
                         {"action": "start", "targets": ["dm:OptimusPrime"], "interval": 1}):
            self.ai.return_value = proposal
            await self.handle("please do something")
        self.assertFalse(self.engine.pending)
        self.execute.assert_not_awaited()

    async def test_status_is_read_only(self):
        await self.handle("status")
        self.execute.assert_awaited_once_with({"action": "status"}, "OptimusPrime")
        self.ai.assert_not_awaited()

    async def test_multiple_targets_and_channel(self):
        await self.handle("range test OptimusPrime and Family every 1 min")
        proposal = self.engine.pending[self.key]["proposal"]
        self.assertEqual(proposal["targets"], ["dm:OptimusPrime", "chan:1"])
        self.assertEqual(proposal["interval"], 60)

    async def test_restart_restores_permissions_but_not_confirmation(self):
        await self.handle("stop")
        restored = module.RemoteCommands(lambda: self.nodes, self.send, self.execute, self.ai, self.engine.snapshot())
        self.assertTrue(restored.allowed(self.key))
        self.assertFalse(restored.pending)

    async def test_stale_or_missing_timestamp_does_not_enqueue(self):
        for stamp in (None, time.time() - 121, time.time() + 60):
            self.engine.submit(self.key, "OptimusPrime", "stop", stamp, asyncio.create_task)
        self.assertTrue(self.engine.queue.empty())
        self.assertIsNone(self.engine.worker)

    async def test_queue_drains_and_close_cancels_worker(self):
        self.engine.submit(self.key, "OptimusPrime", "status", time.time(), asyncio.create_task)
        await self.engine.worker
        self.execute.assert_awaited_once()
        await self.engine.close()

    async def test_rate_limit_does_not_execute_twice(self):
        await self.handle("status")
        await self.engine.handle(self.key, "OptimusPrime", "status")
        self.assertEqual(self.execute.await_count, 1)

    async def test_missing_target_is_proposed_not_executed(self):
        await self.handle("range test")
        self.execute.assert_not_awaited()
        self.assertEqual(self.engine.pending[self.key]["proposal"]["targets"], ["dm:OptimusPrime"])

    async def test_removed_target_cannot_execute(self):
        await self.handle("range test OptimusPrime every 30s")
        self.nodes.clear()
        with self.assertRaises(ValueError):
            await self.handle("1")
        self.execute.assert_not_awaited()

    async def test_ai_timeout_is_visible_and_never_executes(self):
        self.ai.side_effect = asyncio.TimeoutError
        await self.handle("fuzzy request")
        self.execute.assert_not_awaited()
        self.assertIn("timed out", self.send.call_args.args[1])

    async def test_duplicate_target_names_fail_closed(self):
        self.nodes.append(dict(self.nodes[0]))
        await self.handle("range test OptimusPrime every 30s")
        self.assertFalse(self.engine.pending)
        self.execute.assert_not_awaited()

    async def test_failed_confirmation_reply_does_not_arm_command(self):
        self.send.side_effect = RuntimeError("Radio offline")
        with self.assertRaises(RuntimeError):
            await self.handle("stop")
        self.assertFalse(self.engine.pending)

    async def test_immediate_confirmation_is_not_rate_limited(self):
        await self.engine.handle(self.key, "OptimusPrime", "stop")
        await self.engine.handle(self.key, "OptimusPrime", "1")
        self.execute.assert_awaited_once_with({"action": "stop"}, "OptimusPrime")

    async def test_ai_clarification_does_not_assume_range_test(self):
        self.ai.return_value = {"action": "clarify"}
        await self.handle("Hello")
        self.assertFalse(self.engine.pending)
        self.execute.assert_not_awaited()
