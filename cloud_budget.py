"""Server-only Supabase budget adapter. No prompts, credentials or research storage."""

from __future__ import annotations

import json
import os
import re
from uuid import uuid4

import requests

from budget import (BudgetStop, MODEL, TASK_CAP, DAY_CAP, PROJECT_CAP, MAX_TURNS,
                    MAX_INPUT_BOUND, MAX_OUTPUT_TOKENS)


class SupabaseLedger:
    """One durable ledger shared across cloud sessions; never fall back to local files."""

    def __init__(self, url: str, key: str, *, post=None):
        url = url.rstrip("/")
        if not re.fullmatch(r"https://[a-z0-9]{10,40}\.supabase\.co", url):
            raise BudgetStop("عنوان سجل الميزانية السحابي غير صالح.", "cloud_configuration")
        if not key.startswith("sb_secret_") or any(c in key for c in "\r\n"):
            raise BudgetStop("يلزم إعداد مفتاح Supabase السري الخاص بالخادم.", "cloud_configuration")
        self._url, self._key, self._post = url, key, post

    @classmethod
    def configured(cls):
        return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SECRET_KEY"))

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SECRET_KEY", ""))

    def _rpc(self, operation: str, arguments: dict) -> dict:
        response = None
        session = requests.Session()
        session.trust_env = False
        try:
            response = (self._post or session.post)(self._url + "/rest/v1/rpc/ai_budget_" + operation,
                headers={"apikey": self._key, "Content-Type": "application/json"},
                json=arguments, timeout=(5, 15), allow_redirects=False, stream=True)
            if response.status_code != 200:
                raise ValueError("Unavailable")
            raw = bytearray()
            for chunk in response.iter_content(chunk_size=4096):
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise ValueError("Oversized")
            result = json.loads(raw)
            if not isinstance(result, dict) or type(result.get("ok")) is not bool:
                raise ValueError("Invalid response")
        except Exception:
            raise BudgetStop("تعذّر تأكيد سجل الميزانية الدائم؛ أُوقف الاتصال بالنموذج.",
                             "cloud_budget_unavailable") from None
        finally:
            if response is not None:
                response.close()
            session.close()
        if not result["ok"]:
            code = result.get("code")
            if code not in {"task_budget", "daily_budget", "project_budget", "turn_limit",
                            "ledger_uninitialized", "invalid_reservation", "invalid_usage", "invalid_bounds"}:
                code = "cloud_budget_unavailable"
            raise BudgetStop("سجل الميزانية الدائم منع الطلب: " + code, code)
        return result

    def snapshot(self, task=None):
        result = self._rpc("snapshot", {"p_task": task})
        expected = {"version": 1, "model": MODEL, "task_cap": TASK_CAP, "day_cap": DAY_CAP,
                    "project_cap": PROJECT_CAP, "max_turns": MAX_TURNS,
                    "max_input": MAX_INPUT_BOUND, "max_output": MAX_OUTPUT_TOKENS}
        if any(type(result.get(k)) is not type(v) or result[k] != v for k, v in expected.items()):
            raise BudgetStop("إعداد حدود الميزانية السحابية لا يطابق التطبيق.", "cloud_configuration")
        fields = ("calls", "task_nanos", "day_nanos", "project_nanos", "reserved_nanos")
        if any(type(result.get(k)) is not int or result[k] < 0 for k in fields):
            raise BudgetStop("بيانات الميزانية السحابية غير صالحة.", "cloud_budget_unavailable")
        if result["reserved_nanos"] > result["project_nanos"] or result["day_nanos"] > result["project_nanos"]:
            raise BudgetStop("بيانات الميزانية السحابية غير متسقة.", "cloud_budget_unavailable")
        return {k: result[k] for k in fields}

    def reserve(self, task, input_bound, output_bound):
        if (not isinstance(task, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", task)
                or type(input_bound) is not int or not 0 < input_bound <= MAX_INPUT_BOUND
                or type(output_bound) is not int or not 0 < output_bound <= MAX_OUTPUT_TOKENS):
            raise BudgetStop("حدود الاستدعاء غير صالحة؛ لم يُرسل طلب.", "invalid_bounds")
        self.snapshot(task)  # Verify schema/configuration before an atomic reservation.
        reservation = uuid4().hex
        result = self._rpc("reserve", {"p_task": task, "p_id": reservation,
                                       "p_input": input_bound, "p_output": output_bound})
        if result.get("reservation") != reservation or result.get("estimate") != input_bound * 125 + output_bound * 500:
            raise BudgetStop("تعذّر تأكيد الحجز؛ لم يُرسل طلب للنموذج.", "invalid_reservation")
        return reservation

    def settle(self, reservation, usage):
        if not isinstance(usage, dict):
            raise BudgetStop("بيانات الاستهلاك غير صالحة؛ بقي الحجز قائمًا.", "invalid_usage")
        details = usage.get("input_token_details") or {}
        values = (usage.get("input_tokens"), usage.get("output_tokens"),
                  details.get("cache_read", 0) if isinstance(details, dict) else None)
        if (not re.fullmatch(r"[a-f0-9]{32}", str(reservation))
                or any(type(v) is not int or not 0 <= v <= 2_000_000 for v in values)
                or values[2] > values[0]):
            raise BudgetStop("بيانات الاستهلاك غير صالحة؛ بقي الحجز قائمًا.", "invalid_usage")
        result = self._rpc("settle", dict(zip(("p_id", "p_input", "p_output", "p_cached"),
                                            (reservation, *values))))
        if type(result.get("exceeded")) is not bool:
            raise BudgetStop("تعذّر تأكيد التسوية؛ أُوقفت المهمة.", "invalid_usage")
        return result["exceeded"]
