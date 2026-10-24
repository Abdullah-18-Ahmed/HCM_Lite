"""Document loaders for the RAG pipeline (contracts: US2, data-model.md §3).

Markdown and plain-text files carry simple YAML front-matter (flat ``key: value`` pairs).
PDFs are read with pypdf. Everything loaded here is DATA, never instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from hcm_lite.errors import RetrievalError
from hcm_lite.models.domain import AccessScope

SUPPORTED_EXTENSIONS = frozenset({".md", ".markdown", ".txt", ".pdf"})
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB
_DEMO_PREFIX = "DEMO — fictional"

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_KNOWN_KEYS = frozenset({"title", "version", "doc_type", "access_scope", "department", "demo"})

_VALID_SCOPES = frozenset(s.value for s in AccessScope)


class LoadError(RetrievalError):
    """A document could not be loaded (unreadable, unsupported, empty, too large)."""


@dataclass
class LoadedDocument:
    source_path: Path
    document_id: str  # deterministic: uuid5 of the path relative to the documents dir
    title: str
    version: str
    doc_type: str
    access_scope: str  # AccessScope value; "restricted" when absent in front-matter
    department: str | None
    is_demo: bool
    pages: list[tuple[int | None, str]] = field(default_factory=list)  # (page_no, text)


def document_id_for(path: Path, root: Path) -> str:
    """Deterministic document id from the path relative to the documents root."""
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_URL, "hcm-lite-doc:" + path.resolve().relative_to(root.resolve()).as_posix()))


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    """Split optional flat YAML front-matter from the body. No document text is logged."""
    match = _FRONT_MATTER_RE.match(raw)
    if match is None:
        return {}, raw
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip().strip('"').strip("'")
        if key in _KNOWN_KEYS:
            meta[key] = value
    return meta, raw[match.end():]


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def load_document(path: Path, root: Path) -> LoadedDocument:
    """Load one document. Raises :class:`LoadError` for anything unusable."""
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise LoadError(f"unsupported document type: {path.suffix or '(none)'}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise LoadError("document could not be read") from exc
    if size > MAX_DOCUMENT_BYTES:
        raise LoadError("document exceeds the 10 MB limit")
    if size == 0:
        raise LoadError("document is empty")

    if path.suffix.lower() == ".pdf":
        pages = _load_pdf(path)
        full_text = "".join(t for _, t in pages)
        # A PDF may open with a flat front-matter block in its extracted text; use it when
        # present, otherwise the document stays restricted (missing access_scope rule).
        meta, body = _parse_front_matter(full_text)
        scope = meta.get("access_scope", "").strip()
        if scope not in _VALID_SCOPES:
            scope = AccessScope.RESTRICTED.value
        doc = LoadedDocument(
            source_path=path,
            document_id=document_id_for(path, root),
            title=meta.get("title") or _pdf_title(pages[0][1] if pages else ""),
            version=meta.get("version") or "1.0",
            doc_type=meta.get("doc_type") or "policy",
            access_scope=scope,
            department=meta.get("department") or None,
            is_demo=_bool(meta.get("demo", "false")) or _DEMO_PREFIX in full_text[:200],
            pages=pages,
        )
        return doc

    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LoadError("document could not be read") from exc
    meta, body = _parse_front_matter(raw)
    if not body.strip():
        raise LoadError("document is empty")
    scope = meta.get("access_scope", "").strip()
    if scope not in _VALID_SCOPES:
        scope = AccessScope.RESTRICTED.value
    return LoadedDocument(
        source_path=path,
        document_id=document_id_for(path, root),
        title=meta.get("title") or path.stem.replace("-", " ").replace("_", " ").title(),
        version=meta.get("version") or "1.0",
        doc_type=meta.get("doc_type") or "policy",
        access_scope=scope,
        department=meta.get("department") or None,
        is_demo=_bool(meta.get("demo", "false")) or body.lstrip().startswith(_DEMO_PREFIX),
        pages=[(None, body)],
    )


def _load_pdf(path: Path) -> list[tuple[int, str]]:
    try:
        reader = PdfReader(str(path))
        pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
    except (PdfReadError, OSError, ValueError) as exc:
        raise LoadError("PDF document could not be read") from exc
    if not any(text.strip() for _, text in pages):
        raise LoadError("document is empty")
    return pages


def _pdf_title(first_page_text: str) -> str:
    for line in first_page_text.splitlines():
        line = line.strip()
        if line and not line.startswith(_DEMO_PREFIX):
            return line[:120]
    return "Untitled document"


def iter_documents(root: Path) -> list[Path]:
    """All supported document files under ``root`` (recursive), sorted for determinism."""
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )
