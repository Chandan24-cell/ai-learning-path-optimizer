from __future__ import annotations

from urllib.error import URLError

import pytest

from app.services.discovery import providers, safety
from app.services.discovery.interfaces import Book, Candidate
from app.services.discovery.providers import (
    OpenAlexProvider,
    OpenLibraryProvider,
    WikidataProvider,
    WikipediaProvider,
    clean_text,
)
from app.services.discovery.safety import DiscoveryUnavailable
from app.services.discovery.service import (
    DiscoveryService,
    depth_for_level,
    order_topic_sections,
    safe_slug,
)


def test_provider_adapters_extract_only_public_metadata(monkeypatch):
    calls = []
    responses = [
        {
            "query": {
                "pages": [
                    {
                        "title": "<b>Solar System</b>",
                        "fullurl": "https://en.wikipedia.org/wiki/Solar_System",
                        "extract": "  A <em>short</em> description. ",
                    }
                ]
            }
        },
        {
            "parse": {
                "sections": [
                    {"index": "1", "line": "Overview", "toclevel": 1},
                    {"index": "2", "line": "References", "toclevel": 1},
                    {"index": "3", "line": "Planets", "toclevel": 1},
                ],
                "text": (
                    '<section data-mw-section-id="1"><h2>Overview</h2>'
                    "<p>Short overview.</p></section>"
                    '<section data-mw-section-id="2"><h2>References</h2>'
                    "<p>Reference section.</p></section>"
                    '<section data-mw-section-id="3"><h2>Planets</h2>'
                    "<p>Planet section.</p></section>"
                ),
            }
        },
        {
            "query": {
                "pages": [
                    {
                        "title": "Solar System",
                        "extract": " A short overview ",
                        "categories": [{"title": "Category:Planetary systems"}],
                    }
                ]
            }
        },
        {
            "search": [
                {
                    "id": "Q333",
                    "label": "Astronomy",
                    "description": "<script>Stars</script>",
                    "url": "https://www.wikidata.org/wiki/Q333",
                }
            ]
        },
        {
            "docs": [
                {
                    "key": "/works/OL123W",
                    "title": "<i>Space Science</i>",
                    "author_name": ["A. Author"],
                    "edition_key": ["OL456M"],
                    "publisher": ["Example Press"],
                    "first_publish_year": 2020,
                    "isbn": ["1234567890"],
                }
            ]
        },
        {
            "results": [
                {
                    "id": "https://openalex.org/W123",
                    "title": "Research paper title",
                    "primary_topic": {"display_name": "Astrophysics"},
                }
            ]
        },
    ]

    def fake_fetch(url):
        calls.append(url)
        return responses[len(calls) - 1]

    monkeypatch.setattr(providers, "fetch_json", fake_fetch)
    wiki = WikipediaProvider()
    candidates = wiki.search("solar system", "high_school")
    assert candidates[0].name == "Solar System"
    assert candidates[0].summary == "A short description."
    assert wiki.sections("Solar System") == ["Overview", "References", "Planets"]
    assert wiki.page_details("https://en.wikipedia.org/wiki/Solar_System") == (
        "Solar System",
        "A short overview",
        ["Planetary systems"],
    )
    wikidata = WikidataProvider().search("astronomy", "high_school")
    assert wikidata[0].summary == "Stars"

    book = OpenLibraryProvider().search_books("space science")[0]
    assert book == Book(
        title="Space Science",
        authors=("A. Author",),
        edition="OL456M",
        publisher="Example Press",
        year=2020,
        isbn=("1234567890",),
        link="https://openlibrary.org/works/OL123W",
    )
    assert OpenLibraryProvider._book({"title": "No record", "key": "/authors/A1"}).link == ""

    openalex = OpenAlexProvider()
    assert openalex.search("space", "high_school") == []
    research = openalex.search("space", "phd")
    assert research[0].name == "Astrophysics"
    assert len(calls) == 6


def test_discovery_service_deduplicates_and_orders_provider_results():
    candidate = Candidate("Physics", "summary", "Wikipedia", "https://example.org/physics", 0.8)

    class Provider:
        name = "mock"

        def __init__(self, result):
            self.result = result

        def search(self, query, level):
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

    class Books:
        def search_books(self, query):
            raise DiscoveryUnavailable("offline")

    class Wiki:
        def section_details(self, title):
            return [{"title": "Basics"}, {"title": "Advanced"}]

        def page_details(self, url):
            return ("Physics", "Overview", [])

    service = DiscoveryService(
        providers=[
            Provider([candidate]),
            Provider(
                [
                    candidate,
                    Candidate("Astronomy", "summary", "Wikidata", "https://example.org/astro", 0.9),
                ]
            ),
            Provider(DiscoveryUnavailable("offline")),
        ],
        books=Books(),
        wikipedia=Wiki(),
    )
    results, errors = service.search("science", "phd")
    assert [item.name for item in results] == ["Astronomy", "Physics"]
    assert errors == ["mock is temporarily unavailable."]
    assert service.search_books("science") == ([], ["Open Library is temporarily unavailable."])
    assert service.preview(candidate) == ["Basics", "Advanced"]
    assert service.preview(Candidate("Math", "", "Wikidata", "https://example.org", 0.5)) == [
        "Math"
    ]
    assert service.page_details("https://en.wikipedia.org/wiki/Physics") == (
        "Physics",
        "Overview",
        [],
    )
    assert safe_slug("Math & Écology!") == "math-ecology"
    assert safe_slug("***") == "subject"
    assert depth_for_level("phd") == "advanced"
    assert depth_for_level("undergraduate") == "intermediate"
    assert depth_for_level("middle_school") == "beginner"
    assert order_topic_sections(["Core", " Core ", "", "Next"]) == ["Core", "Next"]
    assert clean_text("<b>A &amp; B</b>\n") == "A & B"


class FakeHeaders:
    def __init__(self, content_type: str):
        self.content_type = content_type

    def get_content_type(self) -> str:
        return self.content_type


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json"):
        self.body = body
        self.headers = FakeHeaders(content_type)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _limit: int) -> bytes:
        return self.body


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def open(self, request, timeout):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_fetch_json_is_bounded_cached_and_reports_provider_failures(monkeypatch):
    safety.clear_cache()
    monkeypatch.setattr(safety, "_verify_public_dns", lambda _hostname: None)
    opener = FakeOpener(FakeResponse(b'{"items":[1]}'))
    monkeypatch.setattr(safety, "build_opener", lambda *_handlers: opener)
    url = "https://en.wikipedia.org/w/api.php?unit-test=success"
    result = safety.fetch_json(url)
    result["items"].append(2)
    assert safety.fetch_json(url) == {"items": [1]}
    assert opener.calls == 1

    cases = [
        (FakeResponse(b"{}", "text/html"), "unexpected response"),
        (FakeResponse(b"x" * (safety.MAX_RESPONSE_BYTES + 1)), "exceeded the size limit"),
        (FakeResponse(b"not-json"), "invalid JSON"),
        (FakeOpener(URLError("offline")), "temporarily unavailable"),
    ]
    for index, (response, message) in enumerate(cases):
        safety.clear_cache()
        active_opener = response if isinstance(response, FakeOpener) else FakeOpener(response)
        monkeypatch.setattr(
            safety,
            "build_opener",
            lambda *_handlers, opener=active_opener: opener,
        )
        with pytest.raises(DiscoveryUnavailable, match=message):
            safety.fetch_json(f"https://en.wikipedia.org/w/api.php?unit-test={index}")
    safety.clear_cache()
