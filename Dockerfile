FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps (main + backend)
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e ".[embeddings]"

# Hosted ranking is network-free at runtime. Bake the small BGE ONNX artifact
# into the image so a worker either loads it locally or falls back to BM25.
ENV JOB_FINDER_EMBEDDING_CACHE_DIR=/app/.cache/fastembed
RUN python -c "from fastembed import TextEmbedding; list(TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/app/.cache/fastembed').embed(['artifact check']))"
ENV HF_HUB_OFFLINE=1

COPY backend/pyproject.toml ./backend/
COPY backend/app/ ./backend/app/
RUN pip install --no-cache-dir -e ./backend

# Create data dirs
RUN mkdir -p /app/data /app/knowledge

# Default env
ENV JOB_FINDER_DATA_DIR=/app/data
ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
WORKDIR /app/backend
