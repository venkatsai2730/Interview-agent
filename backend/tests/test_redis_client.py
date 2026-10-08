"""Unit tests for Redis client."""
from __future__ import annotations

import json
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock


class TestRedisURL:
    """Test suite for Redis URL configuration."""

    def test_get_redis_url_from_env(self):
        """Test that REDIS_URL is read from environment."""
        with patch.dict('os.environ', {'REDIS_URL': 'redis://custom:6379/1'}):
            from backend.redis_client import get_redis_url
            url = get_redis_url()
            assert url == 'redis://custom:6379/1'

    def test_get_redis_url_default(self):
        """Test default Redis URL when not in environment."""
        with patch.dict('os.environ', {}, clear=True):
            from backend.redis_client import get_redis_url
            url = get_redis_url()
            assert url == 'redis://localhost:6379/0'


class TestPipelineRegistry:
    """Test suite for pipeline registry operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_register_pipeline_redis(self, mock_redis):
        """Test registering a pipeline in Redis."""
        from backend.redis_client import register_pipeline_redis, PIPELINE_KEY_PREFIX

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            pipeline_info = {
                "host": "test-host",
                "pid": 1234,
                "started_at": "2024-01-01T00:00:00+00:00",
            }

            result = await register_pipeline_redis("test_session", pipeline_info)

            assert result is True
            mock_redis.setex.assert_called_once()

            # Verify key and TTL
            call_args = mock_redis.setex.call_args
            assert call_args[0][0] == f"{PIPELINE_KEY_PREFIX}test_session"
            assert call_args[0][1] == 3600  # 1 hour TTL
            assert json.loads(call_args[0][2]) == pipeline_info

    @pytest.mark.asyncio
    async def test_register_pipeline_redis_no_client(self):
        """Test registration when Redis is unavailable."""
        from backend.redis_client import register_pipeline_redis

        with patch('backend.redis_client.get_redis_client', return_value=None):
            result = await register_pipeline_redis("test_session", {})
            assert result is False

    @pytest.mark.asyncio
    async def test_get_pipeline_redis(self, mock_redis):
        """Test retrieving pipeline info from Redis."""
        from backend.redis_client import get_pipeline_redis, PIPELINE_KEY_PREFIX

        pipeline_info = {
            "host": "test-host",
            "pid": 1234,
            "started_at": "2024-01-01T00:00:00+00:00",
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(pipeline_info))

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            result = await get_pipeline_redis("test_session")

            assert result == pipeline_info
            mock_redis.get.assert_called_once_with(f"{PIPELINE_KEY_PREFIX}test_session")

    @pytest.mark.asyncio
    async def test_get_pipeline_redis_not_found(self, mock_redis):
        """Test retrieving non-existent pipeline."""
        from backend.redis_client import get_pipeline_redis

        mock_redis.get = AsyncMock(return_value=None)

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            result = await get_pipeline_redis("test_session")

            assert result is None

    @pytest.mark.asyncio
    async def test_unregister_pipeline_redis(self, mock_redis):
        """Test unregistering a pipeline from Redis."""
        from backend.redis_client import unregister_pipeline_redis, PIPELINE_KEY_PREFIX

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            result = await unregister_pipeline_redis("test_session")

            assert result is True
            mock_redis.delete.assert_called_once_with(f"{PIPELINE_KEY_PREFIX}test_session")

    @pytest.mark.asyncio
    async def test_list_active_pipelines_redis(self, mock_redis):
        """Test listing all active pipelines."""
        from backend.redis_client import list_active_pipelines_redis, PIPELINE_KEY_PREFIX

        keys = [
            f"{PIPELINE_KEY_PREFIX}session1",
            f"{PIPELINE_KEY_PREFIX}session2",
        ]
        mock_redis.keys = AsyncMock(return_value=keys)

        pipeline_info_1 = {"host": "host1", "pid": 1}
        pipeline_info_2 = {"host": "host2", "pid": 2}

        async def mock_get(key):
            if "session1" in key:
                return json.dumps(pipeline_info_1)
            elif "session2" in key:
                return json.dumps(pipeline_info_2)
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            result = await list_active_pipelines_redis()

            assert len(result) == 2
            assert result[0]["session_id"] == "session1"
            assert result[1]["session_id"] == "session2"

    @pytest.mark.asyncio
    async def test_update_pipeline_ttl_redis(self, mock_redis):
        """Test updating pipeline TTL."""
        from backend.redis_client import update_pipeline_ttl_redis, PIPELINE_KEY_PREFIX

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            result = await update_pipeline_ttl_redis("test_session", 7200)

            assert result is True
            mock_redis.expire.assert_called_once_with(
                f"{PIPELINE_KEY_PREFIX}test_session",
                7200
            )


class TestRedisErrorHandling:
    """Test error handling in Redis operations."""

    @pytest.fixture
    def mock_redis_failing(self):
        """Create a mock Redis client that raises exceptions."""
        mock = AsyncMock()
        mock.setex.side_effect = Exception("Redis connection failed")
        mock.get.side_effect = Exception("Redis connection failed")
        mock.delete.side_effect = Exception("Redis connection failed")
        mock.keys.side_effect = Exception("Redis connection failed")
        mock.expire.side_effect = Exception("Redis connection failed")
        return mock

    @pytest.mark.asyncio
    async def test_register_pipeline_redis_failure(self, mock_redis_failing):
        """Test registration failure handling."""
        from backend.redis_client import register_pipeline_redis

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis_failing):
            result = await register_pipeline_redis("test_session", {})
            assert result is False

    @pytest.mark.asyncio
    async def test_get_pipeline_redis_failure(self, mock_redis_failing):
        """Test retrieval failure handling."""
        from backend.redis_client import get_pipeline_redis

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis_failing):
            result = await get_pipeline_redis("test_session")
            assert result is None

    @pytest.mark.asyncio
    async def test_unregister_pipeline_redis_failure(self, mock_redis_failing):
        """Test unregistration failure handling."""
        from backend.redis_client import unregister_pipeline_redis

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis_failing):
            result = await unregister_pipeline_redis("test_session")
            assert result is False


class TestRedisMultiInstance:
    """Tests for multi-instance deployment scenarios."""

    @pytest.mark.asyncio
    async def test_pipeline_visible_across_instances(self):
        """Test that pipeline registered by one instance is visible to others."""
        from backend.redis_client import register_pipeline_redis, get_pipeline_redis

        mock_redis = AsyncMock()

        pipeline_info = {
            "host": "instance-a",
            "pid": 1234,
            "started_at": "2024-01-01T00:00:00+00:00",
        }

        # Simulate instance A registering
        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            await register_pipeline_redis("session_123", pipeline_info)

        # Simulate instance B querying
        mock_redis.get = AsyncMock(return_value=json.dumps(pipeline_info))

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            result = await get_pipeline_redis("session_123")

            assert result is not None
            assert result["host"] == "instance-a"

    @pytest.mark.asyncio
    async def test_pipeline_host_identification(self):
        """Test that pipeline entries include host information."""
        from backend.redis_client import (
            register_pipeline_redis,
            list_active_pipelines_redis,
            PIPELINE_KEY_PREFIX,
        )

        mock_redis = AsyncMock()

        # Instance A registers
        pipeline_info_a = {"host": "host-a", "pid": 1000}
        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            await register_pipeline_redis("session_a", pipeline_info_a)

        # Instance B registers
        pipeline_info_b = {"host": "host-b", "pid": 2000}
        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            await register_pipeline_redis("session_b", pipeline_info_b)

        # Verify both are listed with correct hosts
        keys = [f"{PIPELINE_KEY_PREFIX}session_a", f"{PIPELINE_KEY_PREFIX}session_b"]
        mock_redis.keys = AsyncMock(return_value=keys)

        async def mock_get(key):
            if "session_a" in key:
                return json.dumps(pipeline_info_a)
            return json.dumps(pipeline_info_b)

        mock_redis.get = AsyncMock(side_effect=mock_get)

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            pipelines = await list_active_pipelines_redis()

            hosts = [p["host"] for p in pipelines]
            assert "host-a" in hosts
            assert "host-b" in hosts


class TestRedisTTL:
    """Tests for TTL behavior."""

    @pytest.mark.asyncio
    async def test_pipeline_has_ttl(self):
        """Test that registered pipelines have TTL set."""
        from backend.redis_client import register_pipeline_redis

        mock_redis = AsyncMock()

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            await register_pipeline_redis("test_session", {})

            # Verify TTL is set to 1 hour (3600 seconds)
            call_args = mock_redis.setex.call_args
            assert call_args[0][1] == 3600

    @pytest.mark.asyncio
    async def test_ttl_can_be_updated(self):
        """Test that TTL can be extended for long-running sessions."""
        from backend.redis_client import update_pipeline_ttl_redis

        mock_redis = AsyncMock()

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            # Extend TTL to 2 hours
            result = await update_pipeline_ttl_redis("test_session", 7200)

            assert result is True
            mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_expired_pipeline_not_returned(self):
        """Test that expired pipeline entries are not returned."""
        from backend.redis_client import get_pipeline_redis

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # Expired/Not found

        with patch('backend.redis_client.get_redis_client', return_value=mock_redis):
            result = await get_pipeline_redis("expired_session")

            assert result is None
