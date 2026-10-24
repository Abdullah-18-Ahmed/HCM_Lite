"""Policy search service (US2, contracts/services.md).

Scope-filtered RAG retrieval with citations and untrusted wrapping. Exact HR figures never
come from here — this is document search only (constitution Art. IX.1.5, XI).
"""

from __future__ import annotations

from hcm_lite.errors import RetrievalError, ValidationError
from hcm_lite.models.domain import AuthenticatedUser
from hcm_lite.models.results import PolicyChunk, PolicySearchResult, ToolResult
from hcm_lite.rag.citations import citation_for, wrap_untrusted
from hcm_lite.rag.retriever import Retriever

MIN_QUERY_LENGTH = 3
MAX_QUERY_LENGTH = 500

SOURCE = "rag:hr_documents"


class PolicyService:
    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    async def search(
        self,
        user: AuthenticatedUser,
        query: str,
        doc_type: str | None = None,
    ) -> ToolResult[PolicySearchResult]:
        query = (query or "").strip()
        if not (MIN_QUERY_LENGTH <= len(query) <= MAX_QUERY_LENGTH):
            raise ValidationError("query", f"must be {MIN_QUERY_LENGTH}-{MAX_QUERY_LENGTH} characters")
        try:
            passages = await self._retriever.search(query, user.role, doc_type=doc_type)
        except RetrievalError:
            return ToolResult.failure(
                "source_unavailable",
                "The document index is unavailable right now.",
                source=SOURCE,
            )
        chunks = [
            PolicyChunk(
                n=index + 1,
                text=wrap_untrusted(passage.text, index + 1),
                citation=citation_for(passage, index + 1),
            )
            for index, passage in enumerate(passages)
        ]
        result = PolicySearchResult(found=bool(chunks), chunks=chunks)
        return ToolResult.success(
            result,
            source=SOURCE,
            scope=None,
            is_demo=any(passage.is_demo for passage in passages),
        )
