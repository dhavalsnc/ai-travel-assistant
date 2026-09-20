from __future__ import annotations

from langchain_core.tools import tool

from travel_assistant.config import DESTINATION
from travel_assistant.rag.retriever import RetrievalResult, retrieve
from travel_assistant.rag.vectorstore import VectorStoreMissingError

NO_COVERAGE_TEMPLATE = (
    "NO_RELEVANT_CONTENT. The {destination} knowledge base has nothing that answers "
    "{query!r} (coverage {coverage:.2f}, threshold {threshold:.2f}).\n\n"
    "Tell the user this topic is not covered by your sources. Do not supply "
    "{destination} facts from memory."
)


def format_chunks(result: RetrievalResult) -> str:
    blocks: list[str] = []
    for index, chunk in enumerate(result.chunks, start=1):
        meta = chunk.document.metadata
        section = f" — {meta['section']}" if meta.get("section") else ""
        header = "\n".join(
            [
                f"[{index}] {meta.get('source_title')}{section}",
                f"URL: {meta.get('source_url')}",
                f"Relevance: {chunk.score:.2f}",
                "---",
            ]
        )
        blocks.append(f"{header}\n{chunk.document.page_content}")
    return "\n\n".join(blocks)


@tool("search_travel_kb", response_format="content_and_artifact")
def search_travel_kb(query: str) -> tuple[str, dict]:
    """Search the curated Singapore travel knowledge base.

    This is the ONLY approved source for destination facts: attractions, neighbourhoods,
    transport (MRT, buses, taxis, EZ-Link), culture and etiquette, food, opening context,
    indoor vs outdoor activities, and sample itineraries.

    Use it for any question about what to see, do, eat, or how to get around Singapore,
    including when you also need live weather or currency data for the same answer.
    Do not use it for current weather or exchange rates.

    Args:
        query: A specific natural-language query, e.g. "indoor attractions for rainy days"
            or "how to get from Changi Airport to the city". Search once per distinct
            topic rather than sending one broad query.
    """
    try:
        result = retrieve(query)
    except VectorStoreMissingError as exc:
        return (
            (
                f"KB_UNAVAILABLE. {exc} Tell the user the knowledge base is not built; "
                "do not answer destination questions from memory."
            ),
            {"status": "unavailable", "query": query, "error": str(exc)},
        )

    if not result.sufficient:
        return (
            NO_COVERAGE_TEMPLATE.format(
                destination=DESTINATION,
                query=query,
                coverage=result.coverage_score,
                threshold=result.threshold,
            ),
            {
                "status": "no_coverage",
                "query": query,
                "coverage_score": result.coverage_score,
                "best_score": result.best_score,
            },
        )

    return (
        format_chunks(result),
        {
            "status": "ok",
            "query": query,
            "citations": result.citations,
            "chunk_count": len(result.chunks),
        },
    )
