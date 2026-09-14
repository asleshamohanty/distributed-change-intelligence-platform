"""Feature engineering + baseline statistics for the anomaly model
(design-doc §5.6). This is the fixed-order feature vector every service's
current telemetry is reduced to — the same shape the Isolation Forest is
trained on, and the same metrics Telemetry Collection (§5.5) exposes.
"""

FEATURE_NAMES = ["latency_ms", "error_rate", "request_rate", "cpu_percent", "memory_mb"]

# (mean, std) per feature under normal operating conditions. Used both to
# generate synthetic training data (ml/train.py) and, at inference time, to
# report which single feature deviated furthest from baseline via a z-score
# (see most_deviant_feature below). That z-score is plain descriptive
# statistics for display purposes only — the Isolation Forest alone decides
# anomalous/normal; see design-doc §5.6's "Scope discipline" callout.
## Calibrated against this project's actual demo mesh under its background
# load generator (services/load-generator, ~3 req/s through the gateway) —
# not generic production numbers. Minimal FastAPI containers under light
# synthetic load run cool (low CPU/memory) and fast (tens of ms), so a
# textbook "50 req/s, 15% CPU" baseline would misfire on every request here.
BASELINE_STATS = {
    "latency_ms": (60.0, 25.0),
    "error_rate": (0.01, 0.01),
    "request_rate": (3.0, 1.0),
    "cpu_percent": (3.0, 2.0),
    "memory_mb": (60.0, 15.0),
}


def build_feature_vector(telemetry: dict) -> list[float]:
    return [float(telemetry.get(name, 0.0)) for name in FEATURE_NAMES]


def most_deviant_feature(feature_vector: list[float]) -> str:
    best_name, best_z = FEATURE_NAMES[0], -1.0
    for name, value in zip(FEATURE_NAMES, feature_vector):
        mean, std = BASELINE_STATS[name]
        z = abs(value - mean) / std if std else 0.0
        if z > best_z:
            best_name, best_z = name, z
    return best_name
