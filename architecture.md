# Architecture

## Overview

Vero is a real-time AI voice agent platform that supports two conversation channels:

- **Teams** — Recall.ai bot joins a Microsoft Teams meeting, conducts a structured conversation using a configurable Skill Pack, and generates a post-session report.
- **Phone** — Twilio dials a phone number, bridges the call into a LiveKit room, and a Sarvam AI real-time speech-to-speech agent handles the conversation.

Both channels are driven by Skill Packs — YAML-defined conversation blueprints that specify the agent persona, questions, scoring rubric, and report template.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            User's Browser                                │
│                         React + Vite Frontend                            │
│          Skill Packs · Sessions · History · Reports · Monitor            │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │ HTTP /api/*
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend (Python)                          │
│   REST API · Session Manager · Report Generator · DB Layer               │
└──────┬──────────────────────────────────┬────────────────────────────────┘
       │                                  │
       │ TEAMS CHANNEL                    │ PHONE CHANNEL
       ▼                                  ▼
┌─────────────────────┐        ┌──────────────────────────────────────────┐
│     Recall.ai       │        │  Twilio → LiveKit SIP → LiveKit Room     │
│  Teams bot joins    │        │                                          │
│  meeting, streams   │        │  ┌────────────────────────────────────┐  │
│  PCM audio via WS   │        │  │   Sarvam AI Agent (Python)         │  │
└──────┬──────────────┘        │  │   livekit_agent/agent.py           │  │
       │ PCM frames            │  │   sarvam.realtime.RealtimeModel    │  │
       ▼                       │  │   Speech-to-speech (STT+LLM+TTS)   │  │
┌─────────────────────┐        │  │   Skill Pack → system prompt       │  │
│   Audio Pipeline    │        │  │   Scoring bridge → Node.js agent   │  │
│   pipeline/         │        │  └────────────────────────────────────┘  │
│                     │        └──────────────────────────────────────────┘
│  Sarvam Saaras v3   │
│  STT (REST batch)   │                    │ SQL
│  EOUDetector        │                    ▼
│  Sarvam Bulbul v3   │          ┌──────────────────┐
│  TTS (REST)         │          │   PostgreSQL      │
│  RPC Bridge         │          │                  │
└──────┬──────────────┘          │  sessions        │
       │ JSONL stdin/stdout      │  turns           │
       ▼                         │  skill_packs     │
┌─────────────────────┐          │  skill_pack_     │
│   Node.js Agent     │          │    versions      │
│   agent/agent.ts    │          │  reports         │
│                     │          │  events          │
│  Sarvam-30B LLM     │          └──────────────────┘
│  Scoring + rubric   │
│  Session summary    │
└─────────────────────┘
```

---

## Components

### Frontend
- React + TypeScript + Vite, served on port 5173 in dev
- Tailwind CSS + shadcn/ui components
- Pages: Sessions (launcher), History, Skill Packs, Reports, Monitor, Docs
- All API calls proxied to backend via `/api` prefix
- Session Launcher supports both Teams (meeting URL) and Phone (E.164 number) channels
- Per-session controls: LLM model selector, voice selector, language selector (both channels)
- **Live session tracking**: History page auto-polls every 3s when active sessions exist; live transcript panel streams turns in real time

### Backend (FastAPI)
- Entry point: `backend/main.py`
- Handles REST API, WebSocket endpoints, session lifecycle
- Two session types: `POST /sessions` (Teams) and `POST /sessions/phone-livekit` (Phone)
- Teams pipeline activation paths:
  1. Recall.ai webhook (`POST /webhooks/recall/`)
  2. Background poller (`_poll_bot_until_active`) — polls every 5s for up to 3 minutes
- DB-level atomic pipeline guard (`pipeline_started_at`) prevents duplicate pipeline starts
- On startup: marks stale `active/joining/pending` sessions as `failed`
- Transcript endpoint `GET /sessions/{id}/transcript` serves both live and completed sessions

### Skill Packs
- YAML-defined conversation blueprints stored in PostgreSQL
- Fields: `skill` (id, name, version), `agent` (name, persona, model_preferences, tts_voice), `sections` (questions/objectives, mode), `rubric`, `report`
- **Two conversation modes:**
  - **Guided Mode** — Fixed question sequence with probes (traditional interview/assessment)
  - **Intelligent Mode** — Objectives-based adaptive conversation (coaching/discovery)
- CRUD API: create, update, activate, delete, version history, **clone**
- **AI Generation** — Create skills from a simple description; AI determines mode, channels, questions/objectives, rubric, and persona
- Only active skill packs are shown in the Session Launcher
- Seeded via `backend/seed_skill_packs.py` (9 packs including Complaint Investigator)

### Teams Channel — Recall.ai + Audio Pipeline

**Recall.ai**
- Joins the Teams meeting as a bot participant (authenticated via Azure AD)
- Streams mixed audio (16kHz mono S16LE PCM) to backend via WebSocket (`/webhooks/recall/audio`)
- Receives synthesised WAV audio back via `POST /api/v1/bot/{id}/output_audio/`
- Region: `ap-northeast-1`

**Audio Pipeline (`pipeline/pipeline.py`)**
- One pipeline instance per session
- Spawns `agent/dist/agent.js` (Node.js) as a child process
- Communicates with the agent over stdin/stdout using JSONL (RPC bridge)
- Feeds PCM frames to audio buffer, transcribes at EOU via Saaras v3 REST API
- On turn complete: sends buffered audio to Saaras v3, then `TurnMessage` to agent
- On `TurnOutputMessage` from agent: calls TTSInjector
- No WebSocket reconnection complexity — simple REST API calls

**EOUDetector (`pipeline/eou_detector.py`)**
- RMS energy-based silence detection
- Fires `turn_complete` after ~0.8s of continuous silence
- Suppressed while Vero is speaking (`vero_speaking` flag)

**TTSInjector (`pipeline/tts_injector.py`)**
- Uses Sarvam Bulbul v3 text-to-speech API
- Returns WAV audio at 16kHz sample rate
- Injects audio to Recall.ai `output_audio` endpoint
- Voice selectable per session (30+ speakers: shubh, ritu, aditya, priya, neha, rahul, etc.)

**Node.js Agent (`agent/agent.ts`)**
- Communicates via stdin/stdout JSONL (RPC bridge)
- Receives `session_start` (with full skill pack) + `turn` messages
- Calls Sarvam-30B via OpenAI-compatible API to generate structured JSON responses
- Returns `turn_output` messages: next utterance, action, score, competency, flags
- Handles silence timeouts, repeat requests, session close
- Sends `session_summary` on session end (scores + full transcript)
- Model selectable per session (sarvam-30b, sarvam-105b)
- **Transcript Persistence** — Persists each turn to backend DB via `POST /livekit/turn` for real-time transcript retrieval

### Phone Channel — LiveKit + Sarvam AI

**Flow**
1. Frontend calls `POST /sessions/phone-livekit` with phone number, skill pack, voice, model
2. Backend creates a LiveKit SIP outbound call via Twilio trunk
3. Twilio bridges the call to the LiveKit SIP URI
4. LiveKit routes the call to the `vero-agent` worker
5. Sarvam AI agent handles the full conversation (STT + LLM + TTS in one real-time stream)

**LiveKit Agent (`livekit_agent/agent.py`)**
- Registers as `vero-agent` with LiveKit cloud
- Uses `livekit.plugins.sarvam.realtime.RealtimeModel` (Sarvam AI speech-to-speech)
- Skill pack injected as system prompt via `_build_instructions()`
- Voice and model configurable per session (passed via room metadata)
- Scoring bridge: spawns Node.js agent in background for turn scoring and session summary
- Notifies backend on session active and session summary via HTTP
- **Transcript Persistence** — Each turn persisted to backend DB via `POST /livekit/turn` for live viewing

**Twilio**
- Outbound call placed to candidate's phone number via LiveKit SIP trunk
- Bridges PSTN call into LiveKit room
- Recording enabled at call creation (`Record=true`)
- Recording status callback configured for async recording URL capture

### MCP Server Architecture

The backend communicates with Twilio via a Model Context Protocol (MCP) integration:

**Protocol**: JSON-RPC 2.0 over subprocess stdio

**MCP Server (`mcp/twilio_mcp_server.py`)**
- Exposes Twilio tools: `make_call`, `get_call_status`, `hangup_call`, `get_recordings`, `get_transcriptions`, `send_sms`
- All tool responses wrapped in `{"result": {...}}` format per MCP spec
- Logging must go to stderr (not stdout) to avoid corrupting JSON-RPC stream

**MCP Client (`backend/mcp/twilio_client.py`)**
- Dual-mode operation:
  - **MCP mode** (default, `TWILIO_MCP_ENABLED=true`): spawns MCP server subprocess, communicates via JSON-RPC
  - **Direct API mode** (`TWILIO_MCP_ENABLED=false`): uses httpx to call Twilio REST API directly
- Paths are mutually exclusive — no automatic fallback between them
- Provides unified interface: `create_call()`, `get_call_status()`, `hangup_call()`, `get_recordings()`

### Recording Lifecycle

1. Recording enabled at call creation time (`Record=true` in TwiML)
2. `RecordingStatusCallback` configured to backend endpoint
3. Callback endpoint: `POST /twilio/recording-callback` (accepts Form data)
4. On recording complete, Twilio POSTs `RecordingSid`, `RecordingUrl`, `CallSid`
5. Backend matches `CallSid` → session, saves `recording_url` with `.mp3` extension
6. Frontend retrieves via `/sessions/{id}/recordings` or uses stored `recording_url`
7. Download proxied through backend (server-side Twilio auth, no redirect to api.twilio.com)

### Database (PostgreSQL)
- Tables: `sessions`, `turns`, `skill_packs`, `skill_pack_versions`, `reports`, `events`
- Managed via SQLAlchemy 2.x async (declarative ORM)
- Key session fields:
  - `pipeline_started_at` — atomic pipeline guard (set once, prevents duplicate starts)
  - `channel` — `teams` or `phone`
  - `twilio_call_sid` — Twilio Call SID for matching recording callbacks
  - `recording_url` — stored recording URL from Twilio (phone channel)
  - `recall_recording_url` — recording URL from Recall.ai (Teams channel)
- `turns` table stores every conversation turn with speaker, transcript, score, timestamp — queryable live during active sessions

---

## Request Flow — Teams Session

```
1.  User selects Skill Pack + pastes Teams URL → clicks "Launch Session"
2.  POST /api/sessions → backend validates skill pack, calls Recall.ai to create bot
3.  Frontend navigates to History page; session shows as "pending" with live auto-refresh
4.  Recall.ai bot joins Teams meeting (Azure AD auth)
5.  Bot reaches in_call_recording → webhook or poller fires
6.  Backend claims pipeline slot (DB atomic guard), spawns AudioPipeline + Node.js agent
7.  Agent receives session_start → generates opening utterance via Sarvam LLM
8.  TTSInjector calls Sarvam Bulbul → gets WAV → posts to Recall.ai output_audio
9.  Participant hears agent speak in the Teams call
10. Participant speaks → Recall.ai streams PCM to /recall/audio WebSocket
11. PCM buffered → Saaras v3 STT at EOU → transcript
12. EOUDetector fires after ~0.8s silence → TurnMessage sent to agent
13. Agent calls Sarvam LLM → generates structured JSON response → TurnOutputMessage
14. TTSInjector synthesises + injects → participant hears response
15. Each turn persisted to DB — visible in live transcript panel
16. On session end → session_summary emitted → report generated → email via Resend
```

## Request Flow — Phone Session

```
1.  User clicks "Call Now" in SessionLauncher
2.  POST /api/sessions/phone-livekit → creates session, LiveKit room, SIP dispatch rule
3.  TwilioMCPClient.create_call() places outbound call (record=True, recording_status_callback set)
4.  Twilio fetches TwiML from /twilio/livekit-bridge?session_id=xxx
5.  TwiML dials LiveKit SIP URI → call bridged to vero-agent worker
6.  Sarvam AI Realtime handles full conversation (STT + LLM + TTS via speech-to-speech streaming)
7.  Each turn persisted to backend DB via POST /livekit/turn — visible in live transcript
8.  On call end, Twilio POSTs to /twilio/recording-callback with RecordingSid, RecordingUrl
9.  Backend matches CallSid → session, saves recording_url
10. close_session() generates report, emails via Resend
```

---

## Infrastructure

- All services run in Docker via `docker-compose.yml` (5 containers: db, redis, backend, frontend, livekit-agent)
- Backend image bakes in compiled `agent/dist/agent.js` at build time
- ngrok tunnels `localhost:8000` for Recall.ai webhooks and Twilio callbacks (URL must match `WEBHOOK_URL` in `.env`)
- Redis used for session data caching and pipeline registration state

---

## External Services

| Service | Purpose | Auth |
|---|---|---|
| Recall.ai | Teams bot + audio streaming | API key |
| Sarvam AI | Saaras v3 (STT), Bulbul v3 (TTS), Sarvam-30B/105B (LLM), Realtime speech-to-speech (phone channel via LiveKit plugins) | API key |
| Azure AD | Teams authenticated bot join | Client credentials |
| Twilio | Outbound phone calls, call recording, SMS (via MCP or direct REST API) | Account SID + Auth Token |
| LiveKit | SIP bridge + real-time audio (Phone channel) | API key + secret |
| Redis | Session data cache, pipeline registration, pub/sub | Connection URL |
| Resend | Report email delivery | API key |
| ngrok | Webhook tunnel (local dev) | — |

---

## Key Design Decisions

- **Dual channel architecture** — Teams uses a multi-stage pipeline (STT → LLM → TTS) for flexibility and scoring; Phone uses Sarvam AI real-time (speech-to-speech) for sub-second latency.
- **Sarvam AI as unified AI stack** — Both channels use Sarvam AI exclusively: Saaras v3 (STT), Bulbul v3 (TTS), Sarvam-30B/105B (LLM), and Sarvam Realtime (phone channel).
- **Skill Pack as single source of truth** — both channels receive the full skill pack at session start; the agent persona, questions, and rubric drive the entire conversation.
- **Atomic pipeline guard** — `pipeline_started_at` DB column prevents duplicate pipelines when both webhook and poller fire simultaneously.
- **Batch STT architecture** — Audio is buffered until EOU detection, then sent to Saaras v3 REST API for transcription. Simpler than WebSocket-based streaming with no connection state management.
- **Live transcript streaming** — All turns are persisted to DB in real time; the frontend polls `GET /sessions/{id}/transcript` every 3s during active sessions, enabling live monitoring without WebSockets.
