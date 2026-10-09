# Task 3 -- Framework Implementation

**Backend:** TensorFlow/Keras

## 3.1 Workflow
1. Load the transformed, MI-selected feature matrices produced in Task 2.
2. Build an MLP regressor predicting the **next assessment score**.
3. Random/grid search over 6 hyper-parameter configurations.
4. Early stopping + LR reduction on the validation split.
5. Evaluate on a held-out set of **unseen students**.

## 3.2 Hyper-parameter search
| Trial | Layers | Units | Dropout | LR | Batch | Val RMSE |
|---|---|---|---|---|---|---|
| 1 | 1 | 32 | 0.0 | 0.001 | 32 | 0.1045 |
| 2 | 2 | 64 | 0.1 | 0.001 | 32 | 0.1028 |
| 3 | 2 | 128 | 0.2 | 0.0005 | 64 | 0.1047 |
| 4 | 3 | 64 | 0.0 | 0.001 | 64 | 0.1053 |
| 5 | 2 | 256 | 0.3 | 0.001 | 32 | 0.1011 |
| 6 | 2 | 96 | 0.15 | 0.002 | 128 | 0.1013 |

**Best configuration:** `{'units': 256, 'dropout': 0.3, 'n_layers': 2, 'lr': 0.001, 'batch_size': 32}` (trial 5)

## 3.3 Test-set performance (unseen students)
* RMSE (normalised): **0.0944**  ->  **9.44 score points**
* MAE  (normalised): **0.0715**  ->  **7.15 score points**
* R²   : **0.8898**
* Baseline (predict mean) RMSE: 0.2967 / R²: -0.0889

## 3.4 Tuning strategy rationale
* Small networks (1-3 layers, 32-256 units) suit ~10k tabular rows.
* Dropout regularises; early stopping prevents over-fitting.
* LR reduction on plateau stabilises convergence.
* A wider search (Bayesian optimisation / Keras Tuner) is a drop-in replacement.