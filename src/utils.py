"""Small shared helpers: seeding, smoothing, plotting, IO."""

from __future__ import annotations

import json
import os
import random

import matplotlib

matplotlib.use("Agg")  # headless-safe
import matplotlib.pyplot as plt
import numpy as np


def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import tensorflow as tf

        tf.keras.utils.set_random_seed(seed)
    except ImportError:
        return


def smooth(values, window: int = 50) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if len(values) < window:
        return values
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="valid")


def save_json(obj, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=str)


def save_fig(fig, name: str) -> str:
    from src.config import PLOT_DIR

    path = os.path.join(PLOT_DIR, name)
    fig.tight_layout()
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def gini(x) -> float:
    """Gini coefficient of a non-negative array."""
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    if n == 0 or x.sum() == 0:
        return 0.0
    index = np.arange(1, n + 1)
    return float((2 * np.sum(index * x)) / (n * np.sum(x)) - (n + 1) / n)


def banner(title: str) -> None:
    line = "=" * 78
    print(f"\n{line}\n{title}\n{line}")
