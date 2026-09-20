from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import yaml

from travel_assistant.config import settings

logger = logging.getLogger(__name__)

WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"
USER_AGENT = "travel-assistant/0.1 (educational assignment; contact via repository)"


@dataclass
class Source:
    id: str
    title: str
    url: str
    license: str
    attribution: str
    page: str
    covers: list[str] = field(default_factory=list)

    @property
    def raw_path(self) -> Path:
        return settings.raw_dir / f"{self.id}.html"

    @property
    def processed_path(self) -> Path:
        return settings.processed_dir / f"{self.id}.md"


def load_sources(path: Path | None = None) -> list[Source]:
    path = path or settings.sources_file
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})

    sources = [
        Source(
            id=merged["id"],
            title=merged["title"],
            url=merged["url"],
            license=merged["license"],
            attribution=merged.get("attribution", ""),
            page=merged["page"],
            covers=merged.get("covers", []),
        )
        for merged in ({**defaults, **entry} for entry in raw["sources"])
    ]

    if not sources:
        raise ValueError(f"No sources in {path}")
    return sources


def fetch_wikivoyage(source: Source, client: httpx.Client) -> str:
    response = client.get(
        WIKIVOYAGE_API,
        params={
            "action": "parse",
            "page": source.page,
            "prop": "text",
            "formatversion": "2",
            "format": "json",
            "redirects": "1",
        },
    )
    response.raise_for_status()
    payload = response.json()

    if "error" in payload:
        raise RuntimeError(f"{source.id}: MediaWiki error — {payload['error'].get('info')}")
    return payload["parse"]["text"]


def fetch_all(sources: list[Source]) -> list[Source]:
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
    fetched: list[Source] = []

    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True) as client:
        for source in sources:
            if source.raw_path.exists():
                logger.info("%s: cached (%s)", source.id, source.raw_path.name)
                fetched.append(source)
                continue

            try:
                html = fetch_wikivoyage(source, client)
            except Exception as exc:  # noqa: BLE001
                logger.error("%s: fetch failed — %s", source.id, exc)
                continue

            source.raw_path.write_text(html, encoding="utf-8")
            logger.info("%s: fetched %d KB", source.id, len(html) // 1024)
            fetched.append(source)

    return fetched
