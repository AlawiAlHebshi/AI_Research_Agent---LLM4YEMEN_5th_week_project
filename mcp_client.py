"""Small synchronous, read-only MCP Streamable HTTP client for two fixed services.

No SDK download, background agent, local file access, or OpenAI calls. Only the
2025 initialize/tools subset is supported; unsupported protocols fail closed.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Callable

import requests

from research_models import make_paper
from safety import clean_text, safe_url
from tracing import NullTrace

ENDPOINTS = {
    "exa": "https://mcp.exa.ai/mcp?tools=web_search_advanced_exa",
    "asta": "https://asta-tools.allen.ai/mcp/v1",
}
TOOLS = {"exa": "web_search_advanced_exa", "asta": "search_papers_by_relevance"}
PROTOCOLS = {"2025-03-26", "2025-06-18", "2025-11-25"}
MAX_BYTES = 1_000_000


class MCPError(RuntimeError):
    """A safe fixed error code; never retain a provider's raw message."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class MCPClient:
    """One bounded session per search, with no retries or server-initiated work."""

    def __init__(self, post: Callable | None = None, *, trace=None, use_keys: bool = True):
        self.post = post
        self.trace = trace or NullTrace()
        self.use_keys = use_keys
        self.requests = 0
        self.bytes_received = 0
        self.searches = 0
        self._id = 0

    @property
    def asta_available(self) -> bool:
        return self.use_keys and bool(os.environ.get("ASTA_TOOL_KEY"))

    def _response(self, response, request_id: int | None) -> dict:
        """Read bounded JSON or SSE, ignoring notifications, never executing them."""
        status = response.status_code
        if status in {401, 403}:
            raise MCPError("access_denied")
        if status == 429:
            raise MCPError("rate_limited")
        if status >= 500:
            raise MCPError("service_unavailable")
        if not 200 <= status < 300:
            raise MCPError("http_error")
        if request_id is None and status in {200, 202, 204}:
            return {}
        media = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if media not in {"application/json", "text/event-stream"}:
            raise MCPError("unsupported_content_type")
        total, buffer, data = 0, b"", []
        started = time.monotonic()

        def match(raw):
            try:
                messages = json.loads(raw)
            except (ValueError, UnicodeError):
                raise MCPError("invalid_response") from None
            for message in messages if isinstance(messages, list) else [messages]:
                if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                    raise MCPError("invalid_response")
                if "method" in message:
                    if "id" in message:
                        raise MCPError("server_request_denied")
                    continue
                if message.get("id") != request_id:
                    raise MCPError("response_id_mismatch")
                if "error" in message:
                    raise MCPError("rpc_error")
                result = message.get("result")
                if not isinstance(result, dict):
                    raise MCPError("invalid_response")
                return result
            return None

        for chunk in response.iter_content(chunk_size=1024):
            total += len(chunk)
            self.bytes_received += len(chunk)
            if total > MAX_BYTES:
                raise MCPError("response_too_large")
            if time.monotonic() - started > 25:
                raise MCPError("timeout")
            buffer += chunk
            if media == "text/event-stream":
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.rstrip(b"\r")
                    if line.startswith(b"data:"):
                        data.append(line[5:].lstrip(b" "))
                    elif not line and data:
                        found = match(b"\n".join(data))
                        data = []
                        if found is not None:
                            return found
        if media == "application/json":
            found = match(buffer)
            if found is not None:
                return found
        raise MCPError("incomplete_response")

    def call(self, provider: str, arguments: dict) -> dict:
        if provider not in ENDPOINTS:
            raise MCPError("provider_denied")
        if self.searches >= 10:
            raise MCPError("mcp_search_limit")
        if provider == "asta" and not self.asta_available:
            raise MCPError("asta_key_missing")
        self.searches += 1
        headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if provider == "asta":
            headers["x-api-key"] = os.environ["ASTA_TOOL_KEY"]
        # Exa is deliberately anonymous: never use an account/key or paid agent.
        with requests.Session() as session:
            # No implicit .netrc credentials, cookies from browsers, or env proxies.
            session.trust_env = False
            send = self.post or session.post

            def rpc(method, params=None, *, notification=False):
                self._id += 1
                payload = {"jsonrpc": "2.0", "method": method}
                if not notification:
                    payload["id"] = self._id
                if params is not None:
                    payload["params"] = params
                response = None
                self.requests += 1
                try:
                    response = send(ENDPOINTS[provider], json=payload, headers=dict(headers),
                                    timeout=(5, 15), stream=True, allow_redirects=False)
                    result = self._response(response, payload.get("id"))
                    sid = response.headers.get("Mcp-Session-Id")
                    if sid:
                        if len(sid) > 512 or not re.fullmatch(r"[\x21-\x7e]+", sid):
                            raise MCPError("invalid_session")
                        headers["Mcp-Session-Id"] = sid
                    return result
                finally:
                    if response is not None:
                        response.close()

            try:
                result = rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                    "clientInfo": {"name": "LLM4YemenResearchAssistant", "version": "0.5"}})
                version = result.get("protocolVersion")
                if version not in PROTOCOLS:
                    raise MCPError("unsupported_protocol")
                headers["MCP-Protocol-Version"] = version
                rpc("notifications/initialized", notification=True)
                discovery = rpc("tools/list", {})
                listed = discovery.get("tools")
                if not isinstance(listed, list) or not any(
                        isinstance(tool, dict) and tool.get("name") == TOOLS[provider] for tool in listed):
                    raise MCPError("required_tool_missing")
                self.trace.emit("mcp_connected", tool=provider, status="ok", public_requests=self.requests)
                result = rpc("tools/call", {"name": TOOLS[provider], "arguments": arguments})
                if result.get("isError"):
                    raise MCPError("remote_tool_error")
                return result
            except requests.Timeout:
                raise MCPError("timeout") from None
            except requests.RequestException:
                raise MCPError("connection_failed") from None
            finally:
                self.trace.emit("mcp_usage", tool=provider, public_requests=self.requests,
                                bytes_received=self.bytes_received)

    def exa_search(self, query: str) -> list[dict]:
        query = checked_query(query)
        result = self.call("exa", {"query": query, "numResults": 5,
                                   "enableHighlights": True, "enableSummary": False})
        structured = result.get("structuredContent")
        rows = structured.get("results") if isinstance(structured, dict) else None
        if rows is None:
            # Advanced search returns JSON inside MCP text content. Never infer
            # source records from Title/URL-like lines inside untrusted prose.
            rows = []
            for block in text_blocks(result):
                try:
                    value = json.loads(block)
                except ValueError:
                    raise MCPError("invalid_response") from None
                if not isinstance(value, dict) or not isinstance(value.get("results"), list):
                    raise MCPError("invalid_response")
                rows.extend(value["results"][:5])
        if not isinstance(rows, list):
            raise MCPError("invalid_response")
        output = []
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            url = safe_url(row.get("url", ""))
            highlights = row.get("highlights")
            text = "\n".join(item for item in highlights[:5] if isinstance(item, str)) if isinstance(highlights, list) else row.get("text")
            if url and isinstance(text, str) and text.strip():
                output.append({"title": clean_text(str(row.get("title", "")), 250),
                               "href": url, "body": clean_text(text, 2500)})
        return output

    def asta_search(self, query: str) -> list:
        result = self.call("asta", {"keyword": checked_query(query), "limit": 5,
            "fields": "title,authors,year,abstract,url,publicationDate,venue"})
        structured = result.get("structuredContent")
        values = [structured] if structured is not None else []
        if not values:
            for block in text_blocks(result):
                try:
                    values.append(json.loads(block))
                except ValueError:
                    raise MCPError("invalid_response") from None
        rows = []
        for value in values:
            if isinstance(value, dict) and "data" in value:
                value = value["data"]
            if isinstance(value, dict) and "papers" in value:
                value = value["papers"]
            rows.extend(value if isinstance(value, list) else [value])
        papers = []
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            try:
                ids = row.get("externalIds") or {}
                papers.append(make_paper(title=row.get("title"),
                    authors=[author.get("name", "") for author in (row.get("authors") or [])],
                    year=row.get("year"), abstract=row.get("abstract"), url=row.get("url"),
                    database="asta", doi=ids.get("DOI"), arxiv_id=ids.get("ArXiv"),
                    publication_type="unknown; peer review not verified"))
            except (ValueError, TypeError, AttributeError):
                continue
        return papers


def checked_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        raise MCPError("invalid_query")
    return clean_text(query, 500).strip()


def text_blocks(result: dict) -> list[str]:
    content = result.get("content", [])
    if not isinstance(content, list):
        raise MCPError("invalid_response")
    return [item["text"] for item in content[:10] if isinstance(item, dict)
            and item.get("type") == "text" and isinstance(item.get("text"), str)]
