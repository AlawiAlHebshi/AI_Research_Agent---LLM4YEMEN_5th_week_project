"""Approved web and report tools; no import-time network or writes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from langchain_core.tools import StructuredTool

from safety import clean_text, safe_url, validate_local_path
from tracing import NullTrace
from mcp_client import MCPClient, MCPError

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)
EXA_DEFAULT = True  # Final JSON search variant passed its free live probe on 2026-11-05.


def public_search(query: str) -> list[dict[str, Any]]:
    """DuckDuckGo only, with a finite timeout and result limit."""
    from ddgs import DDGS

    return DDGS(timeout=10).text(query, backend="duckduckgo", max_results=5)


def encyclopedia_search(query: str) -> list[dict[str, str]]:
    """Fetch public Wikipedia extracts and URLs with an HTTP timeout."""
    import requests

    response = requests.get(
        "https://ar.wikipedia.org/w/api.php" if re.search(r"[\u0600-\u06ff]", query) else "https://en.wikipedia.org/w/api.php",
        params={"action": "query", "format": "json", "generator": "search",
                "gsrsearch": query, "gsrlimit": 2, "prop": "extracts|info",
                "exintro": 1, "explaintext": 1, "exchars": 2500, "inprop": "url"},
        headers={"User-Agent": "LLM4YemenResearchAssistant/0.2 (educational CLI)"},
        timeout=(5, 10),
    )
    response.raise_for_status()
    if len(response.content) > 1_000_000:
        raise ValueError("Wikipedia response exceeds limit")
    return [
        {"title": page.get("title", ""), "body": page.get("extract", ""),
         "href": page.get("fullurl", "")}
        for page in response.json().get("query", {}).get("pages", {}).values()
    ]


@dataclass
class WebResearchContext:
    """Per-task evidence and host-controlled save permission."""

    search_backend: Callable = public_search
    wiki_backend: Callable = encyclopedia_search
    confirm: Callable[[str], str] = input
    display: Callable[[str], None] = print
    reports_dir: Path = ROOT / "reports"
    sources: dict[str, dict[str, str]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    attempted: set[tuple[str, str]] = field(default_factory=set)
    requested_filename: str | None = None
    final_content: str | None = None
    mode: str = "web"
    trace: Any = field(default_factory=NullTrace)
    use_exa: bool = EXA_DEFAULT
    mcp: MCPClient = field(default_factory=MCPClient)
    previous_research: list[dict[str, Any]] = field(default_factory=list)

    def _lookup(self, name: str, query: str, backend: Callable) -> dict[str, Any]:
        self.calls.append(name)
        self.trace.emit("tool_started", tool=name)
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            self.trace.emit("tool_error", tool=name, error_code="invalid_query")
            return {"status": "error", "error_code": "invalid_query", "message": "Query must contain 1–500 characters."}
        query = clean_text(query, 500)
        key = (name, query.casefold())
        if key in self.attempted:
            self.trace.emit("tool_error", tool=name, error_code="duplicate_query_blocked")
            return {"status": "error", "error_code": "duplicate_query_blocked", "message": "Already attempted; use another query or source."}
        self.attempted.add(key)
        try:
            rows = backend(query)
            results = []
            for row in rows[:5]:
                url = safe_url(row.get("href") or row.get("url") or "")
                snippet = clean_text(str(row.get("body") or row.get("snippet") or ""), 2500)
                if not url or not snippet:
                    continue
                record = {"title": clean_text(str(row.get("title", "")), 250),
                          "snippet": snippet, "url": url}
                self.sources[url] = record
                results.append(record)
            if not results:
                self.errors.append(name + ": لا نتائج قابلة للاستشهاد")
            self.trace.emit("tool_result", tool=name, result_count=len(results),
                            source_count=len(self.sources), sources=list(self.sources))
            return {"status": "ok" if results else "empty", "untrusted_data": True,
                    "results": results}
        except Exception as error:
            LOGGER.warning("Public search failed: %s (%s)", name, type(error).__name__)
            code = error.code if isinstance(error, MCPError) else "public_search_failed"
            self.errors.append(name + ": " + code)
            self.trace.emit("tool_error", tool=name, error_code=code)
            return {"status": "error", "error_code": code,
                    "message": "Public search failed; try the other web source."}

    def exa_search(self, query: str) -> dict[str, Any]:
        """Primary web search through free Exa MCP; DuckDuckGo is a bounded fallback."""
        self.mcp.trace = self.trace
        result = self._lookup("exa_search", query, self.mcp.exa_search)
        if result.get("status") in {"error", "empty"} and result.get("error_code") not in {"invalid_query", "duplicate_query_blocked"}:
            self.trace.emit("recovery_started", tool="duckduckgo_search", reason="exa_unavailable")
            return {**result, "fallback": self.duckduckgo_search(query),
                    "message": "Exa unavailable; DuckDuckGo fallback attempted. Wikipedia remains available."}
        return result

    def duckduckgo_search(self, query: str) -> dict[str, Any]:
        """Return DuckDuckGo titles, snippets and URLs as untrusted evidence."""
        return self._lookup("duckduckgo_search", query, self.search_backend)

    def wikipedia_lookup(self, query: str) -> dict[str, Any]:
        """Return Wikipedia extracts and article URLs as untrusted evidence."""
        return self._lookup("wikipedia_lookup", query, self.wiki_backend)

    def validate_filename(self, filename: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\.txt", filename):
            raise ValueError("Invalid report filename")
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        if filename[:-4].upper() in reserved:
            raise ValueError("Reserved report filename")
        validate_local_path(self.reports_dir, ROOT / "reports")

    def save_report_to_disk(self, content: str, filename: str = "research_report.txt") -> dict[str, str]:
        """Queue during research; save the validated report after human confirmation."""
        self.calls.append("save_report_to_disk")
        try:
            self.validate_filename(filename)
            self.trace.emit("save_requested", filename=filename)
            if self.final_content is None:
                self.requested_filename = filename
                return {"status": "pending", "message": "Queued; a human must confirm after the validated final answer."}
            content = self.final_content
            self.display("\nالتقرير المراد حفظه:\n" + content)
            answer = self.confirm(f"هل توافق على حفظ التقرير داخل reports باسم مشتق من {filename}؟ [y/n] ")
            if answer.strip().casefold() not in {"y", "yes", "نعم"}:
                self.trace.emit("save_decision", decision="declined", filename=filename)
                return {"status": "declined", "message": "رُفض الحفظ؛ لم يُنشأ ملف."}
            self.trace.emit("save_decision", decision="approved", filename=filename)
            self.validate_filename(filename)
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            target = self.reports_dir / f"{filename[:-4]}_{stamp}_{uuid4().hex[:8]}.txt"
            validate_local_path(target, ROOT / "reports")
            with target.open("x", encoding="utf-8") as handle:
                handle.write(f"--- Research Output ---\nTimestamp: {stamp}\n\n{content}\n")
            self.trace.emit("save_result", status="saved", filename=target.name)
            return {"status": "saved", "filename": target.name, "message": "حُفظ التقرير بعد موافقتك."}
        except (EOFError, KeyboardInterrupt):
            self.trace.emit("save_decision", decision="cancelled")
            return {"status": "declined", "message": "أُلغي التأكيد؛ لم يُحفظ تقرير."}
        except Exception as error:
            LOGGER.warning("Report not saved (%s)", type(error).__name__)
            self.trace.emit("save_result", status="error", error_code="save_failed")
            return {"status": "error", "message": "تعذّر تأكيد الحفظ؛ تحقق من reports قبل إعادة المحاولة."}


def build_tools(context: WebResearchContext) -> list[StructuredTool]:
    if context.mode == "scientific":
        functions = (context.search_semantic_scholar, context.search_openalex, context.search_arxiv,
                     context.save_report_to_disk)
        if context.asta_available:
            functions = (context.search_asta, *functions)
    elif context.mode == "web":
        functions = (context.duckduckgo_search, context.wikipedia_lookup, context.save_report_to_disk)
        if context.use_exa:
            functions = (context.exa_search, *functions)
    else:
        raise ValueError("Invalid research mode")
    return [StructuredTool.from_function(func) for func in functions]

