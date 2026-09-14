"""Seeds a handful of historical incidents with embeddings (design-doc §5.7,
Phase 1 item 5). Idempotent: skips seeding if incidents already exist.

Run as `python -m scripts.seed_incidents`, or automatically once at backend
startup (see backend/app/main.py) if GEMINI_API_KEY is set.
"""
from app.db import SessionLocal
from app.models import Incident
from app.services import incident_service

# The first entry deliberately mirrors design-doc §5.7's own worked example
# (an order-service deploy causing a downstream inventory-service latency +
# error-rate anomaly) so the demo investigation flow (Phase 1 item 7) has a
# highly-similar historical match to retrieve.
SEED_INCIDENTS = [
    {
        "title": "Order Service deploy caused Inventory Service latency spike",
        "description": (
            "A deployment to order-service introduced a blocking call in the "
            "payment client wrapper. Within minutes, inventory-service — a "
            "direct downstream dependency — showed elevated request latency "
            "and a rise in 5xx error rate. The anomaly detector flagged "
            "inventory-service on the latency and error-rate metrics."
        ),
        "resolution": (
            "Rolled back the order-service deployment. The blocking call was "
            "refactored to run asynchronously before redeploying."
        ),
    },
    {
        "title": "Payment Service error spike after external processor timeout",
        "description": (
            "payment-service began returning 500s at an elevated rate after "
            "its upstream external payment processor started timing out. No "
            "recent deployment to payment-service itself; the anomaly was "
            "isolated to error rate, not latency or resource usage."
        ),
        "resolution": (
            "Added a circuit breaker around the external-api call and a "
            "retry-with-backoff policy; no code change to payment-service's "
            "own logic was required."
        ),
    },
    {
        "title": "Inventory Service memory growth under sustained load",
        "description": (
            "inventory-service's memory usage climbed steadily over several "
            "hours under sustained elevated request volume from "
            "order-service, eventually triggering restarts. CPU and latency "
            "stayed within normal range for most of the window."
        ),
        "resolution": (
            "Found an unbounded in-memory cache of reservation records; "
            "added an eviction policy."
        ),
    },
    {
        "title": "Gateway timeout cascade during a traffic spike",
        "description": (
            "A sudden increase in request rate through gateway caused "
            "downstream order-service latency to climb, which in turn made "
            "gateway's own request latency spike and start timing out. "
            "Anomalies were detected on both gateway and order-service "
            "simultaneously."
        ),
        "resolution": (
            "Added request-rate-based autoscaling headroom and a stricter "
            "per-request timeout at the gateway so failures stayed local "
            "instead of cascading upstream."
        ),
    },
    {
        "title": "Database connection pool exhaustion after an inventory-service redeploy",
        "description": (
            "A redeploy of inventory-service changed its database connection "
            "pool configuration, reducing the pool size. Under normal load "
            "this exhausted the pool, causing elevated latency and "
            "intermittent errors on inventory-service with no change in "
            "request volume."
        ),
        "resolution": (
            "Reverted the connection pool size change and added a minimum-"
            "pool-size check to the deployment's config validation."
        ),
    },
]


def seed_incidents() -> None:
    db = SessionLocal()
    try:
        if db.query(Incident).count() > 0:
            print("Incidents already seeded, skipping.")
            return
        for entry in SEED_INCIDENTS:
            incident_service.add_incident(db, **entry)
        print(f"Seeded {len(SEED_INCIDENTS)} historical incidents.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_incidents()
