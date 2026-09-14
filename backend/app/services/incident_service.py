"""Historical Incident Retrieval (design-doc §5.7).

Every incident is stored with a free-text description and a Gemini
embedding in a pgvector column. A new incident's evidence is embedded the
same way, then compared against stored embeddings via cosine similarity —
pgvector's `<=>` operator, exposed here through SQLAlchemy's
`cosine_distance()` comparator on the Vector column, in the same Postgres
instance (no second vector store). A high-similarity match means the
incident is semantically similar and may offer useful investigation
context — never that today's root cause is confirmed to be the same
(§5.7's "Similar is not identical" callout).
"""
import os

from google import genai
from google.genai import types
from sqlalchemy.orm import Session

from app.models import Incident

EMBEDDING_MODEL = "gemini-embedding-001"
# gemini-embedding-001 defaults to 3072-dim output but supports Matryoshka
# truncation via output_dimensionality; 768 matches the pgvector column
# (models/orm.py EMBEDDING_DIM) and is one of Google's documented supported
# truncation sizes.
EMBEDDING_DIM = 768

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def embed_text(text: str, task_type: str) -> list[float]:
    """`task_type` is Gemini's asymmetric-retrieval hint: incidents are
    embedded as RETRIEVAL_DOCUMENT, a live investigation's evidence summary
    is embedded as RETRIEVAL_QUERY — the two use slightly different
    embedding spaces internally, tuned for document-vs-query matching."""
    client = _get_client()
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=task_type, output_dimensionality=EMBEDDING_DIM
        ),
    )
    return list(response.embeddings[0].values)


def add_incident(
    db: Session, title: str, description: str, resolution: str | None = None
) -> Incident:
    embedding = embed_text(description, task_type="RETRIEVAL_DOCUMENT")
    incident = Incident(
        title=title, description=description, resolution=resolution, embedding=embedding
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def search_historical_incidents(db: Session, query_text: str, limit: int = 3) -> list[dict]:
    query_embedding = embed_text(query_text, task_type="RETRIEVAL_QUERY")
    distance_col = Incident.embedding.cosine_distance(query_embedding).label("distance")
    rows = db.query(Incident, distance_col).order_by(distance_col).limit(limit).all()
    return [
        {
            "id": incident.id,
            "title": incident.title,
            "description": incident.description,
            "resolution": incident.resolution,
            # cosine_distance is in [0, 2]; similarity = 1 - distance/2 keeps
            # it in a human-readable [0, 1] "higher is more similar" range.
            "similarity": round(1 - (distance / 2), 4),
        }
        for incident, distance in rows
    ]
