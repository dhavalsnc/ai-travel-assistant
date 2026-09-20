from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass

from langchain_core.documents import Document

from travel_assistant.config import settings
from travel_assistant.rag.vectorstore import load_store

logger = logging.getLogger(__name__)

MAX_CHUNKS_PER_SOURCE = 3
COVERAGE_SAMPLE = 5


@dataclass
class ScoredChunk:
    document: Document
    score: float

    def __post_init__(self) -> None:
        self.score = float(self.score)

    @property
    def citation(self) -> dict:
        meta = self.document.metadata
        return {
            "title": meta.get("source_title", "Unknown source"),
            "url": meta.get("source_url", ""),
            "section": meta.get("section", ""),
            "score": round(self.score, 3),
        }


@dataclass
class RetrievalResult:
    query: str
    chunks: list[ScoredChunk]
    best_score: float
    coverage_score: float
    threshold: float

    @property
    def sufficient(self) -> bool:
        return bool(self.chunks) and self.coverage_score >= self.threshold

    @property
    def citations(self) -> list[dict]:
        seen: set[tuple[str, str]] = set()
        out: list[dict] = []
        for chunk in self.chunks:
            citation = chunk.citation
            key = (citation["title"], citation["section"])
            if key not in seen:
                seen.add(key)
                out.append(citation)
        return out


def _cap_per_source(scored: list[ScoredChunk], k: int) -> list[ScoredChunk]:
    counts: dict[str, int] = {}
    kept: list[ScoredChunk] = []

    for chunk in scored:
        source_id = chunk.document.metadata.get("source_id", "unknown")
        if counts.get(source_id, 0) >= MAX_CHUNKS_PER_SOURCE:
            continue
        counts[source_id] = counts.get(source_id, 0) + 1
        kept.append(chunk)
        if len(kept) == k:
            break

    return kept


def retrieve(query: str, k: int | None = None) -> RetrievalResult:
    k = k or settings.retrieval_k
    store = load_store()

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Relevance scores must be between")
        pairs = store.similarity_search_with_relevance_scores(
            query, k=settings.retrieval_fetch_k
        )
    scored = [ScoredChunk(document=doc, score=score) for doc, score in pairs]
    scored.sort(key=lambda c: c.score, reverse=True)

    if not scored:
        return RetrievalResult(
            query=query,
            chunks=[],
            best_score=0.0,
            coverage_score=0.0,
            threshold=settings.retrieval_score_threshold,
        )

    best = scored[0].score
    sample = [chunk.score for chunk in scored[:COVERAGE_SAMPLE]]
    coverage = sum(sample) / len(sample)
    threshold = settings.retrieval_score_threshold

    if coverage < threshold:
        logger.info(
            "No coverage for %r (mean top-%d = %.3f < %.3f, best = %.3f)",
            query,
            len(sample),
            coverage,
            threshold,
            best,
        )
        return RetrievalResult(
            query=query,
            chunks=[],
            best_score=best,
            coverage_score=coverage,
            threshold=threshold,
        )

    return RetrievalResult(
        query=query,
        chunks=_cap_per_source(scored, k),
        best_score=best,
        coverage_score=coverage,
        threshold=threshold,
    )
