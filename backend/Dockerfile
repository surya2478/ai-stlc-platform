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
#
# typescript is here for the static quality gate's type check, not for running
# scripts: Playwright loads specs through esbuild, which strips types without
# checking them, so `tsc --noEmit` is the only thing that catches a generated
# bundle whose fixture shape disagrees with what its spec reads
# (static_quality_gate.type_check_bundle). Without it that check reports
# "skipped" and the defect surfaces as a mid-run browser failure.
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    # @types/node is not optional here: generated fixtures read process.env, and
    # without the Node type declarations tsc fails EVERY bundle on
    # "Cannot find name 'process'" — a false block worse than the bug the check
    # exists to catch.
    #
    # @playwright/mcp is the discovery agent's browser layer (mcp_session.py).
    # It MUST be installed here rather than left to the `npx -y` that
    # mcp_session used to spawn: npx resolves a package spec through its
    # install path, so every cold container fetched it from the npm registry
    # at run time. That is a network dependency in the middle of a discovery
    # run, and in an air-gapped deployment it fails the run outright. The
    # version is pinned to PLAYWRIGHT_MCP_PACKAGE in
    # app/agents/automation/mcp_session.py — bump both together, never one.
    #
    # PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: this package depends on its own
    # (alpha) playwright build, whose postinstall would pull a second
    # Chromium into /ms-playwright. mcp_session passes --executable-path at
    # the Chromium the 1.62 install above already provisioned, so that second
    # copy is never launched — downloading it would only inflate the image.
    && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm install -g @playwright/test@1.62.1 @playwright/mcp@0.0.77 typescript@5.4.5 @types/node@20.14.2 \
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
