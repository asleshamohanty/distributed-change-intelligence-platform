FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY ml ./ml
COPY scripts ./scripts
COPY tests ./tests

# Train the Isolation Forest at build time: the training data is synthetic
# and generation is seeded (ml/train.py), so this is fully reproducible and
# needs no external data source or separate training job for Phase 1.
RUN python -m ml.train

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
