"""Deterministic offline embedder: hashed bag of words, L2-normalised (research D-10)."""

from __future__ import annotations

import hashlib
import math
import re

_WORD = re.compile(r"[a-z0-9]+")


class HashingEmbedder:
    model_name = "hashing-test"

    def __init__(self, dimension: int = 256) -> None:
        self.dimension = dimension

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for word in _WORD.findall(text.lower()):
            h = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big")
            vec[h % self.dimension] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]
