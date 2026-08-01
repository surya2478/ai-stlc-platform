FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    locales \
    git \
    libpq-dev \
    libmupdf-dev \
    mupdf-tools \
    curl \
    # Common network-test binaries used by LLM-generated automation specs
    # (ping, traceroute, dig, openssl) — without these, scripts that shell out
    # via child_process / subprocess fail with "command not found".
    iputils-ping \
    traceroute \
    dnsutils \
    openssl \
    netcat-openbsd \
    && echo "en_US.UTF-8 UTF-8" > /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

# Browsers outside /root so a non-root process can reach them (AUT-002).
# The image installs Playwright as root during build; with the default cache
# location that put Chromium under /root/.cache/ms-playwright, readable only by
# root — which is why spawned runner containers had to run as root, and why a
# test that escaped Playwright inherited root in its container. Both the Python
# and the npm Playwright installs below honour this variable, so one setting
# relocates every browser.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# GAP-2: Chromium for Playwright-based portal URL analysis (used by the worker).
# NOTE: `playwright install --with-deps` fails on Debian trixie (it falls back
# to Ubuntu 20.04 package names like ttf-unifont). Install the system
# dependencies explicitly with current Debian package names instead.
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation \
    fonts-unifont \
    fonts-noto-color-emoji \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    && rm -rf /var/lib/apt/lists/* \
    && playwright install chromium

# Node.js + @playwright/test for the LocalPlaywrightRunner that executes
# AI-generated TypeScript automation scripts. The Python Playwright install
# above ships its own Chromium; the @playwright/test CLI reuses it.
# See backend/AUTOMATION_RUNNER.md for the equivalent install on bare metal.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @playwright/test@1.44.0 \
    && npx --yes playwright install chromium \
    # World-readable and traversable: the runner container executes as an
    # unprivileged uid and must still be able to launch Chromium.
    && chmod -R a+rX /ms-playwright

# Docker CLI (client only, no daemon) — Playwright AI Studio's "docker"
# runner mode spawns ephemeral sibling runner containers through the host
# socket mounted at /var/run/docker.sock (see docker-compose.yml). The
# spawned containers use this same image, so everything above (Node,
# @playwright/test, Chromium) is already present in them.
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN mkdir -p /app/storage/uploads /app/storage/reports /app/storage/artifacts /app/storage/scripts
RUN chmod +x /app/start.sh

RUN groupadd -g 10001 appgroup && \
    useradd -r -u 10001 -g appgroup -d /app appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD ["./start.sh"]
