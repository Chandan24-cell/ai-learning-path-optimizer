"""Authenticated discovery search and personal subject creation."""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from threading import Lock
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user
from app.models_db import (
    Enrollment,
    LearnerProfile,
    Resource,
    Subject,
    Topic,
    TopicPrerequisite,
    User,
)
from app.profile_options import load_profile_options
from app.schemas import DiscoveredSubjectIn, ReferenceBookIn, SubjectManualIn
from app.services.discovery import DiscoveryService
from app.services.discovery.interfaces import Candidate
from app.services.discovery.providers import clean_text
from app.services.discovery.safety import DiscoveryUnavailable, validate_provider_url
from app.services.discovery.service import (
    depth_for_level,
    rank_topic_materials,
    safe_slug,
)
from app.services.subject_enrollment import enroll_user, ensure_enrollment_capacity

router = APIRouter(prefix="/api/discovery", tags=["subject discovery"])
manual_router = APIRouter(prefix="/api/subjects", tags=["subjects"])
_service = DiscoveryService()
_logger = logging.getLogger(__name__)
_request_lock = Lock()
_request_times: dict[int, deque[float]] = defaultdict(deque)
_REQUEST_LIMIT = 30
_WINDOW_SECONDS = 60

_LEVELS = {item["id"] for item in load_profile_options()["education_levels"]}


def _rate_limit(user_id: int) -> None:
    now = time.monotonic()
    with _request_lock:
        requests = _request_times[user_id]
        while requests and now - requests[0] >= _WINDOW_SECONDS:
            requests.popleft()
        if len(requests) >= _REQUEST_LIMIT:
            raise HTTPException(status_code=429, detail="Discovery limit reached; try again later")
        requests.append(now)


def _user_level(user: User, db: Session, requested: str | None) -> str:
    level = requested
    if level is None:
        profile = db.get(LearnerProfile, user.id)
        level = profile.education_level if profile else "middle_school"
    if level not in _LEVELS:
        raise HTTPException(status_code=422, detail="Choose a valid education level")
    return level


def _candidate_dict(candidate: Candidate) -> dict[str, object]:
    return {
        "name": candidate.name,
        "summary": clean_text(candidate.summary, 280),
        "source": candidate.source,
        "source_url": candidate.source_url,
        "confidence": candidate.confidence,
    }


def _book_dict(book) -> dict[str, object]:
    return {
        "title": book.title,
        "authors": list(book.authors),
        "edition": book.edition,
        "publisher": book.publisher,
        "year": book.year,
        "isbn": list(book.isbn),
        "link": book.link,
    }


@router.get("/search")
def search_subjects(
    q: str = Query(min_length=2, max_length=120),
    level: str | None = Query(default=None, max_length=40),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    _rate_limit(user.id)
    normalized_level = _user_level(user, db, level)
    try:
        candidates, errors = _service.search(q.strip(), normalized_level)
    except DiscoveryUnavailable:
        return {
            "results": [],
            "message": "Subject discovery is temporarily offline. Please try again later.",
        }
    return {
        "results": [_candidate_dict(candidate) for candidate in candidates],
        "errors": errors,
        "message": (
            "No subjects were found. Try another search." if not candidates and not errors else None
        ),
    }


@router.get("/books")
def search_books(
    q: str = Query(min_length=2, max_length=120),
    user: User = Depends(current_user),
) -> dict:
    _rate_limit(user.id)
    books, errors = _service.search_books(q.strip())
    return {
        "results": [_book_dict(book) for book in books],
        "errors": errors,
        "message": (
            "Open Library is temporarily offline. Please try again later."
            if errors and not books
            else "No books were found. Try another search."
            if not books
            else None
        ),
    }


@router.get("/preview")
def preview_subject(
    name: str = Query(min_length=2, max_length=120),
    source_url: str = Query(min_length=1, max_length=2000),
    level: str | None = Query(default=None, max_length=40),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    _rate_limit(user.id)
    normalized_level = _user_level(user, db, level)
    try:
        hostname = validate_provider_url(source_url)
        if hostname not in {"en.wikipedia.org", "www.wikidata.org", "openalex.org"}:
            raise ValueError("Choose a supported discovery source")
        if hostname == "en.wikipedia.org":
            materials = _service.section_details(name)
        elif hostname == "www.wikidata.org":
            entity_name, summary, _facts = _service.wikidata_details(source_url)
            materials = [{"title": entity_name or name, "extract": summary, "linked_terms": []}]
        else:
            materials = [{"title": name, "extract": "", "linked_terms": []}]
        materials = rank_topic_materials(materials, normalized_level)
    except DiscoveryUnavailable:
        return {"topics": [], "message": "The source is temporarily offline. Please try again."}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not materials:
        return {"topics": [], "message": "No topic outline is available for this result."}
    target_depth = depth_for_level(normalized_level)
    topics = [
        {
            "name": section["title"],
            "order": index + 1,
            "depth": "beginner"
            if index < len(materials) / 3
            else "intermediate"
            if index < 2 * len(materials) / 3
            else "advanced",
        }
        for index, section in enumerate(materials)
    ]
    return {
        "topics": topics,
        "target_depth": target_depth,
        "label": "Draft / auto-built from public sources, unreviewed",
        "message": None,
    }


@router.post("/subjects")
def create_discovered_subject(
    payload: DiscoveredSubjectIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    _rate_limit(user.id)
    return _create_discovered_subject(payload, user, db)


def _create_discovered_subject(
    payload: DiscoveredSubjectIn,
    user: User,
    db: Session,
) -> dict:
    if user.role != "student" or db.get(LearnerProfile, user.id) is None:
        raise HTTPException(status_code=409, detail="Complete learner onboarding first")
    manual_subject: Subject | None = None
    if payload.manual_subject_id:
        manual_subject = db.get(Subject, payload.manual_subject_id)
        if (
            manual_subject is None
            or manual_subject.source != "manual"
            or manual_subject.created_by != user.id
        ):
            raise HTTPException(status_code=404, detail="Manual subject not found")
        if db.query(Topic.id).filter_by(subject_id=manual_subject.id).first() is not None:
            raise HTTPException(
                status_code=409,
                detail="This manual subject already has a topic path",
            )
    try:
        hostname = validate_provider_url(payload.source_url)
        if hostname not in {"en.wikipedia.org", "www.wikidata.org", "openalex.org"}:
            raise ValueError("Choose a supported discovery result")
        if hostname == "en.wikipedia.org":
            name, summary, categories = _service.page_details(payload.source_url)
            materials = _service.section_details(name)
            source = "discovered"
            provider_name = "Wikipedia"
            wikidata_facts: list[dict[str, str]] = []
        elif hostname == "www.wikidata.org":
            name, summary, wikidata_facts = _service.wikidata_details(payload.source_url)
            categories = []
            materials = [
                {
                    "title": name,
                    "extract": summary,
                    "linked_terms": [],
                    "link_count": 0,
                    "depth": 1,
                }
            ]
            source = "discovered"
            provider_name = "Wikidata"
        else:
            name = clean_text(payload.name, 120)
            summary = "Discovered subject; source page provides its overview."
            categories = []
            materials = [
                {
                    "title": name,
                    "extract": "",
                    "linked_terms": [],
                    "link_count": 0,
                    "depth": 1,
                }
            ]
            source = "discovered"
            provider_name = "OpenAlex"
            wikidata_facts = []
    except DiscoveryUnavailable:
        raise HTTPException(
            status_code=503, detail="The discovery source is temporarily offline"
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if manual_subject is not None:
        name = manual_subject.name
    if not name:
        raise HTTPException(
            status_code=422, detail="The discovery result has no usable subject name"
        )
    profile = db.get(LearnerProfile, user.id)
    education_level = profile.education_level if profile else "middle_school"
    materials = rank_topic_materials(materials, education_level, len(categories))
    if not materials:
        materials = [
            {
                "title": f"Overview of {name}",
                "extract": summary if provider_name in {"Wikipedia", "Wikidata"} else "",
                "linked_terms": [],
                "link_count": 0,
                "depth": 1,
            }
        ]
    if not summary:
        summary = f"Draft path based on public source: {name}."
    summary = clean_text(summary, 280)
    base_slug = safe_slug(name)
    subject_id = manual_subject.id if manual_subject else f"web-{base_slug}-{user.id}"[:80]
    if manual_subject is None and db.get(Subject, subject_id):
        raise HTTPException(status_code=409, detail="You already added this discovered subject")
    ensure_enrollment_capacity(db, user.id, subject_id)
    depth = payload.target_depth or depth_for_level(education_level)
    retrieved_at = datetime.now(UTC)
    if manual_subject is None:
        subject = Subject(
            id=subject_id,
            name=name,
            description=summary,
            questions_status="No quiz yet; draft curriculum requires teacher review",
            source=source,
            status="draft",
            created_by=user.id,
            source_url=payload.source_url,
            retrieved_at=retrieved_at,
        )
        db.add(subject)
    else:
        manual_subject.description = summary
        manual_subject.questions_status = "No quiz yet; draft curriculum requires teacher review"
        manual_subject.source_url = payload.source_url
        manual_subject.retrieved_at = retrieved_at
    try:
        db.flush()
        prerequisite_id: str | None = None
        for index, material in enumerate(materials):
            title = clean_text(str(material.get("title", "")), 160)
            topic_slug = f"{index + 1}-{safe_slug(title)}"[:80].rstrip("-")
            topic_id = f"{subject_id}.{topic_slug}"
            topic_facts = wikidata_facts if index == 0 else []
            material_terms = material.get("linked_terms", [])
            if not isinstance(material_terms, list):
                material_terms = []
            link_count = material.get("link_count", 0)
            topic_provenance = {
                "provider": provider_name,
                "source_url": payload.source_url,
                "retrieved_at": retrieved_at.isoformat(),
                "categories": categories[:8] if index == 0 else [],
                "category_depth": len(categories) if index == 0 else 0,
                "outline_section": title,
                "linked_terms": [
                    clean_text(str(term), 80) for term in material_terms if isinstance(term, str)
                ][:12],
                "link_count": link_count if isinstance(link_count, int) else 0,
                "wikidata_facts": topic_facts,
            }
            topic = Topic(
                id=topic_id,
                subject_id=subject_id,
                slug=topic_slug,
                name=clean_text(title, 160),
                order=index + 1,
                source_url=payload.source_url,
                retrieved_at=retrieved_at,
                provenance=json.dumps(topic_provenance, ensure_ascii=True),
                source_extract=clean_text(str(material.get("extract", "")), 280) or None,
            )
            db.add(topic)
            db.flush()
            if prerequisite_id:
                db.add(
                    TopicPrerequisite(
                        topic_id=topic_id,
                        prerequisite_topic_id=prerequisite_id,
                    )
                )
            prerequisite_id = topic_id
            position_difficulty = (
                1.0 if len(materials) == 1 else 1.0 + 4.0 * index / (len(materials) - 1)
            )
            depth_adjustment = {"beginner": 0.0, "intermediate": 0.5, "advanced": 1.0}[depth]
            difficulty = min(5.0, round(position_difficulty + depth_adjustment, 1))
            resources = [
                (f"{provider_name}: {title}", payload.source_url, "article"),
                (
                    f"Search Wikibooks for: {title}",
                    f"https://en.wikibooks.org/wiki/Special:Search?{urlencode({'search': title})}",
                    "article",
                ),
                (
                    f"Search OpenStax for: {title}",
                    f"https://openstax.org/search?{urlencode({'q': title})}",
                    "article",
                ),
                (
                    f"Search MIT OpenCourseWare for: {title}",
                    f"https://ocw.mit.edu/search/?{urlencode({'q': title})}",
                    "article",
                ),
            ]
            for resource_index, (resource_title, url, resource_type) in enumerate(resources):
                resource_id = f"{topic_id}.reference-{resource_index + 1}"
                db.add(
                    Resource(
                        id=resource_id[:180],
                        topic_id=topic_id,
                        type=resource_type,
                        title=clean_text(resource_title, 200),
                        difficulty=difficulty,
                        duration=15,
                        url=url,
                        source_url=payload.source_url,
                        retrieved_at=retrieved_at,
                        provenance=json.dumps(
                            {
                                "provider": provider_name,
                                "source_url": payload.source_url,
                                "retrieved_at": retrieved_at.isoformat(),
                                "reference_search": resource_index > 0,
                            }
                        ),
                    )
                )
        target_subject = manual_subject or subject
        enrollment = enroll_user(db, user, target_subject, depth)
        enrollment.diagnostic_completed = False
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        _logger.exception("Failed to persist a discovered subject path")
        raise HTTPException(
            status_code=409, detail="A subject with this name already exists"
        ) from exc
    except HTTPException:
        db.rollback()
        raise
    return {
        "id": subject_id,
        "name": name,
        "source": manual_subject.source if manual_subject else source,
        "status": "draft",
        "label": "Draft / auto-built from public sources, unreviewed",
        "topic_count": len(materials),
        "education_level_used": education_level,
        "target_depth": depth,
        "source_url": payload.source_url,
        "retrieved_at": retrieved_at.isoformat(),
        "reference_book": None,
    }


def _attempt_manual_subject_path(subject: Subject, user: User, db: Session) -> dict:
    profile = db.get(LearnerProfile, user.id)
    level = profile.education_level if profile else "middle_school"
    offline = False
    candidates: list[Candidate] = []
    try:
        if os.environ.get("DISCOVERY_OFFLINE", "").casefold() in {"1", "true", "yes"}:
            offline = True
        else:
            candidates, errors = _service.search(subject.name, level)
            offline = bool(errors)
    except DiscoveryUnavailable:
        candidates = []
        offline = True

    for candidate in candidates:
        try:
            hostname = validate_provider_url(candidate.source_url)
        except ValueError:
            continue
        if hostname not in {"en.wikipedia.org", "www.wikidata.org", "openalex.org"}:
            continue
        try:
            path = _create_discovered_subject(
                DiscoveredSubjectIn(
                    name=candidate.name,
                    source_url=candidate.source_url,
                    manual_subject_id=subject.id,
                    target_depth=depth_for_level(level),
                ),
                user,
                db,
            )
            return {
                **path,
                "path_status": "built",
                "message": (
                    f"Draft learning path built with {path['topic_count']} topics. "
                    "Quiz questions are prepared when you open a topic."
                ),
            }
        except HTTPException as exc:
            if exc.status_code == 503:
                offline = True
                continue
            if exc.status_code == 422:
                continue
            raise

    if offline:
        message = (
            "Internet discovery is temporarily unavailable. Search again or pick from results "
            "to build this path."
        )
        path_status = "offline"
    else:
        message = (
            "No public topic path was found for this subject. Search again or pick from results "
            "to build this path."
        )
        path_status = "not_found"
    subject.description = message
    subject.questions_status = "No topic path yet; internet discovery needs another attempt"
    db.commit()
    return {
        "id": subject.id,
        "name": subject.name,
        "source": subject.source,
        "status": subject.status,
        "label": "Manual subject · no topic path yet",
        "topic_count": 0,
        "path_status": path_status,
        "message": message,
    }


def _attempt_pack_source_path(subject: Subject, user: User, db: Session) -> dict:
    topics = db.query(Topic).filter_by(subject_id=subject.id).order_by(Topic.order, Topic.id).all()
    if topics and all(topic.source_url and topic.source_extract for topic in topics):
        return {
            "path_status": "built",
            "topic_count": len(topics),
            "message": "Source-backed learning path is ready.",
        }
    profile = db.get(LearnerProfile, user.id)
    level = profile.education_level if profile else "middle_school"
    offline = False
    candidates: list[Candidate] = []
    try:
        if os.environ.get("DISCOVERY_OFFLINE", "").casefold() in {"1", "true", "yes"}:
            offline = True
        else:
            candidates, errors = _service.search(subject.name, level)
            offline = bool(errors)
    except DiscoveryUnavailable:
        candidates = []
        offline = True

    for candidate in candidates:
        try:
            hostname = validate_provider_url(candidate.source_url)
            if hostname != "en.wikipedia.org":
                continue
            source_name, summary, categories = _service.page_details(candidate.source_url)
            materials = rank_topic_materials(
                _service.section_details(source_name), level, len(categories)
            )
        except DiscoveryUnavailable, ValueError:
            offline = True
            continue
        if not materials:
            continue

        retrieved_at = datetime.now(UTC)
        for index, topic in enumerate(topics):
            material = materials[index % len(materials)]
            extract = clean_text(str(material.get("extract", "")), 280)
            if not extract:
                continue
            topic.source_url = candidate.source_url
            topic.retrieved_at = retrieved_at
            topic.source_extract = extract
            topic.quiz_status = "not_generated"
            topic.provenance = json.dumps(
                {
                    "provider": "Wikipedia",
                    "source_url": candidate.source_url,
                    "retrieved_at": retrieved_at.isoformat(),
                    "outline_section": material.get("title", topic.name),
                    "linked_terms": material.get("linked_terms", []),
                    "wikidata_facts": [],
                },
                ensure_ascii=True,
            )
            resource_id = f"{topic.id}.web-source"[:180]
            if db.get(Resource, resource_id) is None:
                db.add(
                    Resource(
                        id=resource_id,
                        topic_id=topic.id,
                        type="article",
                        title=f"Wikipedia: {material.get('title', topic.name)}"[:200],
                        difficulty=max(1.0, min(5.0, float(topic.order))),
                        duration=15,
                        url=candidate.source_url,
                        source_url=candidate.source_url,
                        retrieved_at=retrieved_at,
                        provenance=json.dumps(
                            {
                                "provider": "Wikipedia",
                                "source_url": candidate.source_url,
                                "retrieved_at": retrieved_at.isoformat(),
                            }
                        ),
                    )
                )
        subject.description = clean_text(summary, 280) or subject.description
        subject.source_url = candidate.source_url
        subject.retrieved_at = retrieved_at
        enrollment = db.get(Enrollment, (user.id, subject.id))
        if enrollment is not None:
            enrollment.diagnostic_completed = False
        db.commit()
        return {
            "path_status": "built",
            "topic_count": len(topics),
            "message": (
                f"Source-backed draft learning path ready with {len(topics)} topics. "
                "Rule-based questions are prepared when you start learning."
            ),
        }

    message = (
        "Internet discovery is temporarily unavailable. Try again or choose from search results."
        if offline
        else "No public topic path was found. Try again or choose from search results."
    )
    subject.description = message
    db.commit()
    return {
        "path_status": "offline" if offline else "not_found",
        "topic_count": len(topics),
        "message": message,
    }


def prepare_enrolled_subject_path(subject: Subject, user: User, db: Session) -> dict:
    if subject.source == "pack":
        _rate_limit(user.id)
        return _attempt_pack_source_path(subject, user, db)
    if (
        subject.source == "manual"
        and not db.query(Topic.id).filter_by(subject_id=subject.id).first()
    ):
        _rate_limit(user.id)
        return _attempt_manual_subject_path(subject, user, db)
    return {
        "path_status": "built",
        "topic_count": db.query(Topic.id).filter_by(subject_id=subject.id).count(),
        "message": "Learning path is ready.",
    }


@manual_router.post("/{subject_id}/build-path")
def build_manual_subject_path(
    subject_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.role != "student" or db.get(LearnerProfile, user.id) is None:
        raise HTTPException(status_code=409, detail="Complete learner onboarding first")
    subject = db.get(Subject, subject_id)
    if (
        subject is None
        or subject.source not in {"manual", "pack"}
        or (subject.source == "manual" and subject.created_by != user.id)
    ):
        raise HTTPException(status_code=404, detail="Personal subject not found")
    if (
        subject.source == "manual"
        and db.query(Topic.id).filter_by(subject_id=subject_id).first() is not None
    ):
        raise HTTPException(status_code=409, detail="This subject already has a topic path")
    if db.get(Enrollment, (user.id, subject_id)) is None:
        raise HTTPException(status_code=404, detail="Enrolled subject not found")
    return prepare_enrolled_subject_path(subject, user, db)


@manual_router.post("/manual")
def create_manual_subject(
    payload: SubjectManualIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.role != "student" or db.get(LearnerProfile, user.id) is None:
        raise HTTPException(status_code=409, detail="Complete learner onboarding first")
    subject_id = f"manual-{safe_slug(payload.name)}-{user.id}"[:80]
    if (
        db.get(Subject, subject_id)
        or db.query(Subject).filter(Subject.name == payload.name).first()
    ):
        raise HTTPException(status_code=409, detail="A subject with this name already exists")
    _rate_limit(user.id)
    ensure_enrollment_capacity(db, user.id, subject_id)
    subject = Subject(
        id=subject_id,
        name=payload.name,
        description="Empty subject. Use discovery to add a public-source topic path.",
        questions_status=(
            "No quiz yet; add topics and questions through discovery or teacher review"
        ),
        source="manual",
        status="draft",
        created_by=user.id,
    )
    db.add(subject)
    try:
        db.flush()
        enroll_user(db, user, subject)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    return _attempt_manual_subject_path(subject, user, db)


@manual_router.put("/{subject_id}/reference")
def attach_reference_book(
    subject_id: str,
    payload: ReferenceBookIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    enrollment = db.get(Enrollment, (user.id, subject_id))
    if enrollment is None:
        raise HTTPException(status_code=403, detail="Enroll in this subject first")
    try:
        validate_provider_url(payload.link)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    enrollment.reference_book = json.dumps(payload.model_dump(), ensure_ascii=False)
    db.commit()
    return {"subject_id": subject_id, "reference_book": payload.model_dump()}
