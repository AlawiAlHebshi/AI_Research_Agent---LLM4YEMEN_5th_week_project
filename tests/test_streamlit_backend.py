"""Offline adapter acceptance: existing engine and SDK with mocked HTTP/providers."""

import contextlib
import io
import json
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx

import test_task2 as baseline
import test_scientific as science
from budget import TASK_CAP, today
from frontend.contracts import ResearchRequest
from frontend.demo import localize_result
from memory import ResearchMemory
from streamlit_backend import BackendGateway, GatewayError
from tools import WebResearchContext
from scientific_tools import ScientificResearchContext, ScientificClient
from tracing import TraceWriter, read_trace, export_trace, TraceError


class AdapterTests(unittest.TestCase):
    setUp = baseline.OfflineTests.setUp
    ledger = baseline.OfflineTests.ledger
    model = baseline.OfflineTests.model

    def gateway(self, messages=None, **kwargs):
        model, _ = self.model(messages if messages is not None else [baseline.tool_call(), baseline.final_message()])

        def context_factory(mode, trace):
            options = dict(trace=trace, reports_dir=baseline.ROOT / "reports" / ".tests" / self.test_id)
            if mode == "scientific":
                return ScientificResearchContext(client=ScientificClient(get=Mock(return_value=science.response(science.openalex_data()))), **options)
            return WebResearchContext(search_backend=lambda query: baseline.ROWS,
                wiki_backend=lambda query: baseline.ROWS, use_exa=False, **options)

        options = dict(memory=ResearchMemory(self.work / "ui.sqlite3"), ledger=self.ledger(),
            runtime_mode="local",
            model_factory=lambda session: model.model_copy(update={"session": session}), context_factory=context_factory,
            trace_factory=lambda: TraceWriter(kind="offline_test", path=self.work / (uuid4().hex + ".jsonl")))
        options.update(kwargs)
        return BackendGateway(**options)

    def run_gateway(self, gateway, *, mode="web", request_id="one"):
        with contextlib.redirect_stdout(self.out):
            return gateway.research(ResearchRequest("MCP offline fixture", mode), lambda step: None, request_id=request_id)

    def test_both_modes_use_engine_validation_memory_and_budget(self):
        for mode, messages in [("web", [baseline.tool_call(), baseline.final_message()]),
                               ("scientific", [baseline.tool_call("search_openalex"), science.final_science(["P1", "P2"])])]:
            with self.subTest(mode=mode):
                gateway = self.gateway(messages)
                result = self.run_gateway(gateway, mode=mode, request_id=mode)
                self.assertFalse(result.is_demo)
                self.assertEqual(result.request.mode, mode)
                self.assertEqual(result.model_calls, 2)
                self.assertGreater(result.cost_nanos, 0)
                self.assertIsNotNone(gateway.memory.get(result.id))
                self.assertEqual(localize_result(result, "en"), result)

    def test_duplicate_request_id_never_repeats_model_calls(self):
        gateway = self.gateway()
        original = self.run_gateway(gateway)
        self.assertIs(self.run_gateway(gateway), original)
        self.assertEqual(len(self.requests), 2)
        with self.assertRaises(GatewayError):
            gateway.research(ResearchRequest("Changed question", "web"), lambda step: None, request_id="one")
        self.assertEqual(len(self.requests), 2)

    def test_validation_failure_is_cached_without_fake_result(self):
        gateway = self.gateway([baseline.tool_call(), baseline.final_message(["https://example.net/invented"])])
        for _ in range(2):
            with self.assertRaises(GatewayError) as error:
                self.run_gateway(gateway)
            self.assertEqual(error.exception.code, "invalid_response")
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(gateway.results, {})
        self.assertEqual(gateway.history(), [])

    def test_failed_provider_and_empty_evidence_are_not_displayable_results(self):
        context = lambda mode, trace: WebResearchContext(trace=trace, use_exa=False,
                                                        search_backend=Mock(side_effect=TimeoutError("private error details")))
        gateway = self.gateway(context_factory=context)
        with self.assertRaises(GatewayError) as caught:
            self.run_gateway(gateway)
        self.assertEqual(caught.exception.code, "no_evidence")
        self.assertNotIn("private error details", str(caught.exception))
        self.assertEqual(gateway.results, {})

    def test_budget_blocked_before_transport(self):
        gateway = self.gateway()
        with gateway.ledger.transaction() as state:
            state["calls"].append({"id": uuid4().hex, "task": "prior", "day": today(),
                "status": "measured", "charge": 300_000_000})
        with self.assertRaises(GatewayError) as caught:
            self.run_gateway(gateway)
        self.assertEqual(caught.exception.code, "daily_budget")
        self.assertEqual(self.requests, [])

    def test_transport_failure_keeps_reservation_and_is_not_retried(self):
        model, _ = self.model([], transport_error=httpx.ConnectError("private transport data"))
        gateway = self.gateway(model_factory=lambda session: model.model_copy(update={"session": session}))
        for _ in range(2):
            with self.assertRaises(GatewayError):
                self.run_gateway(gateway)
        self.assertEqual(len(self.requests), 1)
        self.assertGreater(gateway.ledger.snapshot()["reserved_nanos"], 0)

    def test_report_requires_consent_and_reuses_protected_writer(self):
        gateway = self.gateway()
        result = self.run_gateway(gateway)
        context = gateway.results[result.id][1]
        self.assertEqual(gateway.save_report(result.id, consent=False)["status"], "declined")
        self.assertFalse(context.reports_dir.exists())
        saved = gateway.save_report(result.id, consent=True)
        self.assertEqual(saved["status"], "saved")
        target = context.reports_dir / saved["filename"]
        self.assertIn(result.report, target.read_text(encoding="utf-8"))
        self.assertEqual(gateway.save_report(result.id, consent=True), saved)
        self.assertEqual(len(list(context.reports_dir.glob("*.txt"))), 1)
        self.assertEqual(len(self.requests), 2)
        self.assertIsNotNone(gateway.memory.get(result.id))

    def test_history_search_reopen_and_download_need_no_model(self):
        gateway = self.gateway()
        result = self.run_gateway(gateway)
        count = len(self.requests)
        reopened = self.gateway([])
        self.assertEqual(reopened.history("MCP")[0].task_id, result.id)
        history = reopened.open_history(result.id)
        self.assertTrue(history.historical)
        self.assertIn("PREVIOUS RESEARCH", history.report)
        self.assertEqual(history.model_calls, 0)
        self.assertEqual(reopened.results[result.id][1].sources, {})
        self.assertEqual(len(self.requests), count)
        self.assertEqual(history.report.encode().decode(), history.report)

    def test_unknown_record_and_unregistered_report_fail_safely(self):
        gateway = self.gateway([])
        with self.assertRaises(GatewayError):
            gateway.open_history(uuid4().hex)
        with self.assertRaises(GatewayError):
            gateway.save_report(uuid4().hex, consent=True)
        self.assertEqual(self.requests, [])

    def test_missing_key_never_reads_dotenv_or_sends_request(self):
        gateway = self.gateway([], model_factory=None)
        with patch.dict("os.environ", {}, clear=True), patch("main.load_dotenv") as loader:
            with self.assertRaises(GatewayError) as caught:
                self.run_gateway(gateway)
        self.assertEqual(caught.exception.code, "configuration_error")
        loader.assert_not_called()
        self.assertEqual(self.requests, [])

    def test_fresh_streamlit_trace_kind_is_supported_without_exporting_as_cli(self):
        trace = TraceWriter(kind="streamlit", path=self.work / "ui_real_kind_no_api.jsonl")
        trace.emit("run_started", mode="web")
        trace.emit("run_finished", status="configuration_error", calls=0)
        self.assertEqual(read_trace(trace.path)[0]["execution_kind"], "streamlit")
        with self.assertRaises(TraceError):
            export_trace(trace.path, "explicit_failure")
