"""Build README charts from checked-in reports and the latest coverage data."""

from __future__ import annotations

from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
from coverage import Coverage

ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "docs" / "images"
TASK6_REPORT = ROOT / "outputs" / "reports" / "task6_evaluation.md"
VALIDATION_REPORT = ROOT / "docs" / "VALIDATION_REPORT.md"


def _markdown_table_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if not line.startswith("|") or set(line.strip()) <= {"|", "-", ":", " "}:
            continue
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def _policy_rows() -> list[list[str]]:
    labels = {
        "Static curriculum",
        "Behavior policy",
        "ZPD heuristic",
        "Q-learning",
        "Hybrid optimizer",
    }
    rows = [
        row for row in _markdown_table_rows(TASK6_REPORT.read_text()) if row and row[0] in labels
    ]
    if len(rows) != len(labels):
        raise ValueError(f"Expected five policy rows in {TASK6_REPORT}")
    return rows


def _load_rows() -> list[list[str]]:
    report = VALIDATION_REPORT.read_text()
    section = report.split("### Phase F steady-state load results", 1)[-1]
    rows = [
        row
        for row in _markdown_table_rows(section)
        if row and row[0] in {"10", "50", "100"}
    ]
    if len(rows) != 3:
        raise ValueError(f"Expected the latest 10/50/100-user table in {VALIDATION_REPORT}")
    return rows


def _number(value: str) -> float:
    return float(value.replace(",", "").replace("%", "").replace("ms", "").strip())


def _copy_existing_plot(source: Path, destination: Path, title: str) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Required generated plot is missing: {source}")
    image = mpimg.imread(source)
    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.imshow(image)
    axis.set_title(title)
    axis.axis("off")
    figure.tight_layout()
    figure.savefig(destination, dpi=160, bbox_inches="tight")
    plt.close(figure)


def _plot_policy_results(rows: list[list[str]]) -> None:
    names = [row[0] for row in rows]
    means = [_number(row[1]) for row in rows]
    deviations = [_number(row[2]) for row in rows]
    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.bar(names, means, yerr=deviations, capsize=4, color="#386cb0")
    axis.set_ylabel("Mean simulated gain")
    axis.set_title("Policy comparison on simulated learners")
    axis.tick_params(axis="x", rotation=20)
    figure.tight_layout()
    figure.savefig(IMAGE_DIR / "policy-comparison.png", dpi=160)
    plt.close(figure)


def _plot_group_gaps(rows: list[list[str]]) -> None:
    names = [row[0] for row in rows]
    columns = [
        ("Ability gap", 5),
        ("Level gap", 6),
        ("Engagement gap", 7),
        ("Mastery gap", 8),
    ]
    x = np.arange(len(names))
    width = 0.19
    figure, axis = plt.subplots(figsize=(10, 5))
    for offset, (label, column) in enumerate(columns):
        axis.bar(
            x + (offset - 1.5) * width,
            [_number(row[column]) for row in rows],
            width,
            label=label,
        )
    axis.set_xticks(x, names, rotation=20, ha="right")
    axis.set_ylabel("Absolute simulated group gap")
    axis.set_title("Measured group gaps in the simulator")
    axis.legend()
    figure.tight_layout()
    figure.savefig(IMAGE_DIR / "fairness-group-gaps.png", dpi=160)
    plt.close(figure)


def _plot_load_results(rows: list[list[str]]) -> None:
    labels = ["10 users", "50 users", "100 users"]
    users = [10, 50, 100]
    requests_per_second = [_number(row[2]) for row in rows]
    p95_ms = [_number(row[4]) for row in rows]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    axes[0].plot(users, requests_per_second, marker="o", color="#1b9e77")
    axes[0].set_title("Throughput")
    axes[0].set_ylabel("Requests per second")
    axes[1].plot(users, p95_ms, marker="o", color="#d95f02")
    axes[1].set_title("Tail response time")
    axes[1].set_ylabel("p95 milliseconds")
    for axis in axes:
        axis.set_xticks(users, labels, rotation=15, ha="right")
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle("Local simulated-user load test")
    figure.tight_layout()
    figure.savefig(IMAGE_DIR / "load-test.png", dpi=160)
    plt.close(figure)


def _plot_coverage() -> None:
    coverage_file = ROOT / ".coverage"
    if not coverage_file.is_file():
        raise FileNotFoundError("Run pytest before generating the coverage chart.")
    coverage = Coverage(data_file=str(coverage_file))
    coverage.load()
    modules: list[tuple[str, float]] = []
    for measured_file in coverage.get_data().measured_files():
        path = Path(measured_file).resolve()
        try:
            label = path.relative_to(ROOT / "app").as_posix()
        except ValueError:
            continue
        if path.suffix != ".py":
            continue
        _, statements, _, missing, _ = coverage.analysis2(str(path))
        if statements:
            percent = 100 * (len(statements) - len(missing)) / len(statements)
            modules.append((label, percent))
    if not modules:
        raise ValueError("No measured application modules found in the latest coverage data.")
    modules.sort(key=lambda item: item[1])
    labels, values = zip(*modules, strict=True)
    figure, axis = plt.subplots(figsize=(9, max(4, len(labels) * 0.28)))
    axis.barh(labels, values, color="#7570b3")
    axis.set_xlim(0, 100)
    axis.set_xlabel("Line coverage (%)")
    axis.set_title("Latest pytest coverage by application module")
    axis.grid(axis="x", alpha=0.25)
    figure.tight_layout()
    figure.savefig(IMAGE_DIR / "test-coverage.png", dpi=160)
    plt.close(figure)


def main() -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    _copy_existing_plot(
        ROOT / "outputs" / "plots" / "task3_training_curve.png",
        IMAGE_DIR / "predictor-training-curve.png",
        "Simulated score predictor: training artifact",
    )
    _copy_existing_plot(
        ROOT / "outputs" / "plots" / "task3_pred_vs_actual.png",
        IMAGE_DIR / "predicted-vs-actual.png",
        "Simulated score predictor: held-out predictions",
    )
    policies = _policy_rows()
    _plot_policy_results(policies)
    _plot_group_gaps(policies)
    _plot_load_results(_load_rows())
    _plot_coverage()
    print(f"Wrote README charts to {IMAGE_DIR}")


if __name__ == "__main__":
    main()
