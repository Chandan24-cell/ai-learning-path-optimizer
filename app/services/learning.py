"""Update a real student's state after they complete an activity."""

from __future__ import annotations

import numpy as np

from src.domain import zpd_factor


def apply_interaction(
    profile: dict, action: int, catalog: list, score: float, actual_duration: float
) -> dict:
    """Mutate `profile` in place and return outcome metrics.

    Mastery update
    --------------
    We blend the previous estimate with the observed quiz score and add a
    small learning bonus proportional to how well the resource fit the
    zone of proximal development. This mirrors the simulator dynamics but
    is driven by the real score the student just earned.
    """
    entry = catalog[int(action)]
    topic = entry["topic"]

    score_norm = float(np.clip(score / 100.0, 0.0, 1.0))
    old_mastery = float(profile["mastery_est"][topic])

    zpd = zpd_factor(old_mastery, entry["difficulty"])

    learning_bonus = 0.03 * zpd * (1.0 - old_mastery)
    new_mastery = float(
        np.clip(
            0.6 * old_mastery + 0.4 * score_norm + learning_bonus,
            0.0,
            1.0,
        )
    )
    gain = new_mastery - old_mastery

    # engagement from time spent vs expected duration and ZPD fit
    expected = max(float(entry["duration"]), 1e-6)
    ratio = float(np.clip(actual_duration / expected, 0.0, 2.0))
    engagement = float(
        np.clip(
            0.6 * zpd + 0.4 * (ratio / 2.0),
            0.0,
            1.0,
        )
    )

    # -------- mutate profile -------------------------------------------------
    profile["mastery_est"][topic] = new_mastery
    profile["attempts"][topic] = int(profile["attempts"][topic]) + 1

    recent = list(profile.get("recent_scores", []))
    recent.append(float(score))
    profile["recent_scores"] = recent[-5:]

    profile["total_time_min"] = float(profile["total_time_min"]) + float(actual_duration)
    profile["engagement_ma"] = 0.7 * float(profile["engagement_ma"]) + 0.3 * engagement
    profile["last_difficulty"] = float(entry["difficulty"])
    profile["last_score"] = float(score)
    profile["n_interactions"] = int(profile["n_interactions"]) + 1

    # crude ability re-estimate from rolling scores
    if len(profile["recent_scores"]) >= 3:
        profile["ability"] = float((np.mean(profile["recent_scores"]) - 50.0) / 25.0)

    return {
        "gain": round(gain, 4),
        "new_mastery": round(new_mastery, 4),
        "engagement": round(engagement, 4),
        "zpd_fit": round(zpd, 4),
    }
