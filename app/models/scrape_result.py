"""Scrape result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MetadataField(StrEnum):
    """Scrapeable metadata fields (Playnite-inspired)."""

    TITLE = "title"
    OVERVIEW = "overview"
    RELEASE_DATE = "release_date"
    GENRE = "genre"
    DEVELOPER = "developer"
    PUBLISHER = "publisher"
    PLAYERS = "players"
    RATING = "rating"
    COMMUNITY_SCORE = "community_score"
    AGE_RATING = "age_rating"
    SERIES = "series"
    TAGS = "tags"
    BOXART = "boxart"
    BACKGROUND = "background"
    ICON = "icon"
    SCREENSHOTS = "screenshots"


@dataclass
class ScrapeResult:
    """Single provider scrape result."""

    game_id: str = ""
    platform: str = ""
    provider: str = ""  # "igdb" / "screenscraper"
    title: str = ""
    title_en: str = ""
    title_ja: str = ""
    title_zh: str = ""
    overview: str = ""
    release_date: str = ""
    genre: str = ""
    developer: str = ""
    publisher: str = ""
    players: int = 1
    rating: float | None = None
    community_score: float | None = None
    age_rating: str = ""
    series: str = ""
    tags: list[str] = field(default_factory=list)
    boxart_url: str = ""
    boxart_local: str = ""
    background_url: str = ""
    background_local: str = ""
    icon_url: str = ""
    icon_local: str = ""
    screenshot_urls: list[str] = field(default_factory=list)
    scraped_at: str = ""


@dataclass
class MergedMetadata:
    """Per-field merged result — records which provider each field came from."""

    game_id: str = ""
    platform: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)  # field_name → provider
