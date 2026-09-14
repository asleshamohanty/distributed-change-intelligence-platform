"""Unit tests for the anomaly detection model (design-doc §5.6)."""
from ml.features import BASELINE_STATS, FEATURE_NAMES, build_feature_vector, most_deviant_feature
from ml.train import generate_training_data, train


def test_build_feature_vector_preserves_order_and_fills_missing():
    telemetry = {"latency_ms": 100.0, "error_rate": 0.01}
    vector = build_feature_vector(telemetry)
    assert vector == [100.0, 0.01, 0.0, 0.0, 0.0]
    assert len(vector) == len(FEATURE_NAMES)


def test_most_deviant_feature_picks_largest_zscore():
    # cpu_percent baseline is (3.0, 2.0); a value of 20 is ~8.5 std away —
    # far more extreme than the other features, held at their means.
    vector = [
        BASELINE_STATS["latency_ms"][0],
        BASELINE_STATS["error_rate"][0],
        BASELINE_STATS["request_rate"][0],
        20.0,
        BASELINE_STATS["memory_mb"][0],
    ]
    assert most_deviant_feature(vector) == "cpu_percent"


def test_generate_training_data_is_deterministic():
    a = generate_training_data(n_samples=50, seed=42)
    b = generate_training_data(n_samples=50, seed=42)
    assert a == b


def test_generate_training_data_shape_and_nonnegativity():
    data = generate_training_data(n_samples=20, seed=1)
    assert len(data) == 20
    assert all(len(row) == len(FEATURE_NAMES) for row in data)
    assert all(value >= 0 for row in data for value in row)


def test_trained_model_scores_baseline_point_as_normal():
    model = train()
    baseline_point = [mean for mean, _std in BASELINE_STATS.values()]
    prediction = model.predict([baseline_point])[0]
    assert prediction == 1  # 1 = normal


def test_trained_model_flags_multivariate_extreme_as_anomalous():
    model = train()
    # A correlated shift on every feature at once — roughly what a real
    # cascading failure looks like, and the case this model is actually
    # designed to catch. (A single-axis-only outlier with every other
    # feature held exactly at its mean is a genuinely hard case for
    # tree-based isolation — see ml/train.py's docstring on why the
    # training set intentionally excludes an injected "anomalous" cluster.)
    extreme_point = [
        mean + 10 * std for mean, std in BASELINE_STATS.values()
    ]
    prediction = model.predict([extreme_point])[0]
    assert prediction == -1  # -1 = anomalous
