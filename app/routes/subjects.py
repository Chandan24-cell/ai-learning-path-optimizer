"""Subject enrollment, progress, diagnostic, quiz, and teacher content routes."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.content.catalog import scan_content_packs
from app.content.pack import import_content_pack
from app.database import get_db
from app.dependencies import completed_profile_user
from app.models_db import (
    Enrollment,
    Interaction,
    Question,
    QuestionExposure,
    QuestionReport,
    QuestionSession,
    Resource,
    Subject,
    Topic,
    TopicPrerequisite,
    User,
)
from app.profile_options import level_label
from app.routes.discovery import prepare_enrolled_subject_path
from app.schemas import (
    AdaptiveQuestionAnswerIn,
    DiagnosticSubmitIn,
    EnrollmentIn,
    QuestionCreateIn,
    QuestionReportIn,
    QuestionReportReviewIn,
    QuestionUpdateIn,
    ResourceCreateIn,
    ResourceSubmitIn,
    ResourceUpdateIn,
    SubjectSwitchIn,
    TopicCreateIn,
    TopicRatingIn,
    TopicUpdateIn,
)
from app.services.questions.adaptive import public_adaptive_question, select_question
from app.services.questions.rule_based import clean_source_text, limited_quiz
from app.services.questions.store import ensure_topic_question_bank
from app.services.subject_enrollment import enroll_user, ensure_enrollment_capacity
from app.services.subject_learning import (
    apply_resource_interaction,
    get_prerequisites,
    get_profile,
    get_state,
    get_subject_or_404,
    get_topics,
    public_question,
    recommend_subject,
    require_enrollment,
    save_profile,
)
from src.feature_schema import PREREQUISITE_THRESHOLD

router = APIRouter(prefix="/api", tags=["subjects"])
teacher_router = APIRouter(prefix="/api/teacher", tags=["teacher content"])
_logger = logging.getLogger(__name__)


def _require_teacher(user: User) -> None:
    if user.role != "teacher":
        raise HTTPException(status_code=403, detail="Teacher role required")


def _resource_or_404(db: Session, subject_id: str, resource_id: str) -> Resource:
    resource = (
        db.query(Resource)
        .join(Topic, Resource.topic_id == Topic.id)
        .filter(Resource.id == resource_id, Topic.subject_id == subject_id)
        .first()
    )
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found in this subject")
    return resource


def _topic_or_404(db: Session, topic_id: str) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


def _question_or_404(db: Session, question_id: str) -> Question:
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


def _question_session_or_404(
    db: Session, session_id: str, user_id: int, subject_id: str
) -> QuestionSession:
    session = db.get(QuestionSession, session_id)
    if session is None or session.user_id != user_id or session.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Quiz session not found")
    return session


def _topic_questions(db: Session, topic: Topic, learner_level: float) -> list[Question]:
    return ensure_topic_question_bank(db, topic, learner_level)


def _question_ready_recommendations(
    db: Session, user_id: int, subject_id: str, top_k: int
) -> tuple[list[dict], int]:
    topics = get_topics(db, subject_id)
    profile = get_profile(db, user_id, subject_id, topics=topics)
    for topic in topics:
        _topic_questions(db, topic, float(profile["learner_level"]))
    resource_count = (
        db.query(Resource.id)
        .join(Topic, Resource.topic_id == Topic.id)
        .filter(Topic.subject_id == subject_id)
        .count()
    )
    ranked = recommend_subject(db, user_id, subject_id, top_k=max(top_k, resource_count, 1))
    ready: list[dict] = []
    topic_banks: dict[str, bool] = {}
    for item in ranked:
        topic_id = str(item["topic_id"])
        if topic_id not in topic_banks:
            candidate_topic = db.get(Topic, topic_id)
            topic_banks[topic_id] = bool(
                candidate_topic
                and _topic_questions(db, candidate_topic, float(profile["learner_level"]))
            )
        if topic_banks[topic_id]:
            ready.append(item)
            if len(ready) >= top_k:
                break
    limited_count = sum(
        1
        for topic in topics
        if topic.quiz_status == "limited"
        or (topic.source_url and topic.source_extract and not topic_banks.get(topic.id, False))
    )
    return ready, limited_count


def _topic_resource(db: Session, topic_id: str) -> Resource | None:
    return db.query(Resource).filter_by(topic_id=topic_id).order_by(Resource.id).first()


def _question_feedback(db: Session, question: Question, topic: Topic, answer: int) -> dict:
    source_sentence = question.source_sentence or question.explanation
    resource = _topic_resource(db, topic.id)
    return {
        "question_id": question.id,
        "correct": answer == question.correct_option,
        "correct_answer": question.options[question.correct_option],
        "source_sentence": source_sentence,
        "explanation": source_sentence,
        "source_url": (
            question.source_url
            or topic.source_url
            or (resource.source_url or resource.url if resource is not None else None)
        ),
        "attribution": question.attribution,
    }


def _normalized_prerequisites(
    db: Session,
    subject_id: str,
    topic_id: str,
    prerequisite_ids: list[str],
) -> list[str]:
    normalized = [
        value if value.startswith(f"{subject_id}.") else f"{subject_id}.{value}"
        for value in prerequisite_ids
    ]
    if len(normalized) != len(set(normalized)):
        raise HTTPException(status_code=422, detail="Prerequisites must not be duplicated")
    if topic_id in normalized:
        raise HTTPException(status_code=422, detail="A topic cannot be its own prerequisite")
    graph = get_prerequisites(db, subject_id)
    for prerequisite_id in normalized:
        prerequisite = db.get(Topic, prerequisite_id)
        if prerequisite is None or prerequisite.subject_id != subject_id:
            raise HTTPException(
                status_code=422,
                detail="Prerequisites must be other topics in this subject",
            )
        pending = [prerequisite_id]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == topic_id:
                raise HTTPException(
                    status_code=422, detail="Prerequisite changes cannot create a cycle"
                )
            if current not in visited:
                visited.add(current)
                pending.extend(graph.get(current, []))
    return normalized


def _progress(db: Session, user_id: int, subject_id: str) -> dict:
    profile = get_profile(db, user_id, subject_id)
    prerequisite_map = get_prerequisites(db, subject_id)
    topics = []
    for topic in get_topics(db, subject_id):
        prerequisites = prerequisite_map.get(topic.id, [])
        ready = all(
            float(profile["mastery_est"].get(prerequisite, 0.25)) >= PREREQUISITE_THRESHOLD
            for prerequisite in prerequisites
        )
        topic_resources = (
            db.query(Resource).filter_by(topic_id=topic.id).order_by(Resource.id).all()
        )
        question_query = db.query(Question.id).filter(
            Question.topic_id == topic.id,
            Question.source_url.is_not(None),
            Question.generator_version.is_not(None),
        )
        question_count = question_query.count()
        has_questions = question_count > 0
        quiz_status = (
            topic.quiz_status
            if topic.quiz_status in {"limited", "ready"}
            else "ready"
            if has_questions
            else "not_generated"
        )
        topics.append(
            {
                "id": topic.id,
                "name": topic.name,
                "order": topic.order,
                "mastery": round(float(profile["mastery_est"].get(topic.id, 0.25)), 4),
                "attempts": int(profile["attempts"].get(topic.id, 0)),
                "prerequisites": prerequisites,
                "prerequisites_met": ready,
                "has_quiz": has_questions,
                "question_count": question_count,
                "quiz_status": quiz_status,
                "resources": [
                    {
                        "title": resource.title,
                        "type": resource.type,
                        "url": resource.url,
                        "source_url": resource.source_url,
                    }
                    for resource in topic_resources
                ],
            }
        )
    enrollment = db.get(Enrollment, (user_id, subject_id))
    subject = db.get(Subject, subject_id)
    return {
        "subject_id": subject_id,
        "subject": {
            "name": subject.name if subject else subject_id,
            "description": subject.description if subject else "",
            "source": subject.source if subject else "pack",
            "status": subject.status if subject else "draft",
            "source_url": subject.source_url if subject else None,
            "reference_book": (
                json.loads(enrollment.reference_book)
                if enrollment is not None and enrollment.reference_book
                else None
            ),
        },
        "diagnostic_completed": bool(enrollment and enrollment.diagnostic_completed),
        "n_interactions": profile["n_interactions"],
        "total_time_min": profile["total_time_min"],
        "engagement_ma": profile["engagement_ma"],
        "last_score": profile["last_score"],
        "learner_level": profile["learner_level"],
        "learner_level_label": profile["learner_level_label"],
        "learning_goal": profile["learning_goal"],
        "topics": topics,
    }


@router.get("/subjects")
def list_subjects(
    include_samples: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    entries, issues = scan_content_packs(include_examples=include_samples)
    all_entries, _ = scan_content_packs(include_examples=True)
    sample_ids = {
        entry.pack.slug for entry in all_entries if entry.path.parent.parent.name == "examples"
    }
    installed_subjects = {
        subject.id: subject for subject in db.query(Subject).filter(Subject.source == "pack").all()
    }
    for issue in issues:
        _logger.error("Content pack validation failed in %s: %s", issue.directory, issue.message)
    listed_ids = {entry.pack.slug for entry in entries}
    subjects = [
        {
            "id": entry.pack.slug,
            "name": entry.pack.name,
            "description": entry.pack.description,
            "topic_count": len(entry.pack.topics),
            "questions_status": entry.pack.questions_status,
            "source": "pack",
            "status": "draft",
            "installed": entry.pack.slug in installed_subjects,
        }
        for entry in entries
    ]
    subjects.extend(
        {
            "id": subject.id,
            "name": subject.name,
            "description": subject.description,
            "topic_count": db.query(Topic).filter_by(subject_id=subject.id).count(),
            "questions_status": subject.questions_status,
            "source": subject.source,
            "status": subject.status,
            "installed": True,
        }
        for subject in installed_subjects.values()
        if subject.id not in listed_ids and (include_samples or subject.id not in sample_ids)
    )
    return {
        "subjects": sorted(subjects, key=lambda subject: subject["name"].casefold()),
        "errors": [{"directory": issue.directory, "message": issue.message} for issue in issues],
    }


@router.post("/subjects/{subject_id}/install")
def install_subject_pack(
    subject_id: str,
    payload: EnrollmentIn = Body(default=EnrollmentIn()),
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    entries, issues = scan_content_packs(include_examples=True)
    for issue in issues:
        _logger.error("Content pack validation failed in %s: %s", issue.directory, issue.message)
    entry = next((item for item in entries if item.pack.slug == subject_id), None)
    if entry is None:
        invalid_folder = next((issue for issue in issues if issue.directory == subject_id), None)
        if invalid_folder is not None:
            raise HTTPException(
                status_code=422,
                detail=f"Content pack '{subject_id}' failed validation: {invalid_folder.message}",
            )
        raise HTTPException(status_code=404, detail="Content pack not found")
    existing_subject = db.get(Subject, subject_id)
    if existing_subject is not None and existing_subject.source != "pack":
        raise HTTPException(status_code=409, detail="A non-pack subject already uses this ID")
    ensure_enrollment_capacity(db, user.id, subject_id)
    import_result = import_content_pack(entry.path, db)
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status_code=500, detail="Imported pack could not be loaded")
    enrollment = enroll_user(db, user, subject, payload.target_depth)
    enrollment_result = {
        "status": "enrolled",
        "subject_id": subject_id,
        "diagnostic_required": not enrollment.diagnostic_completed,
    }
    path_result = prepare_enrolled_subject_path(subject, user, db)
    return {**import_result, **enrollment_result, **path_result, "installed": True}


@router.get("/me/subjects")
def my_subjects(user: User = Depends(completed_profile_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Enrollment, Subject)
        .join(Subject, Enrollment.subject_id == Subject.id)
        .filter(Enrollment.user_id == user.id)
        .order_by(Subject.name)
        .all()
    )
    return {
        "active_subject_id": user.active_subject_id,
        "subjects": [
            {
                "id": subject.id,
                "name": subject.name,
                "active": user.active_subject_id == subject.id,
                "diagnostic_completed": enrollment.diagnostic_completed,
                "source": subject.source,
                "status": subject.status,
                "topic_count": db.query(Topic).filter_by(subject_id=subject.id).count(),
                "source_url": subject.source_url,
                "target_depth": enrollment.target_depth,
                "education_level_used": enrollment.education_level_used,
                "reference_book": (
                    json.loads(enrollment.reference_book) if enrollment.reference_book else None
                ),
            }
            for enrollment, subject in rows
        ],
    }


@router.post("/subjects/{subject_id}/enroll")
def enroll_subject(
    subject_id: str,
    payload: EnrollmentIn = Body(default=EnrollmentIn()),
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    subject = get_subject_or_404(db, subject_id)
    if subject.created_by is not None and subject.created_by != user.id:
        raise HTTPException(status_code=404, detail="Subject not found")
    enrollment = enroll_user(db, user, subject, payload.target_depth)
    path_result = prepare_enrolled_subject_path(subject, user, db)
    return {
        "status": "enrolled",
        "subject_id": subject_id,
        "diagnostic_required": not enrollment.diagnostic_completed,
        **path_result,
    }


@router.delete("/subjects/{subject_id}/enroll")
def unenroll_subject(
    subject_id: str,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    enrollment = db.get(Enrollment, (user.id, subject_id))
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    db.delete(enrollment)
    if user.active_subject_id == subject_id:
        alternatives = (
            db.query(Enrollment.subject_id)
            .filter(Enrollment.user_id == user.id, Enrollment.subject_id != subject_id)
            .order_by(Enrollment.subject_id)
            .first()
        )
        user.active_subject_id = alternatives[0] if alternatives else None
    db.commit()
    return {"status": "unenrolled", "subject_id": subject_id}


@router.put("/me/subject")
def switch_subject(
    payload: SubjectSwitchIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    require_enrollment(db, user.id, payload.subject_id)
    user.active_subject_id = payload.subject_id
    db.commit()
    return {"active_subject_id": payload.subject_id}


@router.get("/subjects/{subject_id}/progress")
def subject_progress(
    subject_id: str,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    get_subject_or_404(db, subject_id)
    require_enrollment(db, user.id, subject_id)
    return _progress(db, user.id, subject_id)


@router.get("/subjects/{subject_id}/diagnostic")
def get_diagnostic(
    subject_id: str,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    get_subject_or_404(db, subject_id)
    enrollment = require_enrollment(db, user.id, subject_id)
    if enrollment.diagnostic_completed:
        return {"subject_id": subject_id, "completed": True, "questions": []}
    topics = get_topics(db, subject_id)
    if not topics:
        return {
            "subject_id": subject_id,
            "completed": False,
            "session_id": None,
            "questions": [],
            "message": (
                "This subject has no topic path or quiz yet. You can complete setup without a quiz."
            ),
        }
    profile = get_profile(db, user.id, subject_id)
    session = (
        db.query(QuestionSession)
        .filter_by(user_id=user.id, subject_id=subject_id, mode="diagnostic")
        .filter(QuestionSession.completed_at.is_(None))
        .order_by(QuestionSession.started_at.desc())
        .first()
    )
    if session is None:
        session = QuestionSession(
            id=uuid4().hex,
            user_id=user.id,
            subject_id=subject_id,
            topic_id=topics[0].id if topics else f"{subject_id}.diagnostic",
            resource_id="diagnostic",
            mode="diagnostic",
            max_questions=len(topics),
            asked_count=0,
            correct_count=0,
        )
        db.add(session)
        db.flush()
        for topic in topics:
            bank = _topic_questions(db, topic, float(profile["learner_level"]))
            selected = select_question(
                db,
                user_id=user.id,
                subject_id=subject_id,
                session=session,
                topic=topic,
                questions=bank,
                learner_level=float(profile["learner_level"]),
                mastery=float(profile["mastery_est"].get(topic.id, 0.25)),
                previous_correct=None,
                topic_count=len(topics),
                prefer_diagnostic=True,
            )
            if selected is not None:
                session.asked_count += 1
        db.flush()
    exposures = (
        db.query(QuestionExposure, Question)
        .join(Question, QuestionExposure.question_id == Question.id)
        .filter(QuestionExposure.session_id == session.id)
        .all()
    )
    questions_by_topic = {
        exposure.topic_id: (exposure, question) for exposure, question in exposures
    }
    questions: list[dict[str, object]] = []
    limited_topics = 0
    for topic in topics:
        exposure_and_question = questions_by_topic.get(topic.id)
        if exposure_and_question is None:
            limited_topics += 1
            continue
        exposure, question = exposure_and_question
        questions.append(
            {
                **public_question(question),
                "topic_id": topic.id,
                "topic": topic.name,
                "quiz_available": True,
                "quiz_status": topic.quiz_status,
                "source_url": question.source_url,
                "attribution": question.attribution,
                "exposure_id": exposure.id,
            }
        )
    db.commit()
    return {
        "subject_id": subject_id,
        "completed": False,
        "session_id": session.id,
        "questions": questions,
        "message": (
            f"{limited_topics} topic(s) have limited quiz banks and were skipped."
            if limited_topics
            else "Answer the available questions to get your starting point."
        ),
    }


@router.post("/subjects/{subject_id}/diagnostic")
def submit_diagnostic(
    subject_id: str,
    payload: DiagnosticSubmitIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    get_subject_or_404(db, subject_id)
    enrollment = require_enrollment(db, user.id, subject_id)
    if enrollment.diagnostic_completed:
        raise HTTPException(status_code=409, detail="Diagnostic has already been completed")
    if not payload.session_id:
        if get_topics(db, subject_id) or payload.answers or payload.self_ratings:
            raise HTTPException(status_code=422, detail="A diagnostic session is required")
        enrollment.diagnostic_completed = True
        db.commit()
        return {
            "completed": True,
            "feedback": [],
            "self_ratings": {},
            "score_source": "graded quiz answers only",
            "progress": _progress(db, user.id, subject_id),
        }
    session = _question_session_or_404(db, payload.session_id, user.id, subject_id)
    if session.mode != "diagnostic" or session.completed_at is not None:
        raise HTTPException(status_code=409, detail="Diagnostic session is not active")
    exposure_rows = (
        db.query(QuestionExposure, Question)
        .join(Question, QuestionExposure.question_id == Question.id)
        .filter(QuestionExposure.session_id == session.id)
        .all()
    )
    questions = [question for _, question in exposure_rows]
    expected_ids = {question.id for question in questions}
    if set(payload.answers) != expected_ids or payload.self_ratings:
        raise HTTPException(
            status_code=422,
            detail="Answer each available diagnostic question; limited quiz topics are skipped",
        )
    for question in questions:
        answer = payload.answers[question.id]
        if answer < 0 or answer >= len(question.options):
            raise HTTPException(
                status_code=422, detail="Answer option is outside the question choices"
            )
    profile = get_profile(db, user.id, subject_id)
    state = get_state(db, user.id, subject_id)
    feedback = []
    for exposure, question in exposure_rows:
        answer = payload.answers[question.id]
        correct = answer == question.correct_option
        exposure.answer_index = answer
        exposure.is_correct = correct
        exposure.answered_at = datetime.now(UTC)
        profile["mastery_est"][question.topic_id] = 0.70 if correct else 0.25
        feedback.append(
            _question_feedback(db, question, _topic_or_404(db, question.topic_id), answer)
        )
    if questions:
        correct_count = sum(
            1 for question in questions if payload.answers[question.id] == question.correct_option
        )
        level_adjustment = 20.0 * correct_count / len(questions) - 10.0
        profile["learner_level"] = min(100.0, max(0.0, profile["learner_level"] + level_adjustment))
        profile["learner_level_label"] = level_label(profile["learner_level"])
    save_profile(state, profile)
    enrollment.diagnostic_completed = True
    session.completed_at = datetime.now(UTC)
    db.commit()
    return {
        "completed": True,
        "feedback": feedback,
        "self_ratings": {},
        "score": (
            round(100 * sum(item["correct"] for item in feedback) / len(feedback), 2)
            if feedback
            else None
        ),
        "score_source": "graded quiz answers only",
        "progress": _progress(db, user.id, subject_id),
    }


@router.get("/subjects/{subject_id}/recommendations")
def subject_recommendations(
    subject_id: str,
    top_k: int = Query(default=5, ge=1, le=20),
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    get_subject_or_404(db, subject_id)
    enrollment = require_enrollment(db, user.id, subject_id)
    if not enrollment.diagnostic_completed:
        raise HTTPException(
            status_code=409, detail="Complete the diagnostic before recommendations"
        )
    recommendations, limited_count = _question_ready_recommendations(db, user.id, subject_id, top_k)
    db.commit()
    return {
        "subject_id": subject_id,
        "recommendations": recommendations,
        "message": (
            f"{limited_count} topic(s) with limited quiz banks were skipped."
            if limited_count and not recommendations
            else None
        ),
    }


@router.get("/subjects/{subject_id}/resources/{resource_id}/quiz")
def subject_quiz(
    subject_id: str,
    resource_id: str,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    get_subject_or_404(db, subject_id)
    enrollment = require_enrollment(db, user.id, subject_id)
    if not enrollment.diagnostic_completed:
        raise HTTPException(status_code=409, detail="Complete the diagnostic before activities")
    resource = _resource_or_404(db, subject_id, resource_id)
    topic = _topic_or_404(db, resource.topic_id)
    topics = get_topics(db, subject_id)
    profile = get_profile(db, user.id, subject_id)
    questions = _topic_questions(db, topic, float(profile["learner_level"]))
    if not questions:
        db.commit()
        return {
            "subject_id": subject_id,
            "resource_id": resource_id,
            "topic_id": resource.topic_id,
            "questions": [],
            "session_id": None,
            "quiz_status": topic.quiz_status,
            "limited": True,
            "message": "Limited quiz: no source-backed questions passed the quality checks.",
            "resource_url": resource.url,
            "resource_title": resource.title,
        }
    session = QuestionSession(
        id=uuid4().hex,
        user_id=user.id,
        subject_id=subject_id,
        topic_id=topic.id,
        resource_id=resource.id,
        mode="activity",
        max_questions=10,
        asked_count=0,
        correct_count=0,
    )
    db.add(session)
    db.flush()
    selected = select_question(
        db,
        user_id=user.id,
        subject_id=subject_id,
        session=session,
        topic=topic,
        questions=questions,
        learner_level=float(profile["learner_level"]),
        mastery=float(profile["mastery_est"].get(topic.id, 0.25)),
        previous_correct=None,
        topic_count=len(topics),
    )
    if selected is None:
        db.rollback()
        raise HTTPException(status_code=409, detail="No unused question is available")
    session.asked_count = 1
    db.commit()
    is_limited = limited_quiz(len(questions))
    return {
        "subject_id": subject_id,
        "resource_id": resource_id,
        "topic_id": resource.topic_id,
        "session_id": session.id,
        "questions": [public_adaptive_question(selected)],
        "quiz_status": topic.quiz_status,
        "limited": is_limited,
        "bank_size": len(questions),
        "reused": selected.reused,
        "message": (
            f"Limited quiz: {len(questions)} quality-checked question(s) are available."
            if is_limited
            else None
        ),
    }


@router.post("/subjects/{subject_id}/quiz-sessions/{session_id}/answer")
def answer_adaptive_question(
    subject_id: str,
    session_id: str,
    payload: AdaptiveQuestionAnswerIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    get_subject_or_404(db, subject_id)
    session = _question_session_or_404(db, session_id, user.id, subject_id)
    enrollment = require_enrollment(db, user.id, subject_id)
    if not enrollment.diagnostic_completed:
        raise HTTPException(status_code=409, detail="Complete the diagnostic before activities")
    if session.mode != "activity" or session.completed_at is not None:
        raise HTTPException(status_code=409, detail="Quiz session is not active")
    exposure = (
        db.query(QuestionExposure)
        .filter_by(session_id=session.id, question_id=payload.question_id)
        .first()
    )
    if exposure is None or exposure.answered_at is not None:
        raise HTTPException(status_code=409, detail="Question is not awaiting an answer")
    question = _question_or_404(db, payload.question_id)
    if payload.answer >= len(question.options):
        raise HTTPException(status_code=422, detail="Answer option is outside the question choices")
    topic = _topic_or_404(db, question.topic_id)
    resource = _topic_resource(db, topic.id)
    if resource is None:
        raise HTTPException(status_code=409, detail="This topic has no learning resource")

    exposure.answer_index = payload.answer
    exposure.is_correct = payload.answer == question.correct_option
    exposure.answered_at = datetime.now(UTC)
    correct = bool(exposure.is_correct)
    session.correct_count += int(correct)

    profile = get_profile(db, user.id, subject_id)
    outcome = apply_resource_interaction(
        profile,
        resource.__dict__,
        100.0 if correct else 0.0,
        payload.duration,
    )
    state = get_state(db, user.id, subject_id)
    save_profile(state, profile)
    db.add(
        Interaction(
            user_id=user.id,
            subject_id=subject_id,
            resource_id=resource.id,
            topic=topic.id,
            rtype="quiz",
            difficulty=float(question.difficulty),
            duration=payload.duration,
            score=100.0 if correct else 0.0,
            gain=outcome["gain"],
            engagement=outcome["engagement"],
        )
    )

    next_topic = topic
    selected = None
    if session.asked_count < session.max_questions:
        topics = get_topics(db, subject_id)
        db.flush()
        recommendations = recommend_subject(
            db,
            user.id,
            subject_id,
            top_k=max(
                1,
                db.query(Resource.id)
                .join(Topic, Resource.topic_id == Topic.id)
                .filter(Topic.subject_id == subject_id)
                .count(),
            ),
        )
        attempted_topics: set[str] = set()
        for recommendation in recommendations:
            candidate_topic_id = str(recommendation["topic_id"])
            if candidate_topic_id in attempted_topics:
                continue
            attempted_topics.add(candidate_topic_id)
            candidate_topic = db.get(Topic, candidate_topic_id)
            if candidate_topic is None:
                continue
            bank = _topic_questions(db, candidate_topic, float(profile["learner_level"]))
            if not bank:
                continue
            selected = select_question(
                db,
                user_id=user.id,
                subject_id=subject_id,
                session=session,
                topic=candidate_topic,
                questions=bank,
                learner_level=float(profile["learner_level"]),
                mastery=float(profile["mastery_est"].get(candidate_topic.id, 0.25)),
                previous_correct=correct,
                topic_count=len(topics),
            )
            if selected is not None:
                next_topic = candidate_topic
                break
        if selected is not None:
            session.asked_count += 1

    if selected is None:
        session.completed_at = datetime.now(UTC)
    db.commit()
    progress = _progress(db, user.id, subject_id)
    prerequisite_map = get_prerequisites(db, subject_id)
    prerequisite_focus_ids = {
        prerequisite_id for prerequisite_id in prerequisite_map.get(topic.id, [])
    }
    score = round(
        100 * session.correct_count / max(session.asked_count - int(selected is not None), 1), 2
    )
    return {
        "feedback": _question_feedback(db, question, topic, payload.answer),
        "outcome": outcome,
        "next_question": public_adaptive_question(selected) if selected is not None else None,
        "next_topic": next_topic.name if selected is not None else None,
        "session_complete": selected is None,
        "score": score,
        "question_count": session.asked_count - int(selected is not None),
        "reused_questions": session.reused_questions,
        "reuse_message": (
            "The question bank has been used before; this session reused a question."
            if session.reused_questions
            else None
        ),
        "message": (
            "Topics with limited quiz questions were skipped."
            if selected is None
            and any(item.quiz_status == "limited" for item in get_topics(db, subject_id))
            else None
        ),
        "prerequisite_mistake": (
            f"Review prerequisite topic: {next_topic.name}."
            if not correct and selected is not None and next_topic.id in prerequisite_focus_ids
            else None
        ),
        "weak_topics": [
            item["name"]
            for item in progress["topics"]
            if float(item["mastery"]) < PREREQUISITE_THRESHOLD
        ],
        "progress": progress,
    }


@router.post("/subjects/{subject_id}/topics/{topic_id}/rating")
def rate_topic(
    subject_id: str,
    topic_id: str,
    payload: TopicRatingIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
) -> dict:
    get_subject_or_404(db, subject_id)
    require_enrollment(db, user.id, subject_id)
    topic = db.get(Topic, topic_id)
    if topic is None or topic.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Topic not found")
    state = get_state(db, user.id, subject_id)
    ratings = json.loads(state.self_ratings_json or "{}")
    recorded_at = datetime.now(UTC).isoformat()
    ratings[topic_id] = {"rating": payload.rating, "recorded_at": recorded_at}
    state.self_ratings_json = json.dumps(ratings)
    mastery = state.mastery_est
    mastery[topic_id] = payload.rating / 5.0
    state.mastery_est_json = json.dumps(mastery)
    db.commit()
    return {
        "topic_id": topic_id,
        "rating": payload.rating,
        "signal_type": "self-rating (not a quiz score)",
        "recorded_at": recorded_at,
    }


@router.get("/subjects/{subject_id}/improvement")
def subject_improvement(
    subject_id: str,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
) -> dict:
    get_subject_or_404(db, subject_id)
    require_enrollment(db, user.id, subject_id)
    state = get_state(db, user.id, subject_id)
    ratings = json.loads(state.self_ratings_json or "{}")
    interactions = (
        db.query(Interaction)
        .filter_by(user_id=user.id, subject_id=subject_id)
        .order_by(Interaction.id.desc())
        .limit(500)
        .all()
    )
    history: dict[str, list[Interaction]] = {}
    for row in interactions:
        if row.topic:
            history.setdefault(row.topic, []).append(row)
    prerequisites = get_prerequisites(db, subject_id)
    suggestions = []
    for topic in get_topics(db, subject_id):
        rows = history.get(topic.id, [])
        rating = ratings.get(topic.id)
        if not rows and rating is None:
            continue
        mastery = state.mastery_est.get(topic.id)
        score_values = [row.score for row in reversed(rows) if row.score is not None]
        weak = (mastery is not None and mastery < 0.6) or (
            rating is not None and int(rating["rating"]) <= 3
        )
        if not weak:
            continue
        prereq_names = []
        for prerequisite_id in prerequisites.get(topic.id, []):
            prerequisite = db.get(Topic, prerequisite_id)
            if prerequisite is not None:
                prereq_names.append(prerequisite.name)
        resources = (
            db.query(Resource)
            .filter_by(topic_id=topic.id)
            .order_by(Resource.difficulty, Resource.id)
            .all()
        )
        lower_difficulty = (
            min(float(resource.difficulty) for resource in resources) if resources else None
        )
        suggestions.append(
            {
                "topic_id": topic.id,
                "topic": topic.name,
                "mastery": mastery,
                "self_rating": rating["rating"] if rating is not None else None,
                "attempts": len(rows),
                "score_trend": score_values,
                "how_to_improve": [
                    *([f"Review prerequisite: {name}." for name in prereq_names]),
                    *(
                        [
                            {
                                "resource": resource.title,
                                "source_url": resource.source_url or resource.url,
                            }
                            for resource in resources[:1]
                        ]
                        if resources
                        else []
                    ),
                    *(
                        [f"Practice a resource at difficulty {lower_difficulty:g}/5."]
                        if lower_difficulty is not None
                        else []
                    ),
                ],
            }
        )
    suggestions.sort(
        key=lambda item: (
            item["mastery"] if item["mastery"] is not None else float("inf"),
            item["self_rating"] if item["self_rating"] is not None else 5,
            item["topic"],
        )
    )
    return {
        "subject_id": subject_id,
        "topics": suggestions,
        "message": "No topic-specific learning data yet." if not suggestions else None,
    }


@router.post("/subjects/{subject_id}/questions/{question_id}/report")
def report_question(
    subject_id: str,
    question_id: str,
    payload: QuestionReportIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    get_subject_or_404(db, subject_id)
    require_enrollment(db, user.id, subject_id)
    question = (
        db.query(Question)
        .join(Topic, Question.topic_id == Topic.id)
        .filter(Question.id == question_id, Topic.subject_id == subject_id)
        .first()
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found in this subject")
    seen = (
        db.query(QuestionExposure.id)
        .filter_by(user_id=user.id, subject_id=subject_id, question_id=question_id)
        .first()
    )
    if seen is None:
        raise HTTPException(status_code=409, detail="You can report a question after it is shown")
    report = QuestionReport(
        user_id=user.id,
        question_id=question_id,
        reason=payload.reason,
        details=clean_source_text(payload.details, 500).strip() if payload.details else None,
    )
    db.add(report)
    db.commit()
    return {"status": "reported", "report_id": report.id}


@router.post("/subjects/{subject_id}/resources/{resource_id}/submit")
def submit_subject_quiz(
    subject_id: str,
    resource_id: str,
    payload: ResourceSubmitIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    del resource_id, payload, user, db
    raise HTTPException(
        status_code=409,
        detail="This quiz endpoint has been replaced by adaptive question sessions.",
    )


@router.get("/subjects/{subject_id}/history")
def subject_history(
    subject_id: str,
    limit: int = Query(default=20, ge=1, le=200),
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    get_subject_or_404(db, subject_id)
    require_enrollment(db, user.id, subject_id)
    rows = (
        db.query(Interaction)
        .filter_by(user_id=user.id, subject_id=subject_id)
        .order_by(Interaction.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "history": [
            {
                "id": row.id,
                "topic": row.topic,
                "resource_id": row.resource_id,
                "resource_type": row.rtype,
                "difficulty": row.difficulty,
                "duration": row.duration,
                "score": row.score,
                "gain": row.gain,
                "engagement": row.engagement,
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row in rows
        ]
    }


@teacher_router.post("/subjects/{subject_id}/topics")
def create_topic(
    subject_id: str,
    payload: TopicCreateIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    _require_teacher(user)
    get_subject_or_404(db, subject_id)
    topic_id = f"{subject_id}.{payload.slug}"
    if len(topic_id) > 160:
        raise HTTPException(status_code=422, detail="Topic id is too long")
    if db.get(Topic, topic_id):
        raise HTTPException(status_code=409, detail="Topic id already exists")
    prerequisites = _normalized_prerequisites(db, subject_id, topic_id, payload.prerequisites)
    topic = Topic(
        id=topic_id,
        subject_id=subject_id,
        slug=payload.slug,
        name=payload.name,
        order=payload.order,
    )
    db.add(topic)
    for prerequisite_id in prerequisites:
        db.add(TopicPrerequisite(topic_id=topic_id, prerequisite_topic_id=prerequisite_id))
    db.commit()
    return {"id": topic.id, "name": topic.name, "subject_id": subject_id}


@teacher_router.patch("/topics/{topic_id}")
def update_topic(
    topic_id: str,
    payload: TopicUpdateIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    _require_teacher(user)
    topic = _topic_or_404(db, topic_id)
    values = payload.model_dump(exclude_unset=True)
    prerequisites = values.pop("prerequisites", None)
    for key, value in values.items():
        setattr(topic, key, value)
    if prerequisites is not None:
        normalized = _normalized_prerequisites(db, topic.subject_id, topic_id, prerequisites)
        db.query(TopicPrerequisite).filter_by(topic_id=topic_id).delete(synchronize_session=False)
        for prerequisite_id in normalized:
            db.add(TopicPrerequisite(topic_id=topic_id, prerequisite_topic_id=prerequisite_id))
    db.commit()
    return {"id": topic.id, "name": topic.name, "order": topic.order}


@teacher_router.post("/topics/{topic_id}/resources")
def create_resource(
    topic_id: str,
    payload: ResourceCreateIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    _require_teacher(user)
    topic = _topic_or_404(db, topic_id)
    resource_id = f"{topic_id}.{payload.id}"
    if len(resource_id) > 180:
        raise HTTPException(status_code=422, detail="Resource id is too long")
    if db.get(Resource, resource_id):
        raise HTTPException(status_code=409, detail="Resource id already exists")
    resource = Resource(
        id=resource_id,
        topic_id=topic.id,
        type=payload.type,
        title=payload.title,
        difficulty=payload.difficulty,
        duration=payload.duration,
        url=payload.url,
        body=payload.body,
    )
    db.add(resource)
    db.commit()
    return {"id": resource.id, "topic_id": topic_id}


@teacher_router.patch("/resources/{resource_id}")
def update_resource(
    resource_id: str,
    payload: ResourceUpdateIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    _require_teacher(user)
    resource = db.get(Resource, resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(resource, key, value)
    if not (resource.url or resource.body):
        raise HTTPException(status_code=422, detail="A resource needs a non-empty url or body")
    db.commit()
    return {"id": resource.id, "topic_id": resource.topic_id}


@teacher_router.post("/topics/{topic_id}/questions")
def create_question(
    topic_id: str,
    payload: QuestionCreateIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    _require_teacher(user)
    topic = _topic_or_404(db, topic_id)
    question_id = f"{topic_id}.{payload.id}"
    if len(question_id) > 180:
        raise HTTPException(status_code=422, detail="Question id is too long")
    if db.get(Question, question_id):
        raise HTTPException(status_code=409, detail="Question id already exists")
    if (
        payload.diagnostic
        and db.query(Question).filter_by(topic_id=topic_id, diagnostic=True).first()
    ):
        raise HTTPException(status_code=409, detail="This topic already has a diagnostic question")
    question = Question(
        id=question_id,
        topic_id=topic.id,
        difficulty=payload.difficulty,
        text=payload.text,
        options_json=json.dumps(payload.options, ensure_ascii=False),
        correct_option=payload.correct_option,
        explanation=payload.explanation,
        diagnostic=payload.diagnostic,
    )
    db.add(question)
    db.commit()
    return {"id": question.id, "topic_id": topic_id}


@teacher_router.patch("/questions/{question_id}")
def update_question(
    question_id: str,
    payload: QuestionUpdateIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    _require_teacher(user)
    question = _question_or_404(db, question_id)
    values = payload.model_dump(exclude_unset=True)
    if values.get("status") == "approved":
        values["status"] = "teacher-approved"
    if values.get("diagnostic") is True and not question.diagnostic:
        existing = (
            db.query(Question)
            .filter(
                Question.topic_id == question.topic_id,
                Question.diagnostic.is_(True),
                Question.id != question_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409, detail="This topic already has a diagnostic question"
            )
    options = values.pop("options", None)
    for key, value in values.items():
        setattr(question, key, value)
    if options is not None:
        question.options_json = json.dumps(options, ensure_ascii=False)
    if question.correct_option >= len(question.options):
        raise HTTPException(
            status_code=422, detail="correct_option must point to one of the options"
        )
    db.commit()
    return {"id": question.id, "topic_id": question.topic_id}


@teacher_router.delete("/questions/{question_id}")
def delete_question(
    question_id: str,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    _require_teacher(user)
    question = _question_or_404(db, question_id)
    db.delete(question)
    db.commit()
    return {"status": "deleted", "question_id": question_id}


@teacher_router.get("/question-reports")
def list_question_reports(
    status: str = Query(default="open", pattern="^(open|reviewed|dismissed|all)$"),
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    _require_teacher(user)
    query = (
        db.query(QuestionReport, Question, Topic)
        .join(Question, QuestionReport.question_id == Question.id)
        .join(Topic, Question.topic_id == Topic.id)
    )
    if status != "all":
        query = query.filter(QuestionReport.status == status)
    rows = query.order_by(QuestionReport.created_at.desc(), QuestionReport.id.desc()).all()
    return {
        "reports": [
            {
                "id": report.id,
                "question_id": question.id,
                "question": question.text,
                "topic_id": topic.id,
                "topic": topic.name,
                "reason": report.reason,
                "details": report.details,
                "status": report.status,
                "created_at": report.created_at.isoformat() if report.created_at else None,
            }
            for report, question, topic in rows
        ]
    }


@teacher_router.patch("/question-reports/{report_id}")
def review_question_report(
    report_id: int,
    payload: QuestionReportReviewIn,
    user: User = Depends(completed_profile_user),
    db: Session = Depends(get_db),
):
    _require_teacher(user)
    report = db.get(QuestionReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Question report not found")
    report.status = payload.status
    report.reviewed_by = user.id
    report.reviewed_at = datetime.now(UTC)
    db.commit()
    return {"id": report.id, "status": report.status}
