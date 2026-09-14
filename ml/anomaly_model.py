"""Loads the trained model and scores live feature vectors (design-doc §5.6).

Isolation Forest isolates points by recursively splitting on random
features/thresholds; outliers need fewer splits to isolate — a shorter
average path length across many random trees — so they get a higher anomaly
score. That's why it needs no labeled "this was an incident" data, which is
the normal case for a project (or a real team) with no incident history to
train on.
"""
from pathlib import Path

import joblib
from sklearn.ensemble import IsolationForest

from ml.features import most_deviant_feature

MODEL_PATH = Path(__file__).parent / "model.joblib"

_model: IsolationForest | None = None


def load_model() -> IsolationForest:
    global _model
    if _model is None:
        _model = joblib.load(MODEL_PATH)
    return _model


def score(feature_vector: list[float]) -> dict:
    """Runs the trained Isolation Forest on one service's current feature
    vector. `is_anomalous` / `anomaly_score` are the model's actual output.
    `driving_metric` is a separate, non-ML heuristic (largest z-score vs.
    baseline, from ml/features.py) used only to label *which* signal to show
    the engineer first — design-doc §5.6 is explicit that the model itself
    only answers "is this unusual?", never "why?"."""
    model = load_model()
    prediction = model.predict([feature_vector])[0]  # 1 = normal, -1 = anomalous
    anomaly_score = model.decision_function([feature_vector])[0]  # lower = more anomalous
    is_anomalous = bool(prediction == -1)
    return {
        "is_anomalous": is_anomalous,
        "anomaly_score": float(anomaly_score),
        "driving_metric": most_deviant_feature(feature_vector) if is_anomalous else None,
    }
