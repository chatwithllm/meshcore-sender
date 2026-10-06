"""Agent safety is a configuration check, not a prompt-only restriction."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1] / "custom_components/meshcore_sender"


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = SimpleNamespace(_subentry=SimpleNamespace(data={}), supported_features=0)
        self.entry = SimpleNamespace(platform="codex_conversation", disabled_by=None)
        self.lookup = Mock(return_value=self.agent)
        registry = SimpleNamespace(async_get=Mock(side_effect=lambda key: self.entry))
        namespace = {"SUPPORTED": {"codex_conversation", "google_generative_ai_conversation"},
                     "er": SimpleNamespace(async_get=lambda hass: registry),
                     "conversation": SimpleNamespace(async_get_agent=self.lookup)}
        functions = [n for n in ast.parse((ROOT / "ai_agent.py").read_text()).body
                     if isinstance(n, ast.FunctionDef)]
        exec(compile(ast.Module(body=functions, type_ignores=[]), "ai_agent", "exec"), namespace)
        self.safe = lambda: namespace["agent_safe"](None, "conversation.test")

    def test_tool_free_agent_is_accepted(self):
        self.assertTrue(self.safe())

    def test_control_enabled_agent_is_rejected(self):
        self.agent.supported_features = 1
        self.assertFalse(self.safe())

    def test_dynamic_tools_change_rejected_even_if_feature_flag_stale(self):
        self.agent._subentry.data["llm_hass_api"] = ["assist"]
        self.assertFalse(self.safe())

    def test_unknown_custom_agent_is_rejected(self):
        self.entry.platform = "unknown_agent"
        self.assertFalse(self.safe())

    def test_builtin_and_missing_agents_are_rejected(self):
        self.entry = None
        self.assertFalse(self.safe())

    def test_missing_options_fail_closed(self):
        del self.agent._subentry
        self.assertFalse(self.safe())

    def test_disabled_registry_entry_is_rejected(self):
        self.entry.disabled_by = "user"
        self.assertFalse(self.safe())
