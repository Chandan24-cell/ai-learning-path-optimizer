"""End-to-end driver for the AI-Powered Personalized Learning Path Optimizer.

Usage:
    python run_all.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import (
    data_generation,
    task1_problem_analysis,
    task2_preprocessing,
    task3_model,
    task4_qlearning,
    task5_optimizer,
    task6_evaluation,
    task7_conclusion,
)
from src.config import DATA_DIR, MODEL_DIR, PLOT_DIR, REPORT_DIR
from src.utils import banner, set_seed


def main() -> None:
    started = time.time()

    print("""
+--------------------------------------------------------------------------+
|  AI-POWERED PERSONALIZED LEARNING PATH OPTIMIZATION                      |
|  End-to-end reference implementation                                     |
+--------------------------------------------------------------------------+
""")

    set_seed()

    # ---------------------------------------------------------------- Task 1
    task1_problem_analysis.main()

    # ---------------------------------------------------------------- data
    banner("DATA GENERATION")
    data_generation.main()

    # ---------------------------------------------------------------- Task 2
    task2_preprocessing.main()

    # ---------------------------------------------------------------- Task 3
    task3 = task3_model.main()
    predictor = task3["predictor"]

    # ---------------------------------------------------------------- Task 4
    task4 = task4_qlearning.main()
    q_table = task4["q_table"]

    # ---------------------------------------------------------------- Task 5
    task5_optimizer.main(predictor, q_table)

    # ---------------------------------------------------------------- Task 6
    evaluation = task6_evaluation.main(predictor, q_table)

    # ---------------------------------------------------------------- Task 7
    task7_conclusion.main(evaluation)

    # ---------------------------------------------------------------- summary
    elapsed = time.time() - started
    banner("DONE")
    print(f"Total runtime: {elapsed:.1f} s\n")
    print("Artifacts:")
    for label, directory in (
        ("reports", REPORT_DIR),
        ("plots", PLOT_DIR),
        ("models", MODEL_DIR),
        ("data", DATA_DIR),
    ):
        print(f"  {label:<8} -> {directory}")
        for name in sorted(os.listdir(directory)):
            print(f"      - {name}")

    print("\nHeadline metrics")
    print(
        f"  Predictive model : RMSE = {task3['metrics']['rmse'] * 100:.2f} score points, "
        f"R2 = {task3['metrics']['r2']:.4f}"
    )
    print(
        f"  Q-learning       : avg reward {task4['avg_first']:.2f} -> {task4['avg_last']:.2f} "
        f"over {task4['n_states']} states"
    )
    print()
    print(evaluation["summary"].to_string(index=False, float_format=lambda v: f"{v:0.4f}"))
    print()


if __name__ == "__main__":
    main()
