"""Basic ingestion pipeline + CLI (US2 T071; incremental rebuild comes in US7).

``python -m hcm_lite.rag.ingest ingest``   load → chunk → embed → upsert the documents dir
``python -m hcm_lite.rag.ingest status``   collection point count

The report written to ``.ingest/last_report.json`` contains counts and file names only —
never document text.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hcm_lite.config import get_settings
from hcm_lite.rag.chunking import chunk_document
from hcm_lite.rag.embeddings import OpenAIEmbedder
from hcm_lite.rag.loaders import LoadError, iter_documents, load_document
from hcm_lite.rag.vector_store import QdrantStore

REPORT_PATH = Path(".ingest/last_report.json")

# TODO(US7 T112/T113): registry, incremental updates, rebuild/clear/--source/--json.


async def run_ingest(settings: Any, root: Path | None = None) -> dict[str, Any]:
    embedder = OpenAIEmbedder(
        api_key=settings.openai_api_key.get_secret_value(),
        model=settings.openai_embedding_model,
        timeout=settings.model_timeout_seconds,
    )
    store = QdrantStore.from_settings(settings)
    documents_root = root or settings.documents_dir
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "documents_dir": documents_root.as_posix(),
        "embedded": [],
        "skipped": [],
        "failed": [],
        "chunks_indexed": 0,
    }
    try:
        store.ensure_collection(embedder.dimension)
        paths = iter_documents(documents_root)
        by_document: dict[str, list] = {}
        for path in paths:
            try:
                doc = load_document(path, documents_root)
            except LoadError as exc:
                report["failed"].append({"file": path.name, "reason": str(exc)})
                continue
            chunks = chunk_document(doc, size=settings.rag_chunk_size, overlap=settings.rag_chunk_overlap)
            if not chunks:
                report["skipped"].append({"file": path.name, "reason": "no text"})
                continue
            by_document[doc.document_id] = (doc, chunks)
        for document_id, (doc, chunks) in by_document.items():
            vectors = await embedder.embed([chunk.text for chunk in chunks])
            store.delete_by_document(document_id)  # clean re-upsert: re-runs never duplicate
            store.upsert(chunks, vectors)
            report["embedded"].append({"file": doc.source_path.name, "title": doc.title, "chunks": len(chunks)})
            report["chunks_indexed"] += len(chunks)
        report["status"] = "ok"
    finally:
        store.close()
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["total_points"] = _safe_count(settings)
    _write_report(report)
    return report


def _safe_count(settings: Any) -> int | None:
    store = QdrantStore.from_settings(settings)
    try:
        return store.count()
    finally:
        store.close()


def _write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _print_report(report: dict[str, Any]) -> None:
    print(f"Ingested {len(report['embedded'])} document(s), {report['chunks_indexed']} chunk(s).")
    for item in report["embedded"]:
        print(f"  + {item['file']}: {item['chunks']} chunks")
    for item in report["failed"]:
        print(f"  ! {item['file']}: {item['reason']}")
    print(f"Index now holds {report.get('total_points')} point(s). Report: {REPORT_PATH}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hcm_lite.rag.ingest")
    parser.add_argument("command", nargs="?", default="ingest",
                        choices=["ingest", "status", "rebuild", "clear"])
    parser.add_argument("--source", type=Path, default=None,
                        help="ingest from this directory instead of DOCUMENTS_DIR")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="print the report as JSON")
    parser.add_argument("--force", action="store_true",
                        help="required by 'clear' to drop the collection")
    args = parser.parse_args(argv)

    try:
        settings = get_settings()
    except Exception as exc:  # ConfigurationError and friends — never includes values
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.command == "status":
        count = _safe_count(settings)
        print(f"Collection '{settings.vector_store_collection}': {count} point(s).")
        return 0

    if args.command == "clear":
        if not args.force:
            print("Refusing to clear without --force (drops the whole collection).",
                  file=sys.stderr)
            return 2
        store = QdrantStore.from_settings(settings)
        try:
            store.drop()
        finally:
            store.close()
        print(f"Collection '{settings.vector_store_collection}' dropped.")
        return 0

    root = args.source if args.source is not None else settings.documents_dir
    if args.command == "rebuild":
        store = QdrantStore.from_settings(settings)
        try:
            store.drop()
        finally:
            store.close()
    try:
        report = asyncio.run(run_ingest(settings, root))
    except Exception as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)
    return 0 if not report["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
