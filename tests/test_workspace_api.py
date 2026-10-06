"""Exercise the production workspace handler without a full HA installation."""

import ast
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender"
source = ast.parse((ROOT / "workspace.py").read_text())
handler = next(n for n in source.body if isinstance(n, ast.AsyncFunctionDef)
               and n.name == "websocket_workspace")


class WorkspaceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        namespace = {"DOMAIN": "meshcore_sender", "find_pin_bridge": lambda *args: None,
                     "list_agents": lambda hass: [], "agent_safe": lambda hass, agent: False}
        node = copy.deepcopy(handler)
        node.decorator_list = []
        exec(compile(ast.Module(body=[node], type_ignores=[]), "workspace_handler", "exec"), namespace)
        self.handler = namespace["websocket_workspace"]
        self.client = SimpleNamespace(request=AsyncMock(return_value={"running": False}),
            history=SimpleNamespace(snapshot=Mock(return_value={"messages": [], "favorites": []}), favorite=Mock()))
        self.coordinator = SimpleNamespace(client=self.client, entry=SimpleNamespace(entry_id="entry", title="Radio"),
            data={"nodes": [{"id": "dm:OptimusPrime", "name": "OptimusPrime"}], "health": {"radio_ok": True}},
            last_update_success=True, action=AsyncMock(), setting=Mock(return_value=None), save_setting=Mock())
        self.hass = SimpleNamespace(data={"meshcore_sender": {"entry": self.coordinator}})
        self.connection = SimpleNamespace(user=SimpleNamespace(name="Test operator"), send_result=Mock(), send_error=Mock())

    async def call(self, action="snapshot", **fields):
        await self.handler(self.hass, self.connection, {
            "id": 1, "action": action, "prefix": "ping", "interval": 30, "enabled": True, **fields})

    def test_admin_boundary_is_applied_before_async_handler(self):
        decorators = [ast.unparse(n) for n in handler.decorator_list]
        self.assertIn("websocket_api.require_admin", decorators)
        self.assertLess(decorators.index("websocket_api.require_admin"),
                        decorators.index("websocket_api.async_response"))

    async def test_snapshot_does_not_send_radio_messages(self):
        await self.call()
        self.coordinator.action.assert_not_awaited()
        result = self.connection.send_result.call_args.args[1]
        self.assertTrue(result["history_supported"])
        self.assertTrue(result["available"])

    async def test_start_records_authenticated_user_and_interval(self):
        await self.call("start", targets=["dm:OptimusPrime"], interval=60)
        self.coordinator.action.assert_awaited_once_with("/api/range/start", {
            "targets": ["dm:OptimusPrime"], "interval": 60, "prefix": "ping", "started_by": "Test operator"})

    async def test_unknown_entry_cannot_control_another_radio(self):
        await self.call("stop", entry_id="unknown")
        self.coordinator.action.assert_not_awaited()
        self.connection.send_error.assert_called_once()

    async def test_invalid_favorite_is_rejected(self):
        await self.call("favorite", targets=["dm:Missing"])
        self.client.history.favorite.assert_not_called()
        self.connection.send_error.assert_called_once()

    async def test_unavailable_radio_history_remains_readable(self):
        self.coordinator.last_update_success = False
        await self.call()
        result = self.connection.send_result.call_args.args[1]
        self.assertFalse(result["available"])
        self.assertTrue(result["history_supported"])

    async def test_unknown_sender_resolves_without_modifying_saved_history(self):
        saved = {"messages": [{"pubkey_prefix": "abcd", "direction": "in", "name": "Unknown"}], "favorites": []}
        self.client.history.snapshot = lambda: copy.deepcopy(saved)
        self.client.mc = SimpleNamespace(get_contact_by_key_prefix=Mock(return_value={"adv_name": "OptimusPrime"}))
        await self.call()
        result = self.connection.send_result.call_args.args[1]
        self.assertEqual(result["messages"][0]["target"], "dm:OptimusPrime")
        self.assertEqual(saved["messages"][0]["name"], "Unknown")

    async def test_ai_control_enabled_selection_is_rejected_before_settings_change(self):
        self.client.remote = SimpleNamespace(configure=Mock(), snapshot=Mock(return_value={}))
        self.client.remote.data = {"controllers": []}
        await self.call("remote_settings", controllers=[], enabled=False, agent_id="conversation.unsafe")
        self.client.remote.configure.assert_not_called()
        self.connection.send_error.assert_called_once()
        self.coordinator.action.assert_not_awaited()

    async def test_pin_handler_is_admin_only_and_hides_transport_errors(self):
        pin_handler=next(n for n in source.body if isinstance(n,ast.AsyncFunctionDef)
                         and n.name=='websocket_update_radio_pin')
        self.assertIn('websocket_api.require_admin',[ast.unparse(n) for n in pin_handler.decorator_list])
        node=copy.deepcopy(pin_handler);node.decorator_list=[]
        namespace={'DOMAIN':'meshcore_sender','update_radio_pin':AsyncMock(side_effect=RuntimeError('secret 012345'))}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'pin_handler','exec'),namespace)
        await namespace['websocket_update_radio_pin'](self.hass,self.connection,{'id':1,'entry_id':'entry','password':'012345'})
        self.assertNotIn('012345',str(self.connection.send_error.call_args))
