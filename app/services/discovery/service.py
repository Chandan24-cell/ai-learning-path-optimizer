"""Provider orchestration and a provider-independent subject builder."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Literal

from app.services.discovery.interfaces import Book, Candidate, SubjectProvider
from app.services.discovery.providers import (
    OpenAlexProvider,
    OpenLibraryProvider,
    WikidataProvider,
    WikipediaProvider,
)
from app.services.discovery.safety import DiscoveryUnavailable


class DiscoveryService:
    def __init__(
        self,
        providers: Sequence[SubjectProvider] | None = None,
        books: OpenLibraryProvider | None = None,
        wikipedia: WikipediaProvider | None = None,
    ) -> None:
        self.providers: list[SubjectProvider] = list(
            providers
            if providers is not None
            else [WikipediaProvider(), WikidataProvider(), OpenAlexProvider()]
        )
        self.books_provider = books or OpenLibraryProvider()
        self.wikipedia = wikipedia or WikipediaProvider()

    def search(self, query: str, level: str) -> tuple[list[Candidate], list[str]]:
        results: list[Candidate] = []
        errors: list[str] = []
        seen: set[tuple[str, str]] = set()
        for provider in self.providers:
            try:
                candidates = provider.search(query, level)
            except DiscoveryUnavailable:
                errors.append(f"{provider.name} is temporarily unavailable.")
                continue
            for candidate in candidates:
                key = (candidate.name.casefold(), candidate.source_url)
                if key not in seen:
                    results.append(candidate)
                    seen.add(key)
        results.sort(key=lambda item: (-item.confidence, item.name.casefold()))
        return results[:12], errors

    def search_books(self, query: str) -> tuple[list[Book], list[str]]:
        try:
            return self.books_provider.search_books(query), []
        except DiscoveryUnavailable:
            return [], ["Open Library is temporarily unavailable."]

    def preview(self, candidate: Candidate) -> list[str]:
        if candidate.source != "Wikipedia":
            return [candidate.name]
        return [str(section["title"]) for section in self.section_details(candidate.name)]

    def page_details(self, source_url: str) -> tuple[str, str, list[str]]:
        return self.wikipedia.page_details(source_url)

    def section_details(self, title: str) -> list[dict[str, object]]:
        return self.wikipedia.section_details(title)

    def wikidata_details(self, source_url: str) -> tuple[str, str, list[dict[str, str]]]:
        return WikidataProvider().entity_details(source_url)


def safe_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")
    return slug[:64].rstrip("-") or "subject"


def depth_for_level(level: str) -> Literal["beginner", "intermediate", "advanced"]:
    if level in {"postgraduate", "phd", "professional"}:
        return "advanced"
    if level == "undergraduate":
        return "intermediate"
    return "beginner"


_EXCLUDED_SECTIONS = re.compile(
    r"\b(history|conference|conferences|publication|publications|"
    r"references|further reading|see also|external links|awards?|gallery|"
    r"issues and limitations|limitations|criticism)\b",
    re.I,
)
_ADVANCED_LEVELS = {"postgraduate", "phd", "professional"}
_SECTION_ORDER = (
    (("introduction", "overview", "basic", "fundamental", "getting started"), 0),
    (("concept", "principle", "structure", "syntax", "type", "model"), 1),
    (("technique", "method", "feature", "design", "architecture", "implementation"), 2),
    (("application", "use", "example", "ecosystem"), 3),
    (("advanced", "internals", "optimization", "research"), 4),
)


def _section_rank(title: str) -> int:
    folded = title.casefold()
    for signals, rank in _SECTION_ORDER:
        if any(signal in folded for signal in signals):
            return rank
    return 2


def rank_topic_materials(
    sections: Sequence[dict[str, object]],
    education_level: str,
    category_depth: int = 0,
) -> list[dict[str, object]]:
    """Drop non-learning sections and order useful headings from basic to advanced."""
    unique: dict[str, dict[str, object]] = {}
    for original_index, section in enumerate(sections):
        title = str(section.get("title", "")).strip()
        if not title or (
            _EXCLUDED_SECTIONS.search(title)
            and not ("criticism" in title.casefold() and education_level in _ADVANCED_LEVELS)
        ):
            continue
        folded = title.casefold()
        section_rank = _section_rank(title)
        link_count = section.get("link_count", 0)
        link_bonus = 0.2 if isinstance(link_count, int) and 1 <= link_count <= 30 else 0.0
        depth = section.get("depth", 1)
        section_depth = float(depth) if isinstance(depth, (int, float)) else 1.0
        specificity = min(max(category_depth, 0), 10) * 0.01
        score = section_rank - link_bonus + min(section_depth, 5) * 0.03 + specificity
        unique.setdefault(
            folded,
            {
                **section,
                "title": title,
                "_rank": score,
                "_original_index": original_index,
            },
        )

    def topic_sort_key(section: dict[str, object]) -> tuple[float, int]:
        rank = section.get("_rank")
        original_index = section.get("_original_index")
        if not isinstance(rank, (int, float)) or not isinstance(original_index, int):
            raise ValueError("Topic ranking metadata is invalid")
        return float(rank), original_index

    ordered = sorted(unique.values(), key=topic_sort_key)[:12]
    return [
        {key: value for key, value in section.items() if not key.startswith("_")}
        for section in ordered
    ]


def order_topic_sections(
    sections: Sequence[str], education_level: str = "middle_school"
) -> list[str]:
    """Compatibility helper for callers with headings but no section metadata."""
    materials: list[dict[str, object]] = [{"title": title} for title in sections]
    return [str(section["title"]) for section in rank_topic_materials(materials, education_level)]
