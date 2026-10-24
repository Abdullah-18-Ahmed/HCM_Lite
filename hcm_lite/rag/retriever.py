"""Scope-filtered retrieval (US2, constitution Art. XI / XVI).

The store query already filters by access scope; this layer **re-checks** every returned
point in code so that a store that ignores filters can never leak an out-of-scope passage.
"""

from __future__ import annotations

from typing import Any

from hcm_lite.rag.embeddings import Embedder
from hcm_lite.rag.vector_store import QdrantStore, ScoredPassage
from hcm_lite.services.authz import allowed_doc_scopes


class Retriever:
    def __init__(self, store: QdrantStore, embedder: Embedder, settings: Any) -> None:
        self._store = store
        self._embedder = embedder
        self._settings = settings
        self._store.ensure_collection(self._embedder.dimension)

    async def search(
        self,
        query: str,
        role: str,
        *,
        top_k: int | None = None,
        doc_type: str | None = None,
    ) -> list[ScoredPassage]:
        """Embed the query and return in-scope passages above the similarity threshold."""
        limit = top_k or self._settings.rag_top_k
        allowed = set(allowed_doc_scopes(role))
        if not allowed:
            return []
        vector = (await self._embedder.embed([query]))[0]
        passages = self._store.search(
            vector,
            limit=max(limit * 3, limit),  # over-fetch before thresholding
            allowed_scopes=sorted(allowed),
            doc_type=doc_type,
        )
        kept: list[ScoredPassage] = []
        for passage in passages:
            # Code re-check: the store filter is defence in depth, this is the gate.
            if passage.access_scope not in allowed:
                continue
            if passage.score < self._settings.rag_similarity_threshold:
                continue
            kept.append(passage)
        kept.sort(key=lambda p: p.score, reverse=True)
        return kept[:limit]
