"""Preview rule-based questions from current Wikipedia source material."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.discovery.providers import WikipediaProvider
from app.services.questions.rule_based import GeneratedQuestion, RuleBasedQuestionGenerator


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def preview_questions(query: str, limit: int = 10) -> list[GeneratedQuestion]:
    provider = WikipediaProvider()
    candidates = provider.search(query, "undergraduate")
    if not candidates:
        raise RuntimeError("Wikipedia returned no matching subject.")
    generator = RuleBasedQuestionGenerator()
    generated: list[GeneratedQuestion] = []
    seen: set[tuple[str, str]] = set()

    for candidate in candidates:
        sections = provider.section_details(candidate.name)
        sibling_titles = [str(section["title"]) for section in sections]
        sibling_terms = [
            term for sibling in sections for term in _strings(sibling.get("linked_terms"))
        ]
        for index, section in enumerate(sections):
            extract = str(section.get("extract", "")).strip()
            complete_sentences = re.findall(r"[^.!?]+[.!?]", extract)
            for sentence in complete_sentences:
                if not 8 <= len(sentence.split()) <= 30:
                    continue
                questions = generator.generate_questions(
                    candidate.name,
                    str(section["title"]),
                    source_extract=sentence.strip(),
                    source_url=candidate.source_url,
                    linked_terms=[term for term in _strings(section.get("linked_terms"))],
                    sibling_topics=sibling_titles,
                    sibling_terms=sibling_terms,
                    topic_order=index + 1,
                    topic_count=len(sections),
                    learner_level=60.0,
                )
                for question in questions:
                    identity = (candidate.source_url, question["text"])
                    if identity in seen:
                        continue
                    seen.add(identity)
                    generated.append(question)
                    if len(generated) >= limit:
                        return generated
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print up to 10 rule-generated questions for a subject name."
    )
    parser.add_argument("subject", help="Subject or topic to search on Wikipedia")
    args = parser.parse_args()

    try:
        questions = preview_questions(args.subject)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Question preview failed: {exc}", file=sys.stderr)
        return 1

    if not questions:
        print("No source-backed questions passed the quality filters.")
        return 0

    for number, question in enumerate(questions, start=1):
        answer = question["options"][question["correct_option"]]
        print(f"{number}. [{question['question_type']}; difficulty {question['difficulty']:.1f}]")
        print(f"   {question['text']}")
        for option_index, option in enumerate(question["options"]):
            marker = " *" if option_index == question["correct_option"] else ""
            print(f"   - {option}{marker}")
        print(f"   Source: {question['source_url']}")
        print(f"   Answer: {answer}")
        print(f"   Evidence: {question['source_sentence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
