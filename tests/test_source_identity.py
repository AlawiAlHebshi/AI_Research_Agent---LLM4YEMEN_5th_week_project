"""Offline source identity regressions; unknown evidence remains rejected."""

import unittest
from unittest.mock import Mock

import main
import test_scientific as science
import test_task2 as baseline
from research_models import academic_reference, make_paper
from tracing import read_trace


class SourceIdentityTests(unittest.TestCase):
    setUp = baseline.OfflineTests.setUp
    ledger = baseline.OfflineTests.ledger
    context = science.ScientificTests.context
    execute = science.ScientificTests.execute

    def paper(self, url="http://arxiv.org/abs/2601.05264v1", **kwargs):
        return make_paper(title="Synthetic paper", abstract="Synthetic abstract", url=url,
                          database="fixture", **kwargs)

    def evidence(self, paper=None):
        context = self.context()
        context._scientific_lookup("search_arxiv", "fixture", lambda query: [paper or self.paper()])
        return context

    def test_stable_id_resolves_to_exact_retrieved_url(self):
        context = self.evidence()
        response = main.validate_response(science.final_science(["P1"], "Evidence [1].")["content"], context)
        self.assertEqual(response.sources, [self.paper().url])

    def test_scientific_id_order_does_not_change_citation_meaning(self):
        context = self.context()
        context.search_openalex("fixture")
        response = main.validate_response(science.final_science(["P2", "P1"], "Second paper [1], first paper [2].")["content"], context)
        self.assertEqual(response.sources, [context.source_ids["P2"], context.source_ids["P1"]])
        self.assertTrue(response.summary.startswith("Second paper [1], first paper [2]."))

    def test_arxiv_transport_and_versionless_reference_keep_original_evidence(self):
        context = self.evidence()
        for value in ["https://arxiv.org/abs/2601.05264v1", "https://arxiv.org/abs/2601.05264"]:
            self.assertEqual(context.resolve_source(value), self.paper().url)

    def test_different_explicit_version_is_rejected(self):
        context = self.evidence()
        self.assertIsNone(context.resolve_source("https://arxiv.org/abs/2601.05264v2"))
        with self.assertRaises(main.ResearchValidationError):
            main.validate_response(science.final_science(["https://arxiv.org/abs/2601.05264v2"], "Evidence [1].")["content"], context)

    def test_known_doi_metadata_resolves_to_retrieved_landing_page(self):
        paper = self.paper("https://example.org/paper", doi="10.1234/ABC")
        context = self.evidence(paper)
        self.assertEqual(context.resolve_source("https://doi.org/10.1234/abc"), paper.url)
        self.assertEqual(context.resolve_source("http://dx.doi.org/10.1234/ABC"), paper.url)
        self.assertIsNone(context.resolve_source("https://doi.org/10.1234/other"))

    def test_deduplication_alias_cannot_change_explicit_evidence_version(self):
        context = self.evidence(self.paper(arxiv_id="2601.05264"))
        other = self.paper("https://arxiv.org/abs/2601.05264v2", arxiv_id="2601.05264")
        context._scientific_lookup("search_arxiv", "second query", lambda query: [other])
        self.assertIn(other.url, context.aliases)
        self.assertIsNone(context.resolve_source(other.url))
        self.assertEqual(context.resolve_source("P1"), self.paper().url)

    def test_similar_hosts_queries_credentials_and_bad_ports_are_rejected(self):
        context = self.evidence()
        for url in ["https://arxiv.org.evil.example/abs/2601.05264v1",
                    "https://arxiv.org/abs/2601.05264v1?anything=1",
                    "https://arxiv.org/abs/2601.05264v1#fragment",
                    "https://someone@arxiv.org/abs/2601.05264v1",
                    "https://arxiv.org:bad/abs/2601.05264v1",
                    "https://arxiv.org:444/abs/2601.05264v1",
                    "https://arxiv.org/abs/2601.05264v1/extra"]:
            with self.subTest(url=url):
                self.assertIsNone(academic_reference(url))
                self.assertIsNone(context.resolve_source(url))

    def test_ambiguous_versionless_reference_is_rejected(self):
        context = self.evidence()
        other = self.paper("http://arxiv.org/abs/2601.05264v2")
        context.papers[other.url] = other
        context.sources[other.url] = {"url": other.url}
        self.assertIsNone(context.resolve_source("https://arxiv.org/abs/2601.05264"))

    def test_no_abstract_gets_no_source_id_or_doi_access(self):
        paper = make_paper(title="Metadata only", url="https://example.org/metadata",
                           database="fixture", doi="10.1234/metadata")
        context = self.context()
        result = context._scientific_lookup("search_openalex", "fixture", lambda query: [paper])
        self.assertIsNone(result["results"][0]["source_id"])
        self.assertEqual(context.source_ids, {})
        self.assertIsNone(context.resolve_source("https://doi.org/10.1234/metadata"))

    def test_ids_survive_cached_queries_and_deduplication(self):
        context = self.context(Mock(side_effect=[science.response(science.semantic_data()), science.response(science.openalex_data())]))
        first = context.search_semantic_scholar("fixture")
        second = context.search_openalex("fixture")
        self.assertEqual(first["results"][0]["source_id"], second["results"][0]["source_id"])
        self.assertEqual(second, context.search_openalex("fixture"))
        self.assertEqual(len(context.source_ids), 2)

    def test_unknown_id_is_rejected_and_diagnostic_contains_position_only(self):
        context = self.context()
        outcome, _ = self.execute([baseline.tool_call("search_openalex"),
                                  science.final_science(["P1", "P99"], "Evidence [1] and [2].")], context)
        self.assertIsNone(outcome.response)
        event = next(row for row in read_trace(context.trace.path) if row["event"] == "research_finished")
        self.assertEqual(event["data"]["source_index"], 2)
        self.assertEqual(event["data"]["source_issue"], "unknown_source_reference")
        self.assertNotIn("P99", context.trace.path.read_text(encoding="utf-8"))

    def test_full_agent_resolves_scientific_ids_with_existing_budget_controls(self):
        context = self.context()
        outcome, session = self.execute([baseline.tool_call("search_openalex"),
                                        science.final_science(["P1", "P2"])], context)
        self.assertEqual(outcome.status, "success")
        self.assertEqual(session.calls, 2)
        self.assertEqual(outcome.response.sources, list(context.sources))

    def test_prose_url_is_canonicalized_and_unknown_url_still_fails(self):
        context = self.evidence()
        response = main.validate_response(science.final_science(["P1"],
            "Evidence [1] https://arxiv.org/abs/2601.05264.")["content"], context)
        self.assertIn(self.paper().url + ".", response.summary)
        with self.assertRaises(main.ResearchValidationError):
            main.validate_response(science.final_science(["P1"],
                "Evidence [1] https://arxiv.org/abs/2601.99999.")["content"], context)
