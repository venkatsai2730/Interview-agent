# Vero — AI Conversation Agent

Vero is a configurable AI agent that joins Microsoft Teams meetings or calls phone numbers, drives structured conversations autonomously, and delivers scored reports when sessions end. It is not a transcription bot or passive listener — it asks questions, evaluates responses in real time, and generates a post-session report within 60 seconds.

> "Real conversations, intelligently driven."

## What it does

You load a Skill Pack (a YAML file defining the role, question bank, rubric, and report template), point Vero at a Teams meeting URL or phone number, and it takes over. It introduces itself, works through the conversation, scores every response against the rubric, and emails a structured report when the call ends.

Swap the YAML, Vero becomes a different expert — no code changes required.

| Skill Pack | Vero becomes | Output |
|---|---|---|
| `interviewer` | Technical Recruiter | Candidate scorecard + hire/no-hire |
| `sales-coach` | Sales Manager | Rep performance scorecard |
| `solutions-architect` | Enterprise Architect | Requirements brief + gap analysis |
| `discovery-agent` | Pre-sales Consultant | Qualified opportunity brief |
| `compliance-auditor` | Compliance Officer | Audit response log + risk flags |
| `onboarding-buddy` | HR Onboarding Specialist | Onboarding completion record |
| `complaint-investigator` | Customer Care Agent | Complaint investigation report |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DUAL-CHANNEL ARCHITECTURE                       │
├─────────────────────────────────────┬───────────────────────────────────┤
│           TEAMS CHANNEL             │           PHONE CHANNEL           │
├─────────────────────────────────────┼───────────────────────────────────┤
│  Microsoft Teams Meeting            │  PSTN Phone Number                │
│       │                             │       │                           │
│       ▼                             │       ▼                           │
│  Recall.ai Bot                      │  Twilio → LiveKit SIP             │
│  (Azure AD auth)                    │       │                           │
│       │                             │       ▼                           │
│       ▼                             │  LiveKit Room                     │
│  WebSocket (/webhooks/recall/audio) │       │                           │
│       │                             │       ▼                           │
│       ▼                             │  Sarvam AI Agent (Python)         │
│  Audio Pipeline (Python)            │  Real-time STT + LLM + TTS        │
│  ├── Sarvam Saaras v3 (STT)         │       │                           │
│  ├── EOU Detector                   │       ▼                           │
│  └── Sarvam Bulbul v3 (TTS)         │  Backend API                      │
│       │                             │  (transcript persistence)         │
│       ▼                             │                                   │
│  Node.js Agent (TypeScript)         │                                   │
│  ├── Sarvam-30B LLM                 │                                   │
│  └── Scoring + Session Mgmt         │                                   │
│       │                             │                                   │
└───────┼─────────────────────────────┴───────────┼───────────────────────┘
        │                                         │
        ▼                                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend (Python)                           │
│  ├── REST API (sessions, skill packs, reports, transcripts)             │
│  ├── WebSocket endpoints (Recall.ai audio, LiveKit callbacks)           │
│  ├── Session lifecycle management                                       │
│  ├── Report generation + Resend email delivery                          │
│  └── AI Skill Generation (Sarvam-30B)                                  │
│                                                                         │
│  PostgreSQL + React Frontend (Vite)                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

The audio pipeline (Python) and agent (TypeScript) communicate over stdin/stdout JSONL — a clean process boundary that keeps audio handling and conversation logic independently testable.

## AI Stack — Sarvam AI

All AI capabilities are powered by [Sarvam AI](https://dashboard.sarvam.ai):

| Component | Sarvam Service | Usage |
|---|---|---|
| Speech-to-text | Saaras v3 | Teams channel — batch transcription at EOU |
| Text-to-speech | Bulbul v3 | Teams channel — 30+ natural voices |
| LLM | Sarvam-30B / 105B | Both channels — conversation + scoring |
| Real-time STT+LLM+TTS | Sarvam Realtime | Phone channel — sub-second speech-to-speech |

Supports 23 languages: English plus all major Indian languages (Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Gujarati, Marathi, Punjabi, Odia, Urdu, and more).

## Agentic AI Architecture

Vero is built on a TypeScript agent with sophisticated conversation intelligence:

### What Makes Vero "Agentic"

**1. Autonomous Decision Loop**
Every participant turn triggers the agent loop:
- Evaluates the response against the rubric
- Decides the next action (`advance`, `clarify`, `follow_up`, or `close`)
- Generates the next utterance
- Updates session state

**2. State Management**
- Maintains conversation context across turns
- Tracks follow-up counts per question
- Remembers scoring history for consistency
- Manages question progression through sections

**3. Structured Output Generation**
- Returns JSON with specific fields (action, score, utterance, flags)
- Schema-validated outputs with retry logic
- Type-safe message passing via RPC

**4. Context Awareness**
- Full transcript history in every LLM prompt
- Scoring history for consistent evaluation
- Skill Pack state (current question, section, competencies)
- Conversation flow rules (max_follow_ups, silence handling)

### Agent vs Skills

| **Agent** | **Skills** |
|-----------|------------|
| The **runtime intelligence** that processes conversations | The **configuration** that defines conversation behavior |
| One agent instance per session | Multiple Skill Packs can be loaded and selected |
| Handles LLM calls, state management, scoring | Defines persona, questions, rubric, report template |
| Same agent code runs all conversations | Different skills create different expert behaviors |

**Analogy**: The **Agent** is the interviewer's brain (reasoning, listening, responding). The **Skill** is the interview script (what questions to ask, how to evaluate).

## Session Monitoring

Vero provides real-time visibility into active sessions:

- **History page** auto-refreshes every 3 seconds while sessions are in progress
- **Live Transcript** panel streams conversation turns as they happen (no WebSocket required — polls DB)
- Session status progresses: `pending → joining → active → completed/failed`
- Transcript and recordings available after session ends

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- A Sarvam AI account (https://dashboard.sarvam.ai)
- Redis (included in docker-compose, no separate install needed)
- The third-party accounts listed below

## Third-party setup

### 1. Azure AD App Registration (required for Teams)

This is the critical path item — nothing works without it.

1. Go to [portal.azure.com](https://portal.azure.com) → Azure Active Directory → App registrations → New registration
2. Name it (e.g. `Vero Bot`), single tenant
3. Note the `Application (client) ID` → `AZURE_CLIENT_ID` and `TEAMS_BOT_APP_ID`
4. Note the `Directory (tenant) ID` → `AZURE_TENANT_ID`
5. Certificates & secrets → New client secret → copy value → `AZURE_CLIENT_SECRET` and `TEAMS_BOT_APP_PASSWORD`
6. API permissions → Add → Microsoft Graph → Application permissions:
   - `Calls.AccessMedia.All`
   - `Calls.JoinGroupCall.All`
7. Click **Grant admin consent** — requires a tenant admin. This is the #1 setup blocker; raise it on day one.

### 2. Azure Bot Service

1. Create a resource → Azure Bot, use the App ID from step 1
2. Channels → add Microsoft Teams
3. Set the messaging endpoint to `https://<your-public-url>/recall/webhook`

### 3. Recall.ai

Sign up at [recall.ai](https://recall.ai), get an API key → `RECALL_API_KEY`. In the Recall dashboard set your webhook URL to `https://<your-public-url>/recall/webhook`.

### 4. Sarvam AI (STT, TTS, LLM, Real-time)

Sign up at [dashboard.sarvam.ai](https://dashboard.sarvam.ai), create an API key → `SARVAM_API_KEY`.

Sarvam AI provides:
- **Saaras v3**: Speech-to-text for 23 languages (22 Indian + English)
- **Bulbul v3**: Text-to-speech with 30+ natural voices
- **Sarvam-30B / 105B**: Multilingual chat LLM optimized for Indian languages
- **Sarvam Realtime**: Speech-to-speech streaming for the phone channel

### 5. LiveKit + Twilio (required for Phone channel)

- **LiveKit**: Sign up at [livekit.io](https://livekit.io), create a project → `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- **Twilio**: Sign up at [twilio.com](https://twilio.com), get credentials → `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
- Create a Twilio SIP trunk in LiveKit and note the `LIVEKIT_SIP_TRUNK_ID` and `LIVEKIT_SIP_URI`

**MCP Server for Twilio**: The backend includes an MCP server (`mcp/twilio_mcp_server.py`) for Twilio call management using JSON-RPC 2.0 over stdio. It operates in dual-mode: MCP protocol by default, with automatic fallback to direct Twilio API if MCP is unavailable. Set `TWILIO_MCP_ENABLED=false` to always use direct API.

**Phone Call Flow**:
1. Backend → MCP Server → Twilio API → Call placed
2. Twilio fetches TwiML from `/twilio/livekit-bridge`
3. LiveKit SIP bridge connects → Sarvam AI Realtime agent joins

**Recording**: Pass `record=True` on call creation → Twilio records the call → callback to `/twilio/recording-callback` → recording URL saved → proxied playback via `/twilio/recording/{call_sid}`

### 6. Resend (email delivery)

Sign up at [resend.com](https://resend.com), create an API key → `RESEND_API_KEY`. Verify your sending domain in the Resend dashboard.


## Local development

### 1. Clone and configure

```bash
git clone <repo-url>
cd vero
cp .env.example .env
# Fill in all values in .env
```

### 2. Start the stack

```bash
docker compose up --build -d
```

This starts five services:

| Service | URL | Description |
|---|---|---|
| `frontend` | http://localhost:5173 | React UI (Vite dev server) |
| `backend` | http://localhost:8000 | FastAPI + audio pipeline |
| `db` | internal :5432 | PostgreSQL 16 |
| `redis` | internal :6379 | Redis (session state, caching) |
| `livekit-agent` | internal | Sarvam AI LiveKit worker |

### 3. Verify

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "dependencies": {
    "db": { "status": "ok", "latency_ms": 12 },
    "recall": { "status": "ok", "latency_ms": 210 },
    "sarvam": { "status": "ok", "latency_ms": 150 }
  }
}
```

### 4. Expose your local server (for Recall.ai webhooks)

Recall.ai is a cloud service — it needs a public HTTPS URL to send webhook events to your local backend.

```bash
# macOS ARM (Apple Silicon)
curl -O https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-arm64.zip
unzip ngrok-v3-stable-darwin-arm64.zip

# Sign up at https://dashboard.ngrok.com → copy your authtoken
./ngrok config add-authtoken YOUR_NGROK_AUTHTOKEN

# Start the tunnel (keep running)
./ngrok http 8000
```

Register the ngrok URL in Recall.ai dashboard under **Webhooks** → enable events: `bot.joining_call`, `bot.in_call_recording`, `bot.done`.

## Running a session

1. Open http://localhost:5173
2. Go to **Skill Packs** → create or activate a Skill Pack
3. Go to **Sessions** → choose Teams or Phone tab
4. Paste a Teams URL or enter a phone number → submit
5. You're taken to **History** — the session status updates live (pending → joining → active)
6. Click **Live** on an active session to watch the transcript in real time
7. When the call ends, the report is generated and emailed; click **Transcript** or **Report** to view

## Skill Pack YAML structure

```yaml
skill:
  id: interviewer-v1
  name: Technical Interviewer
  version: 1.0.0

agent:
  name: Alex
  persona: professional and encouraging
  language: en-IN
  max_duration_minutes: 45
  model_preferences:
    - provider: sarvam
      model: sarvam-30b
  tts_voice: sarvam:shubh

sections:
  - id: intro
    title: Introduction
    questions:
      - id: q1
        text: "Can you walk me through your background?"
        probes:
          - "What was your most recent role?"
          - "What technologies did you work with day to day?"
        competency: communication
        max_follow_ups: 2

rubric:
  - competency: communication
    scores:
      1: "Unclear, disorganised, hard to follow"
      3: "Clear and structured with some gaps"
      5: "Concise, well-structured, compelling"

report:
  template: scorecard
  email_to: hiring@example.com
  include_transcript: true
```

### Advanced Skill Pack Features

```yaml
agent:
  opening_utterance: "Hi, I'm Alex from Acme Corp. Thanks for joining!"  # Custom greeting

sections:
  - id: discovery
    title: Discovery Questions
    max_duration_seconds: 300  # Per-section time limit (5 minutes)
    questions:
      - id: q1
        text: "Tell me about {{company_name}}'s current challenges."

# Dynamic session parameters
context_data:
  company_name: "Acme Corp"
  industry: "fintech"

input_schema:  # Define expected runtime inputs
  - name: company_name
    type: string
    required: true
  - name: industry
    type: string
    required: false
```

### Conversation modes

| Mode | Use case | How it works |
|---|---|---|
| **Guided** | Interviews, assessments | Fixed question sequence with probes and follow-ups |
| **Intelligent** | Coaching, discovery | Objectives-based adaptive conversation |

Set mode per section: `mode: guided` or `mode: intelligent`.

### Channels

Skill packs can specify which channels they support:

```yaml
skill:
  channels: [teams, phone]  # default: both
```

## Testing

Run the full test suite inside the running backend container:

```bash
# All tests
docker compose exec backend python -m pytest backend/ -v

# Unit tests — Skill Pack validator
docker compose exec backend python -m pytest backend/test_skill_pack_validator.py -v

# Integration tests — API endpoints, webhook handling, latency recording
docker compose exec backend python -m pytest backend/test_integration_points.py -v

# E2E mock tests — full session flow without a real Teams call
docker compose exec backend python -m pytest backend/test_e2e_mock.py -v

# Role switch tests — multiple Skill Packs, isolated session state
docker compose exec backend python -m pytest backend/test_role_switch.py -v
```

## Production deployment (EC2)

The recommended target is a single `t3.medium` EC2 instance running Amazon Linux 2023.

### 1. Launch the instance

- AMI: Amazon Linux 2023
- Instance type: `t3.medium` (2 vCPU, 4GB RAM)
- Security group: open inbound TCP 80, 443, and your `PORT` (default 8000)

### 2. Install Docker

```bash
sudo dnf update -y
sudo dnf install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user
# Log out and back in
```

Install Compose plugin:
```bash
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
```

### 3. Deploy

```bash
git clone <repo-url> /opt/vero
cd /opt/vero
cp .env.example .env
# Fill in .env
docker compose up --build -d
```

### 4. TLS with nginx + Certbot (recommended)

```bash
sudo dnf install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

Add an nginx upstream to proxy `yourdomain.com` → `localhost:8000`.

Update your Recall.ai webhook URL and Azure Bot messaging endpoint to `https://yourdomain.com/recall/webhook`.

### 5. Keep it running

```bash
# View logs
docker compose logs -f backend

# Restart after a code change
git pull && docker compose up --build -d

# Check service health
curl https://yourdomain.com/health
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `AZURE_TENANT_ID` | yes | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | yes | Azure App Registration client ID |
| `AZURE_CLIENT_SECRET` | yes | Azure App Registration client secret |
| `TEAMS_BOT_APP_ID` | yes | Same as `AZURE_CLIENT_ID` |
| `TEAMS_BOT_APP_PASSWORD` | yes | Same as `AZURE_CLIENT_SECRET` |
| `RECALL_API_KEY` | yes | Recall.ai API key |
| `RECALL_REGION` | yes | Recall.ai region — `us-east-1`, `us-west-2`, `eu-central-1`, `ap-northeast-1` |
| `SARVAM_API_KEY` | yes | Sarvam AI API key (STT, TTS, LLM, Realtime) |
| `RESEND_API_KEY` | yes | Resend API key for email delivery |
| `DATABASE_URL` | yes | PostgreSQL connection string |
| `LIVEKIT_URL` | yes (phone) | LiveKit WebSocket URL |
| `LIVEKIT_API_KEY` | yes (phone) | LiveKit API key |
| `LIVEKIT_API_SECRET` | yes (phone) | LiveKit API secret |
| `LIVEKIT_SIP_TRUNK_ID` | yes (phone) | LiveKit SIP trunk ID (Twilio) |
| `TWILIO_ACCOUNT_SID` | yes (phone) | Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | yes (phone) | Twilio Auth Token |
| `TWILIO_PHONE_NUMBER` | yes (phone) | Twilio outbound phone number (E.164) |
| `REDIS_URL` | no | Redis connection URL (default: `redis://redis:6379/0`) |
| `TWILIO_MCP_ENABLED` | no | Use MCP server for Twilio (default: `true`, set `false` for direct API) |
| `LIVEKIT_SIP_URI` | no | LiveKit SIP trunk URI for phone bridging |
| `LIVEKIT_SIP_INBOUND_TRUNK_ID` | no | LiveKit SIP inbound trunk ID |
| `PORT` | no | Backend port, default `8000` |

## Project structure

```
vero/
├── backend/          # FastAPI app, session manager, report generator
│   ├── main.py       # API routes + Recall.ai webhook handler
│   ├── models.py     # SQLAlchemy models
│   ├── session_manager.py
│   ├── recall_client.py
│   ├── report_generator.py
│   ├── skill_pack_validator.py
│   └── test_*.py     # Test suite
├── pipeline/         # Audio pipeline (Teams channel)
│   ├── pipeline.py   # AudioPipeline orchestrator
│   ├── eou_detector.py
│   ├── tts_injector.py
│   └── sarvam_realtime.py
├── agent/            # TypeScript agent (RPC subprocess)
│   ├── agent.ts      # Conversation engine, LLM calls, scoring
│   └── skill_pack_state.ts
├── livekit_agent/    # LiveKit Sarvam AI agent (Phone channel)
│   └── agent.py      # Sarvam Realtime speech-to-speech
├── mcp/              # MCP server for Twilio (JSON-RPC 2.0)
│   └── twilio_mcp_server.py
├── frontend/         # React + Vite UI
│   └── src/
│       ├── pages/    # Sessions, History, Reports, Skill Packs, Monitor
│       └── components/
├── docker-compose.yml
├── .env.example
└── README.md
```
