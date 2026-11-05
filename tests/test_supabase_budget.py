"""Offline HTTP and engine checks. Actual SQL acceptance is checked separately."""

import json
import os
import unittest
from unittest.mock import Mock, patch

from budget import BudgetStop, MODEL, TASK_CAP, DAY_CAP, PROJECT_CAP, MAX_TURNS, MAX_INPUT_BOUND, MAX_OUTPUT_TOKENS
from cloud_budget import SupabaseLedger
from frontend.contracts import ResearchRequest
from streamlit_backend import BackendGateway
import test_streamlit_backend as adapters

URL = "https://abcdefghijklmnopqrst.supabase.co"
KEY = "sb_secret_offline_fixture_only"


def response(data=None, status=200):
    result = Mock(status_code=status)
    result.iter_content.return_value = [json.dumps(data).encode()]
    return result


def snapshot(**changes):
    result = dict(ok=True, version=1, model=MODEL, task_cap=TASK_CAP, day_cap=DAY_CAP,
        project_cap=PROJECT_CAP, max_turns=MAX_TURNS, max_input=MAX_INPUT_BOUND,
        max_output=MAX_OUTPUT_TOKENS, calls=400, task_nanos=0, day_nanos=100,
        project_nanos=200, reserved_nanos=50)
    result.update(changes)
    return result


class RemoteLedgerTests(unittest.TestCase):
    def test_snapshot_is_bounded_and_uses_server_key_without_redirects(self):
        post = Mock(return_value=response(snapshot()))
        ledger = SupabaseLedger(URL, KEY, post=post)
        self.assertEqual(ledger.snapshot()["project_nanos"], 200)
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["apikey"], KEY)
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (5, 15))
        self.assertNotIn(KEY, repr(ledger))

    def test_bad_origins_and_non_server_keys_are_rejected(self):
        for url, key in [("http://localhost", KEY), (URL + "/evil", KEY),
                         (URL + "@example.org", KEY), (URL, "sb_publishable_fixture")]:
            with self.subTest(url=url), self.assertRaises(BudgetStop):
                SupabaseLedger(url, key)

    def test_failures_never_expose_provider_body_or_retry(self):
        for reply in [response({"private": "secret response"}, 401),
                      response({"ok": True}), response(["invalid"]),
                      response(snapshot(project_cap=999))]:
            post = Mock(return_value=reply)
            with self.assertRaises(BudgetStop) as caught:
                SupabaseLedger(URL, KEY, post=post).snapshot()
            self.assertNotIn("secret response", str(caught.exception))
            self.assertEqual(post.call_count, 1)
        post = Mock(side_effect=TimeoutError(KEY))
        with self.assertRaises(BudgetStop) as caught:
            SupabaseLedger(URL, KEY, post=post).reserve("one", 10, 10)
        self.assertNotIn(KEY, str(caught.exception))
        post.assert_called_once()

    def test_inconsistent_or_boolean_financial_totals_are_rejected(self):
        for changes in [dict(calls=True), dict(day_nanos=201), dict(reserved_nanos=201), dict(project_nanos=-1)]:
            with self.subTest(changes=changes), self.assertRaises(BudgetStop):
                SupabaseLedger(URL, KEY, post=Mock(return_value=response(snapshot(**changes)))).snapshot()

    def test_budget_rejections_are_preserved(self):
        for code in ("task_budget", "daily_budget", "project_budget", "turn_limit", "ledger_uninitialized"):
            with self.subTest(code=code):
                post = Mock(side_effect=[response(snapshot()), response(dict(ok=False, code=code))])
                with self.assertRaises(BudgetStop) as caught:
                    SupabaseLedger(URL, KEY, post=post).reserve("one", 10, 10)
                self.assertEqual(caught.exception.code, code)

    def test_reservation_requires_exact_acknowledgement(self):
        calls = []
        def post(url, **kwargs):
            calls.append((url, kwargs["json"]))
            if url.endswith("snapshot"):
                return response(snapshot())
            args = kwargs["json"]
            return response(dict(ok=True, reservation=args["p_id"], estimate=1750))
        ledger = SupabaseLedger(URL, KEY, post=post)
        reserved = ledger.reserve("one", 10, 1)
        self.assertEqual(len(reserved), 32)
        self.assertEqual(len(calls), 2)
        self.assertEqual(set(calls[1][1]), {"p_id", "p_task", "p_input", "p_output"})
        bad = Mock(side_effect=[response(snapshot()), response(dict(ok=True, reservation="other", estimate=1750))])
        with self.assertRaises(BudgetStop):
            SupabaseLedger(URL, KEY, post=bad).reserve("one", 10, 1)

    def test_invalid_usage_never_sends_a_settlement(self):
        post = Mock()
        ledger = SupabaseLedger(URL, KEY, post=post)
        for usage in ({}, {"input_tokens": 1, "output_tokens": True},
                      {"input_tokens": 1, "output_tokens": 1, "input_token_details": {"cache_read": 2}}):
            with self.assertRaises(BudgetStop):
                ledger.settle("a" * 32, usage)
        post.assert_not_called()
        post.return_value = response(dict(ok=True, exceeded=True))
        self.assertTrue(ledger.settle("a" * 32, {"input_tokens": 3, "output_tokens": 1}))

    def test_unconfigured_cloud_stays_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            ledger = SupabaseLedger(URL, KEY, post=Mock())
            gateway = BackendGateway(ledger=ledger, memory=Mock(), model_factory=Mock(), runtime_mode="cloud")
            self.assertFalse(gateway.research_enabled)
            with self.assertRaises(Exception):
                gateway.research(ResearchRequest("fixture", "web"), Mock(), request_id="one")
            ledger._post.assert_not_called()

    def test_ui_gate_requires_a_successful_snapshot_and_closes_on_outage(self):
        post = Mock(return_value=response(snapshot()))
        ledger = SupabaseLedger(URL, KEY, post=post)
        gateway = BackendGateway(ledger=ledger, memory=Mock(), model_factory=Mock(), runtime_mode="cloud")
        with patch.dict(os.environ, {"CLOUD_RESEARCH_ENABLED": "true"}):
            self.assertFalse(gateway.research_enabled)
            gateway.budget_status()
            self.assertTrue(gateway.research_enabled)
            post.side_effect = TimeoutError()
            with self.assertRaises(Exception):
                gateway.budget_status()
            self.assertFalse(gateway.research_enabled)

    def test_cloud_ui_uses_durable_snapshot_without_any_model_calls(self):
        from pathlib import Path
        from streamlit.testing.v1 import AppTest
        ledger = SupabaseLedger(URL, KEY, post=Mock(return_value=response(snapshot())))
        factory = Mock()
        gateway = BackendGateway(ledger=ledger, memory=Mock(), model_factory=factory, runtime_mode="cloud")
        with patch.dict(os.environ, {"CLOUD_RESEARCH_ENABLED": "true"}), \
             patch("streamlit_backend.create_gateway", return_value=gateway), \
             patch("deployment_policy.cloud_probe_enabled", return_value=False):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py"),
                                    default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.button(key="start_research").disabled)
            app.button(key="ui_language_toggle").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.button(key="start_research").label, "Start research")
        factory.assert_not_called()


class CloudEngineTests(unittest.TestCase):
    """Reuse existing engine acceptance tests; add a genuine adapter path with fake HTTP."""

    setUp = adapters.AdapterTests.setUp
    gateway = adapters.AdapterTests.gateway
    model = adapters.AdapterTests.model
    ledger = adapters.AdapterTests.ledger
    run_gateway = adapters.AdapterTests.run_gateway

    def test_enabled_cloud_uses_remote_reservations_and_no_shared_memory(self):
        operations = []
        def post(url, **kwargs):
            args = kwargs["json"]
            operations.append(url.rsplit("_", 1)[-1])
            if url.endswith("snapshot"):
                return response(snapshot())
            if url.endswith("reserve"):
                return response(dict(ok=True, reservation=args["p_id"],
                    estimate=args["p_input"] * 125 + args["p_output"] * 500))
            return response(dict(ok=True, exceeded=False))
        ledger = SupabaseLedger(URL, KEY, post=post)
        gateway = self.gateway(ledger=ledger, runtime_mode="cloud")
        with patch.dict(os.environ, {"CLOUD_RESEARCH_ENABLED": "true"}):
            result = self.run_gateway(gateway)
            self.assertEqual(result.memory_status, "disabled")
            self.assertEqual(len(self.requests), 2)
            self.assertEqual(operations, ["snapshot", "reserve", "settle"] * 2)
            self.assertEqual(gateway.history(), [])
            self.assertIsNone(gateway.memory.get(result.id))
            self.assertIs(self.run_gateway(gateway), result)
            with self.assertRaises(Exception):
                gateway.open_history(result.id)
            self.assertEqual(gateway.save_report(result.id, consent=False)["status"], "declined")

    def test_cloud_ledger_failure_prevents_sdk_transport(self):
        ledger = SupabaseLedger(URL, KEY, post=Mock(side_effect=TimeoutError("private")))
        gateway = self.gateway(ledger=ledger, runtime_mode="cloud")
        with patch.dict(os.environ, {"CLOUD_RESEARCH_ENABLED": "true"}):
            with self.assertRaises(Exception):
                self.run_gateway(gateway)
        self.assertEqual(self.requests, [])
