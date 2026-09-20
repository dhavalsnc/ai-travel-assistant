from __future__ import annotations

import logging
import re

import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify

from travel_assistant.config import settings
from travel_assistant.ingestion.fetch import Source

logger = logging.getLogger(__name__)

NOISE_SELECTORS = [
    ".mw-editsection",
    ".navbox",
    ".metadata",
    ".mw-empty-elt",
    ".reflist",
    ".hatnote",
    ".mw-kartographer-maplink",
    ".pagebanner",
    ".sistersitebox",
    ".ambox",
    "#toc",
    ".toc",
    "sup.reference",
    "script",
    "style",
    "img",
]

DROP_SECTIONS = {"external links", "references", "see also", "notes"}


def html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for selector in NOISE_SELECTORS:
        for node in soup.select(selector):
            node.decompose()

    markdown = markdownify(str(soup), heading_style="ATX", bullets="-")
    return _tidy(markdown)


def _tidy(markdown: str) -> str:
    markdown = re.sub(r"\[\s*edit\s*\]", "", markdown, flags=re.IGNORECASE)
    markdown = re.sub(r"\[\d+\]", "", markdown)
    markdown = re.sub(r"\[\s*\]\([^)]*\)", "", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = re.sub(r"[ \t]+$", "", markdown, flags=re.MULTILINE)
    return markdown.strip()


def drop_trailing_sections(markdown: str) -> str:
    lines = markdown.splitlines()
    out: list[str] = []
    skipping = False

    for line in lines:
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            title = heading.group(2).strip().lower()
            skipping = title in DROP_SECTIONS
        if not skipping:
            out.append(line)

    return "\n".join(out).strip()


def build_frontmatter(source: Source) -> str:
    meta = {
        "source_id": source.id,
        "source_title": source.title,
        "source_url": source.url,
        "license": source.license,
        "attribution": source.attribution,
    }
    return "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True) + "---\n\n"


def clean_source(source: Source) -> str | None:
    settings.processed_dir.mkdir(parents=True, exist_ok=True)

    if source.processed_path.exists():
        return source.processed_path.read_text(encoding="utf-8")

    if not source.raw_path.exists():
        logger.warning("%s: no raw HTML to clean", source.id)
        return None

    html = source.raw_path.read_text(encoding="utf-8")
    body = drop_trailing_sections(html_to_markdown(html))

    if len(body) < 500:
        logger.warning("%s: cleaned output is only %d chars — check selectors", source.id, len(body))

    document = build_frontmatter(source) + f"# {source.title}\n\n" + body
    source.processed_path.write_text(document, encoding="utf-8")
    logger.info("%s: cleaned to %d chars", source.id, len(body))
    return document
