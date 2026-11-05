"""Offline boundary checks for the conservative input limit; no API calls."""

import json
import unittest
from unittest.mock import Mock

import test_task2 as baseline
from budget import BudgetSession, BudgetStop, MAX_INPUT_BOUND, MAX_OUTPUT_TOKENS, MODEL


class ContextLimitTests(unittest.TestCase):
    setUp = baseline.OfflineTests.setUp
    ledger = baseline.OfflineTests.ledger

    def payload(self, bound):
        payload = {"model": MODEL, "reasoning_effort": "none",
                   "max_completion_tokens": MAX_OUTPUT_TOKENS,
                   "messages": [{"role": "user", "content": ""}]}
        # Match the unchanged byte-based estimator exactly, without tokenization.
        base = 2 * len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + 8192
        self.assertEqual((bound - base) % 2, 0)
        payload["messages"][0]["content"] = "x" * ((bound - base) // 2)
        return payload

    def test_input_above_old_limit_can_be_reserved(self):
        session = BudgetSession(self.ledger())
        reservation = session.reserve_payload(self.payload(150_000))
        self.assertIn(reservation, session.pending)

    def test_new_boundary_passes_both_guards(self):
        session = BudgetSession(self.ledger())
        reservation = session.reserve_payload(self.payload(MAX_INPUT_BOUND))
        record = json.loads(session.ledger.path.read_text(encoding="utf-8"))["calls"][0]
        self.assertEqual(record["id"], reservation)
        self.assertEqual(record["estimated_input_bound"], 200_000)
        self.assertEqual(record["max_output_tokens"], 1200)

    def test_over_limit_payload_stops_before_reservation(self):
        ledger = Mock()
        with self.assertRaisesRegex(BudgetStop, "السياق أكبر"):
            BudgetSession(ledger).reserve_payload(self.payload(MAX_INPUT_BOUND + 2))
        ledger.reserve.assert_not_called()

    def test_ledger_rejects_direct_reservation_above_limit(self):
        with self.assertRaisesRegex(BudgetStop, "حدود الاستدعاء غير صالحة"):
            self.ledger().reserve("fixture", MAX_INPUT_BOUND + 1, MAX_OUTPUT_TOKENS)

    def test_larger_context_still_obeys_remaining_task_budget(self):
        ledger = self.ledger()
        ledger.reserve("fixture", 50_000, MAX_OUTPUT_TOKENS)
        with self.assertRaises(BudgetStop) as caught:
            BudgetSession(ledger, task_id="fixture").reserve_payload(self.payload(MAX_INPUT_BOUND))
        self.assertEqual(caught.exception.code, "task_budget")
