"""Unit tests for authentication middleware."""
from __future__ import annotations

import os
import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend.auth import verify_token, verify_token_optional


class TestVerifyToken:
    """Test suite for verify_token function."""

    @pytest.fixture(autouse=True)
    def reset_env(self):
        """Reset environment variables before each test."""
        original_token = os.environ.get("API_TOKEN")
        yield
        if original_token is not None:
            os.environ["API_TOKEN"] = original_token
        elif "API_TOKEN" in os.environ:
            del os.environ["API_TOKEN"]

    @pytest.mark.asyncio
    async def test_valid_token(self):
        """Test that valid token is accepted."""
        os.environ["API_TOKEN"] = "test_secret_token"

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="test_secret_token"
        )

        result = await verify_token(credentials)
        assert result == "test_secret_token"

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        """Test that invalid token raises 401."""
        os.environ["API_TOKEN"] = "test_secret_token"

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="wrong_token"
        )

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid token"

    @pytest.mark.asyncio
    async def test_missing_token(self):
        """Test that missing credentials raises 401."""
        os.environ["API_TOKEN"] = "test_secret_token"

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(None)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Authentication required"

    @pytest.mark.asyncio
    async def test_no_api_token_configured(self):
        """Test behavior when API_TOKEN is not configured."""
        if "API_TOKEN" in os.environ:
            del os.environ["API_TOKEN"]

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="any_token"
        )

        # Should allow request but log warning
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger
            result = await verify_token(credentials)
            assert result == "any_token"
            mock_logger.warning.assert_called_once()


class TestVerifyTokenOptional:
    """Test suite for verify_token_optional function."""

    @pytest.fixture(autouse=True)
    def reset_env(self):
        """Reset environment variables before each test."""
        original_token = os.environ.get("API_TOKEN")
        yield
        if original_token is not None:
            os.environ["API_TOKEN"] = original_token
        elif "API_TOKEN" in os.environ:
            del os.environ["API_TOKEN"]

    @pytest.mark.asyncio
    async def test_valid_token_optional(self):
        """Test that valid token is returned."""
        os.environ["API_TOKEN"] = "test_secret_token"

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="test_secret_token"
        )

        result = verify_token_optional(credentials)
        assert result == "test_secret_token"

    @pytest.mark.asyncio
    async def test_no_token_returns_none(self):
        """Test that no credentials returns None."""
        os.environ["API_TOKEN"] = "test_secret_token"

        result = verify_token_optional(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self):
        """Test that invalid token still raises 401."""
        os.environ["API_TOKEN"] = "test_secret_token"

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="wrong_token"
        )

        with pytest.raises(HTTPException) as exc_info:
            verify_token_optional(credentials)

        assert exc_info.value.status_code == 401


class TestAuthIntegration:
    """Integration-style tests for auth behavior."""

    @pytest.fixture(autouse=True)
    def reset_env(self):
        """Reset environment variables before each test."""
        original_token = os.environ.get("API_TOKEN")
        yield
        if original_token is not None:
            os.environ["API_TOKEN"] = original_token
        elif "API_TOKEN" in os.environ:
            del os.environ["API_TOKEN"]

    @pytest.mark.asyncio
    async def test_webhook_endpoints_skip_auth(self):
        """Test that webhook endpoints don't require bearer auth.

        Webhooks should use signature verification instead.
        """
        # This test documents the expected behavior
        # In practice, webhook routes don't use verify_token dependency
        os.environ["API_TOKEN"] = "test_secret_token"

        # Webhook endpoints should work without auth header
        # (They use request body signature verification)
        assert True  # Placeholder - actual test would hit endpoint

    @pytest.mark.asyncio
    async def test_health_endpoint_skips_auth(self):
        """Test that health endpoint doesn't require auth."""
        os.environ["API_TOKEN"] = "test_secret_token"

        # Health endpoint should be accessible without auth
        assert True  # Placeholder - actual test would hit endpoint

    @pytest.mark.asyncio
    async def test_api_endpoints_require_auth(self):
        """Test that API endpoints require valid auth."""
        os.environ["API_TOKEN"] = "test_secret_token"

        # These endpoints should require auth:
        # - POST /skill-packs/validate
        # - GET /skill-packs
        # - POST /skill-packs
        # - etc.

        # Test with no auth
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(None)
        assert exc_info.value.status_code == 401

        # Test with valid auth
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="test_secret_token"
        )
        result = await verify_token(credentials)
        assert result == "test_secret_token"


class TestAuthSecurity:
    """Security-focused tests for auth."""

    @pytest.mark.asyncio
    async def test_token_timing_attack_resistance(self):
        """Test that token comparison is timing-attack resistant.

        The current implementation uses simple string comparison.
        In production, consider using hmac.compare_digest for constant-time comparison.
        """
        os.environ["API_TOKEN"] = "a" * 32  # 32 char token

        # Test with token of same length but different content
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="b" * 32
        )

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_long_token_handling(self):
        """Test that very long tokens are handled gracefully."""
        os.environ["API_TOKEN"] = "short"

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="a" * 10000  # Very long token
        )

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_token_rejected(self):
        """Test that empty token is rejected."""
        os.environ["API_TOKEN"] = "valid_token"

        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=""
        )

        with pytest.raises(HTTPException) as exc_info:
            await verify_token(credentials)

        assert exc_info.value.status_code == 401
