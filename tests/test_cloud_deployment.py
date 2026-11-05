"""Offline checks for the initial, fail-closed Community Cloud deployment."""

import os
import unittest
from unittest.mock import Mock, patch

from deployment_policy import cloud_probe_enabled, free_exa_probe, initialize_secrets, local_runtime, cloud_configuration_status
from mcp_client import MCPError
from frontend.contracts import ResearchRequest
from scripts.start_streamlit import prepare_environment
from streamlit_backend import BackendGateway, GatewayError


class CloudDeploymentTests(unittest.TestCase):
    def test_configuration_diagnostics_contain_only_booleans(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "not-shown", "SUPABASE_SECRET_KEY": "not-shown",
                                    "CLOUD_RESEARCH_ENABLED": "true"}, clear=True):
            status = cloud_configuration_status()
            self.assertTrue(all(type(value) is bool and value for value in status.values()))
            self.assertNotIn("not-shown", str(status))

    def test_default_cloud_rejects_research_before_model_or_ledger(self):
        with patch.dict(os.environ, {}, clear=True):
            for _ in range(2):  # A new gateway after ephemeral storage loss is still blocked.
                memory, ledger, model = Mock(), Mock(), Mock()
                gateway = BackendGateway(memory=memory, ledger=ledger, model_factory=model)
                self.assertTrue(gateway.configured)
                self.assertFalse(gateway.research_enabled)
                with self.assertRaises(GatewayError) as caught:
                    gateway.research(ResearchRequest("offline question", "web"), Mock(), request_id="one")
                self.assertEqual(caught.exception.code, "durable_budget_unavailable")
                model.assert_not_called()
                self.assertEqual(ledger.mock_calls, [])
                self.assertEqual(memory.mock_calls, [])

    def test_cloud_storage_and_reports_are_inaccessible(self):
        memory, ledger = Mock(), Mock()
        gateway = BackendGateway(memory=memory, ledger=ledger, runtime_mode="cloud")
        self.assertEqual(gateway.history("private"), [])
        for operation in (gateway.budget_status, lambda: gateway.open_history("private-id"),
                          lambda: gateway.save_report("private-id", consent=True)):
            with self.assertRaises(GatewayError):
                operation()
        self.assertEqual(memory.mock_calls, [])
        self.assertEqual(ledger.mock_calls, [])

    def test_explicit_local_launcher_retains_existing_behavior(self):
        environment = prepare_environment({"OPENAI_API_KEY": "fake-offline-value"},
                                          interactive=False, prompt=Mock())
        with patch.dict(os.environ, environment, clear=True):
            self.assertTrue(local_runtime())
            self.assertTrue(BackendGateway(memory=Mock(), ledger=Mock()).research_enabled)
            self.assertFalse(cloud_probe_enabled())

    def test_secret_presence_does_not_read_a_value(self):
        store = Mock()
        store.__contains__ = Mock(return_value=True)
        self.assertTrue(initialize_secrets(store))
        store.__contains__.assert_called_once_with("OPENAI_API_KEY")
        missing = Mock()
        missing.__contains__ = Mock(side_effect=FileNotFoundError())
        self.assertFalse(initialize_secrets(missing))
        missing.__contains__.side_effect = RuntimeError("missing home directory")
        self.assertFalse(initialize_secrets(missing))

    def test_cloud_ui_disables_submit_and_preserves_modes_and_language(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        gateway = BackendGateway(memory=Mock(), ledger=Mock(), model_factory=Mock(), runtime_mode="cloud")
        with patch("streamlit_backend.create_gateway", return_value=gateway), \
             patch("deployment_policy.cloud_probe_enabled", return_value=False):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py"),
                                    default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key="start_research").disabled)
            app.radio(key="live_mode").set_value("scientific").run()
            self.assertTrue(any("الملخصات" in item.value for item in app.caption))
            app.button(key="ui_language_toggle").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.button(key="start_research").label, "Start research")
            self.assertTrue(app.button(key="start_research").disabled)
        self.assertEqual(gateway.model_factory.mock_calls, [])

    def test_probe_requires_explicit_cloud_opt_in(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(cloud_probe_enabled())
        with patch.dict(os.environ, {"CLOUD_MCP_CHECK": "true"}, clear=True):
            self.assertTrue(cloud_probe_enabled())

    def test_free_probe_is_anonymous_and_cached(self):
        free_exa_probe.cache_clear()
        try:
            with patch("deployment_policy.MCPClient") as client, patch("deployment_policy.TraceWriter"):
                client.return_value.exa_search.return_value = [{"href": "https://example.org/"}]
                client.return_value.requests = 4
                result = free_exa_probe()
                self.assertIs(free_exa_probe(), result)
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["openai_requests"], 0)
                self.assertEqual(result["result_count"], 1)
                self.assertFalse(client.call_args.kwargs["use_keys"])
                client.return_value.exa_search.assert_called_once()
        finally:
            free_exa_probe.cache_clear()

    def test_free_probe_reports_safe_provider_failure_without_openai(self):
        free_exa_probe.cache_clear()
        try:
            with patch("deployment_policy.MCPClient") as client, patch("deployment_policy.TraceWriter"):
                client.return_value.exa_search.side_effect = MCPError("rate_limited")
                client.return_value.requests = 1
                result = free_exa_probe()
                self.assertEqual(result["error_code"], "rate_limited")
                self.assertEqual(result["openai_requests"], 0)
                self.assertEqual(result["result_count"], 0)
        finally:
            free_exa_probe.cache_clear()


if __name__ == "__main__":
    unittest.main()
