# -------------------------------------------------------------
# Stage 1: Build Frontend (Vite + React)
# -------------------------------------------------------------
FROM node:20-slim AS frontend-builder
WORKDIR /build

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# -------------------------------------------------------------
# Stage 2: Python 3.11 Runtime for Hugging Face Spaces
# -------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    STORAGE_DIR=/app/storage \
    LLM_SERVICE_URL=http://127.0.0.1:8001

# Install curl for health checking
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces requires running as UID 1000
RUN useradd -m -u 1000 user
WORKDIR /app

# Install Python backend dependencies
COPY services/api/requirements.txt /tmp/api_req.txt
COPY services/llm/requirements.txt /tmp/llm_req.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/api_req.txt -r /tmp/llm_req.txt

# Copy application services and runner
COPY --chown=user:user services /app/services
COPY --chown=user:user run_hf.py /app/run_hf.py

# Copy compiled frontend dist from Stage 1
COPY --from=frontend-builder --chown=user:user /build/dist /app/frontend/dist

# Pre-create storage hierarchy with proper user permissions
RUN mkdir -p /app/storage/images \
             /app/storage/tables \
             /app/storage/users \
             /app/storage/templates \
             /app/storage/skills \
             /app/storage/data \
             /app/storage/indexes \
             /app/storage/artifacts && \
    chown -R user:user /app

USER user
EXPOSE 7860

CMD ["python", "run_hf.py"]
