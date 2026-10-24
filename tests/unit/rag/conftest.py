"""Shared fixtures for the RAG unit tests (T056–T059).

``make_pdf`` builds real single-font PDFs with pypdf (no binary blobs are written by hand);
the demo and fixture PDFs in the repository were produced with the same helper. ``store`` is
an in-memory Qdrant collection and ``ingest_directory`` runs the offline pipeline
(load → chunk → embed → upsert) used by the retriever and service tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from tests.fakes.embedder import HashingEmbedder

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "documents"


def _pdf_escape(text: str) -> str:
    out = text.encode("cp1252", errors="replace").decode("cp1252")
    return (out.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
               .encode("cp1252", errors="replace").decode("latin-1"))


def make_pdf(path: Path, pages: list[list[str]], metadata: dict[str, str] | None = None) -> None:
    """Write a small real PDF: one page per entry, one text line per list item.

    ``metadata`` entries become PDF info keys (``Title``, ``Version``, ``DocType``,
    ``AccessScope``, ``Department``, ``Demo``) — the loaders read document metadata for PDFs
    from there, since PDFs carry no YAML front-matter.
    """
    writer = PdfWriter()
    font = DictionaryObject()
    font[NameObject("/Type")] = NameObject("/Font")
    font[NameObject("/Subtype")] = NameObject("/Type1")
    font[NameObject("/BaseFont")] = NameObject("/Helvetica")
    font[NameObject("/Encoding")] = NameObject("/WinAnsiEncoding")
    font_ref = writer._add_object(font)
    for lines in pages:
        page = writer.add_blank_page(width=612, height=792)
        ops = ["BT", "/F1 11 Tf", "1 0 0 1 72 700 Tm"]
        for line in lines:
            ops.append(f"({_pdf_escape(line)}) Tj")
            ops.append("0 -16 Td")
        ops.append("ET")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(ops).encode("latin-1"))
        page.replace_contents(stream)
        resources = DictionaryObject()
        resources[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): font_ref})
        page[NameObject("/Resources")] = resources
    info = {f"/{key}": value for key, value in (metadata or {}).items()}
    if info:
        writer.add_metadata(info)
    with open(path, "wb") as handle:
        writer.write(handle)


def make_docx(path: Path, text: str) -> None:
    """A tiny real ``.docx`` (zip) container; unsupported by the loaders on purpose."""
    with ZipFile(path, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",
                    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
                    'org/2006/content-types"></Types>')
        zf.writestr("word/document.xml", f"<document>{text}</document>")


def fixture_doc(name: str) -> Path:
    return FIXTURES_DIR / name


@pytest.fixture
def embedder() -> HashingEmbedder:
    return HashingEmbedder()


@pytest.fixture
def store():
    from qdrant_client import AsyncQdrantClient

    from hcm_lite.rag.vector_store import QdrantStore

    client = AsyncQdrantClient(":memory:")
    yield QdrantStore(client=client, collection="test_documents",
                      embedding_model=HashingEmbedder.model_name)
    client.close()


async def ingest_directory(directory: Path, store: Any, embedder: Any) -> dict[str, int]:
    """Offline pipeline over every supported file in ``directory`` (used by the tests)."""
    from hcm_lite.rag.chunking import chunk_document
    from hcm_lite.rag.loaders import load_document

    await store.ensure_collection(embedder.dimension, embedding_model=embedder.model_name)
    loaded = 0
    chunks = 0
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".pdf"}:
            continue
        doc = load_document(path, root=directory)
        doc_chunks = chunk_document(doc)
        vectors = await embedder.embed([c.text for c in doc_chunks])
        await store.upsert(doc_chunks, vectors)
        loaded += 1
        chunks += len(doc_chunks)
    return {"documents": loaded, "chunks": chunks}
