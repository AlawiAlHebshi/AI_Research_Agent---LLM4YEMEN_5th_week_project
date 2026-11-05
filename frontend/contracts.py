"""Presentation contracts for a future, explicitly approved backend adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

Mode = Literal["web", "scientific"]
Scenario = Literal["success", "partial", "error"]
MODE_LABELS = {"web": "البحث في الويب", "scientific": "البحث العلمي"}


@dataclass(frozen=True)
class ResearchRequest:
    query: str
    mode: Mode

    def __post_init__(self):
        if self.mode not in MODE_LABELS:
            raise ValueError("اختر نمط بحث صالحًا.")
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("اكتب سؤالًا أولًا لنجرّب الواجهة.")
        if len(self.query) > 2000:
            raise ValueError("السؤال أطول من 2000 حرف. اختصره ثم حاول مجددًا.")


@dataclass(frozen=True)
class Source:
    title: str
    url: str
    description: str

    def __post_init__(self):
        parsed = urlsplit(self.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Invalid source URL")


@dataclass(frozen=True)
class Progress:
    label: str
    fraction: float


@dataclass(frozen=True)
class ResearchResult:
    """Four familiar result fields, plus explicit frontend demo metadata.

    A future gateway maps the backend's sources URLs into Source display items.
    This demo type cannot be constructed as a real research execution.
    """

    topic: str
    summary: str
    sources: tuple[Source, ...]
    tools_used: tuple[str, ...]
    request: ResearchRequest
    status: Literal["success", "partial"] = "success"
    id: str = field(default_factory=lambda: "demo_" + uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_demo: Literal[True] = field(default=True, init=False)


class ResearchGateway(Protocol):
    """UI boundary only. No live gateway is implemented or configured."""

    def research(self, request: ResearchRequest, on_progress: Callable[[Progress], None],
                 *, scenario: Scenario = "success") -> ResearchResult: ...


def export_report(result: ResearchResult, language: str = "ar") -> str:
    """Build a download in memory; this function never writes a file."""
    sources = "\n".join(f"[{i}] {item.title}\n{item.url}" for i, item in enumerate(result.sources, 1))
    if language == "en":
        return (
            "DEMO ONLY — UI preview, not real research\n"
            "No OpenAI or MCP calls were made. References and tools are illustrative only.\n\n"
            f"Demo mode: {'Web Research' if result.request.mode == 'web' else 'Scientific Research'}\n"
            f"Your question in this demo: {result.request.query}\n"
            f"Fixed example topic (not a generated answer): {result.topic}\n\n"
            f"{result.summary}\n\nIllustrative references:\n{sources}\n\n"
            f"Tools represented only: {', '.join(result.tools_used)}\n"
            "This demo is not scientific evidence or a genuine execution record.\n"
        )
    return (
        "DEMO ONLY — نموذج عرض تجريبي، وليس بحثًا حقيقيًا\n"
        "لم يُستدعَ OpenAI أو MCP. المصادر والأدوات أمثلة توضيحية لم تُسترجع أو تُشغّل.\n\n"
        f"نمط العرض: {MODE_LABELS[result.request.mode]}\n"
        f"السؤال المكتوب في العرض: {result.request.query}\n"
        f"موضوع العينة الثابتة (ليست إجابة مولدة عن السؤال): {result.topic}\n\n"
        f"{result.summary}\n\nالمراجع التوضيحية:\n{sources}\n\n"
        f"أدوات ممثلة فقط: {', '.join(result.tools_used)}\n"
        "هذه النسخة لا تصلح كمصدر علمي أو دليل تنفيذ حقيقي.\n"
    )
