FROM python:3.12-slim

# Install Node.js 20 (agent runs as subprocess) + ffmpeg (for pydub MP3 decode)
RUN apt-get update && apt-get install -y curl ffmpeg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install and compile agent
COPY agent/package.json agent/package-lock.json ./agent/
RUN cd agent && npm ci
COPY agent/ ./agent/
RUN cd agent && npx tsc

# Copy backend + pipeline + mcp source
COPY backend/ ./backend/
COPY pipeline/ ./pipeline/
COPY mcp/ ./mcp/
COPY skill.md ./skill.md

ENV PORT=8000
EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --log-level info"]
