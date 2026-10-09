"""Server-side question bank and answer grading."""

from __future__ import annotations

QUIZZES: dict[str, list[dict]] = {
    "Algebra": [
        {"question": "Solve for x: 2x + 6 = 14", "options": ["2", "4", "6", "8"], "answer": 1},
        {
            "question": "Factor: x² − 9",
            "options": ["(x−3)(x+3)", "(x−9)(x+1)", "(x−3)²", "(x+3)²"],
            "answer": 0,
        },
        {"question": "If 3x = 27, x =", "options": ["3", "9", "27", "81"], "answer": 1},
    ],
    "Geometry": [
        {
            "question": "Area of a triangle with base 6 and height 4?",
            "options": ["10", "12", "24", "48"],
            "answer": 1,
        },
        {
            "question": "Sum of interior angles of a pentagon?",
            "options": ["360°", "540°", "720°", "900°"],
            "answer": 1,
        },
        {
            "question": "Circumference of a circle radius 5 (π≈3.14)?",
            "options": ["15.7", "25.0", "31.4", "78.5"],
            "answer": 2,
        },
    ],
    "Probability": [
        {"question": "P(heads) on a fair coin?", "options": ["0", "0.25", "0.5", "1"], "answer": 2},
        {
            "question": "Two fair dice: P(sum = 7)?",
            "options": ["1/12", "1/9", "1/6", "1/4"],
            "answer": 2,
        },
        {
            "question": "Expected value of a fair 6-sided die?",
            "options": ["3.0", "3.5", "4.0", "6.0"],
            "answer": 1,
        },
    ],
    "Calculus": [
        {"question": "d/dx of x²", "options": ["x", "2x", "x²", "2"], "answer": 1},
        {"question": "∫ 2x dx", "options": ["2 + C", "x² + C", "2x² + C", "x + C"], "answer": 1},
        {"question": "lim x→0 of sin(x)/x", "options": ["0", "1", "∞", "undefined"], "answer": 1},
    ],
    "Statistics": [
        {"question": "Mean of {2, 4, 6, 8}", "options": ["4", "5", "6", "7"], "answer": 1},
        {"question": "Median of {3, 7, 1, 9, 5}", "options": ["3", "5", "7", "9"], "answer": 1},
        {
            "question": "Standard deviation measures…",
            "options": ["Central tendency", "Spread", "Skewness", "Correlation"],
            "answer": 1,
        },
    ],
    "Linear Algebra": [
        {
            "question": "Determinant of [[1,2],[3,4]]",
            "options": ["-2", "2", "10", "-10"],
            "answer": 0,
        },
        {
            "question": "Identity matrix I₂ is…",
            "options": ["[[1,1],[1,1]]", "[[1,0],[0,1]]", "[[0,1],[1,0]]", "[[0,0],[0,0]]"],
            "answer": 1,
        },
        {
            "question": "Transpose of a 2×3 matrix is…",
            "options": ["2×3", "3×2", "2×2", "3×3"],
            "answer": 1,
        },
    ],
}


def public_questions(topic: str) -> list[dict[str, object]]:
    """Return the topic's questions without exposing the answer key."""
    questions = QUIZZES.get(topic)
    if questions is None:
        raise ValueError("No quiz is available for this topic")
    return [
        {"question": question["question"], "options": question["options"]} for question in questions
    ]


def grade_answers(topic: str, answers: list[int]) -> dict[str, int | float]:
    """Grade one selected option index for every question in a topic quiz."""
    questions = QUIZZES.get(topic)
    if questions is None:
        raise ValueError("No quiz is available for this topic")
    if len(answers) != len(questions):
        raise ValueError(f"Answer all {len(questions)} questions")
    if any(
        answer < 0 or answer >= len(question["options"])
        for answer, question in zip(answers, questions, strict=True)
    ):
        raise ValueError("One or more selected answers are invalid")

    correct = sum(
        answer == question["answer"] for answer, question in zip(answers, questions, strict=True)
    )
    return {
        "score": round(correct / len(questions) * 100.0, 1),
        "correct_answers": correct,
        "question_count": len(questions),
    }
