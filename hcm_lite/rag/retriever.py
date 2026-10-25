"""Scope-filtered retrieval (US2, constitution Art. XI / XVI).

The store query already filters by access scope; this layer **re-checks** every returned
point in code so that a store that ignores filters can never leak an out-of-scope passage.

The embedded Qdrant local store file-locks its storage folder, so two processes (the Chainlit
UI and the FastAPI API) cannot each hold a client open. Each search therefore opens the store
briefly, queries, and closes it, retrying briefly if the other process holds the lock.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from hcm_lite.rag.embeddings import Embedder
from hcm_lite.rag.vector_store import QdrantStore, ScoredPassage
from hcm_lite.services.authz import allowed_doc_scopes

_LOCK_RETRY_ATTEMPTS = 4
_LOCK_RETRY_BACKOFF = 0.4


def _is_lock_error(exc: BaseException) -> bool:
    return "already accessed" in str(exc)


class Retriever:
    def __init__(self, store_factory: Callable[[], QdrantStore], embedder: Embedder,
                 settings: Any, *, ensure: bool = True) -> None:
        self._factory = store_factory
        self._embedder = embedder
        self._settings = settings
        if ensure:
            self._with_store(lambda store: store.ensure_collection(embedder.dimension))

    def _with_store(self, operation: Callable[[QdrantStore], Any]) -> Any:
        """Run one store operation on a short-lived client, retrying lock contention."""
        last_error: BaseException | None = None
        for attempt in range(_LOCK_RETRY_ATTEMPTS):
            store = self._factory()
            try:
                return operation(store)
            except RuntimeError as exc:
                last_error = exc
                if _is_lock_error(exc) and attempt < _LOCK_RETRY_ATTEMPTS - 1:
                    time.sleep(_LOCK_RETRY_BACKOFF * (attempt + 1))
                    continue
                raise
            finally:
                store.close()
        raise last_error  # pragma: no cover — loop always returns or raises

    async def _with_store_async(self, operation: Callable[[QdrantStore], Any]) -> Any:
        last_error: BaseException | None = None
        for attempt in range(_LOCK_RETRY_ATTEMPTS):
            store = self._factory()
            try:
                return operation(store)
            except RuntimeError as exc:
                last_error = exc
                if _is_lock_error(exc) and attempt < _LOCK_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(_LOCK_RETRY_BACKOFF * (attempt + 1))
                    continue
                raise
            finally:
                store.close()
        raise last_error  # pragma: no cover

    def count(self) -> int:
        return self._with_store(lambda store: store.count())

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
        passages = await self._with_store_async(
            lambda store: store.search(
                vector,
                limit=max(limit * 3, limit),  # over-fetch before thresholding
                allowed_scopes=sorted(allowed),
                doc_type=doc_type,
            ))
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
