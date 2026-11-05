"""Scientific metadata normalization and conservative paper deduplication."""

from __future__ import annotations

from urllib.parse import urlsplit

import re

from pydantic import BaseModel, Field, field_validator

from safety import clean_text, safe_url


def academic_reference(value: str) -> tuple[str, str, str | None] | None:
    """Recognize exact scholarly URL identities, retaining explicit arXiv versions."""
    if safe_url(value) != value:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if parsed.query or parsed.fragment or port is not None:
        return None
    if parsed.hostname in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        match = re.fullmatch(r"/abs/((?:\d{4}\.\d{4,5}|[a-zA-Z.-]+/\d{7}))(v\d+)?", parsed.path)
        if match:
            return "arxiv", match[1], match[2]
    if parsed.hostname in {"doi.org", "dx.doi.org"}:
        doi = normalize_doi("doi:" + parsed.path.lstrip("/"))
        if doi:
            return "doi", doi, None
    return None


def normalize_doi(value: str | None) -> str | None:
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value or "", flags=re.I).strip().lower()
    return value if re.fullmatch(r"10\.\d{4,9}/[^\s]+", value) else None


def normalize_arxiv(value: str | None) -> str | None:
    value = re.sub(r"^https?://(?:export\.)?arxiv\.org/(?:abs|pdf)/", "", value or "")
    value = re.sub(r"v\d+(?:\.pdf)?$|\.pdf$", "", value)
    return value if re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-zA-Z.-]+/\d{7})", value) else None


class PaperRecord(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    authors: list[str] = Field(default_factory=list, max_length=20)
    year: int | None = Field(default=None, ge=1000, le=2100)
    abstract: str | None = Field(default=None, max_length=30000)
    url: str
    database: str
    doi: str | None = None
    arxiv_id: str | None = None
    publication_type: str = "unknown"
    abstract_truncated: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        url = safe_url(value)
        if not url:
            raise ValueError("Invalid paper URL")
        return url

    def evidence(self) -> dict:
        text = self.abstract or ""
        return {"title": self.title, "authors": self.authors, "year": self.year,
                "abstract": text[:2200] or None, "abstract_truncated": self.abstract_truncated or len(text) > 2200,
                "url": self.url, "doi": self.doi, "arxiv_id": self.arxiv_id,
                "database": self.database, "publication_type": self.publication_type,
                "evidence_available": bool(text)}


def make_paper(**values) -> PaperRecord:
    raw_abstract = values.get("abstract") or ""
    values["title"] = clean_text(str(values.get("title") or ""), 500).strip()
    values["authors"] = [clean_text(str(author), 150) for author in values.get("authors", [])[:20]]
    values["abstract"] = clean_text(str(raw_abstract), 30000).strip() or None
    values["abstract_truncated"] = len(str(raw_abstract)) > 30000
    values["doi"] = normalize_doi(values.get("doi"))
    values["arxiv_id"] = normalize_arxiv(values.get("arxiv_id"))
    return PaperRecord(**values)


def same_paper(left: PaperRecord, right: PaperRecord) -> bool:
    if left.doi and right.doi:
        return left.doi == right.doi
    if left.arxiv_id and right.arxiv_id:
        return left.arxiv_id == right.arxiv_id
    normalize_title = lambda title: re.sub(r"[^\w]", "", title.casefold())
    return bool(left.year and left.year == right.year and normalize_title(left.title) == normalize_title(right.title))


def reconstruct_abstract(index) -> str | None:
    """Reconstruct OpenAlex's position map with bounds on malformed data."""
    if not index:
        return None
    if not isinstance(index, dict) or len(index) > 10000:
        raise ValueError("Invalid abstract index")
    positions = {}
    for word, offsets in index.items():
        if not isinstance(word, str) or len(word) > 200 or not isinstance(offsets, list):
            raise ValueError("Invalid abstract index")
        for offset in offsets:
            if type(offset) is not int or not 0 <= offset < 10000 or offset in positions:
                raise ValueError("Invalid abstract position")
            positions[offset] = word
    if positions and set(positions) != set(range(len(positions))):
        raise ValueError("Incomplete abstract position map")
    return " ".join(positions[offset] for offset in sorted(positions)) or None
