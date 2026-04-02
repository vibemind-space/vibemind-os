# Coding Engine Container
# Ubuntu 22.04 + Python 3.11 + Node 20 + VNC + Claude CLI
#
# Usage:
#   docker build -t coding-engine:latest -f infra/Dockerfile .
#   docker run -p 6080:6080 -p 8000:8000 -v ./output:/data/output coding-engine:latest

FROM ubuntu:22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# Set locale
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# ===== System Dependencies =====
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Base utilities
    curl \
    wget \
    git \
    ca-certificates \
    gnupg \
    lsb-release \
    locales \
    supervisor \
    # Python build dependencies
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    # Build tools for native modules
    build-essential \
    # VNC dependencies
    xvfb \
    x11vnc \
    xterm \
    fluxbox \
    # Browser for web app preview
    chromium-browser \
    # Audio support for Electron apps
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxshmfence1 \
    # Terminal emulator
    xfce4-terminal \
    # Fonts
    fonts-liberation \
    fonts-dejavu-core \
    # Network tools
    net-tools \
    netcat-openbsd \
    # Process tools
    procps \
    htop \
    && rm -rf /var/lib/apt/lists/*

# Generate locale
RUN locale-gen en_US.UTF-8

# ===== Node.js 20 LTS =====
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@latest \
    && rm -rf /var/lib/apt/lists/*

# ===== Python Setup =====
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# ===== noVNC Web Client =====
RUN mkdir -p /opt/novnc \
    && curl -L https://github.com/novnc/noVNC/archive/refs/tags/v1.4.0.tar.gz | tar xz -C /opt/novnc --strip-components=1 \
    && mkdir -p /opt/novnc/utils/websockify \
    && curl -L https://github.com/novnc/websockify/archive/refs/tags/v0.11.0.tar.gz | tar xz -C /opt/novnc/utils/websockify --strip-components=1

# ===== Claude CLI =====
# Note: Claude CLI requires authentication - mount ~/.claude or set ANTHROPIC_API_KEY
RUN npm install -g @anthropic-ai/claude-cli || echo "Claude CLI install may require manual auth"

# ===== Working Directory =====
WORKDIR /app

# ===== Copy Application Code =====
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install FastAPI dependencies for control server
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    websockets \
    python-multipart \
    aiofiles

COPY src/ /app/src/
COPY run_hybrid.py run_society_hybrid.py /app/
COPY infra/control_server/ /app/control_server/
COPY infra/scripts/ /app/scripts/
COPY infra/widget/ /app/widget/
COPY infra/supervisord.conf /etc/supervisor/conf.d/coding-engine.conf

# ===== Create Data Directories =====
RUN mkdir -p /data/requirements /data/output /data/control /data/logs

# ===== Environment Variables =====
# Display configuration
ENV DISPLAY=:99
ENV DISPLAY_WIDTH=1920
ENV DISPLAY_HEIGHT=1080
ENV DISPLAY_DEPTH=24

# VNC configuration
ENV VNC_PORT=5900
ENV NOVNC_PORT=6080
ENV VNC_PASSWORD=""

# Control server configuration
ENV CONTROL_PORT=8000
ENV CONTROL_HOST=0.0.0.0

# Preview configuration (for dev server inside generated apps)
ENV PREVIEW_PORT=5173

# Coding engine configuration
ENV OUTPUT_DIR=/data/output
ENV REQUIREMENTS_DIR=/data/requirements
ENV LOG_DIR=/data/logs

# No timeout mode - runs until user stops
ENV NO_TIMEOUT=true
ENV MAX_ITERATIONS=999999

# ===== Expose Ports =====
# 6080 - noVNC web client (main streaming endpoint)
# 8000 - Control API (start/stop/status)
# 5173 - Dev server preview (internal, proxied through VNC)
EXPOSE 6080 8000 5173

# ===== Health Check =====
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${CONTROL_PORT}/api/health || exit 1

# ===== Entrypoint =====
RUN chmod +x /app/scripts/*.sh
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]