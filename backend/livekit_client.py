"""LiveKit client — create rooms, dispatch agent, and place calls.

Outbound call strategy (hybrid):
  1. Create LiveKit room + dispatch vero-agent
  2. Create a per-session SIP dispatch rule: inbound call → this room
  3. Twilio REST API dials the candidate
  4. Candidate answers → Twilio bridges to LiveKit SIP URI
  5. LiveKit dispatch rule routes to the session room → agent picks up
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _lk_api():
    from livekit import api
    return api.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )


# Singleton instance for health checks
livekit_api = _lk_api()


async def create_room_and_dispatch(session_id: str, skill_pack: dict) -> str:
    """Create a LiveKit room and dispatch the vero-agent worker."""
    import json
    from livekit import api
    from livekit.api import CreateAgentDispatchRequest

    lk = _lk_api()
    await lk.room.create_room(api.CreateRoomRequest(name=session_id))
    await lk.agent_dispatch.create_dispatch(
        CreateAgentDispatchRequest(
            agent_name="vero-agent",
            room=session_id,
            metadata=json.dumps({"skill_pack": skill_pack}),
        )
    )
    logger.info("livekit: room+agent ready session=%s", session_id)
    await lk.aclose()
    return session_id


async def create_sip_outbound_call(
    session_id: str,
    phone_number: str,
    skill_pack: dict,
    sip_trunk_id: str,
    voice: str = "shubh",
    llm_model: str = "sarvam-30b",
    language: str = "en-IN",
    agent_name: str | None = None,
    db = None,
) -> str:
    """Place an outbound call: Twilio dials candidate → bridges to LiveKit.

    Returns the Twilio call SID.
    """
    import json
    import httpx
    from livekit import api
    from livekit.api import sip_service
    from livekit.api import CreateAgentDispatchRequest
    from livekit.protocol import sip as sip_proto

    lk = _lk_api()

    # 1. Create room
    await lk.room.create_room(api.CreateRoomRequest(name=session_id))

    # 2. Dispatch agent into the room
    # Inject channel into skill_pack so the agent knows how to close the session
    skill_pack_with_channel = {**skill_pack, "channel": "phone"}
    await lk.agent_dispatch.create_dispatch(
        CreateAgentDispatchRequest(
            agent_name="vero-agent",
            room=session_id,
            metadata=json.dumps({
                "skill_pack": skill_pack_with_channel,
                "voice": voice,
                "llm_model": llm_model,
                "language": language,
                "channel": "phone",  # This is a phone call session
                **({"agent_name": agent_name} if agent_name else {}),
            }),
        )
    )

    # 3. Clean up any stale dispatch rules for this trunk, then create a fresh one
    inbound_trunk_id = os.environ.get("LIVEKIT_SIP_INBOUND_TRUNK_ID", sip_trunk_id)

    # Delete any existing rules on this trunk to avoid conflicts
    existing = await lk.sip.list_sip_dispatch_rule(
        sip_service.proto_sip.ListSIPDispatchRuleRequest()
    )
    for rule in existing.items:
        if inbound_trunk_id in list(rule.trunk_ids):
            try:
                await lk.sip.delete_sip_dispatch_rule(
                    sip_service.proto_sip.DeleteSIPDispatchRuleRequest(
                        sip_dispatch_rule_id=rule.sip_dispatch_rule_id
                    )
                )
                logger.info("livekit: deleted stale dispatch rule %s", rule.sip_dispatch_rule_id)
            except Exception as e:
                logger.warning("livekit: could not delete rule %s: %s", rule.sip_dispatch_rule_id, e)

    dispatch_rule = await lk.sip.create_sip_dispatch_rule(
        sip_service.proto_sip.CreateSIPDispatchRuleRequest(
            name=f"vero-{session_id}",
            trunk_ids=[inbound_trunk_id],
            rule=sip_proto.SIPDispatchRule(
                dispatch_rule_direct=sip_proto.SIPDispatchRuleDirect(
                    room_name=session_id,
                )
            ),
        )
    )
    logger.info("livekit: dispatch rule created id=%s for session=%s",
                dispatch_rule.sip_dispatch_rule_id, session_id)

    await lk.aclose()

    # 4. Use Twilio MCP client to dial the candidate with recording enabled
    from backend.mcp.twilio_client import get_twilio_mcp_client
    
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    twiml_url = f"{webhook_url}/twilio/livekit-bridge?session_id={session_id}"
    recording_callback = f"{webhook_url}/twilio/recording-callback"
    
    client = get_twilio_mcp_client()
    call_sid = await client.create_call(
        to_number=phone_number,
        twiml_url=twiml_url,
        record=True,
        recording_status_callback=recording_callback,
    )
    
    # Store the call_sid in the session if db is provided
    if db is not None:
        from backend.models import Session as SessionModel
        from sqlalchemy import update
        await db.execute(
            update(SessionModel)
            .where(SessionModel.session_id == session_id)
            .values(twilio_call_sid=call_sid)
        )
        await db.commit()
    
    logger.info("livekit: Twilio call placed sid=%s to=%s (recording enabled)", call_sid, phone_number)
    return call_sid
