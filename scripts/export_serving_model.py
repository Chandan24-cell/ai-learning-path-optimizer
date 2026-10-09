"""Export trusted saved predictor weights and preprocessing to a NumPy artifact."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
from tensorflow import keras

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


def export() -> Path:
    predictor_dir = settings.model_dir / "predictor"
    pipeline = joblib.load(predictor_dir / "pipeline.joblib")
    with (predictor_dir / "meta.json").open(encoding="utf-8") as stream:
        model_meta = json.load(stream)
    if model_meta["kind"] != "tf":
        raise ValueError("Only the saved TensorFlow predictor can be exported")

    model = keras.models.load_model(predictor_dir / "score_model.keras", compile=False)
    dense_layers = [layer for layer in model.layers if isinstance(layer, keras.layers.Dense)]
    arrays: dict[str, np.ndarray] = {
        "scaler_mean": np.asarray(pipeline.scaler_.mean_, dtype=np.float64),
        "scaler_scale": np.asarray(pipeline.scaler_.scale_, dtype=np.float64),
    }
    for index, layer in enumerate(dense_layers):
        kernel, bias = layer.get_weights()
        arrays[f"kernel_{index}"] = np.asarray(kernel, dtype=np.float32)
        arrays[f"bias_{index}"] = np.asarray(bias, dtype=np.float32)
    npz_path = predictor_dir / "serving_model.npz"
    np.savez_compressed(npz_path, **arrays)
    metadata = {
        "format": "numpy-dense-v1",
        "dense_layers": len(dense_layers),
        "columns_after_corr": pipeline.columns_after_corr_,
        "selected_idx": pipeline.selected_idx_,
        "activation": "relu-hidden-linear-output",
    }
    json_path = predictor_dir / "serving_model.json"
    json_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(
        f"Exported NumPy serving predictor: {npz_path.stat().st_size / 1024:.1f} KiB "
        f"(weights + pipeline)"
    )
    return predictor_dir


if __name__ == "__main__":
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    export()
