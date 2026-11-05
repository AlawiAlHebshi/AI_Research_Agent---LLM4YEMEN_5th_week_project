"""Validate public individual-run evidence; optionally compare private originals. No APIs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tracing import read_trace, scrub

EXPECTED = {
    "success_1": "46c433f92cc74827a77a5cddb3a26e6a",
    "near_failure_recovery": "d30d284e0f1341b18c34dea318dc1d8c",
    "explicit_failure": "70d4c78c3b6b44b693f687d892df45d1",
}


def verify(label: str) -> dict:
    path = ROOT / "traces" / (label + ".jsonl")
    # read_trace deliberately requires private paths; validate the public copy here.
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if not records or records[0]["event"] != "run_started" or records[-1]["event"] != "run_finished":
        raise ValueError("Incomplete run")
    task_id = EXPECTED[label]
    from tracing import EVENTS, FIELDS
    for number, record in enumerate(records, 1):
        if (record.get("task_id") != task_id or record.get("sequence") != number
                or record.get("execution_kind") != "cli" or record.get("schema_version") != 1
                or record.get("event") not in EVENTS or set(record.get("data", {})) - FIELDS):
            raise ValueError("Invalid event schema or identity")
    finish = records[-1]["data"]
    usage = [row["data"] for row in records if row["event"] == "model_usage"]
    reserved = [row["data"] for row in records if row["event"] == "model_reserved"]
    if finish["calls"] != len(reserved) or len({row["reservation_id"] for row in reserved}) != len(reserved):
        raise ValueError("Invalid call accounting")
    for field in ["input_tokens", "output_tokens", "cost_nanos"]:
        if sum(row[field] for row in usage) != finish[field]:
            raise ValueError("Usage totals do not match")
    if (finish["reserved_nanos"] != 0 or len(usage) != len(reserved)
            or {row["reservation_id"] for row in usage} != {row["reservation_id"] for row in reserved}
            or any(row["max_output_tokens"] != 1200 for row in reserved)):
        raise ValueError("Unsettled or inconsistent accounting")
    research = next(row["data"] for row in reversed(records) if row["event"] == "research_finished")
    errors = [index for index, row in enumerate(records) if row["event"] == "tool_error"]
    recovered = any(
        any(index < position for index in errors)
        and any(later["event"] == "tool_result" and later["data"].get("tool") == row["data"].get("tool")
                and later["data"].get("result_count", 0) > 0 for later in records[position + 1:])
        for position, row in enumerate(records) if row["event"] == "recovery_started")
    if label == "success_1" and not (finish["status"] == "success" and not errors and research["source_count"] >= 2):
        raise ValueError("Not clean research success")
    if label == "near_failure_recovery" and not (finish["status"] in {"success", "degraded"} and recovered and research["source_count"] >= 2):
        raise ValueError("No meaningful recovery sequence")
    if label == "explicit_failure" and not (finish["status"] == "no_evidence" and errors and research["source_count"] == 0):
        raise ValueError("Not the selected meaningful failure")
    original_path = ROOT / ".runtime" / "traces" / (task_id + ".jsonl")
    original_match = None
    if original_path.exists():
        original = read_trace(original_path)
        expected = [dict(row, data={key: scrub(value) for key, value in row["data"].items()}) for row in original]
        original_match = records == expected
        if not original_match:
            raise ValueError("Export differs from the complete original run")
    return {"file": path.relative_to(ROOT).as_posix(), "task_id": task_id, "event_count": len(records),
            "status": finish["status"], "calls": finish["calls"], "input_tokens": finish["input_tokens"],
            "output_tokens": finish["output_tokens"], "cost_nanos": finish["cost_nanos"],
            "historical_natural_run": True, "private_original_match": original_match,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> int:
    try:
        results = [verify(label) for label in EXPECTED]
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        print("FAIL: submission traces are missing, malformed, or inconsistent; no raw data printed.")
        return 1
    print(json.dumps({"status": "PASS", "traces": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
