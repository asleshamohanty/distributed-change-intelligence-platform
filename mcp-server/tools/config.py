import os

# Tools call the backend's own REST API rather than touching Postgres /
# Prometheus / Gemini directly — see server.py docstring for why.
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")
