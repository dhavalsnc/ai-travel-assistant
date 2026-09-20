from __future__ import annotations

import functools
import logging

from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from travel_assistant.config import settings

logger = logging.getLogger(__name__)


class VectorStoreMissingError(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    logger.info("Loading embedding model %s", settings.embedding_model)
    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        encode_kwargs={"normalize_embeddings": True},
    )


def build_store(documents: list[Document]) -> FAISS:
    if not documents:
        raise ValueError("Cannot build a vector store from zero documents")

    return FAISS.from_documents(
        documents,
        get_embeddings(),
        distance_strategy=DistanceStrategy.COSINE,
    )


def save_store(store: FAISS) -> None:
    settings.vectorstore_dir.mkdir(parents=True, exist_ok=True)
    store.save_local(str(settings.vectorstore_dir))
    logger.info("Saved index to %s", settings.vectorstore_dir)


@functools.lru_cache(maxsize=1)
def load_store() -> FAISS:
    index_file = settings.vectorstore_dir / "index.faiss"
    if not index_file.exists():
        raise VectorStoreMissingError(
            f"No FAISS index at {settings.vectorstore_dir}. Run `make ingest` first."
        )

    return FAISS.load_local(
        str(settings.vectorstore_dir),
        get_embeddings(),
        distance_strategy=DistanceStrategy.COSINE,
        allow_dangerous_deserialization=True,
    )


def prewarm() -> None:
    get_embeddings()
    try:
        load_store()
    except VectorStoreMissingError:
        logger.warning("Prewarm skipped: no index at %s", settings.vectorstore_dir)


def store_stats(store: FAISS) -> dict:
    return {"chunks": store.index.ntotal, "dimensions": store.index.d}
