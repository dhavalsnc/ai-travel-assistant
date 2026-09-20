from __future__ import annotations

import re

import yaml
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from travel_assistant.config import settings

HEADERS_TO_SPLIT_ON = [("#", "h1"), ("##", "h2"), ("###", "h3")]

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

MIN_CHUNK_CHARS = 120


def parse_frontmatter(document: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(document)
    if not match:
        return {}, document
    return yaml.safe_load(match.group(1)) or {}, document[match.end() :]


def section_path(metadata: dict) -> str:
    parts = [metadata.get(level) for level in ("h1", "h2", "h3")]
    return " > ".join(part for part in parts if part)


def chunk_document(document: str) -> list[Document]:
    meta, body = parse_frontmatter(document)

    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=False,
    )
    size_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    sections = header_splitter.split_text(body)
    chunks: list[Document] = []

    for section in sections:
        path = section_path(section.metadata)

        for piece in size_splitter.split_text(section.page_content):
            text = piece.strip()
            if len(text) < MIN_CHUNK_CHARS:
                continue

            content = f"{path}\n\n{text}" if path else text

            chunks.append(
                Document(
                    page_content=content,
                    metadata={
                        "source_id": meta.get("source_id", "unknown"),
                        "source_title": meta.get("source_title", "Unknown source"),
                        "source_url": meta.get("source_url", ""),
                        "license": meta.get("license", ""),
                        "attribution": meta.get("attribution", ""),
                        "section": path,
                    },
                )
            )

    return chunks


def chunk_all(documents: list[str]) -> list[Document]:
    chunks: list[Document] = []
    for document in documents:
        chunks.extend(chunk_document(document))
    return chunks
