"""Trains the Isolation Forest on synthetic baseline telemetry
(design-doc §5.6).

There's no real historical incident data to train on (there never is, for a
project like this — that's the whole reason an unsupervised method was
chosen over a supervised one). This generates synthetic *normal* telemetry
samples from the baseline statistics used at inference time (ml/features.py)
and fits the model on those alone.

Deliberately NOT included: a synthetic "anomalous" cluster mixed into the
training set. Isolation Forest is unsupervised — it doesn't learn from
labels, so injecting a second, internally-consistent cluster of "anomalous"
points doesn't teach it what an anomaly looks like; it just teaches the
model that cluster is a second legitimate mode of the data, since those
points are no longer isolated from each other. (An earlier version of this
file did exactly that, and a clear latency spike scored as *normal* as a
result — the fix is training on baseline data only, and letting
`contamination` set the tail threshold within that.)

Run as `python -m ml.train` — done automatically at Docker build time (see
backend/Dockerfile). Generation is seeded, so the model is fully
reproducible and doesn't depend on any external data source.
"""
import random
from pathlib import Path

import joblib
from sklearn.ensemble import IsolationForest

from ml.features import BASELINE_STATS, FEATURE_NAMES

MODEL_PATH = Path(__file__).parent / "model.joblib"


def _sample(rng: random.Random, stats: dict) -> list[float]:
    return [max(0.0, rng.gauss(*stats[name])) for name in FEATURE_NAMES]


def generate_training_data(n_samples: int = 1000, seed: int = 42) -> list[list[float]]:
    rng = random.Random(seed)
    return [_sample(rng, BASELINE_STATS) for _ in range(n_samples)]


def train() -> IsolationForest:
    data = generate_training_data()
    # contamination=0.05 assumes ~5% of even this baseline data is natural
    # tail noise (a slow request, a brief CPU blip) — it sets the model's
    # decision threshold within the baseline distribution itself, not
    # against any injected "anomaly" examples. A real failure (a 2s latency
    # injection vs. a ~60ms baseline) lands far outside anything seen in
    # training and gets isolated in very few random splits, scoring as
    # strongly anomalous regardless of this threshold.
    model = IsolationForest(contamination=0.05, random_state=42)
    model.fit(data)
    return model


def main() -> None:
    model = train()
    joblib.dump(model, MODEL_PATH)
    print(f"Trained Isolation Forest on {len(FEATURE_NAMES)} features -> {MODEL_PATH}")


if __name__ == "__main__":
    main()
