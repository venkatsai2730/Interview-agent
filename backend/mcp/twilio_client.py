"""
Twilio MCP Client - Wrapper around the Twilio MCP server.

This client connects to the Twilio MCP server and provides a simple
async interface for making calls, checking status, and retrieving recordings.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class TwilioMCPClient:
    """Client for the Twilio MCP server.

    This client can either:
    1. Spawn the MCP server as a subprocess and communicate over stdio (MCP mode)
    2. Use direct Twilio API calls (direct API mode)

    Note: MCP and direct API paths are mutually exclusive; there is no automatic
    fallback between them in a single operation.
    """

    def __init__(self, use_direct_api: bool = False):
        """Initialize the client.

        Args:
            use_direct_api: If True, use direct Twilio API instead of MCP server
        """
        self.use_direct_api = use_direct_api
        self._account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        self._auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        self._from_number = os.environ.get("TWILIO_PHONE_NUMBER", "")
        self._process: Optional[subprocess.Process] = None
        self._stdin: Optional[asyncio.StreamWriter] = None
        self._stdout: Optional[asyncio.StreamReader] = None
        self._lock = asyncio.Lock()
        self._request_id = 0
        self._initialized = False

    async def _ensure_configured(self) -> None:
        """Ensure Twilio credentials are configured."""
        if not all([self._account_sid, self._auth_token, self._from_number]):
            raise RuntimeError(
                "Missing Twilio configuration: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER"
            )

    async def _ensure_mcp_server(self) -> None:
        """Spawn and initialize the MCP server if not already running."""
        if self.use_direct_api:
            return

        async with self._lock:
            # Check if process is still alive
            if self._initialized and self._process and self._process.returncode is None:
                return

            # Need to spawn or respawn the server
            if self._process:
                logger.warning("MCP server process died (returncode=%s), respawning", self._process.returncode)
                self._initialized = False

            # Spawn the MCP server as a subprocess
            import sys
            mcp_server_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "mcp", "twilio_mcp_server.py"
            )

            # Pass through Twilio env vars to the subprocess
            env = os.environ.copy()

            self._process = await asyncio.create_subprocess_exec(
                sys.executable,
                mcp_server_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self._stdin = self._process.stdin
            self._stdout = self._process.stdout

            # Start draining stderr in background to prevent blocking
            asyncio.create_task(self._drain_stderr())

            # Read initialization response
            try:
                line = await asyncio.wait_for(self._stdout.readline(), timeout=5.0)
                if line:
                    init_response = json.loads(line.decode())
                    logger.info("MCP server initialized: %s", init_response.get("result", {}).get("serverInfo", {}).get("name"))
            except asyncio.TimeoutError:
                logger.error("MCP server initialization timeout")
                raise RuntimeError("MCP server failed to initialize")

            self._initialized = True
            logger.info("Twilio MCP server spawned (pid=%d)", self._process.pid)

    async def _drain_stderr(self) -> None:
        """Drain stderr to prevent the subprocess from blocking."""
        if not self._process or not self._process.stderr:
            return
        while True:
            try:
                line = await self._process.stderr.readline()
                if not line:
                    break
                logger.debug("MCP server stderr: %s", line.decode().rstrip())
            except Exception:
                break

    async def _mcp_call(self, tool_name: str, parameters: dict) -> dict:
        """Make an MCP tool call.

        Args:
            tool_name: Name of the tool to call
            parameters: Tool parameters

        Returns:
            Parsed response content
        """
        await self._ensure_mcp_server()

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "parameters": parameters,
            },
        }

        # Send request
        request_line = json.dumps(request) + "\n"
        logger.debug("MCP request: %s", request_line.strip())
        self._stdin.write(request_line.encode())
        await self._stdin.drain()

        # Read response, skipping any non-JSON lines (e.g., log output that leaked to stdout)
        max_retries = 5
        for _ in range(max_retries):
            line = await self._stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed stdout unexpectedly")
            response_str = line.decode().strip()
            if response_str.startswith('{'):
                break
            logger.warning("twilio_mcp: skipping non-JSON line from MCP stdout: %s", response_str[:200])
        else:
            raise RuntimeError("MCP server sent too many non-JSON lines")

        logger.debug("MCP response: %s", response_str)
        response = json.loads(response_str)

        # Log raw response for debugging
        logger.debug("twilio_mcp: raw MCP response: %s", json.dumps(response)[:500])

        # Check for error at top-level (JSON-RPC protocol errors)
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")

        # Check for error at result level (tool execution errors)
        result = response.get("result", {})
        if isinstance(result, dict) and "error" in result:
            raise RuntimeError(f"MCP error: {result['error']}")

        # Extract content from response
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            result_text = content[0]["text"]
            logger.debug("MCP result text: %s", result_text[:200])
            result_dict = json.loads(result_text)
            logger.debug("twilio_mcp: _mcp_call parsed result: %s", result_dict)
            # Check if the parsed result is an error response from the tool
            if isinstance(result_dict, dict) and "error" in result_dict:
                raise RuntimeError(f"MCP error: {result_dict['error']}")
            return result_dict

        logger.warning("twilio_mcp: _mcp_call returning raw result (no content): %s", result)
        return result

    async def create_call(
        self,
        to_number: str,
        twiml_url: str,
        record: bool = True,
        recording_status_callback: Optional[str] = None,
    ) -> str:
        """Place an outbound call via Twilio.

        Args:
            to_number: E.164 phone number to dial
            twiml_url: URL that returns TwiML instructions
            record: Whether to record the call
            recording_status_callback: Webhook URL for recording status

        Returns:
            Twilio Call SID

        Raises:
            Exception: If the call creation fails. Note that if MCP mode fails,
                the call may or may not have been created on Twilio's side.
        """
        # Paths are mutually exclusive to prevent duplicate calls.
        # If MCP is enabled, use MCP only. If it fails, re-raise (don't fallback).
        # If direct API is enabled, use direct API only.
        if not self.use_direct_api:
            # MCP path - no fallback to prevent duplicate calls
            logger.info("twilio_mcp: using MCP path for create_call to=%s", to_number)
            await self._ensure_configured()
            await self._ensure_mcp_server()
            try:
                result = await self._mcp_call("make_call", {
                    "to_number": to_number,
                    "twiml_url": twiml_url,
                    "record": record,
                    "recording_status_callback": recording_status_callback,
                })
                logger.info("twilio_mcp: create_call MCP result: %s", result)
                # Defensive check for 'sid' key
                if not isinstance(result, dict) or "sid" not in result:
                    raise RuntimeError(f"Invalid MCP response: missing 'sid' key. Got: {result}")
                call_sid = result["sid"]
                logger.info("twilio_mcp: call created via MCP sid=%s to=%s", call_sid, to_number)
                return call_sid
            except Exception as exc:
                # Do NOT fall through to direct API - the call may have been created.
                # Re-raise so caller knows the operation status is uncertain.
                logger.error(
                    "twilio_mcp: MCP create_call failed (call may or may not exist): %s",
                    exc,
                )
                raise

        # Direct API path - only used when use_direct_api=True
        logger.info("twilio_mcp: using direct API path for create_call to=%s", to_number)
        await self._ensure_configured()

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Calls.json"

        data: dict[str, str] = {
            "To": to_number,
            "From": self._from_number,
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
                auth=(self._account_sid, self._auth_token),
            )
            resp.raise_for_status()
            result = resp.json()
            call_sid = result["sid"]
            logger.info("twilio_mcp: call created via direct API sid=%s to=%s", call_sid, to_number)
            return call_sid

    async def get_call_status(self, call_sid: str) -> dict:
        """Get the current status of a call.
        
        Args:
            call_sid: The Twilio Call SID
            
        Returns:
            Call status information
        """
        await self._ensure_configured()
        
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Calls/{call_sid}.json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, auth=(self._account_sid, self._auth_token))
            resp.raise_for_status()
            return resp.json()

    async def hangup_call(self, call_sid: str) -> dict:
        """End an active call.

        Args:
            call_sid: The Twilio Call SID to hang up

        Returns:
            Updated call information

        Raises:
            Exception: If the hangup fails. Note that if MCP mode fails,
                the call may or may not have been hung up on Twilio's side.
        """
        # Paths are mutually exclusive to prevent duplicate hangup attempts.
        # Hangup is idempotent, but we maintain consistency with create_call.
        if not self.use_direct_api:
            # MCP path - no fallback
            logger.info("twilio_mcp: using MCP path for hangup_call sid=%s", call_sid)
            await self._ensure_configured()
            await self._ensure_mcp_server()
            try:
                result = await self._mcp_call("hangup_call", {"call_sid": call_sid})
                logger.info("twilio_mcp: call hung up via MCP sid=%s", call_sid)
                return result
            except Exception as exc:
                # Do NOT fall through to direct API - maintain consistent behavior.
                logger.error(
                    "twilio_mcp: MCP hangup_call failed (call may or may not be hung up): %s",
                    exc,
                )
                raise

        # Direct API path - only used when use_direct_api=True
        logger.info("twilio_mcp: using direct API path for hangup_call sid=%s", call_sid)
        await self._ensure_configured()

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Calls/{call_sid}.json"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                data={"Status": "completed"},
                auth=(self._account_sid, self._auth_token),
            )
            resp.raise_for_status()
            logger.info("twilio_mcp: call hung up via direct API sid=%s", call_sid)
            return resp.json()

    async def get_recordings(self, call_sid: Optional[str] = None) -> list[dict]:
        """Get recordings for a call or account.
        
        Args:
            call_sid: Optional Call SID to filter recordings
            
        Returns:
            List of recording metadata
        """
        await self._ensure_configured()
        
        if call_sid:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Calls/{call_sid}/Recordings.json"
        else:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Recordings.json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, auth=(self._account_sid, self._auth_token))
            resp.raise_for_status()
            data = resp.json()
            return data.get("recordings", [])

    async def get_recording(self, recording_sid: str) -> dict:
        """Get metadata for a specific recording.
        
        Args:
            recording_sid: The Recording SID
            
        Returns:
            Recording metadata
        """
        await self._ensure_configured()
        
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Recordings/{recording_sid}.json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, auth=(self._account_sid, self._auth_token))
            resp.raise_for_status()
            return resp.json()

    async def get_recording_media_url(self, recording_sid: str) -> str:
        """Get the URL for downloading a recording.
        
        Args:
            recording_sid: The Recording SID
            
        Returns:
            URL to download the recording audio
        """
        await self._ensure_configured()
        return f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Recordings/{recording_sid}.wav"

    async def get_transcriptions(self, recording_sid: Optional[str] = None) -> list[dict]:
        """Get transcriptions for recordings.
        
        Note: Twilio's transcription service may not be available in all regions.
        
        Args:
            recording_sid: Optional Recording SID to filter
            
        Returns:
            List of transcription metadata
        """
        await self._ensure_configured()
        
        if recording_sid:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Recordings/{recording_sid}/Transcriptions.json"
        else:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Transcriptions.json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, auth=(self._account_sid, self._auth_token))
            resp.raise_for_status()
            data = resp.json()
            return data.get("transcriptions", [])

    async def send_sms(self, to_number: str, message: str) -> dict:
        """Send an SMS message.
        
        Args:
            to_number: E.164 phone number to send to
            message: The message body
            
        Returns:
            Message metadata
        """
        await self._ensure_configured()
        
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                data={
                    "To": to_number,
                    "From": self._from_number,
                    "Body": message,
                },
                auth=(self._account_sid, self._auth_token),
            )
            resp.raise_for_status()
            return resp.json()


# Global client instance
twilio_mcp_client: Optional[TwilioMCPClient] = None


def get_twilio_mcp_client() -> TwilioMCPClient:
    """Get or create the global Twilio MCP client.

    Uses MCP server by default (TWILIO_MCP_ENABLED=true or unset).
    Set TWILIO_MCP_ENABLED=false to use direct Twilio REST API instead.
    """
    global twilio_mcp_client
    if twilio_mcp_client is None:
        # Default to MCP server; allow fallback to direct API via env var
        use_direct_api = os.environ.get("TWILIO_MCP_ENABLED", "true").lower() == "false"
        twilio_mcp_client = TwilioMCPClient(use_direct_api=use_direct_api)
    return twilio_mcp_client
