from __future__ import annotations

import logging
import sys

from travel_assistant.config import settings
from travel_assistant.ingestion.chunk import chunk_all
from travel_assistant.ingestion.clean import clean_source
from travel_assistant.ingestion.fetch import fetch_all, load_sources
from travel_assistant.rag.vectorstore import build_store, save_store, store_stats

logger = logging.getLogger("ingest")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s: %(message)s")

    sources = load_sources()
    logger.info("Registry lists %d source(s)", len(sources))

    fetched = fetch_all(sources)
    if not fetched:
        logger.error("No sources could be fetched — aborting.")
        return 1

    documents = []
    ingested_ids = []
    for source in fetched:
        cleaned = clean_source(source)
        if cleaned:
            documents.append(cleaned)
            ingested_ids.append(source.id)

    skipped = [source.id for source in sources if source.id not in ingested_ids]
    if skipped:
        logger.warning("SKIPPED %d source(s): %s", len(skipped), ", ".join(skipped))
        logger.warning("Check the page names in %s", settings.sources_file)

    chunks = chunk_all(documents)
    logger.info("Produced %d chunks from %d document(s)", len(chunks), len(documents))

    store = build_store(chunks)
    save_store(store)

    stats = store_stats(store)
    logger.info("Index: %d chunks, %d dimensions", stats["chunks"], stats["dimensions"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
