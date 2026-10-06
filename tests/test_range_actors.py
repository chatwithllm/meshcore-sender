"""Verify actor attribution on HA service and button paths without HA calls."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender"


class ActorTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_uses_authenticated_user_and_automation_fallback(self):
        source = ast.parse((ROOT / "__init__.py").read_text())
        function = next(n for n in ast.walk(source) if isinstance(n, ast.AsyncFunctionDef) and n.name == "handle_action")
        chosen = SimpleNamespace(start=AsyncMock(), action=AsyncMock())
        hass = SimpleNamespace(data={"meshcore_sender": {"entry": chosen}},
            auth=SimpleNamespace(async_get_user=AsyncMock(return_value=SimpleNamespace(name="Alice"))))
        namespace = {"hass": hass, "DOMAIN": "meshcore_sender", "MeshCoreError": RuntimeError,
                     "HomeAssistantError": RuntimeError}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "range_service", "exec"), namespace)
        call = SimpleNamespace(service="stop_range_test", context=SimpleNamespace(user_id="user"), data={})
        await namespace["handle_action"](call)
        chosen.action.assert_awaited_with("/api/range/stop", {"stopped_by": "Alice", "stopped_via": "HA"})
        call.context = None
        await namespace["handle_action"](call)
        chosen.action.assert_awaited_with("/api/range/stop", {"stopped_by": "Home Assistant automation", "stopped_via": "HA"})
        call.service = "start_range_test"
        call.context = SimpleNamespace(user_id="user")
        call.data = {"targets": ["dm:OptimusPrime"], "interval": 30, "prefix": "ping"}
        await namespace["handle_action"](call)
        chosen.start.assert_awaited_with(["dm:OptimusPrime"], 30, "ping", started_by="Alice")

    async def test_button_uses_service_context_for_start_and_stop(self):
        source = ast.parse((ROOT / "button.py").read_text())
        method = next(n for n in ast.walk(source) if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_press")
        namespace = {"MeshCoreError": RuntimeError, "HomeAssistantError": RuntimeError}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "range_button", "exec"), namespace)
        button = SimpleNamespace(_context=SimpleNamespace(user_id="user"), key="stop",
            hass=SimpleNamespace(auth=SimpleNamespace(async_get_user=AsyncMock(return_value=SimpleNamespace(name="Alice")))),
            coordinator=SimpleNamespace(action=AsyncMock(), start=AsyncMock()))
        await namespace["async_press"](button)
        button.coordinator.action.assert_awaited_with("/api/range/stop", {"stopped_by": "Alice", "stopped_via": "HA"})
        button.key = "start"
        await namespace["async_press"](button)
        button.coordinator.start.assert_awaited_with(started_by="Alice")
