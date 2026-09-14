"""Background synthetic load generator for the demo mesh.

Keeps a steady trickle of checkout traffic flowing through the gateway so
the Isolation Forest's baseline (ml/features.py's BASELINE_STATS) reflects
real steady-state numbers rather than an idle container, and so the
failure-injection demo (Phase 1 item 8) has a visible "before" signal to
deviate from — mirroring design-doc §5.5's worked example of a steady
latency stream followed by a post-deploy spike.
"""
import os
import random
import time

import httpx

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:8000")
ITEMS = ["widget", "gadget", "gizmo"]
REQUESTS_PER_SECOND = float(os.environ.get("TRAFFIC_RPS", "3"))


def main() -> None:
    interval = 1.0 / REQUESTS_PER_SECOND
    with httpx.Client(timeout=5.0) as client:
        while True:
            item = random.choice(ITEMS)
            try:
                client.post(
                    f"{GATEWAY_URL}/api/checkout",
                    json={"item": item, "quantity": 1, "user": "traffic-generator"},
                )
            except httpx.HTTPError:
                pass
            time.sleep(interval)


if __name__ == "__main__":
    main()
