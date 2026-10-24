"""Citation building (US2, contracts/agent-tools.md #8)."""

from __future__ import annotations

from hcm_lite.models.results import Citation
from hcm_lite.rag.vector_store import ScoredPassage

UNTRUSTED_PREFIX = "<<<UNTRUSTED_DOCUMENT {n}>>>"
UNTRUSTED_SUFFIX = "<<<END_UNTRUSTED_DOCUMENT {n}>>>"


def citation_for(passage: ScoredPassage, n: int) -> Citation:
    return Citation(
        n=n,
        document_id=passage.document_id,
        title=passage.title,
        section=passage.section,
        page=passage.page,
        source_path=passage.source_path,
    )


def wrap_untrusted(text: str, n: int) -> str:
    """Wrap retrieved text so the model treats it as data, never as instructions."""
    return f"{UNTRUSTED_PREFIX.format(n=n)}\n{text}\n{UNTRUSTED_SUFFIX.format(n=n)}"
