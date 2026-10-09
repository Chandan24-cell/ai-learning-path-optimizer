"""Central configuration for the AI-Powered Personalized Learning Path Optimizer."""

from __future__ import annotations

import os

SEED = 42

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
MODEL_DIR = os.path.join(OUTPUT_DIR, "models")
PLOT_DIR = os.path.join(OUTPUT_DIR, "plots")
REPORT_DIR = os.path.join(OUTPUT_DIR, "reports")
DATA_DIR = os.path.join(OUTPUT_DIR, "data")

for _d in (OUTPUT_DIR, MODEL_DIR, PLOT_DIR, REPORT_DIR, DATA_DIR):
    os.makedirs(_d, exist_ok=True)

# --------------------------------------------------------------------------
# Domain
# --------------------------------------------------------------------------
N_STUDENTS = 400

N_TOPICS = 6
TOPIC_NAMES = [
    "Algebra",
    "Geometry",
    "Probability",
    "Calculus",
    "Statistics",
    "Linear Algebra",
]
# intrinsic difficulty of each topic (1 = easy, 5 = hard)
TOPIC_DIFFICULTY = [1.5, 2.0, 3.0, 3.8, 3.0, 3.4]

RESOURCE_TYPES = ["video", "article", "quiz", "interactive", "project"]
N_RESOURCE_TYPES = len(RESOURCE_TYPES)

# (learning_power, engagement_prior, duration_minutes, difficulty_offset)
RESOURCE_PROFILE = {
    "video": (0.50, 0.70, 12, -0.7),
    "article": (0.45, 0.45, 18, -0.3),
    "quiz": (0.65, 0.55, 10, 0.2),
    "interactive": (0.80, 0.85, 25, 0.0),
    "project": (0.90, 0.90, 45, 0.5),
}

DIFFICULTY_STEPS = (-2, -1, 0, 1, 2)
N_ACTIONS = N_RESOURCE_TYPES * len(DIFFICULTY_STEPS)  # 25 abstract actions

# --------------------------------------------------------------------------
# Learning dynamics
# --------------------------------------------------------------------------
LR_SCALE = 0.07  # maximum mastery gain per interaction
ZPD_SIGMA = 1.0  # width of the zone-of-proximal-development kernel

# --------------------------------------------------------------------------
# Reinforcement learning
# --------------------------------------------------------------------------
EPISODE_LENGTH = 30
N_QL_EPISODES = 2500
QL_ALPHA = 0.15
QL_GAMMA = 0.95
QL_EPS_START = 1.0
QL_EPS_END = 0.05

MASTERY_BINS = 3
SCORE_BINS = 3
ENGAGE_BINS = 2

# --------------------------------------------------------------------------
# Supervised learning
# --------------------------------------------------------------------------
N_INTERACTIONS = 40  # logged interactions per student
TRAIN_FRACTION = 0.60
VAL_FRACTION = 0.15
TEST_FRACTION = 0.25

N_EVAL_STUDENTS = 100
