# Asgard Basis
# Multi-stage Dockerfile for production deployment with React frontend

# =============================================================================
# Stage 1: Frontend Builder (Node.js)
# =============================================================================
FROM node:20-slim as frontend-builder

WORKDIR /app/frontend

# Copy package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy frontend source
COPY frontend/ ./

# Build production bundle
RUN npm run build

# =============================================================================
# Stage 2: Python Builder
# =============================================================================
FROM python:3.11-slim as python-builder

# Set build environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt

# =============================================================================
# Stage 3: Production
# =============================================================================
FROM python:3.11-slim as production

# Set production environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_HOME=/app \
    BOT_ENV=production

# Create app user (non-root for security)
RUN groupadd -r -g 1000 botuser && useradd -r -u 1000 -g botuser -s /bin/false botuser

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=python-builder /opt/venv /opt/venv

# Create app directory
WORKDIR ${APP_HOME}

# Copy application code
COPY bot/ ./bot/
COPY shared/ ./shared/
COPY backend/ ./backend/
COPY run_dashboard.py ./

# Copy built frontend from frontend-builder
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create directories for state and logs
RUN mkdir -p ${APP_HOME}/data ${APP_HOME}/logs && \
    chown -R botuser:botuser ${APP_HOME}

# Switch to non-root user
USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health/live --max-time 4 || exit 1

# Default command
CMD ["uvicorn", "backend.dashboard.main:app", "--host", "0.0.0.0", "--port", "8080"]

# =============================================================================
# Stage 4: Development
# =============================================================================
FROM production as development

USER root

# Install development dependencies
RUN pip install --no-cache-dir \
    pytest>=7.0.0 \
    pytest-asyncio>=0.21.0 \
    pytest-cov>=4.0.0 \
    black>=23.0.0 \
    flake8>=6.0.0 \
    mypy>=1.0.0

# Copy tests
COPY tests/ ./tests/

USER botuser

ENV BOT_ENV=development

# Default command for development
CMD ["python", "-m", "pytest", "tests/", "-v"]
