FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99
ENV WINEDEBUG=-all

# Install Debian Native Python 3, Wine, Xvfb, and Node.js (Ultra Fast, Zero Wine Pip Lag)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    procps \
    xauth \
    xvfb \
    wine64 \
    wine \
    curl \
    git \
    ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Setup Linux Native Python Virtual Environment
ENV VIRTUAL_ENV=/app/.venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt /app/requirements.txt
COPY config.ini /app/config.ini
COPY src /app/src
COPY web /app/web

# Install packages into Linux venv directly
RUN pip install --no-cache-dir google-genai pandas numpy pydantic

# Install and build Web Dashboard (Node.js + TypeScript)
WORKDIR /app/web
RUN npm install
WORKDIR /app

COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 3496

ENTRYPOINT ["/app/entrypoint.sh"]
