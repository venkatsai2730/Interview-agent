FROM python:3.12-slim

# Node.js needed to run agent/dist/agent.js (the RPC brain)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY livekit_agent/requirements.txt /app/livekit_agent/requirements.txt
RUN pip install --no-cache-dir -r livekit_agent/requirements.txt

# Patch livekit-plugins-sarvam: WebSocket TTS returns MP3 but plugin declares audio/wav.
# Fix the mime_type so livekit decodes the audio correctly.
RUN python -c "\
import sys; \
path = '/usr/local/lib/python3.12/site-packages/livekit/plugins/sarvam/tts.py'; \
content = open(path).read(); \
old = 'mime_type=\"audio/wav\",\n            stream=True,'; \
new = 'mime_type=\"audio/mpeg\",\n            stream=True,'; \
(open(path, 'w').write(content.replace(old, new, 1)) and print('sarvam TTS mime_type patch applied')) if old in content else print('patch already applied', file=sys.stderr) \
"

# Copy agent code
COPY livekit_agent/ /app/livekit_agent/
COPY agent/ /app/agent/
COPY pipeline/ /app/pipeline/
COPY backend/ /app/backend/

# Build the Node.js agent
WORKDIR /app/agent
RUN npm ci && npm run build 2>/dev/null || npx tsc --outDir dist 2>/dev/null || true

WORKDIR /app

CMD ["python", "-m", "livekit_agent.agent", "start"]
