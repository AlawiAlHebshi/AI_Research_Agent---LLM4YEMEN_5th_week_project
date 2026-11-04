"""Three approved academic APIs; abstracts/metadata only, no PDF ingestion."""

from __future__ import annotations

import json
import os
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable

import requests

from research_models import PaperRecord, make_paper, reconstruct_abstract, same_paper
from safety import clean_text, safe_url
from tools import WebResearchContext

MAX_RESPONSE_BYTES = 1_000_000
_ARXIV_LOCK = threading.Lock()
_ARXIV_LAST_REQUEST = 0.0


class ResearchAPIError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ScientificClient:
    """Bounded, sequential public GET requests with one retry for transient errors."""

    def __init__(self, get: Callable | None = None, sleep: Callable = time.sleep, *, use_keys: bool = True, max_attempts: int = 2):
        if max_attempts not in {1, 2}:
            raise ValueError("Only one attempt and one optional retry are allowed")
        self.get = get or requests.get
        self.sleep = sleep
        self.use_keys = use_keys
        self.max_attempts = max_attempts
        self.requests = 0
        self.bytes_received = 0

    def _fetch(self, url, params, headers=None, *, arxiv=False) -> bytes:
        global _ARXIV_LAST_REQUEST
        headers = {"User-Agent": "LLM4YemenResearchAssistant/0.4 (abstract research)", **(headers or {})}
        for attempt in range(self.max_attempts):
            response = None
            try:
                if arxiv:
                    with _ARXIV_LOCK:
                        delay = max(0.0, 3 - (time.monotonic() - _ARXIV_LAST_REQUEST))
                        if delay:
                            self.sleep(delay)
                        _ARXIV_LAST_REQUEST = time.monotonic()
                self.requests += 1
                response = self.get(url, params=params, headers=headers, timeout=(5, 12), stream=True, allow_redirects=False)
                if response.status_code == 429:
                    raise ResearchAPIError("rate_limited")
                if response.status_code in {401, 403}:
                    raise ResearchAPIError("access_denied")
                if response.status_code >= 500:
                    if attempt + 1 < self.max_attempts:
                        try:
                            delay = min(2.0, max(0.5, float(response.headers.get("Retry-After", "0.5"))))
                        except ValueError:
                            delay = 0.5
                        self.sleep(delay)
                        continue
                    raise ResearchAPIError("service_unavailable")
                if not 200 <= response.status_code < 300:
                    raise ResearchAPIError("http_error")
                chunks, size = [], 0
                for chunk in response.iter_content(chunk_size=16384):
                    size += len(chunk)
                    self.bytes_received += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise ResearchAPIError("response_too_large")
                    chunks.append(chunk)
                return b"".join(chunks)
            except requests.Timeout:
                if attempt + 1 < self.max_attempts:
                    self.sleep(0.5)
                    continue
                raise ResearchAPIError("timeout") from None
            except requests.RequestException:
                raise ResearchAPIError("connection_failed") from None
            finally:
                if response is not None:
                    response.close()
        raise ResearchAPIError("service_unavailable")

    def _json(self, url, params, headers=None):
        try:
            value = json.loads(self._fetch(url, params, headers))
            if not isinstance(value, dict):
                raise ValueError("Invalid result")
            return value
        except (ValueError, UnicodeError):
            raise ResearchAPIError("invalid_response") from None

    def semantic_scholar(self, query: str) -> list[PaperRecord]:
        headers = {}
        if self.use_keys and os.environ.get("SEMANTIC_SCHOLAR_API_KEY"):
            headers["x-api-key"] = os.environ["SEMANTIC_SCHOLAR_API_KEY"]
        data = self._json("https://api.semanticscholar.org/graph/v1/paper/search", {
            "query": query, "limit": 5,
            "fields": "title,authors,year,abstract,url,externalIds,publicationTypes",
        }, headers)
        papers = []
        for row in data.get("data", [])[:5]:
            try:
                ids = row.get("externalIds") or {}
                publication_types = row.get("publicationTypes") or []
                publication_type = ", ".join(str(value) for value in publication_types) or "unknown"
                if ids.get("ArXiv"):
                    publication_type += "; arXiv version available; peer review not verified"
                papers.append(make_paper(title=row.get("title"), authors=[a.get("name", "") for a in (row.get("authors") or [])],
                    year=row.get("year"), abstract=row.get("abstract"), url=row.get("url"), database="semantic_scholar",
                    doi=ids.get("DOI"), arxiv_id=ids.get("ArXiv"),
                    publication_type=publication_type))
            except (ValueError, TypeError, AttributeError):
                continue
        return papers

    def openalex(self, query: str) -> list[PaperRecord]:
        params = {"search": query, "per-page": 5,
                  "select": "id,title,authorships,publication_year,abstract_inverted_index,doi,primary_location,type"}
        if self.use_keys and os.environ.get("OPENALEX_API_KEY"):
            params["api_key"] = os.environ["OPENALEX_API_KEY"]
        data = self._json("https://api.openalex.org/works", params)
        papers = []
        for row in data.get("results", [])[:5]:
            try:
                location = row.get("primary_location") or {}
                url = next((value for value in [location.get("landing_page_url"), row.get("doi"), row.get("id")] if safe_url(value)), None)
                papers.append(make_paper(title=row.get("title"), authors=[(a.get("author") or {}).get("display_name", "") for a in (row.get("authorships") or [])],
                    year=row.get("publication_year"), abstract=reconstruct_abstract(row.get("abstract_inverted_index")),
                    url=url, database="openalex",
                    doi=row.get("doi"), publication_type=str(row.get("type") or "unknown")))
            except (ValueError, TypeError, AttributeError):
                continue
        return papers

    def arxiv(self, query: str) -> list[PaperRecord]:
        content = self._fetch("https://export.arxiv.org/api/query", {
            "search_query": "all:" + query, "start": 0, "max_results": 5,
        }, arxiv=True)
        if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
            raise ResearchAPIError("unsafe_xml")
        try:
            content = content.decode("utf-8-sig")
            root = ET.fromstring(content)
            ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
            papers = []
            for row in root.findall("a:entry", ns)[:5]:
                if row.findtext("a:title", "", ns).casefold() == "error":
                    raise ResearchAPIError("invalid_query")
                try:
                    url = row.findtext("a:id", "", ns)
                    papers.append(make_paper(title=" ".join(row.findtext("a:title", "", ns).split()),
                        authors=[a.findtext("a:name", "", ns) for a in row.findall("a:author", ns)],
                        year=int(row.findtext("a:published", "", ns)[:4]), abstract=row.findtext("a:summary", "", ns),
                        url=url, database="arxiv", doi=row.findtext("x:doi", None, ns), arxiv_id=url,
                        publication_type="preprint; publication status not verified"))
                except (ValueError, TypeError):
                    continue
            return papers
        except (ET.ParseError, UnicodeError):
            raise ResearchAPIError("invalid_response") from None


@dataclass
class ScientificResearchContext(WebResearchContext):
    mode: str = "scientific"
    client: ScientificClient = field(default_factory=ScientificClient)
    papers: dict[str, PaperRecord] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    scientific_cache: dict[tuple[str, str], dict] = field(default_factory=dict)

    def _scientific_lookup(self, name: str, query: str, backend: Callable) -> dict:
        self.calls.append(name)
        self.trace.emit("tool_started", tool=name)
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            self.trace.emit("tool_error", tool=name, error_code="invalid_query")
            return {"status": "error", "error_code": "invalid_query"}
        query = clean_text(query, 500)
        key = (name, query.casefold().strip())
        if key in self.scientific_cache:
            self.trace.emit("tool_cache_hit", tool=name, cache_hit=True)
            return self.scientific_cache[key]
        try:
            records = backend(query)
            results = []
            for paper in records[:5]:
                existing = next((item for item in self.papers.values() if same_paper(item, paper)), None)
                if existing:
                    self.aliases[paper.url] = existing.url
                    if not existing.abstract and paper.abstract:
                        existing.abstract = paper.abstract
                        existing.abstract_truncated = paper.abstract_truncated
                    selected = existing
                elif len(self.papers) < 10:
                    self.papers[paper.url] = paper
                    selected = paper
                else:
                    replace = next((url for url, item in self.papers.items() if not item.abstract), None)
                    if not paper.abstract or replace is None:
                        continue
                    self.papers.pop(replace)
                    self.papers[paper.url] = paper
                    selected = paper
                if selected.abstract:
                    self.sources[selected.url] = {"title": selected.title, "url": selected.url}
                results.append(selected.evidence())
            result = {"status": "ok" if results else "empty", "untrusted_data": True, "results": results}
            if not results:
                self.errors.append(name + ": لا نتائج متاحة")
            self.trace.emit("tool_result", tool=name, result_count=len(results), source_count=len(self.sources),
                            sources=list(self.sources), public_requests=self.client.requests, bytes_received=self.client.bytes_received)
        except ResearchAPIError as error:
            self.errors.append(name + ": " + error.code)
            self.trace.emit("tool_error", tool=name, error_code=error.code)
            result = {"status": "error", "error_code": error.code,
                      "message": "Try another approved academic source; do not invent evidence."}
        except Exception:
            self.errors.append(name + ": invalid_response")
            self.trace.emit("tool_error", tool=name, error_code="invalid_response")
            result = {"status": "error", "error_code": "invalid_response"}
        self.scientific_cache[key] = result
        return result

    def search_semantic_scholar(self, query: str) -> dict:
        """Search scientific metadata/abstracts; on 429 use OpenAlex once."""
        result = self._scientific_lookup("search_semantic_scholar", query, self.client.semantic_scholar)
        if result.get("error_code") == "rate_limited":
            self.trace.emit("recovery_started", tool="search_openalex", reason="semantic_scholar_429")
            fallback = self.search_openalex(query)
            return {**result, "fallback": fallback, "message": "Semantic Scholar rate-limited; OpenAlex fallback attempted."}
        return result

    def search_openalex(self, query: str) -> dict:
        """Search OpenAlex metadata and available abstracts only."""
        return self._scientific_lookup("search_openalex", query, self.client.openalex)

    def search_arxiv(self, query: str) -> dict:
        """Search arXiv abstracts/metadata only; never download papers or PDFs."""
        return self._scientific_lookup("search_arxiv", query, self.client.arxiv)
