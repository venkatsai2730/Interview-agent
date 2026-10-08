"""Authentication utilities for FastAPI endpoints."""
from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import Security, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)


def _constant_time_compare(provided: str, expected: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks.

    Uses hmac.compare_digest for timing-attack-resistant comparison.
    """
    # Encode both strings to bytes for comparison
    provided_bytes = provided.encode("utf-8")
    expected_bytes = expected.encode("utf-8")
    return hmac.compare_digest(provided_bytes, expected_bytes)


async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> str:
    """Verify bearer token for protected endpoints.

    Uses constant-time comparison to prevent timing attacks.

    Args:
        credentials: The Authorization header credentials.

    Returns:
        The validated token string.

    Raises:
        HTTPException: 401 if token is missing or invalid.
    """
    # Allow missing token for webhook endpoints (they use signature verification)
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    expected_token = os.environ.get("API_TOKEN")
    if not expected_token:
        # If no API_TOKEN is configured, allow all requests (dev mode warning)
        import logging

        logger = logging.getLogger(__name__)
        logger.warning("API_TOKEN not configured - authentication disabled")
        return credentials.credentials

    # Constant-time comparison to prevent timing attacks
    if not _constant_time_compare(credentials.credentials, expected_token):
        raise HTTPException(status_code=401, detail="Invalid token")

    return credentials.credentials


def verify_token_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> Optional[str]:
    """Optionally verify bearer token - returns None if not provided.

    Uses constant-time comparison to prevent timing attacks.
    """
    if credentials is None:
        return None

    expected_token = os.environ.get("API_TOKEN")
    if not expected_token:
        return credentials.credentials

    # Constant-time comparison to prevent timing attacks
    if not _constant_time_compare(credentials.credentials, expected_token):
        raise HTTPException(status_code=401, detail="Invalid token")

    return credentials.credentials
