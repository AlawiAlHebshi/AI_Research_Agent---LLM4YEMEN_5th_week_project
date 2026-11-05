"""Limited real MCP search probe. Never loads .env or calls OpenAI."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcp_client import MCPClient, MCPError
from tracing import TraceWriter


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Free MCP connectivity and search; no OpenAI")
    parser.add_argument("--source", choices=["exa", "asta"], default="exa")
    parser.add_argument("--query", default="What is Model Context Protocol? official documentation")
    args = parser.parse_args()
    if not args.query.strip() or len(args.query) > 500:
        print("Query must contain 1-500 characters.")
        return 2
    trace = TraceWriter(kind="public_tool_probe")
    trace.emit("run_started", mode="web" if args.source == "exa" else "scientific")
    client = MCPClient(trace=trace)
    status, error, results = "error", None, []
    try:
        results = getattr(client, args.source + "_search")(args.query)
        if args.source == "asta":
            results = [paper.evidence() for paper in results if paper.abstract]
        status = "ok" if results else "empty"
        trace.emit("tool_result", tool=args.source, result_count=len(results), source_count=len(results),
                   sources=[row.get("href") or row.get("url") for row in results])
    except MCPError as failure:
        error = failure.code
        trace.emit("tool_error", tool=args.source, error_code=error)
    except Exception:
        error = "invalid_response"
        trace.emit("tool_error", tool=args.source, error_code=error)
    trace.emit("run_finished", status=status, source_count=len(results), public_requests=client.requests,
               bytes_received=client.bytes_received)
    print(json.dumps({"source": args.source, "status": status, "error_code": error,
        "result_count": len(results), "sources": [row.get("href") or row.get("url") for row in results],
        "public_requests": client.requests, "bytes_received": client.bytes_received,
        "openai_requests": 0, "trace": str(trace.path.relative_to(ROOT))}, ensure_ascii=False, indent=2))
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
