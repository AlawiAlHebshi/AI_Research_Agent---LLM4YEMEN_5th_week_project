"""Bounded SQLite research snapshots. Stored content is untrusted, never fresh evidence."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from safety import clean_text, safe_url, validate_local_path

ROOT = Path(__file__).resolve().parent
MEMORY_ROOT = ROOT / ".runtime"
DEFAULT_PATH = MEMORY_ROOT / "memory" / "research.sqlite3"
APPLICATION_ID = 0x4152524D
MAX_RESULTS = 10


class MemoryError(RuntimeError):
    """Fixed, non-sensitive storage error code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=500)
    authors: list[str] = Field(default_factory=list, max_length=20)
    year: int | None = Field(default=None, ge=1000, le=2100)
    doi: str | None = Field(default=None, max_length=500)
    arxiv_id: str | None = Field(default=None, max_length=100)
    publication_type: str = Field(default="unknown", max_length=300)

    @field_validator("url")
    @classmethod
    def public_reference(cls, value: str) -> str:
        if safe_url(value) != value:
            raise ValueError("Invalid reference")
        sensitive = {"key", "api_key", "apikey", "token", "access_token", "auth", "password",
                     "secret", "signature", "x-amz-signature"}
        if any(key.casefold() in sensitive for key, _ in parse_qsl(urlsplit(value).query)):
            raise ValueError("Credential-bearing reference")
        return value

    @field_validator("title", "doi", "arxiv_id", "publication_type")
    @classmethod
    def redact_metadata(cls, value: str | None) -> str | None:
        return clean_text(value, len(value)) if value is not None else None

    @field_validator("authors")
    @classmethod
    def redact_authors(cls, values: list[str]) -> list[str]:
        if any(len(value) > 150 for value in values):
            raise ValueError("Invalid author")
        return [clean_text(value, 150) for value in values]


class ResearchRecord(BaseModel):
    """A historical validated snapshot, not authority to reuse citations in a new task."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    task_id: str = Field(min_length=1, max_length=36)
    owner_id: str = Field(default="local", pattern=r"^[A-Za-z0-9_-]{1,80}$")
    question: str = Field(min_length=1, max_length=2000)
    topic: str = Field(min_length=1, max_length=500)
    mode: str
    summary: str = Field(min_length=1, max_length=16000)
    sources: list[SourceReference] = Field(min_length=1, max_length=20)
    status: str
    tools_used: list[str] = Field(default_factory=list, max_length=30)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("task_id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        return UUID(value).hex

    @field_validator("mode")
    @classmethod
    def valid_mode(cls, value: str) -> str:
        if value not in {"web", "scientific"}:
            raise ValueError("Invalid mode")
        return value

    @field_validator("status")
    @classmethod
    def completed_status(cls, value: str) -> str:
        if value not in {"success", "degraded"}:
            raise ValueError("Not validated research")
        return value

    @field_validator("question", "topic", "summary")
    @classmethod
    def safe_text(cls, value: str) -> str:
        value = clean_text(value, len(value)).strip()
        if not value:
            raise ValueError("Empty research text")
        return value

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value: str) -> str:
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is None:
            raise ValueError("Timezone required")
        return timestamp.astimezone(timezone.utc).isoformat()

    @field_validator("sources")
    @classmethod
    def unique_sources(cls, values: list[SourceReference]) -> list[SourceReference]:
        if len({value.url for value in values}) != len(values):
            raise ValueError("Duplicate references")
        return values

    @field_validator("tools_used")
    @classmethod
    def safe_tool_names(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[a-z_]{1,60}", value) for value in values):
            raise ValueError("Invalid tool name")
        return values


def validated_record(task_id: str, question: str, response: Any, context: Any,
                     status: str, owner_id: str = "local") -> ResearchRecord:
    """Called by the host only after its existing validation has succeeded."""
    try:
        if response is None or not response.sources or any(url not in context.sources for url in response.sources):
            raise ValueError("Missing provenance")
        references = []
        for url in response.sources:
            paper = getattr(context, "papers", {}).get(url)
            if paper is not None:
                if not paper.abstract:
                    raise ValueError("No abstract evidence")
                reference = {key: getattr(paper, key) for key in
                             ["title", "authors", "year", "doi", "arxiv_id", "publication_type"]}
            else:
                reference = {"title": context.sources[url].get("title", "")}
            references.append(SourceReference(url=url, **reference))
        return ResearchRecord(task_id=task_id, owner_id=owner_id, question=question, topic=response.topic,
                              mode=context.mode, summary=response.summary, sources=references,
                              status=status, tools_used=response.tools_used)
    except (ValueError, TypeError, AttributeError, KeyError):
        raise MemoryError("invalid_record") from None


class ResearchMemory:
    """One short connection per operation; owner namespaces are NOT authentication."""

    def __init__(self, path: Path | str | None = None, *, owner_id: str = "local"):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", owner_id):
            raise MemoryError("invalid_owner")
        self.owner_id = owner_id
        candidate = Path(path or os.environ.get("RESEARCH_MEMORY_DB") or DEFAULT_PATH)
        self.path = candidate if candidate.is_absolute() else ROOT / candidate
        self._check_path()

    def _check_path(self) -> None:
        try:
            if self.path.suffix.lower() not in {".sqlite3", ".sqlite", ".db"}:
                raise ValueError("Invalid database extension")
            validate_local_path(self.path, MEMORY_ROOT)
            for suffix in ("-journal", "-wal", "-shm"):
                validate_local_path(self.path.with_name(self.path.name + suffix), MEMORY_ROOT)
        except (OSError, ValueError):
            raise MemoryError("invalid_database_path") from None

    @contextmanager
    def _connection(self, *, create: bool = False):
        connection = None
        try:
            self._check_path()
            if create:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._check_path()
            uri = self.path.absolute().as_uri() + ("?mode=rwc" if create else "?mode=ro")
            connection = sqlite3.connect(uri, uri=True, timeout=2.0)
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 512_000)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA trusted_schema=OFF")
            if not create:
                connection.execute("PRAGMA query_only=ON")
            yield connection
        except (sqlite3.Error, OSError):
            raise MemoryError("database_unavailable") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _check_schema(connection: sqlite3.Connection) -> None:
        if (connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID
                or connection.execute("PRAGMA user_version").fetchone()[0] != 1):
            raise MemoryError("unsupported_database")

    def initialize(self) -> None:
        with self._connection(create=True) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            app_id = connection.execute("PRAGMA application_id").fetchone()[0]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if app_id == APPLICATION_ID and version == 1:
                return
            tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if app_id or version or tables:
                raise MemoryError("unsupported_database")
            connection.execute("""CREATE TABLE research_records (
                owner_id TEXT NOT NULL, task_id TEXT NOT NULL,
                question TEXT NOT NULL, topic TEXT NOT NULL,
                mode TEXT NOT NULL CHECK(mode IN ('web','scientific')),
                summary TEXT NOT NULL, sources_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('success','degraded')),
                created_at TEXT NOT NULL, tools_used_json TEXT NOT NULL,
                search_text TEXT NOT NULL, PRIMARY KEY(owner_id, task_id))""")
            connection.execute("CREATE INDEX research_date ON research_records(owner_id, created_at DESC)")
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.execute("PRAGMA user_version=1")

    def save(self, record: ResearchRecord) -> bool:
        """Insert once; a duplicate task never replaces its existing snapshot."""
        try:
            record = ResearchRecord.model_validate(record.model_dump())
            if record.owner_id != self.owner_id:
                raise ValueError("Wrong owner")
        except (ValueError, TypeError, AttributeError):
            raise MemoryError("invalid_record") from None
        self.initialize()
        with self._connection(create=True) as connection, connection:
            self._check_schema(connection)
            cursor = connection.execute("""INSERT INTO research_records
                (owner_id, task_id, question, topic, mode, summary, sources_json, status,
                 created_at, tools_used_json, search_text) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                 ON CONFLICT(owner_id,task_id) DO NOTHING""", (
                record.owner_id, record.task_id, record.question, record.topic, record.mode, record.summary,
                json.dumps([source.model_dump() for source in record.sources], ensure_ascii=False),
                record.status, record.created_at, json.dumps(record.tools_used),
                (record.question + "\n" + record.topic).casefold()))
            return cursor.rowcount == 1

    @staticmethod
    def _record(row: sqlite3.Row) -> ResearchRecord:
        try:
            data = dict(row)
            data.pop("search_text")
            data["sources"] = json.loads(data.pop("sources_json"))
            data["tools_used"] = json.loads(data.pop("tools_used_json"))
            return ResearchRecord.model_validate(data)
        except (ValueError, TypeError, KeyError):
            raise MemoryError("invalid_stored_record") from None

    def get(self, task_id: str) -> ResearchRecord | None:
        try:
            task_id = UUID(task_id).hex
        except (ValueError, TypeError, AttributeError):
            raise MemoryError("invalid_task_id") from None
        self._check_path()
        if not self.path.exists():
            return None
        with self._connection() as connection:
            self._check_schema(connection)
            row = connection.execute("SELECT * FROM research_records WHERE owner_id=? AND task_id=?",
                                     (self.owner_id, task_id)).fetchone()
            return self._record(row) if row else None

    def search(self, query: str = "", *, limit: int = 5, mode: str | None = None) -> list[ResearchRecord]:
        if (type(limit) is not int or not 1 <= limit <= MAX_RESULTS or not isinstance(query, str)
                or len(query) > 2000 or mode not in {None, "web", "scientific"}):
            raise MemoryError("invalid_search")
        clauses, params = ["owner_id=?"], [self.owner_id]
        if mode:
            clauses.append("mode=?")
            params.append(mode)
        if query.strip():
            clauses.append("instr(search_text, ?) > 0")
            params.append(clean_text(query, 2000).strip().casefold())
        self._check_path()
        if not self.path.exists():
            return []
        with self._connection() as connection:
            self._check_schema(connection)
            rows = connection.execute("SELECT * FROM research_records WHERE " + " AND ".join(clauses)
                                      + " ORDER BY created_at DESC, task_id LIMIT ?", (*params, limit)).fetchall()
            return [self._record(row) for row in rows]

    def recall(self, question: str, *, mode: str) -> list[dict]:
        """At most three small historical snippets for the host, never model evidence."""
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise MemoryError("invalid_search")
        stopwords = {"what", "does", "with", "using", "about", "research", "the", "كيف", "حول", "ما", "في", "على", "هل", "من", "وما"}
        terms = list(dict.fromkeys(word for word in re.findall(r"\w+", question.casefold())
                                   if len(word) >= 3 and word not in stopwords))[:6]
        found = {}
        for term in terms:
            for record in self.search(term, limit=3, mode=mode):
                found.setdefault(record.task_id, record)
                if len(found) == 3:
                    break
            if len(found) == 3:
                break
        return [{"kind": "previous_research", "untrusted_data": True, "fresh_evidence": False,
                 "task_id": record.task_id, "created_at": record.created_at, "mode": record.mode,
                 "topic": record.topic[:200], "question": record.question[:300],
                 "summary_excerpt": record.summary[:600]} for record in found.values()]
