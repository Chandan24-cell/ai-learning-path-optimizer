# Task 2 -- Data Transformation & Feature Selection

## 2.1 Transformations
* Candidate mastery, prerequisite average, difficulty gap, engagement, recent score trend, attempts, resource type, cumulative time, learner level, and learning goal are used.
* Skewed counts and cumulative time use `log1p`; resource types and learning goals use fixed one-hot lists.
* All numeric features z-score standardised (`StandardScaler`) **fit on the training split only**.

## 2.2 Feature selection
* Input features: **19**
* After variance filter: **19**  (dropped: none)
* After correlation filter (|r| > 0.95): **19**  (dropped: none)
* After mutual-information top-k: **15**

### Selected features
```
candidate_topic_mastery
difficulty_gap
learner_level
prerequisite_mastery_average
attempts
log_attempts
engagement
recent_score_trend
time
rtype_video
goal_skill
log_time
rtype_project
goal_exam
goal_career
```

## 2.3 Data reduction (PCA)
* Components for 90% variance: **10** / 15
* Components for 95% variance: **11** / 15

## 2.4 Leakage control
The train/val/test split is performed **by random topic graph**, so the test graph is unseen during training. Learners are also disjoint. The scaler and MI selection are fitted on train only.