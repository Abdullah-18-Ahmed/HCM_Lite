"""Chunking with heading paths and deterministic ids (US2).

Chunks never cross a heading boundary, carry their heading path as section context and the
PDF page number when known. Ids are uuid5-derived so re-ingesting the same document produces
the same ids.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass

from hcm_lite.rag.loaders import LoadedDocument

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    text: str
    section: str
    page: int | None
    title: str
    access_scope: str
    department: str | None
    doc_type: str
    is_demo: bool
    source_path: str


def _pieces_by_section(text: str) -> list[tuple[str, list[str]]]:
    """Split markdown text into (section_path, paragraphs), tracking heading levels."""
    sections: list[tuple[str, list[str]]] = []
    headings: list[str] = []
    current: list[str] = []
    section = "Overview"

    def close() -> None:
        nonlocal current
        if current:
            sections.append((section, current))
        current = []

    for block in _PARAGRAPH_SPLIT.split(text):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        heading = _HEADING_RE.match(lines[0])
        if heading and len(lines) == 1:
            level, label = len(heading.group(1)), heading.group(2).strip()
            close()
            headings = headings[: level - 1]
            headings.append(label)
            section = " > ".join(headings)
            continue
        current.append(block)
    close()
    return sections


def _windows(paragraphs: list[str], size: int, overlap: int) -> list[str]:
    """Join paragraphs into ~``size``-char windows carrying ``overlap`` chars forward."""
    windows: list[str] = []
    current: list[str] = []
    current_len = 0
    for part in paragraphs:
        current.append(part)
        current_len += len(part) + 2
        if current_len >= size:
            windows.append("\n\n".join(current))
            tail: list[str] = []
            tail_len = 0
            for previous in reversed(current):
                if tail_len >= overlap:
                    break
                tail.insert(0, previous)
                tail_len += len(previous) + 2
            current = tail
            current_len = tail_len
    if current:
        windows.append("\n\n".join(current))
    return windows


def chunk_document(doc: LoadedDocument, *, size: int, overlap: int) -> list[Chunk]:
    """Split a loaded document into deterministic chunks."""
    chunks: list[Chunk] = []
    seq = 0
    for page_no, text in doc.pages:
        for section, paragraphs in _pieces_by_section(text):
            for window in _windows(paragraphs, size, overlap):
                seq += 1
                digest = hashlib.sha256(window.encode("utf-8")).digest()[:8]
                chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc.document_id}:{seq}:{digest.hex()}"))
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        document_id=doc.document_id,
                        text=window,
                        section=section,
                        page=page_no,
                        title=doc.title,
                        access_scope=doc.access_scope,
                        department=doc.department,
                        doc_type=doc.doc_type,
                        is_demo=doc.is_demo,
                        source_path=doc.source_path.as_posix(),
                    )
                )
    return chunks
