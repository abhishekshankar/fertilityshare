# V1 backend: FastAPI + LangGraph pipeline. RAG index is built at startup if data/rag exists.
FROM python:3.11-slim

WORKDIR /app

# Install system deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python package (pyproject.toml + syllabus)
COPY pyproject.toml ./
COPY syllabus ./syllabus
RUN pip install --no-cache-dir .

# Copy migrations and RAG data
COPY alembic ./alembic
COPY alembic.ini ./

# Copy RAG source data (index built at startup via entrypoint if OPENAI_API_KEY set)
COPY data ./data

# Non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1
ENV RAG_INDEX_PATH=/app/.chroma_rag

EXPOSE 8000

# Migrations, optional RAG index from data/rag, then API
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
USER root
RUN chmod +x /app/docker-entrypoint.sh && chown appuser:appuser /app/docker-entrypoint.sh
USER appuser

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "syllabus.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
