"""Offline frontend acceptance tests; never connect to the real research engine."""

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from frontend.contracts import ResearchRequest, Source, export_report
from frontend.demo import DemoGateway, DemoResearchError, EXAMPLES

ROOT = Path(__file__).resolve().parents[1]


class FrontendTests(unittest.TestCase):
    def setUp(self):
        original_connect = socket.socket.connect

        def local_only(connection, address):
            # Windows asyncio implements socketpair with a loopback connection.
            if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
                return original_connect(connection, address)
            raise AssertionError("External network forbidden in frontend tests")

        network = patch.object(socket.socket, "connect", new=local_only)
        network.start()
        self.addCleanup(network.stop)

    def app(self):
        app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=15).run()
        self.assertFalse(app.exception)
        return app

    def submit(self, app, query="واجهة تجريبية فقط", mode="web", scenario="عرض مكتمل"):
        app.selectbox(key="ui_scenario").set_value(scenario).run()
        app.radio(key="ui_mode").set_value(mode)
        app.text_area(key="ui_query").set_value(query)
        app.button(key="start_demo").click().run()
        self.assertFalse(app.exception)
        return app

    def test_initial_preview_does_not_create_research_history(self):
        app = self.app()
        self.assertEqual(app.session_state["ui_history"], [])
        self.assertEqual(app.session_state["ui_saved"], [])
        self.assertIsNone(app.session_state["ui_active"])
        self.assertTrue(any("وضع تجريبي" in item.value for item in app.markdown))

    def test_blank_and_long_questions_are_rejected_without_history(self):
        app = self.app()
        for query in ["   ", "x" * 2001]:
            self.submit(app, query=query)
            self.assertTrue(app.error)
            self.assertEqual(app.session_state["ui_history"], [])

    def test_web_demo_preserves_request_and_labels_fixed_content(self):
        app = self.submit(self.app(), query="A custom question, not a live search")
        result = app.session_state["ui_active"]
        self.assertEqual(result.request.query, "A custom question, not a live search")
        self.assertTrue(result.is_demo)
        self.assertTrue(result.id.startswith("demo_"))
        self.assertEqual(len(app.session_state["ui_history"]), 1)
        self.assertIn("exa_search", result.tools_used)
        self.assertTrue(any("ليس إجابة" in item.value for item in app.info))

    def test_scientific_mode_is_demo_and_has_numbered_citations(self):
        app = self.submit(self.app(), mode="scientific")
        result = app.session_state["ui_active"]
        self.assertEqual(result.request.mode, "scientific")
        self.assertIn("search_asta", result.tools_used)
        self.assertTrue(all(source.url.startswith("https://example.org/demo/") for source in result.sources))
        self.assertTrue(any("[1](https://example.org/demo/scientific/" in item.value for item in app.markdown))

    def test_partial_result_discloses_single_reference(self):
        app = self.submit(self.app(), scenario="مصدر واحد فقط")
        result = app.session_state["ui_active"]
        self.assertEqual(result.status, "partial")
        self.assertEqual(len(result.sources), 1)
        self.assertTrue(app.warning)
        self.assertNotIn("[2]", result.summary)

    def test_error_scenario_does_not_create_success_record(self):
        app = self.submit(self.app(), scenario="تعذّر البحث")
        self.assertTrue(app.error)
        self.assertIsNone(app.session_state["ui_active"])
        self.assertEqual(app.session_state["ui_history"], [])

    def test_save_requires_consent_and_keeps_only_one_session_copy(self):
        app = self.submit(self.app())
        result = app.session_state["ui_active"]
        save_key = "save_" + result.id
        self.assertTrue(app.button(key=save_key).disabled)
        self.assertEqual(app.session_state["ui_saved"], [])
        app.checkbox(key="consent_" + result.id).check().run()
        self.assertFalse(app.button(key=save_key).disabled)
        app.button(key=save_key).click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state["ui_saved"]), 1)
        self.assertTrue(app.button(key=save_key).disabled)
        app.run()
        self.assertEqual(len(app.session_state["ui_saved"]), 1)

    def test_reports_library_and_download_are_explicitly_demo(self):
        app = self.submit(self.app())
        result = app.session_state["ui_active"]
        app.checkbox(key="consent_" + result.id).check().run()
        app.button(key="save_" + result.id).click().run()
        app.radio(key="ui_page").set_value("التقارير التجريبية").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.download_button), 1)
        self.assertTrue(any("DEMO ONLY" in item.value for item in app.text))
        app.download_button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state["ui_saved"]), 1)
        payload = export_report(result)
        self.assertTrue(payload.startswith("DEMO ONLY"))
        self.assertIn(result.request.query, payload)
        self.assertIn("لم يُستدعَ OpenAI أو MCP", payload)

    def test_history_restores_selected_question_and_mode(self):
        app = self.submit(self.app(), query="Question one", mode="scientific")
        original = app.session_state["ui_active"]
        self.submit(app, query="Question two", mode="web")
        app.button(key="history_" + original.id).click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["ui_active"].id, original.id)
        self.assertEqual(app.text_area(key="ui_query").value, "Question one")
        self.assertEqual(app.radio(key="ui_mode").value, "scientific")

    def test_example_buttons_prepare_form_without_running_research(self):
        app = self.app()
        app.button(key="example_science").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_area(key="ui_query").value, EXAMPLES["scientific"])
        self.assertEqual(app.radio(key="ui_mode").value, "scientific")
        self.assertEqual(app.session_state["ui_history"], [])

    def test_about_page_and_empty_library(self):
        app = self.app()
        for page in ["عن الواجهة", "التقارير التجريبية"]:
            app.radio(key="ui_page").set_value(page).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["ui_saved"], [])

    def test_sessions_are_isolated_and_do_not_persist_history(self):
        first = self.submit(self.app())
        self.assertEqual(len(first.session_state["ui_history"]), 1)
        second = self.app()
        self.assertEqual(second.session_state["ui_history"], [])
        self.assertEqual(second.session_state["ui_saved"], [])

    def test_fixture_mode_cannot_be_marked_real_and_progress_is_local(self):
        steps = []
        result = DemoGateway().research(ResearchRequest("A question", "web"), steps.append)
        self.assertEqual([step.fraction for step in steps], [0.15, 0.45, 0.75, 1.0])
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            result.is_demo = False
        with self.assertRaises(DemoResearchError):
            DemoGateway().research(result.request, scenario="error")

    def test_frontend_has_no_backend_environment_database_or_network_imports(self):
        forbidden = {"main", "tools", "scientific_tools", "mcp_client", "budget", "tracing",
                     "dotenv", "openai", "requests", "httpx", "sqlite3", "urllib.request", "socket", "os"}
        for path in [ROOT / "streamlit_app.py", *(ROOT / "frontend").glob("*.py")]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imports.append(node.module or "")
            self.assertFalse(set(imports) & forbidden, path.name)

    def test_invalid_modes_and_source_links_are_rejected(self):
        with self.assertRaises(ValueError):
            ResearchRequest("A question", "live")
        for url in ["file:///secret", "javascript:alert(1)", "https://user:password@example.org"]:
            with self.assertRaises(ValueError):
                Source("Invalid fixture", url, "Not allowed")

    def test_language_switch_preserves_pending_question_without_research(self):
        app = self.app()
        query = "سؤال لم أشغله بعد — keep my exact text"
        app.text_area(key="ui_query").set_value(query)
        app.button(key="ui_language_toggle").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["ui_language"], "en")
        self.assertEqual(app.text_area(key="ui_query").value, query)
        self.assertEqual(app.text_area(key="ui_query").label, "What would you like to explore?")
        self.assertEqual(app.button(key="start_demo").label, "Start demo research")
        self.assertEqual(app.session_state["ui_history"], [])
        app.button(key="ui_language_toggle").click().run()
        self.assertEqual(app.session_state["ui_language"], "ar")
        self.assertEqual(app.text_area(key="ui_query").value, query)

    def test_english_scientific_result_and_saved_copy_keep_original_identity(self):
        app = self.submit(self.app(), query="My original question", mode="scientific")
        result = app.session_state["ui_active"]
        app.checkbox(key="consent_" + result.id).check().run()
        app.button(key="save_" + result.id).click().run()
        app.button(key="ui_language_toggle").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["ui_active"].id, result.id)
        self.assertEqual(len(app.session_state["ui_history"]), 1)
        self.assertEqual(len(app.session_state["ui_saved"]), 1)
        report = app.text_area(key="report_text_" + result.id + "_en").value
        self.assertIn("No OpenAI or MCP calls", report)
        self.assertIn("My original question", report)
        self.assertIn("Fictional study 1", report)
        self.assertNotIn("هذه عينة", report)
        app.radio(key="ui_page").set_value("التقارير التجريبية").run()
        self.assertTrue(any("Your demo-session reports" in item.value for item in app.markdown))
        app.button(key="ui_language_toggle").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["ui_page"], "التقارير التجريبية")
        self.assertEqual(app.session_state["ui_saved"][0].id, result.id)

    def test_english_validation_and_failure_feedback(self):
        app = self.app()
        app.button(key="ui_language_toggle").click().run()
        app.button(key="start_demo").click().run()
        self.assertIn("Enter a question first", app.error[0].value)
        self.submit(app, query="A demo question", scenario="تعذّر البحث")
        self.assertTrue(any("simulated failure" in error.value for error in app.error))
        self.assertEqual(app.session_state["ui_history"], [])


if __name__ == "__main__":
    unittest.main()
