"""Offline regression tests; no historical or live model responses are replayed."""

import json
import unittest
from unittest.mock import Mock

import test_scientific as science
import test_task2 as baseline
import main
from tracing import read_trace


class ValidationTests(unittest.TestCase):
    setUp = baseline.OfflineTests.setUp
    ledger = baseline.OfflineTests.ledger
    context = science.ScientificTests.context
    execute = science.ScientificTests.execute

    def evidence(self):
        context = self.context()
        context.search_openalex("fixture")
        return context

    def assert_code(self, code, value, context):
        with self.assertRaises(main.ResearchValidationError) as caught:
            main.validate_response(value, context)
        self.assertEqual(caught.exception.code, code)

    def test_output_shape_and_schema_have_distinct_codes(self):
        context = self.evidence()
        self.assert_code("unsupported_output_shape", {"unknown": "private text"}, context)
        for value in ["not JSON private text", '{"summary":"private text"}']:
            self.assert_code("invalid_output_schema", value, context)

    def test_source_rejections_have_distinct_codes(self):
        context = self.evidence()
        for urls, code in [([], "missing_sources"), (["https://example.net/invented"], "unretrieved_source"),
                           (["file:///private"], "unretrieved_source")]:
            self.assert_code(code, baseline.final_message(urls)["content"], context)

    def test_no_guessed_http_https_aliases(self):
        context = self.evidence()
        self.assert_code("unretrieved_source", science.final_science(
            ["http://example.org/paper-1"], "Evidence [1].")["content"], context)

    def test_missing_and_out_of_range_citations_are_distinct(self):
        context = self.evidence()
        for summary, code in [("No citation", "missing_numbered_citation"),
                              ("Evidence [0]", "citation_out_of_range"),
                              ("Evidence [3]", "citation_out_of_range"),
                              ("Evidence [" + "9" * 5000 + "]", "citation_out_of_range")]:
            self.assert_code(code, science.final_science(summary=summary)["content"], context)

    def test_unknown_prose_link_is_still_rejected(self):
        self.assert_code("unsupported_summary_url", science.final_science(
            summary="Evidence [1] https://example.net/invented")["content"], self.evidence())

    def alias_evidence(self):
        context = self.context(Mock(side_effect=[science.response(science.semantic_data()),
                                                science.response(science.openalex_data())]))
        context.search_semantic_scholar("fixture")
        context.search_openalex("fixture")
        return context

    def test_known_alias_is_canonicalized_without_rejecting_answer(self):
        context = self.alias_evidence()
        response = main.validate_response(science.final_science()["content"], context)
        self.assertEqual(response.sources, ["https://example.com/semantic-1", "https://example.org/paper-2"])
        self.assertIn("[1]", response.summary)
        self.assertIn("[2]", response.summary)

    def test_duplicate_aliases_remap_all_citations_in_original_order(self):
        context = self.alias_evidence()
        urls = ["https://example.org/paper-1", "https://example.com/semantic-1", "https://example.org/paper-2"]
        response = main.validate_response(science.final_science(urls, "A [1], B [2], C [3], C again [3].")["content"], context)
        self.assertEqual(response.sources, [urls[1], urls[2]])
        self.assertTrue(response.summary.startswith("A [1], B [1], C [2], C again [2]."))

    def test_known_prose_alias_rewritten_with_punctuation_preserved(self):
        context = self.alias_evidence()
        response = main.validate_response(science.final_science(
            summary="Evidence [1] https://example.org/paper-1،")["content"], context)
        self.assertIn("https://example.com/semantic-1،", response.summary)

    def test_invalid_answer_has_safe_trace_code_and_no_retry_or_report(self):
        context = self.context()
        outcome, session = self.execute([baseline.tool_call("search_openalex"),
                                         science.final_science(summary="PRIVATE_REJECTED_TEXT without citations")], context)
        self.assertEqual(outcome.status, "invalid_response")
        self.assertIn("missing_numbered_citation", outcome.reason)
        self.assertIsNone(context.final_content)
        self.assertFalse(context.reports_dir.exists())
        self.assertEqual(session.calls, 2)
        event = next(e for e in read_trace(context.trace.path) if e["event"] == "research_finished")
        self.assertEqual(event["data"]["error_code"], "missing_numbered_citation")
        self.assertEqual(event["data"]["reason"], "output_validation")
        self.assertNotIn("PRIVATE_REJECTED_TEXT", context.trace.path.read_text(encoding="utf-8"))

    def test_service_failure_is_not_reported_as_absence_of_studies(self):
        context = self.context(Mock(return_value=science.response(status=403)))
        outcome, session = self.execute([baseline.tool_call("search_semantic_scholar"),
                                         baseline.tool_call("search_arxiv"), science.final_science()], context)
        self.assertEqual(outcome.status, "no_evidence")
        self.assertIn("no_usable_evidence", outcome.reason)
        self.assertIn("access_denied", outcome.reason)
        self.assertIn("لا يثبت عدم وجود دراسات", outcome.reason)
        self.assertIsNone(context.final_content)
        self.assertEqual(session.calls, 3)

    def test_metadata_only_remains_ineligible(self):
        context = self.context(Mock(return_value=science.response(science.openalex_data(abstracts=False))))
        context.search_openalex("fixture")
        self.assert_code("no_usable_evidence", science.final_science()["content"], context)

    def test_canonical_answer_unchanged_and_tools_come_from_execution(self):
        context = self.evidence()
        response = main.validate_response(science.final_science()["content"], context)
        self.assertEqual(response.sources, json.loads(science.final_science()["content"])["sources"])
        self.assertEqual(response.tools_used, ["search_openalex"])
