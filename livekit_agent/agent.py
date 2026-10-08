"""
Vero LiveKit Agent — Sarvam AI (speech-to-speech)

Sarvam handles STT + LLM + TTS via WebSocket streaming,
integrated with LiveKit's Sarvam plugin for real-time conversation.
The skill pack questions/instructions are embedded directly in the system
prompt so Sarvam follows the interview flow.

The Node.js agent is still spawned in the background to handle scoring and
session summary generation — it receives turn transcripts via the same
stdin/stdout RPC protocol.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from livekit.agents import Agent, AgentSession, JobContext, JobProcess, WorkerOptions, cli
from livekit.plugins import openai as lk_openai
from livekit.plugins import sarvam

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logger = logging.getLogger("vero.livekit_agent")

# ---------------------------------------------------------------------------
# In-memory session summary store
# ---------------------------------------------------------------------------
_session_summaries: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Session close events for auto-close when all questions are complete
# ---------------------------------------------------------------------------
_session_close_events: dict[str, asyncio.Event] = {}


# ---------------------------------------------------------------------------
# Node.js scoring bridge (fire-and-forget, non-blocking)
# ---------------------------------------------------------------------------

class ScoringBridge:
    """Spawns the Node.js agent for scoring/summary only — not for audio."""

    def __init__(self, session_id: str, skill_pack: dict) -> None:
        self._session_id = session_id
        self._skill_pack = skill_pack
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._turn_index = 0
        # Callback for when the scoring bridge makes a decision.
        # Called with (action, question_id, next_utterance, score)
        self.on_turn_decision: Optional[callable] = None

    async def start(self) -> None:
        agent_path = os.path.join(os.path.dirname(__file__), "..", "agent", "dist", "agent.js")
        self._proc = await asyncio.create_subprocess_exec(
            "node", agent_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("scoring_bridge[%s]: Node.js spawned pid=%d", self._session_id, self._proc.pid)
        asyncio.ensure_future(self._drain_stderr())
        asyncio.ensure_future(self._read_loop())
        await self._write({"type": "session_start", "session_id": self._session_id, "skill_pack": self._skill_pack})

    async def send_turn(self, speaker: str, transcript: str) -> None:
        timestamp_ms = int(asyncio.get_event_loop().time() * 1000)
        turn_index = self._turn_index
        self._turn_index += 1

        # Persist to backend DB first — independent of Node.js bridge health.
        # If _write fails (Node.js crashed / agent.js not found), transcripts
        # would be silently lost without this ordering.
        await self._persist_turn_to_backend(speaker, transcript, turn_index, timestamp_ms)

        # Send to Node.js scoring bridge (non-critical path)
        try:
            await self._write({
                "type": "turn",
                "session_id": self._session_id,
                "speaker": speaker,
                "transcript": transcript,
                "turn_index": turn_index,
                "timestamp_ms": timestamp_ms,
            })
        except Exception as exc:
            logger.warning("send_turn[%s]: Node.js write failed: %s", self._session_id, exc)

    async def _persist_turn_to_backend(self, speaker: str, transcript: str, turn_index: int, timestamp_ms: int) -> None:
        """Persist turn transcript to backend database."""
        import httpx
        backend_url = os.environ.get("BACKEND_URL", "http://backend:8000")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{backend_url}/livekit/turn",
                    json={
                        "session_id": self._session_id,
                        "turn_index": turn_index,
                        "speaker": speaker,
                        "transcript": transcript,
                        "timestamp_ms": timestamp_ms,
                    }
                )
        except Exception as exc:
            logger.warning("persist_turn_to_backend[%s]: failed: %s", self._session_id, exc)

    async def stop(self) -> None:
        if self._proc and self._proc.returncode is None:
            try:
                await self._write({"type": "session_end", "session_id": self._session_id, "reason": "manual"})
            except Exception:
                pass
            # Give Node.js a moment to flush, then force-kill
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self._proc.kill()
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass

    async def _write(self, msg: dict) -> None:
        if self._proc and self._proc.stdin:
            self._proc.stdin.write((json.dumps(msg) + "\n").encode())
            await self._proc.stdin.drain()

    async def _drain_stderr(self) -> None:
        if not self._proc or not self._proc.stderr:
            return
        while True:
            line = await self._proc.stderr.readline()
            if not line:
                break
            logger.debug("node_stderr: %s", line.decode().rstrip())

    async def _read_loop(self) -> None:
        if not self._proc or not self._proc.stdout:
            return
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode())
            except Exception:
                continue
            msg_type = msg.get("type")
            if msg_type == "session_summary":
                logger.info("scoring_bridge[%s]: summary received", self._session_id)
                _session_summaries[self._session_id] = msg
            elif msg_type == "error":
                logger.error("scoring_bridge[%s]: %s", self._session_id, msg.get("message"))
            elif msg_type == "turn_output":
                action = msg.get("action")
                question_id = msg.get("question_id", "")
                next_utterance = msg.get("next_utterance", "")
                score = msg.get("score")
                logger.info("scoring_bridge[%s]: turn_output action=%s question=%s score=%s",
                            self._session_id, action, question_id, score)
                # Notify the conversation handler about the scoring decision
                if self.on_turn_decision:
                    try:
                        self.on_turn_decision(action, question_id, next_utterance, score)
                    except Exception as exc:
                        logger.warning("scoring_bridge[%s]: on_turn_decision callback failed: %s",
                                       self._session_id, exc)


# ---------------------------------------------------------------------------
# Build system prompt from skill pack
# ---------------------------------------------------------------------------

def _substitute_context_templates(text: str, context_data: dict | None) -> str:
    """Substitute {{variable}} templates and {% if var == 'val' %}...{% else %}...{% endif %} blocks."""
    if not context_data:
        return text
    import re

    # Process {% if var == 'value' %}...{% else %}...{% endif %} blocks
    def replace_if(match):
        var_name = match.group(1)
        compare_val = match.group(2)
        then_block = match.group(3)
        else_block = match.group(4) or ''
        actual_val = str(context_data.get(var_name, ''))
        result = then_block if actual_val == compare_val else else_block
        return result.strip()

    text = re.sub(
        r'\{%-?\s*if\s+(\w+)\s*==\s*[\'"]([^\'"]+)[\'"]\s*-?%\}(.*?)(?:\{%-?\s*else\s*-?%\}(.*?))?\{%-?\s*endif\s*-?%\}',
        replace_if,
        text,
        flags=re.DOTALL,
    )

    # Substitute {{variable}} placeholders
    def replace_var(match):
        key = match.group(1)
        value = context_data.get(key)
        return str(value) if value is not None else match.group(0)

    return re.sub(r'\{\{(\w+)\}\}', replace_var, text)


def _build_instructions(skill_pack: dict, voice_name: str = "", channel: str = "teams") -> tuple[str, str]:
    """Build the system prompt and extract the opening greeting.

    Returns:
        (instructions, opening_greeting) — the system prompt does NOT include
        the opening greeting so the LLM doesn't repeat it after session.say().
    """
    skill = skill_pack.get("skill", {})
    name = skill.get("name", "Session")
    agent_cfg = skill_pack.get("agent", {})
    context_data = dict(skill_pack.get("context_data") or {})

    # Use voice name as agent name if provided, otherwise fall back to skill pack agent name
    original_name = agent_cfg.get("name", "Vero")
    agent_display_name = voice_name.capitalize() if voice_name else original_name

    # Inject agent_name into context_data so {{agent_name}} in templates resolves correctly
    context_data["agent_name"] = agent_display_name

    persona = agent_cfg.get("persona", f"You are {agent_display_name}, a professional AI assistant.")
    # First substitute context templates (handles {{agent_name}}, {% if %} etc.)
    persona = _substitute_context_templates(persona, context_data)
    # Fallback: replace hardcoded original agent name in persona text
    if voice_name and original_name and original_name != agent_display_name:
        persona = persona.replace(original_name, agent_display_name)

    # Extract the opening greeting from the skill pack (to be spoken via session.say())
    opening = agent_cfg.get("opening_utterance", "")
    if not opening:
        # Try to use the complaint summary for a more specific greeting
        complaint_summary = context_data.get("complaint_summary", "")
        if complaint_summary:
            opening = f"Hello, I'm {agent_display_name}. I understand you're experiencing an issue regarding {complaint_summary}. Could you please explain what happened?"
        else:
            opening = f"Hello, I'm {agent_display_name}. I understand you're experiencing an issue. Could you please explain what happened?"
    # Substitute templates first ({{agent_name}} → agent_display_name)
    opening = _substitute_context_templates(opening, context_data)
    # Fallback: replace hardcoded original agent name in opening text
    if voice_name and original_name and original_name != agent_display_name:
        opening = opening.replace(original_name, agent_display_name)

    logger.info("_build_instructions: agent_display_name=%r original_name=%r opening_start=%r",
                agent_display_name, original_name, opening[:80])

    # Strong identity instruction
    identity_instruction = (
        f"You are {agent_display_name}. Your name is {agent_display_name}. "
        f"Always speak in FIRST PERSON (use 'I', 'me', 'my'). "
        f"NEVER refer to yourself in third person. NEVER say '{agent_display_name} understands' — say 'I understand'."
    )

    lines = [identity_instruction, "", persona, "", f"You are facilitating a '{name}' session.", ""]

    # Add context information if available
    if context_data:
        lines.append("## Context Information")
        for key, value in context_data.items():
            if not key.startswith("_"):
                lines.append(f"- {key}: {value}")
        lines.append("")

    # NOTE: The opening greeting is spoken via session.say() before the first user turn.
    lines.append(f"The session has begun. {agent_display_name} has already introduced themselves.")
    lines.append("NEVER re-introduce yourself. NEVER say 'Hello, I'm...' again during this call.")
    lines.append("If there is silence, just say 'I am here, please continue.' — do NOT restart the conversation.")
    lines.append("")

    # Handle both guided (questions) and intelligent (objectives) modes
    has_questions = False
    for section in skill_pack.get("sections", []):
        mode = section.get("mode", "guided")
        section_name = section.get("name", section.get("title", ""))

        if section_name:
            lines.append(f"\nSection: {section_name}")

        if mode == "intelligent":
            objectives = section.get("objectives", "")
            if objectives:
                objectives = _substitute_context_templates(objectives, context_data)
                lines.append(f"\nObjectives:")
                lines.append(objectives)
                lines.append("\nApproach:")
                lines.append("- Guide the conversation naturally to achieve these objectives")
                lines.append("- Ask relevant follow-up questions based on responses")
                lines.append("- Adapt your approach based on the flow of conversation")
                lines.append("- Don't follow a rigid script - be responsive and intelligent")
        else:
            has_questions = True
            lines.append("\nQuestions to ask in order:")
            for qi, q in enumerate(section.get("questions", []), 1):
                text = _substitute_context_templates(q.get("text", ""), context_data)
                follow_ups = q.get("probes", q.get("follow_ups", []))
                lines.append(f"{qi}. {text}")
                for fu in follow_ups:
                    lines.append(f"   Follow-up if needed: {_substitute_context_templates(fu, context_data)}")
            lines.append("")
            lines.append("Ask these questions one at a time. When all are answered, summarize and say goodbye.")

    lines += [
        "",
        "Rules:",
        "- Ask ONE question at a time. Keep responses to 1 sentence MAX on phone calls.",
        "- NEVER repeat a question. If the person already answered, accept it and move on.",
        "- If the person says 'I already told you' or 'why are you asking again', apologize briefly and ask a DIFFERENT question.",
        "- Accept short answers. If someone says 'nothing happened', accept that and move to the next topic.",
        "- Do NOT rephrase the same question in different words. That counts as repeating.",
        "- Be warm but concise. Acknowledge briefly, then ask the next thing.",
        "- Never re-introduce yourself during the call.",
        "- If there is silence, say 'I am here, please continue.'",
        "- If the STT transcript seems garbled or unclear, try to understand the intent from context rather than asking them to repeat.",
        "- When you have enough information, summarize in one sentence and say goodbye.",
        "- Your goodbye MUST contain the word 'goodbye'.",
    ]

    if not has_questions:
        lines += [
            "",
            "INTELLIGENT MODE:",
            "- You are not following a fixed script. Use your judgment to guide the conversation.",
            "- Focus on achieving the stated objectives through natural dialogue.",
            "- Be adaptive and responsive to the conversation flow.",
        ]

    # Channel-specific closing and style instructions
    if channel == "phone":
        lines += [
            "",
            "PHONE CALL RULES:",
            "- Every response must be 1 sentence only. Never more than 2 sentences.",
            "- Do NOT give long summaries during the call. Save the summary for the very end.",
            "- When closing: one sentence summary, then goodbye. Nothing more.",
            "- If the person has answered a question, do NOT ask it again in different words.",
        ]
    else:
        lines += [
            "",
            "When done, tell the user they can disconnect from the Teams meeting.",
        ]

    return "\n".join(lines), opening


# ---------------------------------------------------------------------------
# LiveKit Agent entrypoint
# ---------------------------------------------------------------------------

async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    session_id = ctx.room.name
    try:
        metadata = json.loads(ctx.job.metadata or "{}")
    except Exception:
        metadata = {}

    skill_pack = metadata.get("skill_pack", {})
    voice = metadata.get("voice", "shubh")
    llm_model = metadata.get("llm_model", "sarvam-30b")
    language = metadata.get("language", "en-IN")
    agent_name = metadata.get("agent_name") or voice
    channel = metadata.get("channel", "teams")

    # Validate voice against bulbul:v3 speaker list
    _BULBUL_V3_SPEAKERS = {
        'shubh', 'ritu', 'rahul', 'pooja', 'simran', 'kavya', 'amit', 'ratan', 'rohan',
        'dev', 'ishita', 'shreya', 'manan', 'sumit', 'priya', 'aditya', 'kabir', 'neha',
        'varun', 'roopa', 'aayan', 'ashutosh', 'advait', 'amelia', 'sophia',
    }
    if voice not in _BULBUL_V3_SPEAKERS:
        logger.warning("entrypoint[%s]: voice %r not in bulbul:v3, falling back to 'shubh'", session_id, voice)
        voice = "shubh"

    if not skill_pack:
        logger.error("entrypoint[%s]: no skill_pack in metadata", session_id)
        return

    logger.info("entrypoint[%s]: starting Sarvam agent voice=%s model=%s language=%s", session_id, voice, llm_model, language)

    # Build system prompt (without the opening greeting embedded)
    # The opening greeting is returned separately and spoken via session.say()
    instructions, opening_greeting = _build_instructions(skill_pack, voice_name=agent_name, channel=channel)

    # Start scoring bridge in background
    bridge = ScoringBridge(session_id=session_id, skill_pack=skill_pack)
    await bridge.start()

    sarvam_api_key = os.environ.get("SARVAM_API_KEY", "")

    # Pre-populate the chat context with the opening greeting as an assistant message.
    # This prevents the LLM from auto-generating a greeting when the session starts
    # (empty chat history → LLM initiates conversation → double greeting).
    # The greeting is still spoken audibly via session.say() below.
    from livekit.agents import llm as lk_llm
    initial_ctx = lk_llm.ChatContext()
    if opening_greeting:
        initial_ctx.add_message(role="assistant", content=opening_greeting)

    agent = Agent(instructions=instructions, chat_ctx=initial_ctx)

    # Configure turn handling for phone calls:
    # - Increase min_delay so the agent waits longer before assuming the user is done speaking.
    #   Phone calls have natural pauses between sentences — 0.5s default is too aggressive.
    # - Use dynamic endpointing to adapt to the caller's speaking pace over time.
    from livekit.agents.voice import AgentSession as _AgentSession
    turn_handling_opts = None
    if channel == "phone":
        try:
            from livekit.agents.voice import TurnHandlingOptions, EndpointingOptions
            turn_handling_opts = TurnHandlingOptions(
                endpointing=EndpointingOptions(
                    min_delay=1.5,   # Wait 1.5s of silence before responding (default 0.5s)
                    max_delay=5.0,   # Max wait 5s (default 3s)
                ),
            )
            logger.info("entrypoint[%s]: using phone turn handling (min_delay=1.5s)", session_id)
        except ImportError:
            logger.warning("entrypoint[%s]: TurnHandlingOptions not available in this SDK version", session_id)

    # Provider API keys and GCP config — must be defined before STT/LLM selection
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "")
    gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    gcp_location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

    # STT/TTS provider selection.
    # Sarvam STT for Sarvam LLMs, Google STT (Chirp 2) for Gemini/GPT.
    # Always Sarvam TTS (Bulbul) for Indian voices.
    is_sarvam_llm = not (llm_model.startswith("gpt-") or llm_model.startswith("gemini"))

    if not is_sarvam_llm and gcp_project:
        try:
            from livekit.plugins import google as lk_google
            google_stt = lk_google.STT(
                languages=language if language else "en-IN",
                location=gcp_location,
                model="chirp_2",
            )
            # The plugin doesn't accept project as a constructor param.
            # With authorized_user ADC, project_id can't be inferred from
            # credentials, so we set it explicitly from the env var.
            google_stt._project_id = gcp_project
            logger.info("entrypoint[%s]: using Google STT (Chirp 2, project=%s) + Sarvam TTS", session_id, gcp_project)
            session_kwargs = dict(
                stt=google_stt,
                tts=sarvam.TTS(
                    api_key=sarvam_api_key,
                    target_language_code=language,
                    speaker=voice,
                    model="bulbul:v3",
                ),
            )
        except Exception as exc:
            logger.warning("entrypoint[%s]: Google STT init failed (%s), falling back to Sarvam STT", session_id, exc)
            session_kwargs = dict(
                stt=sarvam.STT(api_key=sarvam_api_key, language=language, model="saarika:v2.5"),
                tts=sarvam.TTS(api_key=sarvam_api_key, target_language_code=language, speaker=voice, model="bulbul:v3"),
            )
    else:
        logger.info("entrypoint[%s]: using Sarvam STT + TTS (llm=%s)", session_id, llm_model)
        session_kwargs = dict(
            stt=sarvam.STT(
                api_key=sarvam_api_key,
                language=language,
                model="saarika:v2.5",
            ),
            tts=sarvam.TTS(
                api_key=sarvam_api_key,
                target_language_code=language,
                speaker=voice,
                model="bulbul:v3",
            ),
        )

    # Map UI model names to OpenRouter model IDs
    OPENROUTER_MODELS = {
        "gemini-2.5-flash": "google/gemini-2.5-flash",
        "gpt-4o-mini": "openai/gpt-4o-mini",
        "gpt-4o": "openai/gpt-4o",
    }

    # Vertex AI Gemini models (uses gcloud auth, no API key needed)
    VERTEX_AI_MODELS = {
        "gemini-2.5-flash": "gemini-2.5-flash",
        "gemini-2.5-pro": "gemini-2.5-pro",
    }

    if llm_model in VERTEX_AI_MODELS and gcp_project:
        # Use Vertex AI directly via Google plugin (gcloud ADC auth)
        vertex_model = VERTEX_AI_MODELS[llm_model]
        from livekit.plugins import google as lk_google
        logger.info("entrypoint[%s]: using Vertex AI LLM model=%s (project=%s, location=%s)",
                    session_id, vertex_model, gcp_project, gcp_location)
        session_kwargs["llm"] = lk_google.LLM(
            model=vertex_model,
            project=gcp_project,
            location=gcp_location,
            vertexai=True,
        )
    elif llm_model in OPENROUTER_MODELS and openrouter_api_key:
        # Route through OpenRouter (supports Gemini, GPT, Claude, etc.)
        or_model = OPENROUTER_MODELS[llm_model]
        logger.info("entrypoint[%s]: using OpenRouter LLM model=%s (mapped to %s)", session_id, llm_model, or_model)
        session_kwargs["llm"] = lk_openai.LLM(
            model=or_model,
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_api_key,
        )
    elif llm_model.startswith("gpt-") and openai_api_key:
        # Direct OpenAI
        logger.info("entrypoint[%s]: using OpenAI LLM model=%s", session_id, llm_model)
        session_kwargs["llm"] = lk_openai.LLM(
            model=llm_model,
            api_key=openai_api_key,
        )
    else:
        # Default: Sarvam LLM
        logger.info("entrypoint[%s]: using Sarvam LLM model=%s", session_id, llm_model)
        session_kwargs["llm"] = lk_openai.LLM(
            model=llm_model,
            base_url="https://api.sarvam.ai/v1",
            api_key=sarvam_api_key,
            extra_headers={"api-subscription-key": sarvam_api_key},
        )
    if turn_handling_opts is not None:
        session_kwargs["turn_handling"] = turn_handling_opts

    session = AgentSession(**session_kwargs)

    # Hook transcripts into scoring bridge
    # LiveKit agents v1.4 event names:
    # - "user_input_transcribed" fires with UserInputTranscribedEvent (has .transcript, .is_final)
    # - "conversation_item_added" fires with ConversationItemAddedEvent (has .item: ChatMessage)

    # Track whether the session is ready for scoring (after greeting is spoken).
    # The opening greeting is pre-populated in chat context and fires
    # conversation_item_added — we must NOT send it to the scoring bridge
    # because it would cause the Node.js agent to advance the question index.
    scoring_ready = False

    # ---------------------------------------------------------------------------
    # Guided mode: feed scoring bridge decisions back into the LLM context
    # ---------------------------------------------------------------------------
    # Build a flat list of all guided questions for tracking
    all_guided_questions = []
    for section in skill_pack.get("sections", []):
        if section.get("mode", "guided") == "guided":
            for q in section.get("questions", []):
                all_guided_questions.append({
                    "id": q.get("id", ""),
                    "text": _substitute_context_templates(q.get("text", ""), skill_pack.get("context_data")),
                    "probes": [_substitute_context_templates(p, skill_pack.get("context_data"))
                               for p in q.get("probes", q.get("follow_ups", []))],
                })

    is_guided = len(all_guided_questions) > 0
    guided_question_index = 0  # which question we're currently on

    def on_scoring_decision(action: str, question_id: str, next_utterance: str, score):
        """Called by the scoring bridge when it makes a decision about a turn."""
        nonlocal guided_question_index

        if not is_guided:
            return

        if action in ("advance", "close"):
            guided_question_index += 1

        total = len(all_guided_questions)
        remaining = total - guided_question_index

        if action == "close" or remaining <= 0:
            # All questions done — inject ONE clear close message
            directive = (
                "All questions have been covered. Summarize briefly and say goodbye."
            )
            logger.info("entrypoint[%s]: injecting CLOSE directive into LLM context", session_id)
            agent.chat_ctx.add_message(role="system", content=directive)

            # Also trigger the close event so the call ends after the LLM speaks
            close_ev = _session_close_events.get(session_id)
            if close_ev and not close_ev.is_set():
                async def _delayed_close():
                    await asyncio.sleep(8)
                    if not close_ev.is_set():
                        logger.info("entrypoint[%s]: scoring bridge close — forcing session end", session_id)
                        close_ev.set()
                asyncio.ensure_future(_delayed_close())

        # For advance and follow_up: do NOT inject system messages.
        # Sarvam-30B gets confused by too many system messages in the context.
        # The questions are already in the system prompt — let the LLM follow them naturally.
        elif action == "advance" and remaining > 0:
            logger.info("entrypoint[%s]: scoring bridge advance to q%d/%d (no directive injected)", session_id, guided_question_index + 1, total)
        elif action == "follow_up":
            logger.info("entrypoint[%s]: scoring bridge follow_up (no directive injected)", session_id)

    bridge.on_turn_decision = on_scoring_decision

    @session.on("user_input_transcribed")
    def on_user_speech(ev):
        if ev.is_final and ev.transcript and scoring_ready:
            logger.info("send_turn[%s]: user transcript=%r", session_id, ev.transcript[:60])
            asyncio.ensure_future(bridge.send_turn("participant", ev.transcript))

    @session.on("conversation_item_added")
    def on_conversation_item(ev):
        if not scoring_ready:
            return
        item = ev.item
        # Only capture assistant (agent) messages that were not interrupted
        if getattr(item, "role", None) == "assistant" and not getattr(item, "interrupted", False):
            text = item.text_content
            if text:
                logger.info("send_turn[%s]: agent transcript=%r", session_id, text[:60])
                asyncio.ensure_future(bridge.send_turn("agent", text))

                # Detect when the LLM naturally ends the conversation (says goodbye).
                text_lower = text.lower().strip()
                goodbye_phrases = ["goodbye", "good bye", "bye!", "bye.", "that completes our call", "that completes our session"]
                if any(phrase in text_lower for phrase in goodbye_phrases):
                    close_ev = _session_close_events.get(session_id)
                    if close_ev and not close_ev.is_set():
                        nonlocal llm_said_goodbye
                        llm_said_goodbye = True
                        logger.info("entrypoint[%s]: LLM said goodbye — triggering session close", session_id)
                        close_ev.set()

    # Create close event before session starts so participant_disconnected can set it
    close_event = asyncio.Event()
    _session_close_events[session_id] = close_event

    # Track whether the close was triggered by the participant hanging up (vs. session
    # completing normally).  We must not try to speak a goodbye to an already-dead line.
    closed_by_participant = False
    llm_said_goodbye = False

    # Track whether the session is ready (greeting spoken, participant confirmed).
    # SIP participants can briefly connect/disconnect during Twilio→LiveKit bridge
    # setup — we must not treat those transient disconnects as real hang-ups.
    session_ready = False
    human_participant_connected = False

    # Detect participant connection: track when a real human joins
    @ctx.room.on("participant_connected")
    def on_participant_connected(participant):
        nonlocal human_participant_connected
        is_agent = getattr(participant, "is_agent", False)
        if not is_agent:
            human_participant_connected = True
            logger.info(
                "entrypoint[%s]: human participant connected identity=%s",
                session_id, getattr(participant, "identity", "?"),
            )

    # Detect participant hang-up: when the human disconnects, close the session
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        nonlocal closed_by_participant
        is_agent = getattr(participant, "is_agent", False)
        logger.info(
            "entrypoint[%s]: participant_disconnected identity=%s is_agent=%s session_ready=%s",
            session_id, getattr(participant, "identity", "?"), is_agent, session_ready,
        )
        # Only treat as a real hang-up if:
        # 1. It's not the agent itself disconnecting
        # 2. The session is ready (greeting has been spoken)
        # 3. A human participant was actually connected at some point
        if not is_agent and session_ready and human_participant_connected and not close_event.is_set():
            logger.info("entrypoint[%s]: human participant hung up — closing session", session_id)
            closed_by_participant = True
            close_event.set()

    await session.start(agent, room=ctx.room)

    # Check if any human participants are already in the room (SIP may connect before agent)
    for p in ctx.room.remote_participants.values():
        is_agent = getattr(p, "is_agent", False)
        if not is_agent:
            human_participant_connected = True
            logger.info("entrypoint[%s]: human participant already in room identity=%s",
                        session_id, getattr(p, "identity", "?"))

    # Wait for a human participant to join before speaking the greeting.
    # For phone calls, the SIP participant typically bridges in within 5-10 seconds.
    if not human_participant_connected:
        logger.info("entrypoint[%s]: waiting for human participant to join...", session_id)
        wait_start = asyncio.get_event_loop().time()
        while not human_participant_connected:
            await asyncio.sleep(0.3)
            if asyncio.get_event_loop().time() - wait_start > 15:
                logger.warning("entrypoint[%s]: timed out waiting for human participant", session_id)
                break

    # Speak the opening greeting immediately after session.start() — before any
    # async HTTP calls — so the LLM cannot auto-generate a response in the gap.
    # The chat context was pre-populated with this text so the LLM already knows
    # it was spoken and will not generate another greeting.
    if opening_greeting:
        logger.info("entrypoint[%s]: speaking opening greeting via Sarvam TTS", session_id)
        await session.say(opening_greeting)

    # Mark session as ready — now participant disconnects are treated as real hang-ups
    session_ready = True

    # Enable scoring bridge — turns will now be forwarded to the Node.js agent.
    # This must happen AFTER the greeting is spoken so the opening greeting
    # (pre-populated in chat context) doesn't get sent as a scoreable turn.
    scoring_ready = True

    await _notify_backend_active(session_id)

    logger.info("entrypoint[%s]: Sarvam pipeline ready — conversation started", session_id)

    shutdown_event = asyncio.Event()

    async def _on_shutdown():
        shutdown_event.set()

    ctx.add_shutdown_callback(_on_shutdown)

    # Max-duration timeout — forcibly ends the session if it runs too long.
    # Uses skill pack's max_duration_minutes (default 30 min).
    max_duration_seconds = skill_pack.get("agent", {}).get("max_duration_minutes", 30) * 60
    timeout_task = asyncio.create_task(asyncio.sleep(max_duration_seconds))

    # Wait for: manual LiveKit shutdown, participant hang-up, scoring bridge "close", or timeout
    shutdown_task = asyncio.create_task(shutdown_event.wait())
    close_task = asyncio.create_task(close_event.wait())

    done, pending = await asyncio.wait(
        [shutdown_task, close_task, timeout_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    timed_out = timeout_task in done and not close_event.is_set()

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    _session_close_events.pop(session_id, None)

    # ---- IMPORTANT: Send backend notifications BEFORE disconnecting the room ----
    # Once ctx.room.disconnect() is called, the LiveKit framework may kill the
    # process immediately, so we must persist state to the backend first.
    await bridge.stop()

    summary = _session_summaries.pop(session_id, None)
    if summary:
        logger.info("entrypoint[%s]: sending summary to backend", session_id)
        await _notify_backend_summary(session_id, summary)
    else:
        logger.info("entrypoint[%s]: no summary, sending close to backend", session_id)
        await _notify_backend_close(session_id)

    # If the session completed normally and the participant is still on the line,
    # disconnect the room. Skip the hardcoded goodbye if the LLM already said it.
    if not closed_by_participant and not shutdown_event.is_set():
        if timed_out:
            logger.info("entrypoint[%s]: max duration reached — ending call", session_id)
        # Only speak a goodbye if the LLM didn't already say one
        if not llm_said_goodbye:
            if channel == "phone":
                goodbye = "Thank you for your time. That completes our call. Goodbye!"
            else:
                goodbye = "Thank you for your time. That completes our session. You can now disconnect. Have a great day!"
            try:
                await session.say(goodbye, allow_interruptions=False)
            except Exception as exc:
                logger.warning("entrypoint[%s]: goodbye utterance failed: %s", session_id, exc)
        else:
            # Give TTS a moment to finish speaking the LLM's goodbye
            await asyncio.sleep(3)
        try:
            await ctx.room.disconnect()
            logger.info("entrypoint[%s]: room disconnected — call ended by agent", session_id)
        except Exception as exc:
            logger.warning("entrypoint[%s]: room disconnect failed: %s", session_id, exc)

    logger.info("entrypoint[%s]: done", session_id)


async def _notify_backend_active(session_id: str) -> None:
    import httpx
    backend_url = os.environ.get("BACKEND_URL", "http://backend:8000")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{backend_url}/livekit/session-active", json={"session_id": session_id})
    except Exception as exc:
        logger.warning("notify_active failed: %s", exc)


async def _notify_backend_summary(session_id: str, summary: dict) -> None:
    import httpx
    backend_url = os.environ.get("BACKEND_URL", "http://backend:8000")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{backend_url}/livekit/session-summary",
                json={"session_id": session_id, "summary": summary},
            )
    except Exception as exc:
        logger.warning("notify_summary failed: %s", exc)


async def _notify_backend_close(session_id: str) -> None:
    """Close the session in the backend DB when the participant disconnects mid-session."""
    import httpx
    backend_url = os.environ.get("BACKEND_URL", "http://backend:8000")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{backend_url}/livekit/session-close",
                json={"session_id": session_id},
            )
        logger.info("notify_close[%s]: session closed in backend", session_id)
    except Exception as exc:
        logger.warning("notify_close[%s]: failed: %s", session_id, exc)


def prewarm(proc: JobProcess) -> None:
    pass  # Sarvam has built-in VAD — no prewarming needed


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="vero-agent",
        )
    )
