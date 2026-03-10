#!/bin/sh
set -e

# Run migrations (DATABASE_URL must be set)
alembic upgrade head

# Build RAG index at first run if OPENAI_API_KEY is set and data/rag has content
if [ -n "$OPENAI_API_KEY" ] && [ -d /app/data/rag ]; then
  count=$(find /app/data/rag -maxdepth 1 -type f \( -name '*.txt' -o -name '*.md' \) 2>/dev/null | wc -l)
  if [ "$count" -gt 0 ]; then
    if [ ! -d "$RAG_INDEX_PATH" ] || [ -z "$(ls -A $RAG_INDEX_PATH 2>/dev/null)" ]; then
      echo "Building RAG index from data/rag..."
      python -m syllabus index-rag /app/data/rag || true
    fi
  fi
fi

# Start API (Railway sets PORT)
port="${PORT:-8000}"
exec python -m uvicorn syllabus.api.main:app --host 0.0.0.0 --port "$port"
