"""Session-scoped adapter; uses the existing engine, ledger, memory and report writer."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from threading import RLock
from types import SimpleNamespace
from typing import Callable

from budget import BudgetSession, BudgetStop, GuardedChatOpenAI, UsageLedger
from frontend.contracts import BackendResult, Progress, ResearchRequest, Source
from main import ResearchResponse, format_report, run_research
from memory import MemoryError as StorageError, ResearchMemory
from safety import clean_text
from scientific_tools import ScientificResearchContext
from tools import WebResearchContext
from tracing import NullTrace, TraceError, TraceWriter


class GatewayError(RuntimeError):
    def __init__(self, code: str, message: str = "تعذّر إكمال العملية بأمان؛ لم تُعرض نتيجة غير متحققة."):
        self.code = code
        self.message = clean_text(message, 1500)
        super().__init__(self.message)


class ProgressTrace:
    """Forward genuine events; progress contains approved labels, never tool content."""

    def __init__(self, trace, callback):
        self.trace, self.callback, self.count = trace, callback, 0
        self.task_id = trace.task_id

    def emit(self, event, **data):
        self.trace.emit(event, **data)
        if event in {"tool_started", "model_reserved", "memory_saved"}:
            self.count += 1
            label = "تشغيل أداة البحث" if event == "tool_started" else (
                "حفظ النتيجة في الذاكرة" if event == "memory_saved" else "معالجة البحث بالنموذج")
            self.callback(Progress(label, min(0.9, 0.1 + self.count * 0.06)))


class BackendGateway:
    """One local operator namespace; this adapter provides no authentication."""

    def __init__(self, *, memory=None, ledger=None, model_factory=None, context_factory=None, trace_factory=None):
        self.memory = memory if memory is not None else ResearchMemory()
        self.ledger = ledger if ledger is not None else UsageLedger()
        self.model_factory = model_factory
        self.context_factory = context_factory
        self.trace_factory = trace_factory or (lambda: TraceWriter(kind="streamlit"))
        self.lock = RLock()
        self.attempts = {}
        self.results = {}
        self.saved = {}
        self.last_usage = {}

    @property
    def configured(self):
        # Only check presence. SDK loads the process credential when research is submitted.
        return self.model_factory is not None or bool(os.environ.get("OPENAI_API_KEY"))

    def budget_status(self):
        try:
            return self.ledger.snapshot()
        except (BudgetStop, OSError, ValueError):
            raise GatewayError("budget_unavailable", "تعذّرت قراءة الميزانية؛ لا تصفّر سجل الاستخدام.") from None

    def _context(self, mode, trace):
        context = (self.context_factory(mode, trace) if self.context_factory else
                   ScientificResearchContext(trace=trace) if mode == "scientific" else WebResearchContext(trace=trace))
        context.confirm = lambda prompt: "n"
        context.display = lambda content: None
        return context

    def research(self, request: ResearchRequest, on_progress: Callable, *, request_id: str) -> BackendResult:
        # Cache failures too: reruns must never silently retry uncertain paid requests.
        with self.lock:
            if request_id in self.attempts:
                cached_request, cached = self.attempts[request_id]
                if cached_request != request:
                    raise GatewayError("request_id_conflict")
                if isinstance(cached, GatewayError):
                    raise cached
                return cached
            self.attempts[request_id] = (request, GatewayError("interrupted", "توقفت المحاولة؛ راجع الميزانية قبل إعادة البحث صراحةً."))
            self.last_usage = {}
            try:
                if not self.configured:
                    raise GatewayError("configuration_error", "OPENAI_API_KEY غير مهيّأ في بيئة العملية. لم يُرسل طلب.")
                result = self._research(request, on_progress)
                self.attempts[request_id] = (request, result)
                return result
            except GatewayError as error:
                self.attempts[request_id] = (request, error)
                raise
            except Exception:
                error = GatewayError("execution_error")
                self.attempts[request_id] = (request, error)
                raise error from None

    def _research(self, request, on_progress):
        trace = ProgressTrace(self.trace_factory(), on_progress)
        trace.emit("run_started", mode=request.mode)
        session = BudgetSession(self.ledger, task_id=trace.task_id, trace=trace, mode=request.mode)
        status = "execution_error"
        try:
            on_progress(Progress("تجهيز البحث والتحقق من الميزانية", 0.05))
            context = self._context(request.mode, trace)
            os.environ["LANGSMITH_TRACING"] = "false"
            os.environ["LANGCHAIN_TRACING_V2"] = "false"
            model = self.model_factory(session) if self.model_factory else GuardedChatOpenAI.for_session(session)
            outcome = run_research(request.query, model, context, memory=self.memory, task_id=trace.task_id)
            status = outcome.status
            if outcome.response is None:
                raise GatewayError(status, outcome.reason)
            response = outcome.response
            sources = tuple(Source(
                title=getattr(getattr(context, "papers", {}).get(url), "title", None)
                      or context.sources[url].get("title", url),
                url=url, description="مصدر مسترجع؛ يعتمد البحث على المقتطف أو الملخص المتاح.") for url in response.sources)
            result = BackendResult(response.topic, response.summary, sources, tuple(response.tools_used),
                request, outcome.status, trace.task_id, datetime.now(timezone.utc).isoformat(),
                context.final_content, memory_status=outcome.memory_status, model_calls=session.calls,
                input_tokens=session.input_tokens, output_tokens=session.output_tokens,
                cost_nanos=session.measured_cost, reserved_nanos=sum(session.pending.values()))
            self.results[result.id] = (result, context)
            on_progress(Progress("اكتمل التحقق من النتيجة", 1.0))
            return result
        finally:
            self.last_usage = {"calls": session.calls, "input_tokens": session.input_tokens,
                "output_tokens": session.output_tokens, "cost_nanos": session.measured_cost,
                "reserved_nanos": sum(session.pending.values())}
            trace.emit("run_finished", status=status, **self.last_usage)

    def history(self, query="", *, limit=5):
        try:
            return self.memory.search(query, limit=limit)
        except StorageError:
            raise GatewayError("memory_unavailable", "تعذّر استعراض ذاكرة SQLite بأمان.") from None

    def open_history(self, task_id):
        try:
            record = self.memory.get(task_id)
        except StorageError:
            raise GatewayError("memory_unavailable", "تعذّر استرجاع البحث السابق بأمان.") from None
        if record is None:
            raise GatewayError("record_missing", "البحث السابق غير موجود.")
        response = ResearchResponse(topic=record.topic, summary=record.summary,
            sources=[source.url for source in record.sources], tools_used=record.tools_used)
        context = self._context(record.mode, NullTrace())
        context.papers = {source.url: SimpleNamespace(**source.model_dump()) for source in record.sources}
        report = (f"PREVIOUS RESEARCH / بحث سابق\nUTC: {record.created_at}\n"
                  f"Status: {record.status}\nQuestion: {record.question}\n\n" + format_report(response, context))
        context.final_content = report
        result = BackendResult(record.topic, record.summary,
            tuple(Source(source.title or source.url, source.url, "مرجع تاريخي؛ لم يُسترجع مجددًا.") for source in record.sources),
            tuple(record.tools_used), ResearchRequest(record.question, record.mode), record.status,
            record.task_id, record.created_at, report, historical=True)
        # Do not populate context.sources: historical citations are not fresh evidence.
        self.results[result.id] = (result, context)
        return result

    def save_report(self, result_id, *, consent=False):
        with self.lock:
            if consent is not True:
                return {"status": "declined"}
            if result_id in self.saved:
                return self.saved[result_id]
            if result_id not in self.results:
                raise GatewayError("result_missing", "لا توجد نتيجة متحققة قابلة للحفظ.")
            result, context = self.results[result_id]
            old_trace, old_confirm = context.trace, context.confirm
            trace = self.trace_factory()
            status = "error"
            try:
                trace.emit("run_started", mode=result.request.mode, reason="report_save")
                context.trace = trace
                context.confirm = lambda prompt: "y"  # Only this explicit UI consent path.
                saved = context.save_report_to_disk(context.final_content, f"{result.request.mode}_report.txt")
                status = saved["status"]
                if status == "saved":
                    self.saved[result_id] = saved
                return saved
            except Exception:
                raise GatewayError("save_failed", "تعذّر حفظ التقرير؛ تحقق من التقارير قبل إعادة المحاولة.") from None
            finally:
                context.trace, context.confirm = old_trace, old_confirm
                trace.emit("run_finished", status=status, calls=0, cost_nanos=0)


def create_gateway():
    """Called once per Streamlit session, not cached globally across browsers."""
    try:
        return BackendGateway()
    except (StorageError, OSError, ValueError):
        raise GatewayError("memory_configuration", "مسار ذاكرة SQLite غير صالح؛ راجع إعدادات العملية.") from None
