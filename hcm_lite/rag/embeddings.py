"""Embedding providers (US2).

The :class:`Embedder` protocol keeps the pipeline testable with deterministic fakes; the real
implementation calls the OpenAI embeddings API in batches. Any transport/API failure becomes
:class:`~hcm_lite.errors.RetrievalError`.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from hcm_lite.errors import RetrievalError

_BATCH_SIZE = 64
_MAX_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 1.0

_KNOWN_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}
_DEFAULT_DIMENSION = 1536


class Embedder(Protocol):
    """Anything that can turn texts into fixed-size vectors."""

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    """Batched OpenAI embeddings with bounded retries; failures raise ``RetrievalError``."""

    def __init__(self, api_key: str, model: str, *, timeout: float = 30.0) -> None:
        import openai

        self._client = openai.AsyncOpenAI(api_key=api_key, timeout=timeout)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return _KNOWN_DIMENSIONS.get(self._model, _DEFAULT_DIMENSION)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start:start + _BATCH_SIZE]
            vectors.extend(await self._embed_batch(batch))
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        import openai

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await self._client.embeddings.create(model=self._model, input=batch)
                data = sorted(response.data, key=lambda item: item.index)
                return [item.embedding for item in data]
            except openai.OpenAIError as exc:  # transport, rate limit, server errors
                last_error = exc
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_RETRY_BACKOFF_SECONDS * (attempt + 1))
        raise RetrievalError("The embedding service is unavailable") from last_error
