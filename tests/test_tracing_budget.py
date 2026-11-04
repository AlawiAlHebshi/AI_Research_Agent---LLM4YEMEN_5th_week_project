"""Offline audit/durability tests. Synthetic usage never touches production state."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import test_task2 as baseline
from budget import BudgetSession, BudgetStop, DAY_CAP, UsageLedger, today
from main import main
from tools import ROOT
from tracing import TraceError, TraceWriter, export_trace, read_trace


class AuditTests(unittest.TestCase):
    setUp = baseline.OfflineTests.setUp
    ledger = baseline.OfflineTests.ledger

    def trace(self):
        return TraceWriter(kind="offline_test", path=self.work / (uuid4().hex + ".jsonl"))

    def test_schema_sequence_and_redaction(self):
        trace = self.trace()
        trace.emit("run_started", mode="scientific")
        trace.emit("tool_error", tool="search_openalex", error_code="api_key=fixture-private")
        trace.emit("tool_result", sources=["https://example.org/a?api_key=fixture-private"])
        trace.emit("run_finished", status="failed")
        records = read_trace(trace.path)
        self.assertEqual([r["sequence"] for r in records], [1, 2, 3, 4])
        self.assertNotIn("fixture-private", trace.path.read_text())
        self.assertTrue(all(r["execution_kind"] == "offline_test" for r in records))

    def test_unknown_fields_and_prompt_recording_rejected(self):
        trace = self.trace()
        with self.assertRaises(TraceError):
            trace.emit("model_reserved", api_key="fixture")
        with self.assertRaises(TraceError):
            trace.emit("run_started", prompt="fixture")
        self.assertFalse(trace.path.exists())

    def test_malformed_and_truncated_trace_rejected(self):
        trace = self.trace()
        trace.emit("run_started", mode="web")
        with trace.path.open("a") as handle:
            handle.write('{"unfinished":')
        with self.assertRaises(ValueError):
            read_trace(trace.path)

    def test_trace_never_overwrites_previous_run(self):
        trace = self.trace()
        trace.emit("run_started", mode="web")
        with self.assertRaises(TraceError):
            TraceWriter(path=trace.path)

    def test_offline_trace_cannot_be_promoted_to_capstone(self):
        trace = self.trace()
        trace.emit("run_started", mode="web")
        trace.emit("run_finished", status="invalid_input")
        for label in ["success_1", "near_failure_recovery", "explicit_failure"]:
            with self.assertRaises(TraceError):
                export_trace(trace.path, label)

    def test_public_probe_not_presented_as_full_agent_success(self):
        trace = TraceWriter(kind="public_tool_probe", path=self.work / "probe.jsonl")
        trace.emit("run_started", mode="scientific")
        trace.emit("tool_result", source_count=2)
        trace.emit("run_finished", status="success")
        with self.assertRaises(TraceError):
            export_trace(trace.path, "success_1")

    def test_trace_failure_prevents_network_request(self):
        model, session = baseline.OfflineTests.model(self, [baseline.final_message()])
        session.trace = Mock()
        session.trace.emit.side_effect = TraceError("fixture storage failure")
        with self.assertRaises(TraceError):
            model.invoke("fixture")
        self.assertEqual(self.requests, [])
        state = json.loads(self.ledger().path.read_text())
        self.assertEqual(state["calls"][0]["status"], "reserved")

    def test_snapshot_does_not_change_ledger(self):
        ledger = self.ledger()
        ledger.reserve("fixture", 100, 10)
        before = hashlib.sha256(ledger.path.read_bytes()).hexdigest()
        state = ledger.snapshot("fixture")
        self.assertGreater(state["reserved_nanos"], 0)
        self.assertEqual(before, hashlib.sha256(ledger.path.read_bytes()).hexdigest())

    def test_budget_cli_does_not_load_env_or_call_model(self):
        ledger = self.ledger()
        ledger.reserve("fixture", 1, 1)
        with (patch("main.UsageLedger", return_value=ledger), patch("main.load_dotenv") as load,
              patch("main.GuardedChatOpenAI.for_session") as factory, contextlib.redirect_stdout(io.StringIO()) as output):
            self.assertEqual(main(["--budget-status"]), 0)
        load.assert_not_called()
        factory.assert_not_called()
        self.assertIn("project_charged_usd", output.getvalue())

    def test_invalid_usage_keeps_reservation(self):
        ledger = self.ledger()
        reservation = ledger.reserve("fixture", 100, 10)
        for usage in [{}, {"input_tokens": -1, "output_tokens": 2},
                      {"input_tokens": 10, "output_tokens": 2, "input_token_details": {"cache_read": 11}}]:
            with self.assertRaises(BudgetStop):
                ledger.settle(reservation, usage)
        self.assertEqual(ledger.snapshot()["reserved_nanos"], 17500)

    def test_duplicate_or_negative_ledger_rows_fail_closed(self):
        for bad in [
            [{"id": "x", "task": "fixture", "day": today(), "charge": -1, "status": "measured"}],
            [{"id": "x", "task": "fixture", "day": today(), "charge": 1, "status": "measured"}] * 2,
        ]:
            ledger = UsageLedger(self.work / (uuid4().hex + ".json"))
            ledger.path.write_text(json.dumps({"version": 1, "calls": bad}))
            with self.assertRaises(BudgetStop):
                ledger.reserve("fixture", 1, 1)

    def test_missing_previous_ledger_not_silently_reset(self):
        ledger = self.ledger()
        ledger.reserve("fixture", 1, 1)
        # Move within the isolated fixture, preserving the original file.
        ledger.path.rename(self.work / "preserved-usage.json")
        with self.assertRaises(BudgetStop):
            ledger.snapshot()
        with self.assertRaises(BudgetStop):
            ledger.reserve("another-task", 1, 1)
        self.assertTrue((self.work / "preserved-usage.json").exists())

    def test_two_processes_cannot_spend_same_remaining_daily_budget(self):
        ledger = self.ledger()
        with ledger.transaction() as state:
            state["calls"].append({"id": "synthetic-seed", "task": "seed", "day": today(),
                "charge": DAY_CAP - 625, "status": "measured"})
        code = """from pathlib import Path
import sys
from budget import UsageLedger,BudgetStop
try:
 UsageLedger(Path(sys.argv[1])).reserve(sys.argv[2],1,1)
except BudgetStop:
 sys.exit(2)
"""
        processes = [subprocess.Popen([sys.executable, "-B", "-c", code, str(ledger.path), uuid4().hex],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        codes = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            codes.append(process.returncode)
        self.assertEqual(sorted(codes), [0, 2])
        self.assertEqual(ledger.snapshot()["day_nanos"], DAY_CAP)


if __name__ == "__main__":
    unittest.main()
