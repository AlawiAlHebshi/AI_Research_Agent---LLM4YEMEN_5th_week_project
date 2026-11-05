"""Separate presentation contracts for demo fixtures and validated backend results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal, Protocol
from uuid import uuid4
from safety import safe_url

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
        if safe_url(self.url) != self.url:
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
    """Connected UI boundary; demo fixtures use their separate offline gateway."""

    def research(self, request: ResearchRequest, on_progress: Callable[[Progress], None],
                 *, request_id: str) -> BackendResult: ...


@dataclass(frozen=True)
class BackendResult:
    """Validated engine output or a clearly labelled historical SQLite snapshot."""

    topic: str
    summary: str
    sources: tuple[Source, ...]
    tools_used: tuple[str, ...]
    request: ResearchRequest
    status: Literal["success", "degraded"]
    id: str
    created_at: str
    report: str
    historical: bool = False
    memory_status: str = "saved"
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_nanos: int = 0
    reserved_nanos: int = 0
    is_demo: Literal[False] = field(default=False, init=False)


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
