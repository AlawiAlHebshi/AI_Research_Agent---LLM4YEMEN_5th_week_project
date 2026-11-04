"""Synthetic scientific fixtures; these are NOT live papers or capstone traces."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import requests

import test_task2 as baseline
from budget import BudgetSession, BudgetStop
from main import build_executor, format_report, run_research, validate_response
from research_models import make_paper, normalize_arxiv, normalize_doi, reconstruct_abstract, same_paper
from scientific_tools import ResearchAPIError, ScientificClient, ScientificResearchContext
from tools import ROOT, build_tools
from tracing import TraceWriter, read_trace


def response(data=None, status=200, content=None):
    result = requests.Response()
    result.status_code = status
    result._content = content if content is not None else json.dumps(data or {}).encode()
    result._content_consumed = True
    return result


def openalex_data(*, abstracts=True):
    return {"results": [
        {"id": f"https://openalex.org/W{index}", "title": f"Offline fixture paper {index}",
         "authorships": [{"author": {"display_name": "Fixture Author"}}], "publication_year": 2026,
         "abstract_inverted_index": {"Fixture": [0], "evidence": [1], str(index): [2]} if abstracts else None,
         "doi": f"https://doi.org/10.1234/fixture-{index}", "type": "article",
         "primary_location": {"landing_page_url": f"https://example.org/paper-{index}"}}
        for index in (1, 2)
    ]}


def semantic_data():
    return {"data": [{"title": "Offline fixture paper 1", "authors": [{"name": "Fixture Author"}],
        "year": 2026, "abstract": "Fixture evidence 1", "url": "https://example.com/semantic-1",
        "externalIds": {"DOI": "10.1234/fixture-1"}}]}


def final_science(sources=None, summary="Fixture finding [1] and comparison [2]."):
    return baseline.final_message(sources or ["https://example.org/paper-1", "https://example.org/paper-2"], summary)


ARXIV_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
 <entry><id>https://arxiv.org/abs/9999.00001v2</id><title>Offline arXiv fixture</title>
 <published>2026-01-01T00:00:00Z</published><author><name>Fixture Author</name></author>
 <summary>Only a synthetic abstract.</summary><arxiv:doi>10.1234/arxiv-fixture</arxiv:doi></entry>
</feed>'''


class ScientificTests(unittest.TestCase):
    setUp = baseline.OfflineTests.setUp
    ledger = baseline.OfflineTests.ledger

    def context(self, get=None):
        return ScientificResearchContext(client=ScientificClient(get=get or Mock(return_value=response(openalex_data())), sleep=lambda delay: None),
            reports_dir=ROOT / "reports" / ".tests" / self.test_id, confirm=lambda prompt: "n", display=lambda value: None,
            trace=TraceWriter(kind="offline_test", path=self.work / (uuid4().hex + ".jsonl")))

    def execute(self, messages, context):
        model, session = baseline.OfflineTests.model(self, messages)
        session.mode = "scientific"
        session.trace = context.trace
        context.trace.emit("run_started", mode="scientific")
        with contextlib.redirect_stdout(io.StringIO()):
            outcome = run_research("بحث علمي: RAG in education", model, context)
        context.trace.emit("run_finished", status=outcome.status, calls=session.calls,
                           input_tokens=session.input_tokens, output_tokens=session.output_tokens,
                           cost_nanos=session.measured_cost)
        return outcome, session

    def test_scientific_happy_path_and_bibliography(self):
        context = self.context()
        outcome, session = self.execute([baseline.tool_call("search_openalex"), final_science()], context)
        self.assertIsNotNone(outcome.response)
        self.assertEqual(session.calls, 2)
        self.assertIn("Fixture Author", context.final_content)
        self.assertIn("الملخصات", outcome.response.summary)
        self.assertEqual(outcome.response.tools_used, ["search_openalex"])
        events = read_trace(context.trace.path)
        self.assertEqual(sum(e["data"]["cost_nanos"] for e in events if e["event"] == "model_usage"), session.measured_cost)
        ledger_ids = {call["id"] for call in json.loads(self.ledger().path.read_text())["calls"]}
        audit_ids = {event["data"]["reservation_id"] for event in events if event["event"] == "model_reserved"}
        self.assertEqual(ledger_ids, audit_ids)

    def test_five_scientific_input_topics(self):
        for question in ["RAG in education", "Arabic natural language processing", "Solar energy forecasting",
                         "Quantum computing algorithms", "Very narrow educational retrieval topic"]:
            with self.subTest(question=question):
                context = self.context()
                outcome, _ = self.execute([baseline.tool_call("search_openalex", {"query": question}), final_science()], context)
                self.assertIsNotNone(outcome.response)

    def test_scientific_report_refusal_has_no_write(self):
        context = self.context()
        outcome, _ = self.execute([baseline.tool_call("search_openalex"), final_science()], context)
        self.assertIsNotNone(outcome.response)
        result = context.save_report_to_disk("unverified override", "scientific_report.txt")
        self.assertEqual(result["status"], "declined")
        self.assertFalse(context.reports_dir.exists())

    def test_optional_keys_not_written_to_traces_and_probe_ignores_keys(self):
        context = self.context(Mock(return_value=response(openalex_data())))
        with patch.dict("os.environ", {"OPENALEX_API_KEY": "fixture-private-value"}):
            context.search_openalex("fixture")
            self.assertEqual(context.client.get.call_args.kwargs["params"]["api_key"], "fixture-private-value")
            get = Mock(return_value=response(openalex_data()))
            ScientificClient(get=get, use_keys=False).openalex("fixture")
            self.assertNotIn("api_key", get.call_args.kwargs["params"])
        self.assertNotIn("fixture-private-value", context.trace.path.read_text())

    def test_semantic_429_automatically_recovers_with_openalex(self):
        get = Mock(side_effect=[response(status=429), response(openalex_data())])
        context = self.context(get)
        outcome, _ = self.execute([baseline.tool_call("search_semantic_scholar"), final_science()], context)
        self.assertEqual(outcome.status, "degraded")
        self.assertEqual(context.calls, ["search_semantic_scholar", "search_openalex"])
        self.assertEqual(get.call_count, 2)
        self.assertIn("rate_limited", outcome.response.summary)
        self.assertTrue(any(e["event"] == "recovery_started" for e in read_trace(context.trace.path)))

    def test_mode_tools_are_isolated(self):
        names = {tool.name for tool in build_tools(self.context())}
        self.assertEqual(names, {"search_semantic_scholar", "search_openalex", "search_arxiv", "save_report_to_disk"})
        model, session = baseline.OfflineTests.model(self, [])
        session.mode = "scientific"
        with self.assertRaises(BudgetStop):
            model.bind_tools(baseline.build_tools(baseline.OfflineTests.context(self))).invoke("fixture")
        self.assertEqual(self.requests, [])

    def test_scientific_prompt_does_not_request_web_tools(self):
        context = self.context()
        self.execute([baseline.tool_call("search_openalex"), final_science()], context)
        prompt = self.requests[0]["messages"][0]["content"]
        self.assertIn("Scientific Research", prompt)
        self.assertNotIn("Use duckduckgo_search", prompt)

    def test_no_abstract_is_not_evidence(self):
        context = self.context(Mock(return_value=response(openalex_data(abstracts=False))))
        result = context.search_openalex("fixture")
        self.assertFalse(result["results"][0]["evidence_available"])
        self.assertEqual(context.sources, {})
        with self.assertRaises(ValueError):
            validate_response(final_science()["content"], context)

    def test_duplicate_papers_count_once(self):
        context = self.context(Mock(side_effect=[response(semantic_data()), response(openalex_data())]))
        context.search_semantic_scholar("fixture")
        context.search_openalex("fixture")
        self.assertEqual(len(context.papers), 2)
        self.assertEqual(context.aliases["https://example.org/paper-1"], "https://example.com/semantic-1")

    def test_different_dois_do_not_merge_by_title(self):
        left = make_paper(title="Same title", year=2026, doi="10.1234/a", url="https://example.org/a", database="fixture")
        right = make_paper(title="Same title", year=2026, doi="10.1234/b", url="https://example.org/b", database="fixture")
        self.assertFalse(same_paper(left, right))

    def test_same_title_year_fallback_and_arxiv_versions(self):
        left = make_paper(title="Same title", year=2026, url="https://example.org/a", database="fixture")
        right = make_paper(title="SAME TITLE!", year=2026, url="https://example.org/b", database="fixture")
        self.assertTrue(same_paper(left, right))
        self.assertEqual(normalize_arxiv("https://arxiv.org/abs/9999.00001v2"), "9999.00001")
        self.assertEqual(normalize_doi("https://doi.org/10.1234/ABC"), "10.1234/abc")

    def test_openalex_position_map_and_invalid_map(self):
        self.assertEqual(reconstruct_abstract({"world": [1], "hello": [0]}), "hello world")
        for index in [{"word": [-1]}, {"a": [0], "b": [0]}, {"word": [99999]}]:
            with self.assertRaises(ValueError):
                reconstruct_abstract(index)

    def test_arxiv_metadata_only_no_pdf_request(self):
        get = Mock(return_value=response(content=ARXIV_XML))
        context = self.context(get)
        result = context.search_arxiv("fixture")
        paper = result["results"][0]
        self.assertEqual(paper["arxiv_id"], "9999.00001")
        self.assertIn("preprint", paper["publication_type"])
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.args[0], "https://export.arxiv.org/api/query")

    def test_unsafe_or_malformed_xml_rejected(self):
        for xml in [b'<!DOCTYPE a [<!ENTITY x "bad">]><feed/>', b'<invalid', b'\xff\xfe<\x00']:
            context = self.context(Mock(return_value=response(content=xml)))
            self.assertEqual(context.search_arxiv("fixture")["status"], "error")

    def test_arxiv_request_spacing_uses_clock_without_real_sleep(self):
        sleep = Mock()
        with patch("scientific_tools.time.monotonic", return_value=10), patch("scientific_tools._ARXIV_LAST_REQUEST", 9):
            client = ScientificClient(get=Mock(return_value=response(content=ARXIV_XML)), sleep=sleep)
            client.arxiv("fixture")
        sleep.assert_called_once_with(2)

    def test_cached_query_makes_no_duplicate_network_request(self):
        get = Mock(return_value=response(openalex_data()))
        context = self.context(get)
        self.assertEqual(context.search_openalex("fixture"), context.search_openalex("FIXTURE"))
        self.assertEqual(get.call_count, 1)

    def test_missing_metadata_record_skipped(self):
        data = openalex_data()
        data["results"].insert(0, {"title": None})
        context = self.context(Mock(return_value=response(data)))
        self.assertEqual(len(context.search_openalex("fixture")["results"]), 2)

    def test_abstract_clipping_disclosed(self):
        paper = make_paper(title="Fixture", abstract="x" * 5000, url="https://example.org/a", database="fixture")
        self.assertTrue(paper.evidence()["abstract_truncated"])
        self.assertEqual(len(paper.evidence()["abstract"]), 2200)

    def test_ten_paper_limit(self):
        context = self.context()
        def backend(query):
            return [make_paper(title=f"Fixture {query} {i}", abstract="Evidence", url=f"https://example.org/{query}-{i}", database="fixture") for i in range(5)]
        for query in ["a", "b", "c"]:
            context._scientific_lookup("search_openalex", query, backend)
        self.assertEqual(len(context.papers), 10)

    def test_metadata_only_does_not_crowd_out_abstracts(self):
        context = self.context()
        for i in range(10):
            paper = make_paper(title=f"Metadata {i}", url=f"https://example.org/m-{i}", database="fixture")
            context.papers[paper.url] = paper
        paper = make_paper(title="Useful evidence", abstract="Fixture abstract", url="https://example.org/useful", database="fixture")
        context._scientific_lookup("search_openalex", "new", lambda query: [paper])
        self.assertIn(paper.url, context.sources)
        self.assertEqual(len(context.papers), 10)

    def test_missing_authors_and_bad_landing_link_keep_valid_paper(self):
        data = openalex_data()
        data["results"][0]["authorships"] = None
        data["results"][0]["primary_location"]["landing_page_url"] = "file:///private"
        papers = ScientificClient(get=Mock(return_value=response(data))).openalex("fixture")
        self.assertEqual(len(papers), 2)
        self.assertEqual(papers[0].authors, [])
        self.assertTrue(papers[0].url.startswith("https://doi.org/"))

    def test_citations_must_be_numbered_and_in_range(self):
        context = self.context()
        context.search_openalex("fixture")
        for text in ["No numbered citation", "Unsupported [3]"]:
            with self.assertRaises(ValueError):
                validate_response(final_science(summary=text)["content"], context)

    def test_invalid_json_and_all_api_failures_are_explicit(self):
        context = self.context(Mock(return_value=response(content=b"not JSON")))
        self.assertEqual(context.search_openalex("fixture")["error_code"], "invalid_response")
        context = self.context(Mock(return_value=response(status=403)))
        context.search_semantic_scholar("fixture")
        context.search_openalex("fixture")
        context.search_arxiv("fixture")
        self.assertEqual(context.sources, {})

    def test_retry_only_transient_reads_and_bounded_size(self):
        get = Mock(side_effect=[response(status=503), response(openalex_data())])
        client = ScientificClient(get=get, sleep=lambda delay: None)
        self.assertEqual(len(client.openalex("fixture")), 2)
        self.assertEqual(get.call_count, 2)
        get = Mock(return_value=response(status=429))
        client = ScientificClient(get=get)
        with self.assertRaises(ResearchAPIError):
            client.openalex("fixture")
        self.assertEqual(get.call_count, 1)
        client = ScientificClient(get=Mock(return_value=response(content=b"x" * 1_000_001)))
        with self.assertRaises(ResearchAPIError):
            client.openalex("fixture")


if __name__ == "__main__":
    unittest.main()
