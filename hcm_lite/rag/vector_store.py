"""Qdrant vector store wrapper (US2).

Embedded local mode by default (``VECTOR_STORE_PATH``), or a remote server when
``VECTOR_STORE_URL`` is set. Searching uses ``query_points`` (qdrant-client 1.20 removed
``search``) with a ``MatchAny`` access-scope filter. Callers still re-check scopes in code —
the store filter is defence in depth, not the only gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hcm_lite.errors import ConfigurationError
from hcm_lite.rag.chunking import Chunk

PAYLOAD_TEXT = "text"
PAYLOAD_DOCUMENT_ID = "document_id"
PAYLOAD_ACCESS_SCOPE = "access_scope"
PAYLOAD_DOC_TYPE = "doc_type"


@dataclass
class ScoredPassage:
    chunk_id: str
    document_id: str
    text: str
    title: str
    section: str
    page: int | None
    access_scope: str
    department: str | None
    doc_type: str
    is_demo: bool
    source_path: str
    score: float


class QdrantStore:
    """Thin async-friendly wrapper over a synchronous embedded Qdrant client."""

    def __init__(self, client: Any, collection: str) -> None:
        self._client = client
        self._collection = collection

    # ------------------------------------------------------------------ construction

    @classmethod
    def from_settings(cls, settings: Any) -> "QdrantStore":
        from qdrant_client import QdrantClient

        url = settings.vector_store_url
        if url:
            client = QdrantClient(
                url=url,
                api_key=settings.vector_store_api_key.get_secret_value() or None,
                timeout=10,
            )
        elif settings.vector_store_path:
            Path(settings.vector_store_path).mkdir(parents=True, exist_ok=True)
            client = QdrantClient(path=settings.vector_store_path)
        else:
            client = QdrantClient(":memory:")
        return cls(client, settings.vector_store_collection)

    @property
    def collection(self) -> str:
        return self._collection

    # ------------------------------------------------------------------ lifecycle

    def ensure_collection(self, dimension: int) -> None:
        """Create the collection if missing; refuse a dimension mismatch."""
        from qdrant_client import models

        existing = self._get_collection_info()
        if existing is None:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE),
            )
        elif existing.size != dimension:
            raise ConfigurationError(
                "Vector index dimension mismatch: the collection was built with a different "
                "embedding model. Run 'python -m hcm_lite.rag.ingest rebuild'.",
                variables=["OPENAI_EMBEDDING_MODEL"],
            )
        self._ensure_payload_indexes()

    def _ensure_payload_indexes(self) -> None:
        """Index the payload fields we filter on.

        Embedded Qdrant filters on any field without an index; Qdrant server (Cloud)
        returns 400 ("Index required but not found") unless the field is indexed. We filter
        on document_id (re-upsert delete), access_scope and doc_type (retrieval), so index
        all three. Idempotent: creating an existing index is ignored.
        """
        from qdrant_client import models

        for field in (PAYLOAD_DOCUMENT_ID, PAYLOAD_ACCESS_SCOPE, PAYLOAD_DOC_TYPE):
            try:
                self._client.create_payload_index(
                    collection_name=self._collection,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass  # already indexed, or embedded client that does not require it

    def _get_collection_info(self) -> Any | None:
        from qdrant_client import models

        try:
            info = self._client.get_collection(self._collection)
        except Exception:
            return None
        params = getattr(info, "config", None)
        vectors = getattr(params, "params", None) if params else None
        vp = getattr(vectors, "vectors", None) if vectors else None
        if isinstance(vp, models.VectorParams):
            return vp
        return None

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ operations

    def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        from qdrant_client import models

        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")
        points = [
            models.PointStruct(
                id=chunk.chunk_id,
                vector=vector,
                payload={
                    PAYLOAD_TEXT: chunk.text,
                    PAYLOAD_DOCUMENT_ID: chunk.document_id,
                    "title": chunk.title,
                    "section": chunk.section,
                    "page": chunk.page,
                    PAYLOAD_ACCESS_SCOPE: chunk.access_scope,
                    "department": chunk.department,
                    PAYLOAD_DOC_TYPE: chunk.doc_type,
                    "is_demo": chunk.is_demo,
                    "source_path": chunk.source_path,
                },
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        for start in range(0, len(points), 100):
            self._client.upsert(collection_name=self._collection, points=points[start:start + 100])

    def delete_by_document(self, document_id: str) -> None:
        from qdrant_client import models

        self._client.delete(
            collection_name=self._collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(key=PAYLOAD_DOCUMENT_ID, match=models.MatchValue(value=document_id))]
                )
            ),
        )

    def search(
        self,
        vector: list[float],
        *,
        limit: int,
        allowed_scopes: list[str],
        doc_type: str | None = None,
    ) -> list[ScoredPassage]:
        """Nearest passages with the scope filter applied in the store query."""
        from qdrant_client import models

        conditions: list[models.Condition] = [
            models.FieldCondition(key=PAYLOAD_ACCESS_SCOPE, match=models.MatchAny(any=list(allowed_scopes)))
        ]
        if doc_type:
            conditions.append(
                models.FieldCondition(key=PAYLOAD_DOC_TYPE, match=models.MatchValue(value=doc_type))
            )
        result = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=limit,
            query_filter=models.Filter(must=conditions),
            with_payload=True,
        )
        passages: list[ScoredPassage] = []
        for point in result.points:
            payload = point.payload or {}
            passages.append(
                ScoredPassage(
                    chunk_id=str(point.id),
                    document_id=str(payload.get(PAYLOAD_DOCUMENT_ID, "")),
                    text=str(payload.get(PAYLOAD_TEXT, "")),
                    title=str(payload.get("title", "")),
                    section=str(payload.get("section", "Overview")),
                    page=payload.get("page"),
                    access_scope=str(payload.get(PAYLOAD_ACCESS_SCOPE, "")),
                    department=payload.get("department"),
                    doc_type=str(payload.get(PAYLOAD_DOC_TYPE, "")),
                    is_demo=bool(payload.get("is_demo", False)),
                    source_path=str(payload.get("source_path", "")),
                    score=float(point.score),
                )
            )
        return passages

    def count(self) -> int:
        try:
            return int(self._client.count(collection_name=self._collection, exact=True).count)
        except Exception:
            return 0

    def drop(self) -> None:
        try:
            self._client.delete_collection(self._collection)
        except Exception:
            pass
