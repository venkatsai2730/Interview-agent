"""
Twilio MCP Server - Exposes Twilio functionality via Model Context Protocol.

This server provides tools for:
- Making outbound calls with recording enabled
- Checking call status
- Fetching recordings and transcripts
- Hanging up calls
- Sending SMS

Usage:
    python -m mcp.twilio_mcp_server
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(name)s: %(message)s"
)
logger = logging.getLogger("twilio_mcp")

# Twilio configuration
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")
TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


class TwilioClient:
    """Async Twilio client for MCP server."""

    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.base_url = f"{TWILIO_API_BASE}/Accounts/{account_sid}"

    async def make_call(
        self,
        to_number: str,
        twiml_url: str,
        record: bool = True,
        recording_status_callback: Optional[str] = None,
    ) -> dict:
        """Place an outbound call with optional recording."""
        url = f"{self.base_url}/Calls.json"
        
        data: dict[str, Any] = {
            "To": to_number,
            "From": self.from_number,
            "Url": twiml_url,
        }
        
        if record:
            data["Record"] = "true"
            if recording_status_callback:
                data["RecordingStatusCallback"] = recording_status_callback
                data["RecordingStatusCallbackEvent"] = "completed"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                data=data,
                auth=(self.account_sid, self.auth_token),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_call_status(self, call_sid: str) -> dict:
        """Get the current status of a call."""
        url = f"{self.base_url}/Calls/{call_sid}.json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, auth=(self.account_sid, self.auth_token))
            resp.raise_for_status()
            return resp.json()

    async def hangup_call(self, call_sid: str) -> dict:
        """End an active call."""
        url = f"{self.base_url}/Calls/{call_sid}.json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                data={"Status": "completed"},
                auth=(self.account_sid, self.auth_token),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_recordings(self, call_sid: Optional[str] = None) -> list[dict]:
        """Get recordings for an account or specific call."""
        if call_sid:
            url = f"{self.base_url}/Calls/{call_sid}/Recordings.json"
        else:
            url = f"{self.base_url}/Recordings.json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, auth=(self.account_sid, self.auth_token))
            resp.raise_for_status()
            data = resp.json()
            return data.get("recordings", [])

    async def get_recording(self, recording_sid: str) -> dict:
        """Get a specific recording's metadata."""
        url = f"{self.base_url}/Recordings/{recording_sid}.json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, auth=(self.account_sid, self.auth_token))
            resp.raise_for_status()
            return resp.json()

    async def get_recording_media(self, recording_sid: str) -> bytes:
        """Get the actual audio data for a recording."""
        url = f"{self.base_url}/Recordings/{recording_sid}.wav"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, auth=(self.account_sid, self.auth_token))
            resp.raise_for_status()
            return resp.content

    async def get_transcriptions(self, recording_sid: Optional[str] = None) -> list[dict]:
        """Get transcriptions for recordings."""
        if recording_sid:
            url = f"{self.base_url}/Recordings/{recording_sid}/Transcriptions.json"
        else:
            url = f"{self.base_url}/Transcriptions.json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, auth=(self.account_sid, self.auth_token))
            resp.raise_for_status()
            data = resp.json()
            return data.get("transcriptions", [])

    async def send_sms(self, to_number: str, message: str) -> dict:
        """Send an SMS message."""
        url = f"{self.base_url}/Messages.json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                data={
                    "To": to_number,
                    "From": self.from_number,
                    "Body": message,
                },
                auth=(self.account_sid, self.auth_token),
            )
            resp.raise_for_status()
            return resp.json()


# Tool definitions for MCP
TOOLS = {
    "make_call": {
        "description": "Place an outbound phone call with optional recording",
        "parameters": {
            "to_number": {"type": "string", "description": "E.164 phone number to call (e.g., +1234567890)"},
            "twiml_url": {"type": "string", "description": "URL that returns TwiML instructions for the call"},
            "record": {"type": "boolean", "description": "Whether to record the call", "default": True},
            "recording_status_callback": {"type": "string", "description": "Webhook URL for recording status updates", "optional": True},
        },
    },
    "get_call_status": {
        "description": "Get the current status of a call",
        "parameters": {
            "call_sid": {"type": "string", "description": "The Twilio Call SID"},
        },
    },
    "hangup_call": {
        "description": "End an active call",
        "parameters": {
            "call_sid": {"type": "string", "description": "The Twilio Call SID to hang up"},
        },
    },
    "get_recordings": {
        "description": "Get recordings for a call or account",
        "parameters": {
            "call_sid": {"type": "string", "description": "Optional Call SID to filter recordings", "optional": True},
        },
    },
    "get_recording": {
        "description": "Get metadata for a specific recording",
        "parameters": {
            "recording_sid": {"type": "string", "description": "The Recording SID"},
        },
    },
    "get_recording_media": {
        "description": "Get the audio data for a recording",
        "parameters": {
            "recording_sid": {"type": "string", "description": "The Recording SID"},
        },
    },
    "get_transcriptions": {
        "description": "Get transcriptions for recordings",
        "parameters": {
            "recording_sid": {"type": "string", "description": "Optional Recording SID to filter", "optional": True},
        },
    },
    "send_sms": {
        "description": "Send an SMS message",
        "parameters": {
            "to_number": {"type": "string", "description": "E.164 phone number to send to"},
            "message": {"type": "string", "description": "The message body"},
        },
    },
}


class MCPServer:
    """Simple MCP server over stdio."""

    def __init__(self):
        self.client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)

    async def handle_request(self, request: dict) -> dict:
        """Handle an MCP request."""
        method = request.get("method")
        params = request.get("params", {})

        if method == "tools/list":
            return {
                "tools": [
                    {"name": name, "description": info["description"], "parameters": info["parameters"]}
                    for name, info in TOOLS.items()
                ]
            }

        if method == "tools/call":
            tool_name = params.get("name")
            tool_params = params.get("parameters", {})
            return await self.call_tool(tool_name, tool_params)

        if method == "resources/list":
            return {"resources": []}

        return {"error": f"Unknown method: {method}"}

    async def call_tool(self, name: str, params: dict) -> dict:
        """Execute a tool call."""
        try:
            if name == "make_call":
                result = await self.client.make_call(
                    to_number=params["to_number"],
                    twiml_url=params["twiml_url"],
                    record=params.get("record", True),
                    recording_status_callback=params.get("recording_status_callback"),
                )
                logger.info("make_call: Twilio API returned: %s", result)
                response_text = json.dumps(result, indent=2)
                logger.debug("make_call: returning content text: %s", response_text[:500])
                return {"content": [{"type": "text", "text": response_text}]}

            elif name == "get_call_status":
                result = await self.client.get_call_status(params["call_sid"])
                return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

            elif name == "hangup_call":
                result = await self.client.hangup_call(params["call_sid"])
                return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

            elif name == "get_recordings":
                result = await self.client.get_recordings(params.get("call_sid"))
                return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

            elif name == "get_recording":
                result = await self.client.get_recording(params["recording_sid"])
                return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

            elif name == "get_recording_media":
                # Return base64-encoded audio
                audio_data = await self.client.get_recording_media(params["recording_sid"])
                import base64
                encoded = base64.b64encode(audio_data).decode()
                return {
                    "content": [
                        {"type": "text", "text": f"Audio data (base64, {len(audio_data)} bytes):"},
                        {"type": "text", "text": encoded[:200] + "..." if len(encoded) > 200 else encoded},
                    ]
                }

            elif name == "get_transcriptions":
                result = await self.client.get_transcriptions(params.get("recording_sid"))
                return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

            elif name == "send_sms":
                result = await self.client.send_sms(params["to_number"], params["message"])
                return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

            else:
                return {"error": f"Unknown tool: {name}"}

        except httpx.HTTPStatusError as e:
            return {"error": f"Twilio API error: {e.response.status_code} - {e.response.text}"}
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}

    async def run(self):
        """Run the MCP server over stdio."""
        logger.info("Twilio MCP server starting...")
        
        # Validate configuration
        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
            logger.error("Missing Twilio configuration. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER")
            return

        # Send initialization message
        init_response = {
            "jsonrpc": "2.0",
            "id": 0,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                },
                "serverInfo": {
                    "name": "twilio-mcp",
                    "version": "1.0.0",
                },
            },
        }
        print(json.dumps(init_response), flush=True)
        logger.info("Twilio MCP server initialized")

        # Process incoming requests from stdin
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                if not line:
                    # EOF - stdin closed
                    logger.info("stdin closed, shutting down")
                    break

                line = line.strip()
                if not line:
                    continue

                request = json.loads(line)
                handler_response = await self.handle_request(request)
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": handler_response,
                }
                print(json.dumps(response), flush=True)

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
            except EOFError:
                logger.info("EOF received, shutting down")
                break
            except Exception as e:
                logger.error(f"Error processing request: {e}")


if __name__ == "__main__":
    server = MCPServer()
    asyncio.run(server.run())
