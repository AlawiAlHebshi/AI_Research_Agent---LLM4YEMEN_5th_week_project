"""Allowlisted JSONL audit events. No prompts, headers or raw exceptions."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from safety import clean_text, safe_url, validate_local_path

ROOT = Path(__file__).resolve().parent
EVENTS = {
    "run_started", "run_finished", "research_finished", "model_reserved", "model_usage",
    "model_error", "budget_blocked", "tool_started", "tool_result", "tool_error",
    "tool_cache_hit", "recovery_started", "save_requested", "save_decision", "save_result",
    "mcp_connected", "mcp_usage",
    "memory_loaded", "memory_saved", "memory_error",
}
FIELDS = {
    "mode", "status", "reason", "tool", "error_code", "result_count", "source_count",
    "sources", "reservation_id", "input_bound", "max_output_tokens", "estimated_nanos",
    "input_tokens", "output_tokens", "cached_input_tokens", "cost_nanos", "calls",
    "filename", "decision", "cache_hit", "public_requests", "bytes_received",
    "reserved_nanos", "source_index", "source_issue",
}


class TraceError(RuntimeError):
    pass


class NullTrace:
    """Explicitly disabled tracing for callers that only test individual helpers."""

    def emit(self, event: str, **data) -> None:
        pass


def scrub(value):
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            # Queries may contain provider credentials. Never persist them.
            return (safe_url(value) or "[REDACTED URL]").split("?", 1)[0]
        return clean_text(value, 1000)
    if value is None or type(value) in {bool, int, float}:
        return value
    if isinstance(value, list):
        return [scrub(item) for item in value[:20]]
    raise TraceError("Unsupported audit value")


class TraceWriter:
    def __init__(self, task_id: str | None = None, *, kind: str = "cli", path: Path | None = None):
        if kind not in {"cli", "streamlit", "offline_test", "public_tool_probe"}:
            raise TraceError("Invalid execution kind")
        self.task_id = task_id or uuid4().hex
        self.kind = kind
        self.path = path or ROOT / ".runtime" / "traces" / f"{self.task_id}.jsonl"
        validate_local_path(self.path, ROOT / ".runtime")
        if self.path.exists():
            raise TraceError("A trace must not overwrite another run")
        self.sequence = 0
        self.lock = threading.Lock()

    def emit(self, event: str, **data) -> None:
        if event not in EVENTS or set(data) - FIELDS:
            raise TraceError("Unapproved audit fields")
        with self.lock:
            try:
                validate_local_path(self.path, ROOT / ".runtime")
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.sequence += 1
                record = {
                    "schema_version": 1, "task_id": self.task_id, "sequence": self.sequence,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "execution_kind": self.kind, "event": event,
                    "data": {key: scrub(value) for key, value in data.items()},
                }
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except (OSError, ValueError) as error:
                raise TraceError("تعذّر تسجيل التنفيذ بأمان؛ أُوقفت المهمة.") from None


def read_trace(path: Path) -> list[dict]:
    validate_local_path(path, ROOT / ".runtime")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if not records:
        raise TraceError("Empty trace")
    if not isinstance(records[0], dict) or records[0].get("event") != "run_started":
        raise TraceError("Missing run header")
    for index, record in enumerate(records, 1):
        if (not isinstance(record, dict) or not isinstance(record.get("data"), dict)
                or record.get("schema_version") != 1 or record.get("sequence") != index
                or not isinstance(record.get("task_id"), str)
                or record.get("task_id") != records[0].get("task_id")
                or record.get("execution_kind") != records[0].get("execution_kind")
                or record.get("execution_kind") not in {"cli", "streamlit", "offline_test", "public_tool_probe"}
                or record.get("event") not in EVENTS or set(record.get("data", {})) - FIELDS):
            raise TraceError("Invalid trace sequence or schema")
    return records


def export_trace(path: Path, label: str) -> Path:
    """Export genuine CLI evidence only; never promote offline fixtures."""
    records = read_trace(path)
    if records[0]["execution_kind"] != "cli" or records[-1]["event"] != "run_finished":
        raise TraceError("Only completed genuine CLI runs can be exported")
    finished = records[-1]["data"]
    success = finished.get("status") in {"success", "degraded"}
    has_model = any(record["event"] == "model_usage" for record in records)
    has_sources = any(record["event"] == "tool_result" and record["data"].get("source_count", 0) for record in records)
    recovered = any(record["event"] == "tool_error" for record in records)
    if label == "success_1":
        valid = success and has_model and has_sources and not recovered
    elif label == "near_failure_recovery":
        valid = success and has_model and has_sources and recovered
    elif label == "explicit_failure":
        valid = not success and finished.get("status") != "cancelled"
    else:
        valid = False
    if not valid:
        raise TraceError("This run does not satisfy the selected evidence label")
    target = ROOT / "traces" / f"{label}.jsonl"
    validate_local_path(target, ROOT / "traces")
    target.parent.mkdir(exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        for record in records:
            clean = dict(record, data={key: scrub(value) for key, value in record["data"].items()})
            handle.write(json.dumps(clean, ensure_ascii=False) + "\n")
    return target
