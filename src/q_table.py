"""Safe JSON serialization for trained Q-table artifacts."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from src.feature_schema import N_Q_ACTIONS, N_Q_STATE_VALUES


def save_q_table(
    q_table: Mapping[tuple[int, ...], np.ndarray | Sequence[float]], path: str | Path
) -> None:
    for state, values in q_table.items():
        if len(state) != N_Q_STATE_VALUES or len(values) != N_Q_ACTIONS:
            raise ValueError("Q-table state or action-value vector has an invalid shape")
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("Q-table action values must be finite")
    rows = [
        {"state": list(state), "values": [float(value) for value in values]}
        for state, values in sorted(q_table.items())
    ]
    Path(path).write_text(
        json.dumps(rows, separators=(",", ":"), allow_nan=False), encoding="utf-8"
    )


def load_q_table(path: str | Path) -> dict[tuple[int, ...], np.ndarray]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Q-table artifact must contain a list")

    q_table: dict[tuple[int, ...], np.ndarray] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Q-table rows must be objects")
        state = row.get("state")
        values = row.get("values")
        if (
            not isinstance(state, list)
            or len(state) != N_Q_STATE_VALUES
            or any(type(value) is not int for value in state)
            or not isinstance(values, list)
            or len(values) != N_Q_ACTIONS
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in values
            )
        ):
            raise ValueError("Q-table row has an invalid state or action-value vector")
        key = tuple(state)
        if key in q_table:
            raise ValueError("Q-table artifact contains a duplicate state")
        q_table[key] = np.asarray(values, dtype=float)
    return q_table
