"""Lightweight NumPy-only inference for the exported score predictor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.feature_schema import LEARNING_GOALS, RESOURCE_TYPES

DESIGN_COLUMNS = (
    "candidate_topic_mastery",
    "prerequisite_mastery_average",
    "difficulty_gap",
    "engagement",
    "recent_score_trend",
    "attempts",
    "time",
    "learner_level",
    "log_attempts",
    "log_time",
    *(f"rtype_{item}" for item in RESOURCE_TYPES),
    *(f"goal_{item}" for item in LEARNING_GOALS),
)


class NumpyPipeline:
    def __init__(
        self,
        columns_after_corr: list[str],
        selected_idx: list[int],
        mean: np.ndarray,
        scale: np.ndarray,
    ):
        self.columns_after_corr_ = columns_after_corr
        self.selected_idx_ = selected_idx
        self.mean = mean
        self.scale = scale

    def transform(self, features: pd.DataFrame) -> np.ndarray:
        values: dict[str, np.ndarray] = {}
        for column in DESIGN_COLUMNS:
            if column in features:
                values[column] = features[column].to_numpy(dtype=np.float64)
            elif column == "log_attempts":
                values[column] = np.log1p(features["attempts"].to_numpy(dtype=np.float64))
            elif column == "log_time":
                values[column] = np.log1p(features["time"].to_numpy(dtype=np.float64))
            elif column.startswith("rtype_"):
                values[column] = (
                    features["resource_type"].to_numpy() == column.removeprefix("rtype_")
                ).astype(np.float64)
            elif column.startswith("goal_"):
                values[column] = (
                    features["learning_goal"].to_numpy() == column.removeprefix("goal_")
                ).astype(np.float64)
            else:
                raise ValueError(f"Unsupported serving feature: {column}")
        matrix = np.column_stack([values[name] for name in self.columns_after_corr_])
        standardized = (matrix - self.mean) / self.scale
        return standardized[:, self.selected_idx_].astype(np.float32)


class NumpyPredictor:
    def __init__(self, pipeline: NumpyPipeline, weights: list[np.ndarray]):
        self.pipeline = pipeline
        self.weights = weights

    @classmethod
    def load(cls, directory: str | Path) -> NumpyPredictor:
        path = Path(directory)
        with (path / "serving_model.json").open(encoding="utf-8") as stream:
            metadata = json.load(stream)
        with np.load(path / "serving_model.npz", allow_pickle=False) as arrays:
            pipeline = NumpyPipeline(
                metadata["columns_after_corr"],
                metadata["selected_idx"],
                arrays["scaler_mean"],
                arrays["scaler_scale"],
            )
            weights = [
                pair
                for index in range(metadata["dense_layers"])
                for pair in (arrays[f"kernel_{index}"], arrays[f"bias_{index}"])
            ]
        return cls(pipeline, weights)

    def predict(self, features: Any) -> np.ndarray:
        values = self.pipeline.transform(features)
        for index in range(0, len(self.weights), 2):
            values = values @ self.weights[index] + self.weights[index + 1]
            if index < len(self.weights) - 2:
                values = np.maximum(values, 0)
        return np.clip(values.reshape(-1) * 100.0, 0.0, 100.0)
