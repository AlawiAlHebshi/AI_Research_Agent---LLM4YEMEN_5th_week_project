"""Small real public-API probe: no .env, API keys, OpenAI or PDF downloads."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scientific_tools import ScientificClient, ScientificResearchContext
from tracing import TraceWriter
from mcp_client import MCPClient


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Public academic tools only; no OpenAI charges")
    parser.add_argument("--source", choices=["all", "semantic_scholar", "openalex", "arxiv"], default="all")
    parser.add_argument("--query", default="retrieval augmented generation education")
    args = parser.parse_args()
    if not args.query.strip() or len(args.query) > 500:
        print("Query must contain 1-500 characters.")
        return 2
    trace = TraceWriter(kind="public_tool_probe")
    trace.emit("run_started", mode="scientific")
    client = ScientificClient(use_keys=False, max_attempts=1)
    context = ScientificResearchContext(client=client, trace=trace, mcp=MCPClient(use_keys=False))
    names = ["semantic_scholar", "openalex", "arxiv"] if args.source == "all" else [args.source]
    for name in names:
        result = getattr(context, "search_" + name)(args.query)
        print(json.dumps({"source": name, "status": result["status"], "error_code": result.get("error_code"),
                          "papers_with_abstracts_so_far": len(context.sources)}, ensure_ascii=False), flush=True)
    trace.emit("run_finished", status="public_tools_checked", source_count=len(context.sources),
               public_requests=client.requests, bytes_received=client.bytes_received)
    print(json.dumps({"openai_requests": 0, "public_requests": client.requests, "bytes_received": client.bytes_received,
                      "trace": str(trace.path.relative_to(ROOT))}, ensure_ascii=False))
    return 0 if context.sources else 1


if __name__ == "__main__":
    raise SystemExit(main())
