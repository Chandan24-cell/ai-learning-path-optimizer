"""Provider and question-generation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Candidate:
    name: str
    summary: str
    source: str
    source_url: str
    confidence: float


@dataclass(frozen=True)
class Book:
    title: str
    authors: tuple[str, ...]
    edition: str | None
    publisher: str | None
    year: int | None
    isbn: tuple[str, ...]
    link: str


class SubjectProvider(Protocol):
    name: str

    def search(self, query: str, level: str) -> list[Candidate]: ...


class QuestionGenerator(Protocol):
    """Generate only quality-checked questions from stored, cited source material."""

    def generate_questions(
        self,
        subject: str,
        topic: str,
        *,
        source_extract: str = "",
        source_url: str = "",
        linked_terms: list[str] | None = None,
        sibling_topics: list[str] | None = None,
        sibling_terms: list[str] | None = None,
        sibling_extracts: list[str] | None = None,
        wikidata_facts: list[dict[str, str]] | None = None,
        sibling_facts: list[dict[str, str]] | None = None,
        topic_order: int = 1,
        topic_count: int = 1,
        learner_level: float = 50.0,
    ) -> list[dict[str, object]]: ...
