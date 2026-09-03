# ==============================================================================
# Production-Grade Multi-Tenant Monorepo Dockerfile
# ==============================================================================

# 1. Base Image - Lightweight Python 3.13 Slim
FROM python:3.13-slim

# 2. Set Architectural Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_SYSTEM_PYTHON=1
ENV PATH="/root/.local/bin/:$PATH"

# 3. Install System Dependencies, Curl, and Rust Compiler (Required for tiktoken compilation on Python 3.13)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    cargo \
    rustc \
    && rm -rf /var/lib/apt/lists/*

# 4. Install Astral UV (Fastest Dependency Resolver)
ADD https://astral.sh/uv/install.sh /install.sh
RUN sh /install.sh && rm /install.sh

# 5. Establish Workspace Directory
WORKDIR /app

# 6. Docker Layer Caching - Install dependencies first based on Lockfile
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv pip install --system --no-cache -r pyproject.toml

# 7. Copy Project Codebases (Retaining identical relative sibling layout)
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# 8. Anchor Execution inside the backend folder context
WORKDIR /app/backend

# 9. Create persistent database and log directories inside the container
RUN mkdir -p db logs

# 10. Expose Uvicorn API Port
EXPOSE 8000

# 11. Production Run Entrypoint
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
