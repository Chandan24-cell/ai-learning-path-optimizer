"""Small public API adapters; returned text is metadata, never page content."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urlencode, urlsplit

from app.services.discovery.interfaces import Book, Candidate
from app.services.discovery.safety import fetch_json, validate_provider_url


def clean_text(value: str, limit: int = 280) -> str:
    value = re.sub(r"<[^>]*>", " ", value)
    value = html.unescape(value)
    value = "".join(char for char in value if char.isprintable())
    return " ".join(value.split())[:limit]


class WikipediaProvider:
    name = "Wikipedia"
    base_url = "https://en.wikipedia.org/w/api.php"

    def search(self, query: str, level: str) -> list[Candidate]:
        params = urlencode(
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": 6,
                "prop": "extracts|info",
                "exintro": 1,
                "explaintext": 1,
                "exchars": 280,
                "inprop": "url",
                "format": "json",
                "formatversion": 2,
            }
        )
        pages = fetch_json(f"{self.base_url}?{params}").get("query", {}).get("pages", [])
        candidates = []
        for page in pages:
            title = clean_text(str(page.get("title", "")), 120)
            source_url = str(page.get("fullurl", ""))
            if title and source_url:
                candidates.append(
                    Candidate(
                        title,
                        clean_text(str(page.get("extract", ""))),
                        self.name,
                        source_url,
                        0.82,
                    )
                )
        return candidates

    def sections(self, title: str) -> list[str]:
        return [str(item["title"]) for item in self.section_details(title)]

    def section_details(self, title: str) -> list[dict[str, object]]:
        params = urlencode(
            {
                "action": "parse",
                "page": title,
                "prop": "sections|text",
                "format": "json",
                "formatversion": 2,
            }
        )
        parsed = fetch_json(f"{self.base_url}?{params}").get("parse", {})
        headings = {
            str(section.get("index")): (
                clean_text(str(section.get("line", "")), 160),
                section.get("toclevel", 1),
            )
            for section in parsed.get("sections", [])
        }
        raw_html = parsed.get("text", "")
        if isinstance(raw_html, dict):
            raw_html = raw_html.get("*", "")
        parser = _WikipediaSectionParser()
        parser.feed(str(raw_html))
        result = []
        for section in parser.sections:
            title_text, depth = headings.get(
                section["index"], (section["title"], section.get("depth", 1))
            )
            if title_text:
                result.append(
                    {
                        "title": title_text,
                        "extract": clean_text(section["text"], 280),
                        "linked_terms": section["terms"][:12],
                        "link_count": section["link_count"],
                        "depth": depth,
                    }
                )
        return result[:40]

    def page_details(self, source_url: str) -> tuple[str, str, list[str]]:
        hostname = validate_provider_url(source_url)
        parts = urlsplit(source_url)
        if hostname != "en.wikipedia.org" or not parts.path.startswith("/wiki/"):
            raise ValueError("Choose a Wikipedia article to build a topic path")
        title = unquote(parts.path.removeprefix("/wiki/").split("/", 1)[0])
        if not title or ":" in title:
            raise ValueError("Choose a standard Wikipedia article")
        params = urlencode(
            {
                "action": "query",
                "titles": title,
                "prop": "extracts|categories|info",
                "exintro": 1,
                "explaintext": 1,
                "exchars": 280,
                "inprop": "url",
                "cllimit": 8,
                "format": "json",
                "formatversion": 2,
            }
        )
        page = fetch_json(f"{self.base_url}?{params}").get("query", {}).get("pages", [{}])[0]
        name = clean_text(str(page.get("title", "")), 120)
        categories = [
            clean_text(str(category.get("title", "")).removeprefix("Category:"), 120)
            for category in page.get("categories", [])
        ]
        return name, clean_text(str(page.get("extract", ""))), categories


class WikidataProvider:
    name = "Wikidata"
    base_url = "https://www.wikidata.org/w/api.php"

    def search(self, query: str, level: str) -> list[Candidate]:
        params = urlencode(
            {
                "action": "wbsearchentities",
                "search": query,
                "language": "en",
                "format": "json",
                "limit": 4,
            }
        )
        items = fetch_json(f"{self.base_url}?{params}").get("search", [])
        candidates = []
        for item in items:
            entity_id = str(item.get("id", ""))
            if not re.fullmatch(r"Q\d+", entity_id):
                continue
            candidates.append(
                Candidate(
                    clean_text(str(item.get("label", "")), 120),
                    clean_text(str(item.get("description", ""))),
                    self.name,
                    f"https://www.wikidata.org/wiki/{entity_id}",
                    0.68,
                )
            )
        return candidates

    def entity_details(self, source_url: str) -> tuple[str, str, list[dict[str, str]]]:
        hostname = validate_provider_url(source_url)
        parts = urlsplit(source_url)
        match = re.search(r"/(?:wiki/|entity/)(Q\d+)$", parts.path)
        if hostname != "www.wikidata.org" or match is None:
            raise ValueError("Choose a Wikidata entity page")
        entity_id = match.group(1)
        body = fetch_json(f"https://www.wikidata.org/wiki/Special:EntityData/{entity_id}.json")
        entity = body.get("entities", {}).get(entity_id)
        if not isinstance(entity, dict):
            raise ValueError("The Wikidata entity has no usable record")
        name = clean_text(str(entity.get("labels", {}).get("en", {}).get("value", "")), 120)
        summary = clean_text(str(entity.get("descriptions", {}).get("en", {}).get("value", "")))
        properties = {
            "P31": "instance of",
            "P170": "creator",
            "P571": "inception",
            "P178": "developer",
            "P277": "programming language",
            "P2566": "programming paradigm",
            "P400": "platform",
            "P366": "use",
        }
        facts: list[dict[str, str]] = []
        labels: dict[str, str] = {}
        claims = entity.get("claims", {})
        for property_id in properties:
            for claim in claims.get(property_id, [])[:5]:
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if isinstance(value, dict) and re.fullmatch(r"Q\d+", str(value.get("id", ""))):
                    labels.setdefault(str(value["id"]), "")
        if labels:
            label_params = urlencode(
                {
                    "action": "wbgetentities",
                    "ids": "|".join(labels),
                    "props": "labels",
                    "languages": "en",
                    "format": "json",
                }
            )
            label_body = fetch_json(f"{self.base_url}?{label_params}")
            for value_id, value_entity in label_body.get("entities", {}).items():
                labels[value_id] = clean_text(
                    str(value_entity.get("labels", {}).get("en", {}).get("value", "")), 80
                )
        for property_id, property_name in properties.items():
            for claim in claims.get(property_id, [])[:5]:
                value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if isinstance(value, dict) and value.get("time"):
                    year_match = re.search(r"[+-]?(\d{4})-", str(value["time"]))
                    if year_match:
                        facts.append(
                            {
                                "property": property_name,
                                "value": year_match.group(1),
                                "value_type": "year",
                            }
                        )
                elif isinstance(value, dict) and str(value.get("id", "")) in labels:
                    label = labels[str(value["id"])]
                    if label:
                        facts.append(
                            {
                                "property": property_name,
                                "value": label,
                                "value_type": "entity",
                            }
                        )
        return name, summary, facts[:20]


class _WikipediaSectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[dict[str, Any]] = []
        self.index = ""
        self.title = ""
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.term_parts: list[str] = []
        self.terms: list[str] = []
        self.heading = False
        self.term_depth = 0
        self.link_count = 0
        self.depth = 1
        self.skip_elements: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "section" and attributes.get("data-mw-section-id"):
            self._finish_section()
            self.index = str(attributes["data-mw-section-id"])
        if tag in {"h2", "h3", "h4"}:
            if self.heading:
                self.heading = False
            if self.index and self.title:
                self._finish_section()
            if not self.index:
                self.index = str(len(self.sections) + 1)
            self.title_parts = []
            self.heading = True
        if tag in {"sup", "table", "script", "style", "nav"} or {
            "navbox",
            "metadata",
            "noprint",
        }.intersection(classes):
            self.skip_elements.append(tag)
        if not self.heading and not self.skip_elements and tag == "a":
            self.link_count += 1
        if not self.heading and not self.skip_elements and (tag == "a" or tag in {"b", "strong"}):
            if self.term_depth == 0:
                self.term_parts = []
            self.term_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.skip_elements:
            reverse_index = self.skip_elements[::-1].index(tag)
            del self.skip_elements[len(self.skip_elements) - reverse_index - 1 :]
        if not self.heading and (tag == "a" or tag in {"b", "strong"}) and self.term_depth:
            self.term_depth -= 1
            if self.term_depth == 0:
                term = clean_text(" ".join(self.term_parts), 80)
                if term and len(term.split()) <= 5:
                    self.terms.append(term)
        if self.heading and tag in {"h2", "h3", "h4"}:
            self.heading = False
            self.title = clean_text(" ".join(self.title_parts), 160)
        if tag == "section":
            self._finish_section()

    def handle_data(self, data: str) -> None:
        if self.skip_elements:
            return
        if self.heading:
            self.title_parts.append(data)
        elif self.index:
            self.text_parts.append(data)
            if self.term_depth:
                self.term_parts.append(data)

    def _finish_section(self) -> None:
        if self.index and self.title:
            text = clean_text(" ".join(self.text_parts), 280)
            self.sections.append(
                {
                    "index": self.index,
                    "title": self.title,
                    "text": text,
                    "terms": list(dict.fromkeys(self.terms)),
                    "link_count": self.link_count,
                    "depth": self.depth,
                }
            )
        self.text_parts = []
        self.terms = []
        self.link_count = 0
        self.depth = 1
        self.index = ""
        self.title = ""


class OpenLibraryProvider:
    name = "Open Library"
    base_url = "https://openlibrary.org/search.json"

    def search_books(self, query: str) -> list[Book]:
        params = urlencode(
            {
                "q": query,
                "limit": 10,
                "fields": "title,author_name,edition_key,publisher,first_publish_year,isbn,key",
            }
        )
        documents = fetch_json(f"{self.base_url}?{params}").get("docs", [])
        return [self._book(document) for document in documents if document.get("title")]

    @staticmethod
    def _book(document: dict[str, Any]) -> Book:
        work_key = str(document.get("key", ""))
        edition_keys = document.get("edition_key") or []
        publishers = document.get("publisher") or []
        isbns = document.get("isbn") or []
        year = document.get("first_publish_year")
        return Book(
            title=clean_text(str(document.get("title", "")), 200),
            authors=tuple(
                clean_text(str(author), 100) for author in document.get("author_name", [])[:5]
            ),
            edition=clean_text(str(edition_keys[0]), 80) if edition_keys else None,
            publisher=clean_text(str(publishers[0]), 120) if publishers else None,
            year=year if isinstance(year, int) else None,
            isbn=tuple(clean_text(str(isbn), 32) for isbn in isbns[:5]),
            link=f"https://openlibrary.org{work_key}" if work_key.startswith("/works/") else "",
        )


class OpenAlexProvider:
    name = "OpenAlex"
    base_url = "https://api.openalex.org/works"

    def search(self, query: str, level: str) -> list[Candidate]:
        if level not in {"postgraduate", "phd"}:
            return []
        params = urlencode({"search": query, "per-page": 5, "select": "id,title,primary_topic"})
        works = fetch_json(f"{self.base_url}?{params}").get("results", [])
        return [
            Candidate(
                name=clean_text(
                    str((work.get("primary_topic") or {}).get("display_name", query)), 120
                ),
                summary=clean_text(str(work.get("title", ""))),
                source=self.name,
                source_url=str(work.get("id", "")),
                confidence=0.62,
            )
            for work in works
            if work.get("id") and work.get("title")
        ]
