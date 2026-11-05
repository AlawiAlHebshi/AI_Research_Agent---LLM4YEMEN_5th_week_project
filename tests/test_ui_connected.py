"""Connected Streamlit AppTest, with the real adapter/engine and offline HTTP fixtures."""

import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import test_task2 as baseline
import test_scientific as science
import test_streamlit_backend as adapters
import test_ui as demo_tests


class ConnectedUITests(unittest.TestCase):
    ledger = baseline.OfflineTests.ledger
    model = baseline.OfflineTests.model
    gateway = adapters.AdapterTests.gateway

    def setUp(self):
        baseline.OfflineTests.setUp(self)
        self.network.stop()
        demo_tests.FrontendTests.setUp(self)

    def app(self, messages=None):
        self.backend = self.gateway(messages)
        factory = patch("streamlit_backend.create_gateway", return_value=self.backend)
        factory.start()
        self.addCleanup(factory.stop)
        app = AppTest.from_file(str(baseline.ROOT / "streamlit_app.py"), default_timeout=20).run()
        self.assertFalse(app.exception)
        return app

    def submit(self, app, *, mode="web", question="MCP offline fixture"):
        app.radio(key="live_mode").set_value(mode)
        app.text_area(key="live_query").set_value(question)
        app.button(key="start_research").click().run()
        self.assertFalse(app.exception)
        return app

    def test_initial_load_and_navigation_make_no_requests_or_fake_results(self):
        app = self.app([])
        self.assertIsNone(app.session_state["live_active"])
        for page in ["history", "reports", "about", "workspace"]:
            app.radio(key="live_page").set_value(page).run()
        self.assertFalse(app.exception)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.backend.results, {})

    def test_both_modes_display_validated_results_and_clickable_citations(self):
        app = self.app([baseline.tool_call("search_openalex"), science.final_science(["P1", "P2"])])
        self.submit(app, mode="scientific")
        result = app.session_state["live_active"]
        self.assertFalse(result.is_demo)
        self.assertEqual(result.request.mode, "scientific")
        self.assertTrue(any("[1](https://example.org/paper-1)" in item.value for item in app.markdown))
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(app.download_button)

    def test_reruns_language_history_save_download_and_repeat_click_are_not_paid_again(self):
        app = self.submit(self.app())
        result = app.session_state["live_active"]
        count = len(self.requests)
        app.run()
        app.button(key="ui_language_toggle").click().run()
        self.assertEqual(app.session_state["live_active"].summary, result.summary)
        self.assertEqual(app.button(key="start_research").label, "Start research")
        self.assertTrue(app.button(key="live_save_" + result.id).disabled)
        app.checkbox(key="live_consent_" + result.id).check().run()
        app.button(key="live_save_" + result.id).click().run()
        app.download_button(key="live_download_" + result.id).click().run()
        app.radio(key="live_page").set_value("history").run()
        app.text_input(key="live_history_search").set_value("MCP").run()
        app.button(key="search_" + result.id).click().run()
        self.assertTrue(app.session_state["live_active"].historical)
        app.button(key="start_research").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(self.requests), count)
        self.assertEqual(self.backend.saved[result.id]["status"], "saved")

    def test_explicit_repeat_consent_allows_a_new_task(self):
        app = self.submit(self.app([baseline.tool_call(), baseline.final_message(), baseline.tool_call(), baseline.final_message()]))
        first = app.session_state["live_active"].id
        app.run()
        app.checkbox(key="live_repeat_" + app.session_state["live_request_id"]).check().run()
        app.button(key="start_research").click().run()
        self.assertFalse(app.exception)
        self.assertNotEqual(app.session_state["live_active"].id, first)
        self.assertEqual(len(self.requests), 4)
        app.button(key="start_research").click().run()
        self.assertEqual(len(self.requests), 4)
        self.assertFalse(app.checkbox(key="live_repeat_" + app.session_state["live_request_id"]).value)

    def test_editing_question_and_changing_mode_do_not_submit_research(self):
        app = self.submit(self.app())
        original = app.session_state["live_active"].id
        app.radio(key="live_mode").set_value("scientific").run()
        app.text_area(key="live_query").set_value("A different unsubmitted question").run()
        app.button(key="ui_language_toggle").click().run()
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["live_active"].id, original)
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(len(self.backend.attempts), 1)
        self.assertEqual(len(self.backend.results), 1)

    def test_invalid_results_never_enable_saving_or_downloading(self):
        app = self.app([baseline.tool_call(), baseline.final_message(["https://example.net/unretrieved"])])
        self.submit(app)
        self.assertIsNone(app.session_state["live_active"])
        self.assertTrue(app.error)
        self.assertEqual(len(app.download_button), 0)
        self.assertEqual(self.backend.history(), [])
        app.run()
        self.assertEqual(len(self.requests), 2)

    def test_blank_question_does_not_run_model(self):
        app = self.app([])
        self.submit(app, question=" ")
        self.assertTrue(app.error)
        self.assertEqual(self.requests, [])

    def test_explicit_demo_switch_never_calls_backend_research(self):
        app = self.app([])
        app.toggle(key="ui_demo_mode").set_value(True).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("وضع تجريبي" in item.value for item in app.markdown))
        self.assertEqual(self.requests, [])

    def test_budget_failure_is_visible_without_requests_or_results(self):
        from budget import today
        from uuid import uuid4
        app = self.app([])
        with self.backend.ledger.transaction() as state:
            state["calls"].append({"id": uuid4().hex, "task": "old", "day": today(),
                                   "status": "measured", "charge": 300_000_000})
        self.submit(app)
        self.assertTrue(app.error)
        self.assertIsNone(app.session_state["live_active"])
        self.assertEqual(self.requests, [])

    def test_new_ui_session_can_open_persistent_history_without_research(self):
        app = self.submit(self.app())
        task_id = app.session_state["live_active"].id
        count = len(self.requests)
        reopened = self.gateway([])
        with patch("streamlit_backend.create_gateway", return_value=reopened):
            other = AppTest.from_file(str(baseline.ROOT / "streamlit_app.py"), default_timeout=20).run()
            self.assertIsNone(other.session_state["live_active"])
            other.button(key="recent_" + task_id).click().run()
        self.assertFalse(other.exception)
        self.assertTrue(other.session_state["live_active"].historical)
        self.assertEqual(len(self.requests), count)

    def test_missing_environment_key_disables_live_submit(self):
        app = self.app([])
        self.backend.model_factory = None
        with patch.dict("os.environ", {}, clear=True):
            app.run()
        self.assertTrue(app.button(key="start_research").disabled)
        self.assertTrue(any("OPENAI_API_KEY" in item.value for item in app.info))
        self.assertEqual(self.requests, [])
