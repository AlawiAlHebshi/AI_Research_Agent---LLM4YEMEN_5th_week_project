"""Fail-closed Community Cloud policy; ephemeral files are not durable spending controls."""

import os
from functools import lru_cache

from mcp_client import MCPClient, MCPError
from tracing import TraceWriter


def local_runtime() -> bool:
    """Only an explicitly configured local launcher may use the file-based budget."""
    return os.environ.get("AI_RESEARCH_RUNTIME", "cloud") == "local"


def initialize_secrets(secret_store) -> bool:
    """Trigger Streamlit's standard root-secret environment export; return presence only."""
    try:
        return "OPENAI_API_KEY" in secret_store
    except (FileNotFoundError, KeyError, RuntimeError):
        return False


@lru_cache(maxsize=1)
def free_exa_probe() -> dict:
    """One fixed anonymous MCP search per process, enabled only by operator configuration."""
    trace = TraceWriter(kind="public_tool_probe")
    client = MCPClient(use_keys=False, trace=trace)
    status, count, error = "error", 0, None
    trace.emit("run_started", mode="web", reason="cloud_free_mcp_check")
    try:
        rows = client.exa_search("Model Context Protocol official documentation")
        count = len(rows)
        status = "ok" if count else "empty"
        trace.emit("tool_result", tool="exa_search", result_count=count, source_count=count,
                   sources=[row["href"] for row in rows])
    except MCPError as failure:
        error = failure.code
        trace.emit("tool_error", tool="exa_search", error_code=error)
    except Exception:
        error = "probe_unavailable"
    finally:
        trace.emit("run_finished", status=status, calls=0, cost_nanos=0,
                   public_requests=client.requests, result_count=count)
    return {"provider": "Exa MCP", "status": status, "result_count": count,
            "error_code": error, "openai_requests": 0}


def cloud_probe_enabled() -> bool:
    return not local_runtime() and os.environ.get("CLOUD_MCP_CHECK", "").casefold() == "true"
