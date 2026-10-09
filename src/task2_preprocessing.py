"""Task 2 -- Data transformation, feature selection, data reduction."""

from __future__ import annotations

import os

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.feature_selection import VarianceThreshold, mutual_info_regression
from sklearn.preprocessing import StandardScaler

from src.config import (
    DATA_DIR,
    MODEL_DIR,
    REPORT_DIR,
    SEED,
    TRAIN_FRACTION,
    VAL_FRACTION,
)
from src.data_generation import load_or_create
from src.feature_schema import build_design_matrix
from src.utils import banner, save_fig

PIPELINE_PATH = os.path.join(MODEL_DIR, "pipeline.joblib")
PROCESSED_PATH = os.path.join(DATA_DIR, "processed.npz")


# --------------------------------------------------------------------------
# Leak-free pipeline
# --------------------------------------------------------------------------
class FeaturePipeline:
    """Variance filter -> correlation filter -> scaling -> mutual-information."""

    def __init__(self, mi_k: int = 15, corr_threshold: float = 0.95):
        self.mi_k = mi_k
        self.corr_threshold = corr_threshold
        self.scaler_ = None
        self.columns_after_var_: list = []
        self.columns_after_corr_: list = []
        self.selected_columns_: list = []
        self.selected_idx_: list = []
        self.mi_scores_: pd.Series | None = None
        self.dropped_constant_: list = []
        self.dropped_correlated_: list = []

    # ------------------------------------------------------------------ fit
    def fit(self, df: pd.DataFrame, y: np.ndarray) -> FeaturePipeline:
        X = build_design_matrix(df)
        all_cols = list(X.columns)

        # 1. remove near-constant features
        vt = VarianceThreshold(threshold=1e-8).fit(X.values)
        self.columns_after_var_ = [
            c for c, keep in zip(all_cols, vt.get_support(), strict=True) if keep
        ]
        self.dropped_constant_ = [c for c in all_cols if c not in self.columns_after_var_]

        # 2. remove highly correlated features (keep the earlier one)
        Z = StandardScaler().fit_transform(X[self.columns_after_var_].values)
        corr = np.corrcoef(Z, rowvar=False)
        corr = np.nan_to_num(corr, nan=0.0)
        drop = set()
        cols = self.columns_after_var_
        for i in range(len(cols)):
            if cols[i] in drop:
                continue
            for j in range(i + 1, len(cols)):
                if abs(corr[i, j]) > self.corr_threshold:
                    drop.add(cols[j])
        self.columns_after_corr_ = [c for c in cols if c not in drop]
        self.dropped_correlated_ = sorted(drop)

        # 3. z-score standardisation
        self.scaler_ = StandardScaler().fit(X[self.columns_after_corr_].values)
        Z2 = self.scaler_.transform(X[self.columns_after_corr_].values)

        # 4. mutual-information feature selection
        mi = mutual_info_regression(Z2, y, random_state=SEED)
        self.mi_scores_ = pd.Series(mi, index=self.columns_after_corr_).sort_values(ascending=False)
        k = min(self.mi_k, len(self.columns_after_corr_))
        self.selected_columns_ = list(self.mi_scores_.index[:k])
        self.selected_idx_ = [self.columns_after_corr_.index(c) for c in self.selected_columns_]
        return self

    # -------------------------------------------------------------- transform
    def transform(self, df: pd.DataFrame) -> np.ndarray:
        X = build_design_matrix(df)
        Z = self.scaler_.transform(X[self.columns_after_corr_].values)
        Z = Z[:, self.selected_idx_]
        return Z.astype(np.float32)

    # ------------------------------------------------------------------ info
    def summary(self) -> dict:
        return dict(
            n_input_features=len(self.columns_after_var_) + len(self.dropped_constant_),
            n_after_variance=len(self.columns_after_var_),
            n_after_correlation=len(self.columns_after_corr_),
            n_selected=len(self.selected_columns_),
            dropped_constant=self.dropped_constant_,
            dropped_correlated=self.dropped_correlated_,
            selected=self.selected_columns_,
            mi_scores=self.mi_scores_.round(5).to_dict() if self.mi_scores_ is not None else {},
        )


# --------------------------------------------------------------------------
# Splitting (by student -- no learner leakage)
# --------------------------------------------------------------------------
def split_by_student(df: pd.DataFrame, seed: int = SEED):
    if "graph_id" in df and df["graph_id"].nunique() >= 3:
        graph_ids = np.array(sorted(df["graph_id"].unique()))
        rng = np.random.default_rng(seed)
        rng.shuffle(graph_ids)
        n_train = max(1, int(len(graph_ids) * TRAIN_FRACTION))
        n_val = max(1, int(len(graph_ids) * VAL_FRACTION))
        if n_train + n_val >= len(graph_ids):
            n_train = len(graph_ids) - 2
        train_graphs = set(graph_ids[:n_train])
        val_graphs = set(graph_ids[n_train : n_train + n_val])
        test_graphs = set(graph_ids[n_train + n_val :])
        return (
            df[df["graph_id"].isin(train_graphs)].reset_index(drop=True),
            df[df["graph_id"].isin(val_graphs)].reset_index(drop=True),
            df[df["graph_id"].isin(test_graphs)].reset_index(drop=True),
        )

    ids = np.sort(df["student_id"].unique())
    rng = np.random.default_rng(seed)
    rng.shuffle(ids)

    n = len(ids)
    n_train = int(n * TRAIN_FRACTION)
    n_val = int(n * VAL_FRACTION)

    train_ids = set(ids[:n_train].tolist())
    val_ids = set(ids[n_train : n_train + n_val].tolist())
    test_ids = set(ids[n_train + n_val :].tolist())

    return (
        df[df["student_id"].isin(train_ids)].reset_index(drop=True),
        df[df["student_id"].isin(val_ids)].reset_index(drop=True),
        df[df["student_id"].isin(test_ids)].reset_index(drop=True),
    )


# --------------------------------------------------------------------------
# Data-reduction report
# --------------------------------------------------------------------------
def pca_report(X: np.ndarray) -> dict:
    pca_full = PCA(random_state=SEED).fit(X)
    cum = np.cumsum(pca_full.explained_variance_ratio_)

    n90 = int(np.searchsorted(cum, 0.90) + 1)
    n95 = int(np.searchsorted(cum, 0.95) + 1)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(np.arange(1, len(cum) + 1), cum, marker="o", ms=4)
    ax.axhline(0.90, color="orange", ls="--", lw=1, label="90% variance")
    ax.axhline(0.95, color="red", ls="--", lw=1, label="95% variance")
    ax.set_xlabel("Number of principal components")
    ax.set_ylabel("Cumulative explained variance")
    ax.set_title("PCA -- data reduction")
    ax.legend()
    ax.grid(alpha=0.3)
    save_fig(fig, "task2_pca_explained_variance.png")

    return dict(n_components_90=n90, n_components_95=n95, total_components=len(cum))


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main(force_data: bool = False):
    banner("TASK 2 -- DATA TRANSFORMATION & FEATURE SELECTION")

    df = load_or_create(force=force_data)
    train_df, val_df, test_df = split_by_student(df)

    print(f"[task2] train rows={len(train_df)}  val rows={len(val_df)}  test rows={len(test_df)}")

    y_train = (train_df["score"].values / 100.0).astype(np.float32)
    y_val = (val_df["score"].values / 100.0).astype(np.float32)
    y_test = (test_df["score"].values / 100.0).astype(np.float32)

    pipe = FeaturePipeline(mi_k=15, corr_threshold=0.95).fit(train_df, y_train)

    X_train = pipe.transform(train_df)
    X_val = pipe.transform(val_df)
    X_test = pipe.transform(test_df)

    summary = pipe.summary()
    pca_info = pca_report(X_train)
    summary.update(pca_info)

    # ---- plots -----------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 5))
    ms = pipe.mi_scores_.head(15)[::-1]
    ax.barh(ms.index, ms.values, color="#2b6cb0")
    ax.set_xlabel("Mutual information with next score")
    ax.set_title("Top features by mutual information")
    ax.grid(alpha=0.3, axis="x")
    save_fig(fig, "task2_mutual_information.png")

    # ---- persist ---------------------------------------------------------
    joblib.dump(pipe, PIPELINE_PATH)
    np.savez_compressed(
        PROCESSED_PATH,
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
        train_ids=train_df["student_id"].unique(),
        val_ids=val_df["student_id"].unique(),
        test_ids=test_df["student_id"].unique(),
    )

    # ---- report ----------------------------------------------------------
    lines = [
        "# Task 2 -- Data Transformation & Feature Selection",
        "",
        "## 2.1 Transformations",
        (
            "* Candidate mastery, prerequisite average, difficulty gap, engagement, recent score "
            "trend, attempts, resource type, and cumulative time are used."
        ),
        "* Skewed counts and cumulative time use `log1p`; resource types use a fixed one-hot list.",
        (
            "* All numeric features z-score standardised (`StandardScaler`) **fit on the training "
            "split only**."
        ),
        "",
        "## 2.2 Feature selection",
        f"* Input features: **{summary['n_input_features']}**",
        (
            f"* After variance filter: **{summary['n_after_variance']}**  "
            f"(dropped: {summary['dropped_constant'] or 'none'})"
        ),
        (
            f"* After correlation filter (|r| > 0.95): **{summary['n_after_correlation']}**  "
            f"(dropped: {summary['dropped_correlated'] or 'none'})"
        ),
        f"* After mutual-information top-k: **{summary['n_selected']}**",
        "",
        "### Selected features",
        "```",
        "\n".join(summary["selected"]),
        "```",
        "",
        "## 2.3 Data reduction (PCA)",
        f"* Components for 90% variance: **{summary['n_components_90']}** / "
        f"{summary['total_components']}",
        f"* Components for 95% variance: **{summary['n_components_95']}** / "
        f"{summary['total_components']}",
        "",
        "## 2.4 Leakage control",
        (
            "The train/val/test split is performed **by random topic graph**, so the test graph "
            "is unseen during training. Learners are also disjoint. The scaler and MI selection "
            "are fitted on train only."
        ),
    ]
    report_path = os.path.join(REPORT_DIR, "task2_preprocessing.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(f"[task2] selected {summary['n_selected']} features (from {summary['n_after_variance']})")
    print(f"[task2] PCA: {summary['n_components_90']} comps for 90% variance")
    print(f"[task2] pipeline -> {PIPELINE_PATH}")
    print(f"[task2] report   -> {report_path}")

    return dict(
        pipeline=pipe,
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        X_test=X_test,
        y_test=y_test,
        summary=summary,
        report_path=report_path,
    )


if __name__ == "__main__":
    main()
