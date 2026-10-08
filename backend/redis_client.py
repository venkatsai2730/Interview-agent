"""Redis client for distributed pipeline registry.

This module provides Redis connectivity for multi-instance deployments,
replacing the in-memory _active_pipelines dict.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Global Redis client instance
_redis_client: Optional[redis.Redis] = None

# Key prefix for pipeline registry entries
PIPELINE_KEY_PREFIX = "vero:pipeline:"


def get_redis_url() -> str:
    """Get Redis URL from environment or default."""
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


async def get_redis_client() -> Optional[redis.Redis]:
    """Get or create the Redis client instance.

    Returns:
        Redis client if REDIS_URL is configured, None otherwise.
    """
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    redis_url = get_redis_url()
    if not redis_url or redis_url == "redis://localhost:6379/0":
        # Check if we're in Docker - if so, try the service name
        if os.path.exists("/.dockerenv"):
            redis_url = "redis://redis:6379/0"

    try:
        _redis_client = redis.from_url(redis_url, decode_responses=True)
        # Test connection
        await _redis_client.ping()
        logger.info("Redis client connected to %s", redis_url)
        return _redis_client
    except Exception as exc:
        logger.warning("Failed to connect to Redis at %s: %s", redis_url, exc)
        return None


async def close_redis_client() -> None:
    """Close the Redis client connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis client closed")


def _pipeline_key(session_id: str) -> str:
    """Generate Redis key for a pipeline entry."""
    return f"{PIPELINE_KEY_PREFIX}{session_id}"


async def register_pipeline_redis(
    session_id: str,
    pipeline_info: dict,
    ttl_seconds: int = 3600,
) -> bool:
    """Register a pipeline in Redis.

    Args:
        session_id: The session identifier.
        pipeline_info: Dict with pipeline metadata (host, pid, started_at, etc.)
        ttl_seconds: Time-to-live in seconds (default: 1 hour).
                     Should be based on skill_pack max_duration_minutes.

    Returns:
        True if registered successfully, False otherwise.
    """
    client = await get_redis_client()
    if client is None:
        return False

    try:
        key = _pipeline_key(session_id)
        await client.setex(key, ttl_seconds, json.dumps(pipeline_info))
        logger.info(
            "register_pipeline_redis[%s]: registered with TTL=%ds",
            session_id,
            ttl_seconds,
        )
        return True
    except Exception as exc:
        logger.error("register_pipeline_redis[%s]: failed: %s", session_id, exc)
        return False


async def get_pipeline_redis(session_id: str) -> Optional[dict]:
    """Get pipeline info from Redis.

    Args:
        session_id: The session identifier.

    Returns:
        Pipeline info dict if found, None otherwise.
    """
    client = await get_redis_client()
    if client is None:
        return None

    try:
        key = _pipeline_key(session_id)
        data = await client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as exc:
        logger.error("get_pipeline_redis[%s]: failed: %s", session_id, exc)
        return None


async def unregister_pipeline_redis(session_id: str) -> bool:
    """Unregister a pipeline from Redis.

    Args:
        session_id: The session identifier.

    Returns:
        True if unregistered successfully, False otherwise.
    """
    client = await get_redis_client()
    if client is None:
        return False

    try:
        key = _pipeline_key(session_id)
        await client.delete(key)
        logger.info("unregister_pipeline_redis[%s]: unregistered", session_id)
        return True
    except Exception as exc:
        logger.error("unregister_pipeline_redis[%s]: failed: %s", session_id, exc)
        return False


async def list_active_pipelines_redis() -> list[dict]:
    """List all active pipelines from Redis.

    Returns:
        List of pipeline info dicts with session_id.
    """
    client = await get_redis_client()
    if client is None:
        return []

    try:
        keys = await client.keys(f"{PIPELINE_KEY_PREFIX}*")
        if not keys:
            return []

        pipelines = []
        for key in keys:
            data = await client.get(key)
            if data:
                info = json.loads(data)
                # Extract session_id from key
                session_id = key.replace(PIPELINE_KEY_PREFIX, "")
                info["session_id"] = session_id
                pipelines.append(info)
        return pipelines
    except Exception as exc:
        logger.error("list_active_pipelines_redis: failed: %s", exc)
        return []


# Key prefix for session summary entries
SUMMARY_KEY_PREFIX = "vero:summary:"


def _summary_key(session_id: str) -> str:
    """Generate Redis key for a session summary entry."""
    return f"{SUMMARY_KEY_PREFIX}{session_id}"


async def store_session_summary_redis(
    session_id: str,
    summary: dict,
    ttl_seconds: int = 7200,
) -> bool:
    """Store a session summary in Redis.

    Args:
        session_id: The session identifier.
        summary: Dict with session summary (scores, transcript, etc.)
        ttl_seconds: Time-to-live in seconds (default: 2 hours).

    Returns:
        True if stored successfully, False otherwise.
    """
    client = await get_redis_client()
    if client is None:
        return False

    try:
        key = _summary_key(session_id)
        await client.setex(key, ttl_seconds, json.dumps(summary))
        logger.info("store_session_summary_redis[%s]: stored with TTL=%ds", session_id, ttl_seconds)
        return True
    except Exception as exc:
        logger.error("store_session_summary_redis[%s]: failed: %s", session_id, exc)
        return False


async def get_session_summary_redis(session_id: str) -> Optional[dict]:
    """Get session summary from Redis.

    Args:
        session_id: The session identifier.

    Returns:
        Summary dict if found, None otherwise.
    """
    client = await get_redis_client()
    if client is None:
        return None

    try:
        key = _summary_key(session_id)
        data = await client.get(key)
        if data:
            # Delete after reading (one-time use)
            await client.delete(key)
            return json.loads(data)
        return None
    except Exception as exc:
        logger.error("get_session_summary_redis[%s]: failed: %s", session_id, exc)
        return None


async def update_pipeline_ttl_redis(session_id: str, ttl_seconds: int = 3600) -> bool:
    """Update the TTL for a pipeline entry.

    Args:
        session_id: The session identifier.
        ttl_seconds: New TTL in seconds.

    Returns:
        True if updated successfully, False otherwise.
    """
    client = await get_redis_client()
    if client is None:
        return False

    try:
        key = _pipeline_key(session_id)
        await client.expire(key, ttl_seconds)
        return True
    except Exception as exc:
        logger.error("update_pipeline_ttl_redis[%s]: failed: %s", session_id, exc)
        return False
