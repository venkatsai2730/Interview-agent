"""Pre-session weightage analysis for interview skills.

Takes a resume (text) and job description (text), calls the LLM to produce
a structured topic-priority analysis, and returns it as context_data fields
that get injected into the agent's system prompt.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Vertex AI config
GCP_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
GCP_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

ANALYSIS_PROMPT = """You are an expert interviewer preparing for a technical interview.

Given the RESUME and JOB DESCRIPTION below, produce a structured interview plan with topic weightage.

RESUME:
{resume_text}

JOB DESCRIPTION:
{job_description}

Analyze the resume against the JD requirements and produce a JSON response with:
1. Key topics to assess, prioritized by gaps between resume and JD requirements
2. For each topic: priority (1-5), why it matters, and 2-3 suggested questions
3. Overall time allocation percentages

RULES:
- Priority 5 = critical gap (JD requires it strongly, resume is weak) → spend most time here
- Priority 4 = important gap (JD mentions it, resume doesn't clearly demonstrate)
- Priority 3 = moderate (JD requires, resume partially covers)
- Priority 2 = validation only (resume shows strength, just confirm)
- Priority 1 = skip or one quick question (resume clearly matches JD)
- Total topics should be 4-7 (not more)
- Time allocation should sum to 100%
- Questions should be specific and reference resume/JD details

Respond with ONLY valid JSON in this exact format:
{{
  "candidate_summary": "One sentence summary of candidate's profile",
  "key_strengths": ["strength1", "strength2"],
  "key_gaps": ["gap1", "gap2"],
  "topics": [
    {{
      "topic": "topic_name",
      "priority": 5,
      "jd_requirement": "What the JD asks for",
      "resume_evidence": "What the resume shows (or lacks)",
      "reason": "Why this priority level",
      "suggested_questions": [
        "Question 1 referencing specific details",
        "Question 2 probing deeper"
      ],
      "max_follow_ups": 3
    }}
  ],
  "time_allocation": {{
    "topic_name": 30,
    "topic_name_2": 25
  }},
  "interview_approach": "Brief strategy note for the interviewer"
}}"""


async def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF file using PyMuPDF."""
    import fitz  # pymupdf

    text_parts = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())

    full_text = "\n".join(text_parts).strip()
    # Truncate to ~8000 chars to fit in LLM context
    if len(full_text) > 8000:
        full_text = full_text[:8000] + "\n... [truncated]"
    return full_text


async def _call_vertex_ai(prompt: str) -> str:
    """Call Vertex AI Gemini 2.5 Flash for the analysis."""
    from google.auth import default as ga_default
    from google.auth.transport.requests import Request as AuthRequest

    credentials, project = ga_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(AuthRequest())
    token = credentials.token

    project_id = GCP_PROJECT or project
    location = GCP_LOCATION
    model = "gemini-2.5-flash"

    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}"
        f"/locations/{location}/publishers/google/models/{model}:generateContent"
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4000},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code != 200:
            logger.error("Vertex AI analysis failed: %d %s", response.status_code, response.text[:500])
            raise RuntimeError(f"Vertex AI error {response.status_code}")

        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return text


async def _call_openrouter(prompt: str) -> str:
    """Fallback: call OpenRouter for the analysis."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("No OPENROUTER_API_KEY for fallback analysis")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "google/gemini-2.5-flash",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 4000,
            },
        )
        if response.status_code != 200:
            raise RuntimeError(f"OpenRouter error {response.status_code}")
        data = response.json()
        return data["choices"][0]["message"]["content"]


def _parse_analysis_json(text: str) -> dict:
    """Extract JSON from LLM response (handles markdown code blocks, thinking blocks)."""
    text = text.strip()
    
    # Strip thinking blocks (Gemini 2.5 may include <think>...</think>)
    import re
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try extracting from markdown code block (```json ... ```)
    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
    if match:
        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning("JSON in code block failed to parse: %s (first 200 chars: %s)", e, json_str[:200])
    
    # Try finding first { ... last } (greedy)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        json_str = text[start:end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning("Extracted JSON block failed to parse: %s (first 200 chars: %s)", e, json_str[:200])
    
    raise ValueError(f"Could not parse analysis JSON from LLM response (length={len(text)}): {text[:300]}")


async def analyze_resume_jd(
    resume_text: str,
    job_description: str,
    llm_model: Optional[str] = None,
) -> dict:
    """Run the weightage analysis and return structured results.

    Returns a dict with keys: weighted_topics, time_allocation, candidate_summary,
    key_strengths, key_gaps, interview_approach — ready to inject into context_data.
    """
    prompt = ANALYSIS_PROMPT.format(
        resume_text=resume_text,
        job_description=job_description,
    )

    # Try Vertex AI first, fall back to OpenRouter
    try:
        raw_response = await _call_vertex_ai(prompt)
    except Exception as exc:
        logger.warning("Vertex AI analysis failed (%s), trying OpenRouter", exc)
        try:
            raw_response = await _call_openrouter(prompt)
        except Exception as fallback_exc:
            logger.error("Both Vertex AI and OpenRouter failed for analysis: %s", fallback_exc)
            # Return empty analysis rather than failing the session
            return {
                "weighted_topics": "Analysis unavailable. Conduct a general interview.",
                "time_allocation": "",
                "candidate_summary": "",
                "interview_approach": "Conduct a general technical interview covering the JD requirements.",
            }

    try:
        analysis = _parse_analysis_json(raw_response)
    except ValueError as exc:
        logger.error("Failed to parse analysis: %s", exc)
        return {
            "weighted_topics": "Analysis unavailable. Conduct a general interview.",
            "time_allocation": "",
            "candidate_summary": "",
            "interview_approach": "Conduct a general technical interview covering the JD requirements.",
        }

    # Format the analysis into text that the agent can use in its prompt
    topics = analysis.get("topics", [])
    topics_sorted = sorted(topics, key=lambda t: t.get("priority", 0), reverse=True)

    weighted_topics_lines = []
    for t in topics_sorted:
        priority = t.get("priority", 3)
        topic = t.get("topic", "unknown")
        reason = t.get("reason", "")
        questions = t.get("suggested_questions", [])
        max_fu = t.get("max_follow_ups", 2)

        weighted_topics_lines.append(
            f"- [{priority}/5] {topic}: {reason}\n"
            f"  Suggested questions ({max_fu} follow-ups max):\n"
            + "\n".join(f"    • {q}" for q in questions)
        )

    time_alloc = analysis.get("time_allocation", {})
    time_lines = [f"  - {topic}: {pct}%" for topic, pct in time_alloc.items()]

    return {
        "weighted_topics": "\n".join(weighted_topics_lines),
        "time_allocation": "\n".join(time_lines),
        "candidate_summary": analysis.get("candidate_summary", ""),
        "key_strengths": ", ".join(analysis.get("key_strengths", [])),
        "key_gaps": ", ".join(analysis.get("key_gaps", [])),
        "interview_approach": analysis.get("interview_approach", ""),
    }
