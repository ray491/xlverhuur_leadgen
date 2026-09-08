FROM node:20-bookworm

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update -o Acquire::Retries=3 -o Acquire::https::Timeout=30 \
    && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    xvfb \
    xauth \
    openssh-server \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir mcp playwright aiohttp httpx --break-system-packages \
    && playwright install --with-deps

RUN npm i -g opencode-ai

WORKDIR /app

COPY opencode.json /app/opencode.json

RUN mkdir -p /root/.config/opencode/skills/xlverhuur-leadgen \
    && cp /app/opencode.json /root/.config/opencode/opencode.json

COPY skills/xlverhuur-leadgen/SKILL.md /root/.config/opencode/skills/xlverhuur-leadgen/SKILL.md

# Entrypoint script to start sshd + opencode
RUN printf '%s\n' \
    '#!/bin/bash' \
    'set -e' \
    'Xvfb :99 -screen 0 1280x720x24 &' \
    'sleep 1' \
    'export DISPLAY=:99' \
    'exec opencode serve --hostname 0.0.0.0' \
    > /entrypoint.sh \
    && chmod +x /entrypoint.sh

EXPOSE 4096
EXPOSE 1455

CMD ["/entrypoint.sh"]