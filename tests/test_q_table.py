from __future__ import annotations

import json

import numpy as np
import pytest

from src.feature_schema import N_Q_ACTIONS, N_Q_STATE_VALUES
from src.q_table import load_q_table, save_q_table


def test_q_table_json_round_trip(tmp_path) -> None:
    path = tmp_path / "q_table.json"
    original = {
        (0, 1, 2, 0): np.linspace(-1.0, 1.0, N_Q_ACTIONS),
        (2, 2, 1, 1): np.zeros(N_Q_ACTIONS),
    }

    save_q_table(original, path)

    loaded = load_q_table(path)
    assert loaded.keys() == original.keys()
    for state, values in original.items():
        np.testing.assert_array_equal(loaded[state], values)


def test_q_table_saver_rejects_non_finite_values(tmp_path) -> None:
    path = tmp_path / "q_table.json"
    table = {(0,) * N_Q_STATE_VALUES: np.full(N_Q_ACTIONS, float("nan"))}

    with pytest.raises(ValueError):
        save_q_table(table, path)


@pytest.mark.parametrize(
    "rows",
    [
        {},
        [{"state": [0] * (N_Q_STATE_VALUES - 1), "values": [0] * N_Q_ACTIONS}],
        [{"state": [0] * N_Q_STATE_VALUES, "values": [0] * (N_Q_ACTIONS - 1)}],
        [{"state": [0] * (N_Q_STATE_VALUES - 1) + [True], "values": [0] * N_Q_ACTIONS}],
        [{"state": [0] * N_Q_STATE_VALUES, "values": [float("nan")] * N_Q_ACTIONS}],
    ],
)
def test_q_table_loader_rejects_malformed_rows(tmp_path, rows) -> None:
    path = tmp_path / "q_table.json"
    path.write_text(json.dumps(rows), encoding="utf-8")

    with pytest.raises(ValueError):
        load_q_table(path)


def test_q_table_loader_rejects_duplicate_states(tmp_path) -> None:
    row = {"state": [0] * N_Q_STATE_VALUES, "values": [0] * N_Q_ACTIONS}
    path = tmp_path / "q_table.json"
    path.write_text(json.dumps([row, row]), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate state"):
        load_q_table(path)
