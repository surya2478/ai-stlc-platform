FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libpq-dev \
    libmupdf-dev \
    mupdf-tools \
    curl \
    && rm -rf /var/lib/apt/lists/*

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

COPY . .

RUN mkdir -p /app/storage/uploads /app/storage/reports /app/storage/artifacts /app/storage/scripts
RUN chmod +x /app/start.sh

RUN groupadd -g 10001 appgroup && \
    useradd -r -u 10001 -g appgroup -d /app appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD ["./start.sh"]
