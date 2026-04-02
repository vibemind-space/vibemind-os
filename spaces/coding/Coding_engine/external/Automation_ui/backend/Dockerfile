# =============================================================================
# TRAE Backend - Docker Build
# =============================================================================
# FastAPI Backend mit WebSocket-Unterstützung
# Optimiert für Container-Umgebung (ohne GUI-Abhängigkeiten)
# =============================================================================

FROM python:3.11-slim AS base

# Labels
LABEL maintainer="TRAE Development Team"
LABEL description="TRAE Desktop Streaming Backend"
LABEL version="1.0"

# Umgebungsvariablen
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ============================================
# Stage 1: System Dependencies
# ============================================
FROM base AS system-deps

# System-Pakete installieren
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wget \
    git \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    # Für Pillow
    libjpeg-dev \
    libpng-dev \
    zlib1g-dev \
    # Für OpenCV (headless)
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1 \
<<<<<<< HEAD
=======
    # Für PyAV (aiortc dependency)
    pkg-config \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
>>>>>>> 8df31a1d44ad033e99adfe4ddd8c290de7a40ad0
    && rm -rf /var/lib/apt/lists/*

# ============================================
# Stage 2: Python Dependencies
# ============================================
FROM system-deps AS python-deps

# Kopiere Requirements
COPY requirements-docker.txt ./requirements.txt

# Installiere Python-Pakete
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ============================================
# Stage 3: Production Image
# ============================================
FROM python:3.11-slim AS production

# System-Laufzeit-Abhängigkeiten (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    libjpeg62-turbo \
    libpng16-16 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Umgebungsvariablen
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    LOG_LEVEL=INFO

WORKDIR /app

# Kopiere installierte Pakete
COPY --from=python-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin

# Kopiere Anwendungscode
COPY app/ ./app/
COPY autogen_service/ ./autogen_service/
COPY moire_agents/ ./moire_agents/
COPY config/ ./config/

# Erstelle Log-Verzeichnis
RUN mkdir -p /app/logs && chmod 755 /app/logs

# Nicht-Root-Benutzer für Sicherheit
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Exponiere Port
EXPOSE 8007

# Health Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8007/api/health/health || exit 1

# Starte Uvicorn Server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007", "--workers", "1"]