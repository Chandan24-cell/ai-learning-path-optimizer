"""Quality-filtered recall questions from short, cited source extracts."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import UTC, datetime
from typing import TypedDict
from urllib.parse import urlsplit

GENERATOR_VERSION = "rule-based-wikipedia-wikidata-v1"
WIKIPEDIA_ATTRIBUTION = "Wikipedia, CC BY-SA 4.0"
WIKIDATA_ATTRIBUTION = "Wikidata, CC0"
LIMITED_QUIZ_THRESHOLD = 5
MAX_SOURCE_EXTRACT = 280
_WORD = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")
_BAD_CITATION = re.compile(r"\[\s*\d+\s*\]|\[(?:citation needed|note \d+)\]", re.I)
_PRONOUN_START = re.compile(r"^\s*(?:it|this|they)\b", re.I)
_ALLOWED_SENTENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ,.;:'!?&/_-]*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class GeneratedQuestion(TypedDict):
    question_type: str
    difficulty: float
    text: str
    options: list[str]
    correct_option: int
    explanation: str
    source_sentence: str
    source_url: str
    attribution: str
    generated_at: datetime
    generator_version: str
    status: str


def clean_source_text(value: str, limit: int = MAX_SOURCE_EXTRACT) -> str:
    """Strip markup and controls while retaining citation markers for rejection."""
    value = html.unescape(re.sub(r"<[^>]*>", " ", value))
    value = unicodedata.normalize("NFKD", value)
    value = value.replace("\u2019", "'").replace("\u2018", "'")
    value = value.replace("\u201c", '"').replace("\u201d", '"').replace("\u2013", "-")
    value = value.encode("ascii", "ignore").decode("ascii")
    value = "".join(character for character in value if character.isprintable())
    return " ".join(value.split())[:limit]


def source_sentences(extract: str) -> list[str]:
    normalized = clean_source_text(extract)
    return [sentence.strip() for sentence in _SENTENCE_SPLIT.split(normalized) if sentence.strip()]


def sentence_passes_quality(sentence: str) -> bool:
    words = _WORD.findall(sentence)
    return (
        8 <= len(words) <= 30
        and not _PRONOUN_START.search(sentence)
        and "(" not in sentence
        and ")" not in sentence
        and not _BAD_CITATION.search(sentence)
        and _ALLOWED_SENTENCE.fullmatch(sentence) is not None
    )


def answer_is_masked(answer: str, question: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(answer)}(?![A-Za-z0-9])", question, re.I) is None


def options_pass_quality(
    options: list[str],
    correct_option: int,
    question: str,
    *,
    fact_type: str | None = None,
) -> bool:
    is_boolean_pair = len(options) == 2 and {value.casefold() for value in options} == {
        "true",
        "false",
    }
    if (len(options) != 4 and not is_boolean_pair) or not 0 <= correct_option < len(options):
        return False
    normalized = [clean_source_text(option, 80).strip() for option in options]
    if any(not option for option in normalized):
        return False
    if len({option.casefold() for option in normalized}) != len(normalized):
        return False
    if not answer_is_masked(normalized[correct_option], question):
        return False
    option_kinds = {
        "boolean"
        if option.casefold() in {"true", "false"}
        else "number"
        if re.fullmatch(r"-?\d+(?:\.\d+)?", option)
        else "text"
        for option in normalized
    }
    if len(option_kinds) != 1:
        return False
    lengths = [len(option) for option in normalized]
    if max(lengths) > min(lengths) * 2:
        return False
    if fact_type == "year":
        return all(re.fullmatch(r"\d{3,4}", option) for option in normalized)
    if fact_type == "entity":
        return all(re.fullmatch(r"[A-Z][A-Za-z0-9 -]{1,48}", option) for option in normalized)
    return True


def _mask_once(text: str, term: str) -> str | None:
    matches = list(re.finditer(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.I))
    if len(matches) != 1:
        return None
    match = matches[0]
    return f"{text[: match.start()]}_____{text[match.end() :]}"


def _stable_options(answer: str, distractors: list[str], seed: str) -> tuple[list[str], int]:
    choices = [answer, *distractors]
    choices.sort(
        key=lambda value: hashlib.sha256(f"{seed}|{value.casefold()}".encode()).hexdigest()
    )
    return choices, next(
        index for index, value in enumerate(choices) if value.casefold() == answer.casefold()
    )


def _question(
    *,
    question_type: str,
    difficulty: float,
    text: str,
    options: list[str],
    correct_option: int,
    explanation: str,
    source_sentence: str,
    source_url: str,
    attribution: str,
    fact_type: str | None = None,
) -> GeneratedQuestion | None:
    if not sentence_passes_quality(source_sentence):
        return None
    if question_type != "true_false" and not sentence_passes_quality(text):
        return None
    if not options_pass_quality(options, correct_option, text, fact_type=fact_type):
        return None
    return GeneratedQuestion(
        question_type=question_type,
        difficulty=difficulty,
        text=text,
        options=options,
        correct_option=correct_option,
        explanation=explanation[:280],
        source_sentence=source_sentence[:280],
        source_url=source_url[:2000],
        attribution=attribution,
        generated_at=datetime.now(UTC),
        generator_version=GENERATOR_VERSION,
        status=f"auto-generated from {attribution.split(',')[0]}, unreviewed",
    )


def _noun_phrases(sentence: str) -> list[str]:
    candidates = re.findall(
        r"\b(?:a|an|the)\s+([A-Za-z]+(?:[- ][A-Za-z]+){1,2})\b",
        sentence,
        flags=re.I,
    )
    return list(dict.fromkeys(candidate.strip(" .,:;") for candidate in candidates))


def _fact_question(
    subject: str,
    fact: dict[str, str],
    sibling_facts: list[dict[str, str]],
    source_url: str,
) -> GeneratedQuestion | None:
    value = clean_source_text(fact.get("value", ""), 80).strip()
    property_name = clean_source_text(fact.get("property", ""), 80).strip().lower()
    fact_type = fact.get("value_type", "")
    if not value or not property_name or fact_type not in {"year", "entity"}:
        return None
    distractors = []
    for candidate in sibling_facts:
        if candidate.get("value_type") != fact_type:
            continue
        distractor = clean_source_text(candidate.get("value", ""), 80).strip()
        if distractor.casefold() != value.casefold() and distractor not in distractors:
            distractors.append(distractor)
    if len(distractors) < 3:
        return None
    distractors = distractors[:3]
    question = f"According to Wikidata, which {property_name} is recorded for {subject}?"
    options, correct = _stable_options(value, distractors, question)
    source_sentence = (
        f"Wikidata records {value} as the {property_name} for {subject}."
        if len(_WORD.findall(f"Wikidata records {value} as the {property_name} for {subject}."))
        >= 8
        else (
            f"The Wikidata record lists {value} as the {property_name} for {subject} "
            "in its cited subject data."
        )
    )
    return _question(
        question_type="wikidata_fact",
        difficulty=5.0,
        text=question,
        options=options,
        correct_option=correct,
        explanation=source_sentence,
        source_sentence=source_sentence,
        source_url=source_url,
        attribution=WIKIDATA_ATTRIBUTION,
        fact_type=fact_type,
    )


class RuleBasedQuestionGenerator:
    """Create only questions that pass explicit content and distractor checks."""

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
    ) -> list[GeneratedQuestion]:
        del subject
        siblings = [clean_source_text(value, 80).strip() for value in sibling_topics or []]
        siblings = [value for value in siblings if value and value.casefold() != topic.casefold()]
        same_type_siblings = [clean_source_text(value, 80).strip() for value in sibling_terms or []]
        same_type_siblings = [
            value for value in same_type_siblings if value and value.casefold() != topic.casefold()
        ]
        sentences = [
            sentence
            for sentence in source_sentences(source_extract)
            if sentence_passes_quality(sentence)
        ]
        source_host = (urlsplit(source_url).hostname or "").lower()
        if not sentences or source_host not in {"en.wikipedia.org", "www.wikidata.org"}:
            return []

        position = (max(topic_order - 1, 0) / max(topic_count - 1, 1)) * 0.5
        level_adjustment = min(max(float(learner_level), 0.0), 100.0) / 100.0 * 0.5
        questions: list[GeneratedQuestion] = []
        attribution = (
            WIKIDATA_ATTRIBUTION if source_host == "www.wikidata.org" else WIKIPEDIA_ATTRIBUTION
        )

        for sentence in sentences:
            masked = _mask_once(sentence, topic)
            if masked and len(siblings) >= 3:
                options, correct = _stable_options(
                    topic, siblings[:3], f"definition:{topic}:{sentence}"
                )
                prompt = f"Definition: {masked}"
                generated = _question(
                    question_type="definition_to_term",
                    difficulty=min(5.0, 1.0 + position + level_adjustment),
                    text=prompt,
                    options=options,
                    correct_option=correct,
                    explanation=sentence,
                    source_sentence=sentence,
                    source_url=source_url,
                    attribution=attribution,
                )
                if generated:
                    questions.append(generated)

            terms = [*(linked_terms or []), *_noun_phrases(sentence)]
            for term in dict.fromkeys(clean_source_text(value, 60).strip() for value in terms):
                masked_term = _mask_once(sentence, term)
                distractor_source = same_type_siblings or siblings
                distractors = [
                    sibling
                    for sibling in distractor_source
                    if sibling.casefold() != term.casefold()
                    and len(term) / 2 <= len(sibling) <= len(term) * 2
                ]
                if not masked_term or len(distractors) < 3:
                    continue
                options, correct = _stable_options(
                    term, distractors[:3], f"cloze:{topic}:{sentence}:{term}"
                )
                prompt = f"Complete the cited sentence: {masked_term}"
                generated = _question(
                    question_type="cloze",
                    difficulty=min(5.0, 3.0 + position + level_adjustment),
                    text=prompt,
                    options=options,
                    correct_option=correct,
                    explanation=sentence,
                    source_sentence=sentence,
                    source_url=source_url,
                    attribution=attribution,
                )
                if generated:
                    questions.append(generated)
                break

            for truth, statement in ((True, sentence), (False, sentence)):
                if not truth:
                    replaceable = next(
                        (
                            sibling
                            for sibling in siblings
                            if _mask_once(sentence, topic) is not None
                        ),
                        None,
                    )
                    if replaceable is None:
                        continue
                    statement = re.sub(
                        rf"(?<![A-Za-z0-9]){re.escape(topic)}(?![A-Za-z0-9])",
                        replaceable,
                        sentence,
                        count=1,
                        flags=re.I,
                    )
                prompt = f"Statement: {statement}"
                options = ["True", "False"]
                correct = 0 if truth else 1
                if not options_pass_quality(options, correct, prompt):
                    continue
                if not sentence_passes_quality(sentence):
                    continue
                questions.append(
                    GeneratedQuestion(
                        question_type="true_false",
                        difficulty=min(5.0, 1.0 + position + level_adjustment),
                        text=prompt,
                        options=options,
                        correct_option=correct,
                        explanation=sentence,
                        source_sentence=sentence[:280],
                        source_url=source_url[:2000],
                        attribution=attribution,
                        generated_at=datetime.now(UTC),
                        generator_version=GENERATOR_VERSION,
                        status="auto-generated from Wikipedia, unreviewed",
                    )
                )

        for fact in wikidata_facts or []:
            generated = _fact_question(
                topic,
                fact,
                sibling_facts or [],
                source_url,
            )
            if generated:
                questions.append(generated)

        unique: dict[tuple[str, str, tuple[str, ...]], GeneratedQuestion] = {}
        for question in questions:
            key = (
                question["question_type"],
                question["text"].casefold(),
                tuple(option.casefold() for option in question["options"]),
            )
            unique.setdefault(key, question)
        return list(unique.values())[:20]


def limited_quiz(question_count: int) -> bool:
    return question_count < LIMITED_QUIZ_THRESHOLD


def adaptive_difficulty(
    question_difficulty: float,
    topic_order: int,
    topic_count: int,
    learner_level: float,
    mastery: float,
    previous_correct: bool | None,
) -> float:
    position = max(0.0, min(1.0, (topic_order - 1) / max(topic_count - 1, 1)))
    level = max(0.0, min(100.0, learner_level)) / 100.0
    mastery_adjustment = (max(0.0, min(1.0, mastery)) - 0.5) * 2.0
    recent_adjustment = (
        0.5 if previous_correct is True else -0.5 if previous_correct is False else 0
    )
    return round(
        max(
            1.0,
            min(
                5.0,
                question_difficulty
                + position * 0.4
                + level * 0.4
                + mastery_adjustment
                + recent_adjustment,
            ),
        ),
        2,
    )
