"""Task 3 -- Predictive component (TensorFlow workflow + hyper-parameter tuning)."""

from __future__ import annotations

import json
import os

import joblib
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src.config import MODEL_DIR, REPORT_DIR, SEED
from src.task2_preprocessing import PIPELINE_PATH, PROCESSED_PATH
from src.utils import banner, save_fig, set_seed

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers

    HAS_TF = True
except Exception:  # pragma: no cover
    HAS_TF = False

PREDICTOR_DIR = os.path.join(MODEL_DIR, "predictor")

# --------------------------------------------------------------------------
# Hyper-parameter search space
# --------------------------------------------------------------------------
SEARCH_SPACE = [
    dict(units=32, dropout=0.00, n_layers=1, lr=1e-3, batch_size=32),
    dict(units=64, dropout=0.10, n_layers=2, lr=1e-3, batch_size=32),
    dict(units=128, dropout=0.20, n_layers=2, lr=5e-4, batch_size=64),
    dict(units=64, dropout=0.00, n_layers=3, lr=1e-3, batch_size=64),
    dict(units=256, dropout=0.30, n_layers=2, lr=1e-3, batch_size=32),
    dict(units=96, dropout=0.15, n_layers=2, lr=2e-3, batch_size=128),
]


# --------------------------------------------------------------------------
# TensorFlow model builder
# --------------------------------------------------------------------------
def build_tf_model(input_dim: int, units: int, dropout: float, n_layers: int, lr: float):
    tf.keras.utils.set_random_seed(SEED)
    inputs = keras.Input(shape=(input_dim,), name="learner_state_action")
    x = inputs
    for i in range(n_layers):
        x = layers.Dense(units, activation="relu", name=f"dense_{i}")(x)
        if dropout > 0:
            x = layers.Dropout(dropout, name=f"dropout_{i}")(x)
    outputs = layers.Dense(1, name="next_score")(x)

    model = keras.Model(inputs, outputs, name="score_predictor")
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=lr),
        loss="mse",
        metrics=["mae"],
    )
    return model


# --------------------------------------------------------------------------
# Predictor wrapper (TF with sklearn fallback)
# --------------------------------------------------------------------------
class ScorePredictor:
    def __init__(self, pipeline, kind: str, model=None, params: dict | None = None):
        self.pipeline = pipeline
        self.kind = kind
        self.model = model
        self.params = params or {}

    def predict(self, df) -> np.ndarray:
        X = self.pipeline.transform(df)
        if self.kind == "tf":
            pred = self.model(X, training=False).numpy().ravel()
        else:
            pred = self.model.predict(X)
        return np.clip(np.asarray(pred, dtype=float) * 100.0, 0.0, 100.0)

    # ------------------------------------------------------------- persistence
    def save(self, directory: str = PREDICTOR_DIR) -> None:
        os.makedirs(directory, exist_ok=True)
        joblib.dump(self.pipeline, os.path.join(directory, "pipeline.joblib"))
        if self.kind == "tf":
            self.model.save(os.path.join(directory, "score_model.keras"))
        else:
            joblib.dump(self.model, os.path.join(directory, "score_model.joblib"))
        with open(os.path.join(directory, "meta.json"), "w", encoding="utf-8") as fh:
            json.dump({"kind": self.kind, "params": self.params}, fh, indent=2, default=str)

    @classmethod
    def load(cls, directory: str = PREDICTOR_DIR) -> ScorePredictor:
        pipeline = joblib.load(os.path.join(directory, "pipeline.joblib"))
        with open(os.path.join(directory, "meta.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
        if meta["kind"] == "tf":
            model = keras.models.load_model(os.path.join(directory, "score_model.keras"))
        else:
            model = joblib.load(os.path.join(directory, "score_model.joblib"))
        return cls(pipeline, meta["kind"], model, meta["params"])


# --------------------------------------------------------------------------
# Training
# --------------------------------------------------------------------------
def _load_processed():
    data = np.load(PROCESSED_PATH, allow_pickle=True)
    return (
        data["X_train"],
        data["y_train"],
        data["X_val"],
        data["y_val"],
        data["X_test"],
        data["y_test"],
    )


def _train_tf(X_train, y_train, X_val, y_val, cfg):
    model = build_tf_model(
        X_train.shape[1],
        units=cfg["units"],
        dropout=cfg["dropout"],
        n_layers=cfg["n_layers"],
        lr=cfg["lr"],
    )
    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=12, restore_best_weights=True, min_delta=1e-5
        ),
        keras.callbacks.ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=5, min_lr=1e-5),
    ]
    history = model.fit(
        X_train,
        y_train,
        validation_data=(X_val, y_val),
        epochs=120,
        batch_size=cfg["batch_size"],
        verbose=0,
        callbacks=callbacks,
    )
    val_pred = model(X_val, training=False).numpy().ravel()
    val_rmse = float(np.sqrt(mean_squared_error(y_val, val_pred)))
    return model, history, val_rmse


def _train_sklearn(X_train, y_train, X_val, y_val, cfg):
    from sklearn.neural_network import MLPRegressor

    model = MLPRegressor(
        hidden_layer_sizes=tuple([cfg["units"]] * cfg["n_layers"]),
        alpha=cfg["dropout"] * 1e-2,
        learning_rate_init=cfg["lr"],
        batch_size=min(cfg["batch_size"], len(X_train)),
        max_iter=400,
        early_stopping=True,
        n_iter_no_change=12,
        random_state=SEED,
    )
    model.fit(X_train, y_train)
    val_pred = model.predict(X_val)
    val_rmse = float(np.sqrt(mean_squared_error(y_val, val_pred)))
    return model, model.loss_curve_, val_rmse


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main():
    banner("TASK 3 -- PREDICTIVE MODEL (TensorFlow) + HYPER-PARAMETER TUNING")
    set_seed(SEED)

    pipeline = joblib.load(PIPELINE_PATH)
    X_train, y_train, X_val, y_val, X_test, y_test = _load_processed()

    backend = "TensorFlow/Keras" if HAS_TF else "scikit-learn MLP (TensorFlow not available)"
    print(f"[task3] backend: {backend}")
    print(f"[task3] train={X_train.shape}  val={X_val.shape}  test={X_test.shape}")

    results = []
    best = None
    for i, cfg in enumerate(SEARCH_SPACE, 1):
        if HAS_TF:
            model, history, val_rmse = _train_tf(X_train, y_train, X_val, y_val, cfg)
        else:
            model, history, val_rmse = _train_sklearn(X_train, y_train, X_val, y_val, cfg)
        results.append(dict(trial=i, val_rmse=val_rmse, **cfg))
        print(f"[task3] trial {i}/{len(SEARCH_SPACE)}  val_RMSE={val_rmse:.4f}  cfg={cfg}")
        if best is None or val_rmse < best["val_rmse"]:
            best = dict(trial=i, val_rmse=val_rmse, cfg=cfg, model=model, history=history)

    print(f"[task3] best trial {best['trial']}  val_RMSE={best['val_rmse']:.4f}")
    print(f"[task3] best config: {best['cfg']}")

    kind = "tf" if HAS_TF else "sklearn"
    predictor = ScorePredictor(pipeline, kind, best["model"], best["cfg"])
    predictor.save()

    # ---------------------------------------------------------- evaluation
    if kind == "tf":
        raw = best["model"](X_test, training=False).numpy().ravel()
    else:
        raw = best["model"].predict(X_test)
    raw = np.clip(raw, 0.0, 1.0)

    rmse = float(np.sqrt(mean_squared_error(y_test, raw)))
    mae = float(mean_absolute_error(y_test, raw))
    r2 = float(r2_score(y_test, raw))

    baseline = np.full_like(y_test, y_train.mean())
    b_rmse = float(np.sqrt(mean_squared_error(y_test, baseline)))
    b_r2 = float(r2_score(y_test, baseline))

    print(
        f"[task3] TEST  RMSE={rmse:.4f}  MAE={mae:.4f}  R2={r2:.4f}  "
        f"(score units x100: RMSE={rmse * 100:.2f})"
    )
    print(f"[task3] baseline (predict mean) RMSE={b_rmse:.4f}  R2={b_r2:.4f}")

    # ------------------------------------------------------------- plots
    hist = best["history"]
    fig, ax = plt.subplots(figsize=(6.5, 4))
    if kind == "tf":
        ax.plot(hist.history["loss"], label="train")
        ax.plot(hist.history["val_loss"], label="validation")
    else:
        ax.plot(hist, label="train (sklearn loss curve)")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("MSE loss (normalised score)")
    ax.set_title(f"Best model training curve (trial {best['trial']})")
    ax.legend()
    ax.grid(alpha=0.3)
    save_fig(fig, "task3_training_curve.png")

    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.scatter(y_test * 100, raw * 100, s=6, alpha=0.25, color="#2b6cb0")
    lims = [0, 100]
    ax.plot(lims, lims, "r--", lw=1.2)
    ax.set_xlabel("Actual next score")
    ax.set_ylabel("Predicted next score")
    ax.set_title(f"Predicted vs actual (R2 = {r2:.3f})")
    ax.grid(alpha=0.3)
    save_fig(fig, "task3_pred_vs_actual.png")

    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.hist((raw - y_test) * 100, bins=40, color="#805ad5", alpha=0.85)
    ax.set_xlabel("Residual (predicted - actual, score points)")
    ax.set_ylabel("Count")
    ax.set_title("Residual distribution")
    ax.grid(alpha=0.3)
    save_fig(fig, "task3_residuals.png")

    # ------------------------------------------------------------ report
    lines = [
        "# Task 3 -- Framework Implementation",
        "",
        f"**Backend:** {backend}",
        "",
        "## 3.1 Workflow",
        "1. Load the transformed, MI-selected feature matrices produced in Task 2.",
        "2. Build an MLP regressor predicting the **next assessment score**.",
        "3. Random/grid search over 6 hyper-parameter configurations.",
        "4. Early stopping + LR reduction on the validation split.",
        "5. Evaluate on a held-out set of **unseen students**.",
        "",
        "## 3.2 Hyper-parameter search",
        "| Trial | Layers | Units | Dropout | LR | Batch | Val RMSE |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['trial']} | {r['n_layers']} | {r['units']} | {r['dropout']} | "
            f"{r['lr']} | {r['batch_size']} | {r['val_rmse']:.4f} |"
        )
    lines += [
        "",
        f"**Best configuration:** `{best['cfg']}` (trial {best['trial']})",
        "",
        "## 3.3 Test-set performance (unseen students)",
        f"* RMSE (normalised): **{rmse:.4f}**  ->  **{rmse * 100:.2f} score points**",
        f"* MAE  (normalised): **{mae:.4f}**  ->  **{mae * 100:.2f} score points**",
        f"* R²   : **{r2:.4f}**",
        f"* Baseline (predict mean) RMSE: {b_rmse:.4f} / R²: {b_r2:.4f}",
        "",
        "## 3.4 Tuning strategy rationale",
        "* Small networks (1-3 layers, 32-256 units) suit ~10k tabular rows.",
        "* Dropout regularises; early stopping prevents over-fitting.",
        "* LR reduction on plateau stabilises convergence.",
        "* A wider search (Bayesian optimisation / Keras Tuner) is a drop-in replacement.",
    ]
    report_path = os.path.join(REPORT_DIR, "task3_model.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"[task3] model saved -> {PREDICTOR_DIR}")
    print(f"[task3] report     -> {report_path}")

    return dict(
        predictor=predictor,
        metrics=dict(rmse=rmse, mae=mae, r2=r2, baseline_rmse=b_rmse, baseline_r2=b_r2),
        search_results=results,
        best=best,
        report_path=report_path,
    )


if __name__ == "__main__":
    main()
