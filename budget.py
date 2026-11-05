"""Pre-call reservations and persistent spending limits, without storing prompts."""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_openai import ChatOpenAI
from pydantic import Field

from safety import validate_local_path
from tracing import NullTrace

ROOT = Path(__file__).resolve().parent
MODEL = "gpt-6-luna"
# Standard pricing checked 2026-11-04; amounts are integer nanodollars.
INPUT_RATE = 100
CACHED_INPUT_RATE = 10
OUTPUT_RATE = 500
TASK_CAP = 30_000_000
DAY_CAP = 300_000_000
PROJECT_CAP = 5_000_000_000
MAX_OUTPUT_TOKENS = 1200
MAX_TURNS = 10
_THREAD_LOCK = threading.RLock()


class BudgetStop(RuntimeError):
    """A safe, user-facing reason to refuse or stop a model call."""

    def __init__(self, message: str, code: str = "budget_stop"):
        super().__init__(message)
        self.code = code


def today() -> str:
    return datetime.now(timezone(timedelta(hours=3))).date().isoformat()


@contextmanager
def locked_file(path: Path):
    """Serialize ledger access across processes; keep the lock file in place."""
    with _THREAD_LOCK, path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            for attempt in range(20):
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if attempt == 19:
                        raise BudgetStop("سجل الميزانية مشغول؛ لم يُرسل طلب.") from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


class UsageLedger:
    """Keep reservations across restarts; corruption fails closed."""

    def __init__(self, path: Path | None = None):
        self.path = path or ROOT / ".runtime" / "usage.json"

    @contextmanager
    def transaction(self, *, write: bool = True):
        validate_local_path(self.path, ROOT / ".runtime")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        validate_local_path(lock, ROOT / ".runtime")
        prior_lock = lock.exists()
        with locked_file(lock):
            try:
                if self.path.exists():
                    state = json.loads(self.path.read_text(encoding="utf-8"))
                    if state.get("version") != 1 or not isinstance(state.get("calls"), list):
                        raise ValueError("Invalid ledger")
                    for call in state["calls"]:
                        if (not isinstance(call, dict) or type(call.get("charge")) is not int
                                or call["charge"] < 0 or not isinstance(call.get("task"), str)
                                or not isinstance(call.get("day"), str)
                                or not isinstance(call.get("id"), str)
                                or call.get("status") not in {"reserved", "measured"}):
                            raise ValueError("Invalid ledger entry")
                        datetime.strptime(call["day"], "%Y-%m-%d")
                    if len({call["id"] for call in state["calls"]}) != len(state["calls"]):
                        raise ValueError("Duplicate ledger entry")
                else:
                    if prior_lock:
                        raise ValueError("Previously initialized ledger is missing")
                    state = {"version": 1, "calls": []}
            except (ValueError, OSError, TypeError, AttributeError):
                raise BudgetStop("سجل الميزانية غير صالح؛ أُوقف الاتصال لحماية الرصيد.") from None
            yield state
            if not write:
                return
            temporary = self.path.with_suffix(".pending")
            validate_local_path(temporary, ROOT / ".runtime")
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)

    def snapshot(self, task: str | None = None) -> dict:
        if not self.path.exists():
            if self.path.with_suffix(".lock").exists():
                raise BudgetStop("سجل الميزانية السابق مفقود؛ أُوقف التشغيل دون تصفير الرصيد.")
            return {"calls": 0, "task_nanos": 0, "day_nanos": 0, "project_nanos": 0, "reserved_nanos": 0}
        with self.transaction(write=False) as state:
            calls = state["calls"]
            return {"calls": len(calls), "task_nanos": sum(c["charge"] for c in calls if c["task"] == task),
                    "day_nanos": sum(c["charge"] for c in calls if c["day"] == today()),
                    "project_nanos": sum(c["charge"] for c in calls),
                    "reserved_nanos": sum(c["charge"] for c in calls if c["status"] == "reserved")}

    def reserve(self, task: str, input_bound: int, output_bound: int) -> str:
        if (type(input_bound) is not int or type(output_bound) is not int
                or not 0 < input_bound <= 100_000 or not 0 < output_bound <= MAX_OUTPUT_TOKENS):
            raise BudgetStop("حدود الاستدعاء غير صالحة؛ لم يُرسل طلب.")
        # Reserve at cache-write rates, higher than ordinary input pricing.
        estimate = input_bound * 125 + output_bound * OUTPUT_RATE
        with self.transaction() as state:
            calls = state["calls"]
            task_calls = [call for call in calls if call["task"] == task]
            if len(task_calls) >= MAX_TURNS:
                raise BudgetStop("توقفت المهمة عند حد 10 استدعاءات للنموذج.", "turn_limit")
            totals = [sum(call["charge"] for call in task_calls),
                      sum(call["charge"] for call in calls if call["day"] == today()),
                      sum(call["charge"] for call in calls)]
            for total, cap, code in zip(totals, [TASK_CAP, DAY_CAP, PROJECT_CAP], ["task_budget", "daily_budget", "project_budget"]):
                if total + estimate > cap:
                    raise BudgetStop("الميزانية المتبقية لا تكفي للاستدعاء المتوقع؛ لم يُرسل الطلب.", code)
            reservation = uuid4().hex
            calls.append({"id": reservation, "task": task, "day": today(), "model": MODEL,
                          "status": "reserved", "charge": estimate,
                          "estimated_input_bound": input_bound, "max_output_tokens": output_bound})
        return reservation

    def settle(self, reservation: str, usage: dict[str, Any]) -> bool:
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        if type(input_tokens) is not int or type(output_tokens) is not int or min(input_tokens, output_tokens) < 0:
            raise BudgetStop("تعذّر قياس الاستهلاك؛ بقي تقدير الاستدعاء محجوزًا وأُوقفت المهمة.")
        details = usage.get("input_token_details") or {}
        cached = details.get("cache_read", 0)
        if type(cached) is not int or cached < 0 or cached > input_tokens:
            raise BudgetStop("بيانات الاستهلاك غير صالحة؛ بقي الحجز المالي قائمًا.")
        charge = (input_tokens - cached) * INPUT_RATE + cached * CACHED_INPUT_RATE + output_tokens * OUTPUT_RATE
        exceeded = False
        with self.transaction() as state:
            call = next((call for call in state["calls"] if call["id"] == reservation), None)
            if call is None or call["status"] != "reserved":
                raise BudgetStop("تعذّر تسوية سجل الاستهلاك؛ أُوقفت المهمة.")
            call.update(status="measured", charge=charge, input_tokens=input_tokens,
                        output_tokens=output_tokens, cached_input_tokens=cached)
            exceeded = input_tokens > call["estimated_input_bound"] or output_tokens > call["max_output_tokens"]
        return exceeded


class BudgetSession:
    def __init__(self, ledger: UsageLedger, task_id: str | None = None, *, trace=None, mode="web"):
        if mode not in {"web", "scientific"}:
            raise ValueError("Invalid research mode")
        self.ledger = ledger
        self.task_id = task_id or uuid4().hex
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.pending: dict[str, int] = {}
        self.measured_cost = 0
        self.trace = trace or NullTrace()
        self.mode = mode

    def reserve_payload(self, payload: dict[str, Any]) -> str:
        allowed_fields = {"model", "messages", "max_completion_tokens", "reasoning_effort", "n",
                          "stream", "service_tier", "tools", "tool_choice", "parallel_tool_calls", "stop"}
        if set(payload) - allowed_fields:
            raise BudgetStop("معاملات اتصال غير معتمدة؛ لم يُرسل طلب.")
        if (payload.get("model") != MODEL or payload.get("reasoning_effort") != "none"
                or payload.get("n", 1) != 1 or payload.get("stream", False)
                or payload.get("service_tier", "default") != "default"):
            raise BudgetStop("إعداد النموذج لا يطابق إعداد التسعير الآمن.")
        output = payload.get("max_completion_tokens")
        if type(output) is not int or not 1 <= output <= MAX_OUTPUT_TOKENS:
            raise BudgetStop("حد توكنات الإخراج غير آمن.")
        if any(not isinstance(message.get("content"), (str, type(None))) for message in payload.get("messages", [])):
            raise BudgetStop("هذا الإصدار يحسب تكلفة النص فقط.")
        allowed = ({"search_asta", "search_semantic_scholar", "search_openalex", "search_arxiv", "save_report_to_disk"}
                   if self.mode == "scientific" else {"exa_search", "duckduckgo_search", "wikipedia_lookup", "save_report_to_disk"})
        for tool in payload.get("tools", []):
            if tool.get("type") != "function" or tool.get("function", {}).get("name") not in allowed:
                raise BudgetStop("أداة غير معتمدة في طلب النموذج.")
        # No tokenizer downloads: a conservative byte estimate plus protocol
        # allowance. This is application protection, not a provider guarantee.
        input_bound = 2 * len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + 8192
        if input_bound > 100_000:
            raise BudgetStop("السياق أكبر من الحد الآمن لهذا الإصدار؛ اختصر المهمة.")
        reservation = self.ledger.reserve(self.task_id, input_bound, output)
        self.calls += 1
        self.pending[reservation] = input_bound * 125 + output * OUTPUT_RATE
        self.trace.emit("model_reserved", reservation_id=reservation, input_bound=input_bound,
                        max_output_tokens=output, estimated_nanos=self.pending[reservation])
        return reservation

    def summary(self) -> str:
        return (f"استدعاءات النموذج: {self.calls}؛ توكنات مقاسة: إدخال {self.input_tokens}، إخراج {self.output_tokens}. "
                f"تكلفة مقدرة من الاستهلاك: ${self.measured_cost / 1e9:.8f}؛ "
                f"حجوزات غير مسوّاة: ${sum(self.pending.values()) / 1e9:.8f}.")


class GuardedChatOpenAI(ChatOpenAI):
    """Guard actual synchronous requests, including agent tool-call rounds."""

    session: Any = Field(exclude=True, repr=False)

    @classmethod
    def for_session(cls, session: BudgetSession, **kwargs: Any) -> GuardedChatOpenAI:
        return cls(model=MODEL, session=session, reasoning_effort="none",
                   max_completion_tokens=MAX_OUTPUT_TOKENS, max_retries=0, timeout=30,
                   use_responses_api=False, streaming=False, cache=False,
                   disable_streaming=True,
                   base_url="https://api.openai.com/v1", service_tier="default", **kwargs)

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kwargs: Any):
        if self.max_retries != 0 or self.openai_api_base != "https://api.openai.com/v1":
            raise BudgetStop("المحاولات التلقائية أو عنوان المزوّد غير معتمد.")
        payload = self._get_request_payload(messages, stop=stop, **kwargs)
        try:
            reservation = self.session.reserve_payload(payload)
        except BudgetStop as error:
            self.session.trace.emit("budget_blocked", reason=error.code)
            raise
        # Errors/timeouts/Ctrl+C leave a charged reservation: the server might
        # already have processed the request. Never automatically retry it.
        try:
            result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except BaseException:
            self.session.trace.emit("model_error", reservation_id=reservation, error_code="transport_or_provider_error")
            raise
        usage = result.generations[0].message.usage_metadata or {}
        try:
            exceeded = self.session.ledger.settle(reservation, usage)
        except BudgetStop:
            self.session.trace.emit("model_error", reservation_id=reservation, error_code="usage_unavailable_or_invalid")
            raise
        self.session.input_tokens += usage["input_tokens"]
        self.session.output_tokens += usage["output_tokens"]
        cached = (usage.get("input_token_details") or {}).get("cache_read", 0)
        self.session.measured_cost += ((usage["input_tokens"] - cached) * INPUT_RATE
                                       + cached * CACHED_INPUT_RATE + usage["output_tokens"] * OUTPUT_RATE)
        self.session.pending.pop(reservation, None)
        self.session.trace.emit("model_usage", reservation_id=reservation,
            input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"], cached_input_tokens=cached,
            cost_nanos=(usage["input_tokens"] - cached) * INPUT_RATE + cached * CACHED_INPUT_RATE + usage["output_tokens"] * OUTPUT_RATE)
        if exceeded:
            raise BudgetStop("تجاوز الاستهلاك الحدود المقدرة؛ أُوقفت المهمة. راجع سجل الميزانية.")
        return result

    async def _agenerate(self, *args: Any, **kwargs: Any):
        raise BudgetStop("الاتصال غير المتزامن غير متاح في CLI المحمي.")

    def _stream(self, *args: Any, **kwargs: Any):
        raise BudgetStop("البث غير متاح في CLI المحمي.")
        yield
