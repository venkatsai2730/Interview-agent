"""Skill Pack router - CRUD operations for skill packs."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import verify_token
from backend.db import get_db
from backend.models import SkillPack as SkillPackModel, SkillPackVersion as SkillPackVersionModel
from backend.schemas import (
    SkillPackCreateRequest,
    SkillPackUpdateRequest,
    SkillPackSummary,
    SkillPackVersionRecord,
    SectionSummary,
    ValidateSkillPackRequest,
    GenerateSkillPackRequest,
    GenerateSkillPackResponse,
)
from backend.skill_pack_validator import ParseError, parse_skill_pack_yaml, validate_skill_pack

router = APIRouter(prefix="/skill-packs", tags=["skill-packs"])


def _extract_sections_summary(yaml_content: str) -> list[SectionSummary]:
    import yaml as _yaml
    try:
        parsed = _yaml.safe_load(yaml_content) or {}
    except Exception:
        return []
    summaries = []
    for section in parsed.get("sections", []):
        mode = section.get("mode", "")
        if mode == "guided":
            questions = [q.get("text", "") for q in section.get("questions", []) if q.get("text")]
            summaries.append(SectionSummary(mode=mode, questions=questions, objectives=None))
        elif mode == "intelligent":
            objectives = section.get("objectives")
            summaries.append(SectionSummary(mode=mode, questions=[], objectives=str(objectives).strip() if objectives else None))
    return summaries


async def _get_db():
    """Dependency to get DB session."""
    async for session in get_db():
        yield session


@router.post("/validate")
async def validate_skill_pack_endpoint(
    request: ValidateSkillPackRequest,
    token: str = Depends(verify_token),
):
    """Validate a Skill Pack YAML without starting a session."""
    try:
        parsed = parse_skill_pack_yaml(request.yaml_content)
    except ParseError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"YAML parse error at line {exc.line}: {exc.message}",
        ) from exc

    result = validate_skill_pack(parsed)
    if not result.is_valid:
        raise HTTPException(
            status_code=422,
            detail={"message": "Validation failed", "errors": result.errors},
        )

    return {"valid": True}


@router.get("/", response_model=list[SkillPackSummary])
async def list_skill_packs(
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """List all stored Skill Packs."""
    result = await db.execute(select(SkillPackModel).order_by(SkillPackModel.created_at.desc()))
    rows = result.scalars().all()

    return [
        SkillPackSummary(
            id=row.id,
            name=row.name,
            skill_id=row.skill_id,
            version=row.version,
            is_active=row.is_active,
            channels=row.channels or ["teams", "phone"],
            created_at=row.created_at,
            yaml_content=row.yaml_content,
            sections_summary=_extract_sections_summary(row.yaml_content),
        )
        for row in rows
    ]


@router.post("/", status_code=201)
async def create_skill_pack(
    request: SkillPackCreateRequest,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Validate YAML, store in skill_packs table, create initial version record."""
    try:
        parsed = parse_skill_pack_yaml(request.yaml_content)
    except ParseError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"YAML parse error at line {exc.line}: {exc.message}",
        ) from exc

    result = validate_skill_pack(parsed)
    if not result.is_valid:
        raise HTTPException(
            status_code=422,
            detail={"message": "Validation failed", "errors": result.errors},
        )

    skill_id = parsed.get("skill", {}).get("id", "")
    name = parsed.get("skill", {}).get("name", "")
    version = parsed.get("skill", {}).get("version", "")
    channels = parsed.get("channels", ["teams", "phone"])
    now = datetime.now(tz=timezone.utc)
    new_id = str(uuid.uuid4())

    skill_pack_row = SkillPackModel(
        id=new_id,
        name=name,
        skill_id=skill_id,
        version=version,
        yaml_content=request.yaml_content,
        parsed_content=parsed,
        is_active=False,
        channels=channels,
        created_at=now,
        updated_at=now,
    )
    db.add(skill_pack_row)

    version_row = SkillPackVersionModel(
        skill_pack_id=new_id,
        version_number=1,
        yaml_content=request.yaml_content,
        parsed_content=parsed,
        change_summary=request.change_summary,
        created_at=now,
    )
    db.add(version_row)

    await db.commit()

    return {
        "id": new_id,
        "name": name,
        "skill_id": skill_id,
        "version": version,
        "is_active": False,
        "channels": channels,
        "created_at": now.isoformat(),
    }


@router.put("/{skill_pack_id}")
async def update_skill_pack(
    skill_pack_id: str,
    request: SkillPackUpdateRequest,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Validate YAML, update skill_packs row, insert new version record."""
    result = await db.execute(
        select(SkillPackModel).where(SkillPackModel.id == skill_pack_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Skill Pack not found")

    try:
        parsed = parse_skill_pack_yaml(request.yaml_content)
    except ParseError as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"YAML parse error: {exc.message} at line {exc.line}")
        logger.error(f"YAML content (first 500 chars): {request.yaml_content[:500]}")
        raise HTTPException(
            status_code=422,
            detail=f"YAML parse error at line {exc.line}: {exc.message}",
        ) from exc

    validation = validate_skill_pack(parsed)
    if not validation.is_valid:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Validation failed: {validation.errors}")
        logger.error(f"YAML content (first 500 chars): {request.yaml_content[:500]}")
        raise HTTPException(
            status_code=422,
            detail={"message": "Validation failed", "errors": validation.errors},
        )

    # Determine next version number
    max_result = await db.execute(
        select(func.max(SkillPackVersionModel.version_number)).where(
            SkillPackVersionModel.skill_pack_id == skill_pack_id
        )
    )
    current_max = max_result.scalar() or 0
    next_version_number = current_max + 1

    now = datetime.now(tz=timezone.utc)

    # Update skill_packs row
    row.yaml_content = request.yaml_content
    row.parsed_content = parsed
    row.name = parsed.get("skill", {}).get("name", row.name)
    row.skill_id = parsed.get("skill", {}).get("id", row.skill_id)
    row.version = parsed.get("skill", {}).get("version", row.version)
    row.updated_at = now

    # Insert new version record
    version_row = SkillPackVersionModel(
        skill_pack_id=skill_pack_id,
        version_number=next_version_number,
        yaml_content=request.yaml_content,
        parsed_content=parsed,
        change_summary=request.change_summary,
        created_at=now,
    )
    db.add(version_row)

    await db.commit()

    return {
        "id": skill_pack_id,
        "name": row.name,
        "skill_id": row.skill_id,
        "version": row.version,
        "is_active": row.is_active,
        "updated_at": now.isoformat(),
        "version_number": next_version_number,
    }


@router.post("/{skill_pack_id}/activate", response_model=SkillPackSummary)
async def activate_skill_pack(
    skill_pack_id: str,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Activate a Skill Pack."""
    from sqlalchemy import update

    result = await db.execute(
        select(SkillPackModel).where(SkillPackModel.id == skill_pack_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Skill Pack not found")

    await db.execute(
        update(SkillPackModel)
        .where(SkillPackModel.id == skill_pack_id)
        .values(is_active=True)
    )
    await db.commit()
    await db.refresh(row)

    return SkillPackSummary(
        id=row.id,
        name=row.name,
        skill_id=row.skill_id,
        version=row.version,
        is_active=row.is_active,
        channels=row.channels or ["teams", "phone"],
        created_at=row.created_at,
        yaml_content=row.yaml_content,
    )


@router.post("/{skill_pack_id}/deactivate", response_model=SkillPackSummary)
async def deactivate_skill_pack(
    skill_pack_id: str,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Deactivate a Skill Pack."""
    from sqlalchemy import update

    result = await db.execute(
        select(SkillPackModel).where(SkillPackModel.id == skill_pack_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Skill Pack not found")

    await db.execute(
        update(SkillPackModel)
        .where(SkillPackModel.id == skill_pack_id)
        .values(is_active=False)
    )
    await db.commit()
    await db.refresh(row)

    return SkillPackSummary(
        id=row.id,
        name=row.name,
        skill_id=row.skill_id,
        version=row.version,
        is_active=row.is_active,
        channels=row.channels or ["teams", "phone"],
        created_at=row.created_at,
        yaml_content=row.yaml_content,
    )


@router.delete("/{skill_pack_id}", status_code=204)
async def delete_skill_pack(
    skill_pack_id: str,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Delete a Skill Pack (cascade deletes versions)."""
    result = await db.execute(
        select(SkillPackModel).where(SkillPackModel.id == skill_pack_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Skill Pack not found")

    await db.delete(row)
    await db.commit()


@router.get("/{skill_pack_id}/versions", response_model=list[SkillPackVersionRecord])
async def list_skill_pack_versions(
    skill_pack_id: str,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Return all version records for a Skill Pack."""
    # Check the skill pack exists
    sp_result = await db.execute(
        select(SkillPackModel).where(SkillPackModel.id == skill_pack_id)
    )
    if sp_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Skill Pack not found")

    versions_result = await db.execute(
        select(SkillPackVersionModel)
        .where(SkillPackVersionModel.skill_pack_id == skill_pack_id)
        .order_by(desc(SkillPackVersionModel.version_number))
    )
    rows = versions_result.scalars().all()

    return [
        SkillPackVersionRecord(
            version_number=row.version_number,
            yaml_content=row.yaml_content,
            created_at=row.created_at,
            change_summary=row.change_summary,
        )
        for row in rows
    ]


@router.post("/{skill_pack_id}/clone", response_model=SkillPackSummary)
async def clone_skill_pack(
    skill_pack_id: str,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Clone an existing skill pack with a new ID and name."""
    result = await db.execute(
        select(SkillPackModel).where(SkillPackModel.id == skill_pack_id)
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404, detail="Skill Pack not found")
    
    # Parse the YAML to modify ID and name
    try:
        parsed = parse_skill_pack_yaml(source.yaml_content)
    except ParseError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"YAML parse error at line {exc.line}: {exc.message}",
        ) from exc
    
    # Generate new ID and name
    original_id = parsed.get("skill", {}).get("id", "")
    original_name = parsed.get("skill", {}).get("name", "")
    
    # Append -clone or increment version
    if "-clone" in original_id:
        base_id = original_id.rsplit("-clone", 1)[0]
        new_id = f"{base_id}-clone-2"
    elif original_id.endswith("-v1"):
        new_id = original_id.replace("-v1", "-clone-v1")
    else:
        new_id = f"{original_id}-clone"
    
    new_name = f"{original_name} (Clone)"
    
    # Update parsed content
    parsed["skill"]["id"] = new_id
    parsed["skill"]["name"] = new_name
    parsed["skill"]["version"] = "1.0.0"
    
    # Re-serialize to YAML
    import yaml
    new_yaml = yaml.dump(parsed, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    # Create new skill pack
    now = datetime.now(tz=timezone.utc)
    new_pack = SkillPackModel(
        id=str(uuid.uuid4()),
        skill_id=new_id,
        name=new_name,
        version="1.0.0",
        yaml_content=new_yaml,
        parsed_content=parsed,
        is_active=False,  # Cloned skills start as inactive
        created_at=now,
        updated_at=now,
    )
    
    db.add(new_pack)
    await db.commit()
    await db.refresh(new_pack)
    
    return SkillPackSummary(
        id=new_pack.id,
        name=new_pack.name,
        skill_id=new_pack.skill_id,
        version=new_pack.version,
        is_active=new_pack.is_active,
        channels=parsed.get("channels", []),
        created_at=new_pack.created_at,
        yaml_content=new_pack.yaml_content,
    )


@router.post("/generate", response_model=GenerateSkillPackResponse)
async def generate_skill_pack(
    request: GenerateSkillPackRequest,
    token: str = Depends(verify_token),
):
    """Generate a complete skill pack YAML using AI based on a single description."""
    import json
    import os
    
    prompt = f"""You are an expert instructional designer and AI conversation specialist. 
Create a complete Vero skill pack based on the following description:

DESCRIPTION: {request.description}

Based on this description, you must:
1. Determine the best mode (intelligent or guided)
2. Determine appropriate channels (teams, phone, or both)
3. Create an appropriate skill ID and name
4. Design the complete conversation flow

Generate a complete skill pack in YAML format following this exact structure:

```yaml
skill:
  id: <descriptive-kebab-case-id>
  name: <Human Readable Name>
  version: "1.0.0"
  description: <brief description of what this skill does>

channels:
  - teams
  - phone

activation:
  trigger: inbound

agent:
  name: <Agent Name>
  persona: |
    <2-3 sentences describing the agent's personality, tone, and approach>

<MODE_SECTION>
```

For MODE_SECTION:
- If INTELLIGENT mode (best for exploratory, coaching, or adaptive conversations):
  sections:
    - title: Objectives
      mode: intelligent
      objectives: |
        - <Objective 1>
        - <Objective 2>
        - <Objective 3>
        - <Objective 4>
        - <Objective 5>
      max_duration_seconds: 1800

- If GUIDED mode (best for structured interviews, assessments, or surveys):
  sections:
    - title: <Section Title>
      mode: guided
      questions:
        - id: q1
          text: "<Question text>"
          probes:
            - "<Follow-up probe 1>"
            - "<Follow-up probe 2>"
          competency: <snake_case_competency>
          max_follow_ups: 2
        - id: q2
          text: "<Question text>"
          probes:
            - "<Follow-up probe 1>"
            - "<Follow-up probe 2>"
          competency: <snake_case_competency>
          max_follow_ups: 2
      max_duration_seconds: 1800

rubric:
  - competency: <competency_1>
    scores:
      1: <Description of score 1>
      2: <Description of score 2>
      3: <Description of score 3>
      4: <Description of score 4>
      5: <Description of score 5>
  - competency: <competency_2>
    scores:
      1: <Description>
      2: <Description>
      3: <Description>
      4: <Description>
      5: <Description>

report:
  template: <choose from: scorecard, discovery-brief, audit-log, coaching-report>
  email_to: []
  include_transcript: true

Rules:
1. Choose intelligent mode for coaching, discovery, or adaptive conversations
2. Choose guided mode for structured interviews, assessments, or surveys
3. Include 3-5 competencies in the rubric
4. For guided mode, include 4-6 questions with 2-3 probes each
5. For intelligent mode, include 5-8 clear objectives
6. Set max_duration_seconds based on complexity (900-3600 seconds)
7. Choose the most appropriate report template for the skill type
8. Use proper YAML indentation (2 spaces)

Return ONLY the YAML content, no markdown code blocks, no explanations."""

    try:
        # Call Sarvam LLM via OpenAI-compatible API
        import httpx
        
        sarvam_key = os.environ.get("SARVAM_API_KEY", "")
        if not sarvam_key:
            raise HTTPException(
                status_code=500,
                detail="SARVAM_API_KEY not configured"
            )
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.sarvam.ai/v1/chat/completions",
                headers={
                    "api-subscription-key": sarvam_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sarvam-30b",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 4000,
                    "temperature": 0.7,
                }
            )
            
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=500,
                    detail=f"Sarvam API error: {response.status_code}"
                )
            
            data = response.json()
            ai_response = data["choices"][0]["message"]["content"]
        
        # Clean up response - remove markdown code blocks if present
        yaml_content = ai_response.strip()
        if yaml_content.startswith("```yaml"):
            yaml_content = yaml_content[7:]
        if yaml_content.startswith("```"):
            yaml_content = yaml_content[3:]
        if yaml_content.endswith("```"):
            yaml_content = yaml_content[:-3]
        yaml_content = yaml_content.strip()
        
        return GenerateSkillPackResponse(yaml_content=yaml_content)
            
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI generation failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )
