"""
Tests for dashboard main.py FastAPI application.
"""
import pytest
import os
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Patch secrets before importing main (new config uses get_server_secret default_factory)
with patch.dict(os.environ, {
    "JWT_SECRET": "test-secret-key-for-testing",
    "SESSION_SECRET": "test-secret-key-for-testing",
    "INTERNAL_TOKEN": "test-token-for-testing",
}):
    from backend.dashboard.main import create_app, lifespan, _recover_stuck_jobs
    from backend.dashboard.dependencies import (
        get_bot_bridge, set_bot_bridge,
        set_position_monitor, set_intent_scanner,
    )


@asynccontextmanager
async def _noop_lifespan(app):
    yield


def _mock_settings(**overrides):
    """Create mock dashboard settings."""
    defaults = dict(
        dashboard_env="development",
        bot_api_url="http://bot:8000",
        internal_token="test_token",
        database_url="postgresql://test:test@localhost/test",
        redis_url="redis://localhost:6379",
        log_level="INFO",
    )
    defaults.update(overrides)
    settings = MagicMock(**defaults)
    settings.get_allowed_origins_list.return_value = ["http://localhost:3000"]
    return settings


def _create_test_app(**settings_overrides):
    """Create app with noop lifespan for structural tests."""
    settings = _mock_settings(**settings_overrides)
    with patch('backend.dashboard.main.get_dashboard_settings', return_value=settings):
        with patch('backend.dashboard.main.lifespan', _noop_lifespan):
            return create_app()


class TestCreateApp:
    """Tests for create_app function."""

    def test_create_app_returns_fastapi(self):
        """Test that create_app returns a FastAPI instance."""
        app = _create_test_app()
        assert isinstance(app, FastAPI)
        assert app.title == "Asgard Basis API"

    def test_create_app_includes_routers(self):
        """Test that create_app includes all API routers."""
        app = _create_test_app()
        routes = [route.path for route in app.routes]
        assert len(routes) > 0

    def test_create_app_security_headers(self):
        """Test that security headers middleware is configured."""
        app = _create_test_app()

        @app.get("/test-headers")
        async def test_headers():
            return {"test": "ok"}

        client = TestClient(app)
        response = client.get("/test-headers")

        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"


class TestLifespan:
    """Tests for lifespan context manager."""

    @pytest.mark.asyncio
    @patch('backend.dashboard.main._release_service_lock', new_callable=AsyncMock)
    @patch('shared.redis_client.close_redis', new_callable=AsyncMock)
    @patch('backend.dashboard.main.IntentScanner')
    @patch('backend.dashboard.main.PositionMonitorService')
    @patch('backend.dashboard.main.BotBridge')
    @patch('backend.dashboard.main.event_manager')
    @patch('backend.dashboard.auth.session_manager')
    @patch('shared.redis_client.get_redis', new_callable=AsyncMock)
    @patch('backend.dashboard.main._recover_stuck_jobs', new_callable=AsyncMock, return_value=0)
    @patch('backend.dashboard.main.run_migrations', new_callable=AsyncMock, return_value="v1.0")
    @patch('backend.dashboard.main.init_db', new_callable=AsyncMock)
    @patch('backend.dashboard.main._configure_logging')
    @patch('backend.dashboard.main.get_dashboard_settings')
    async def test_lifespan_startup_shutdown(
        self, mock_settings, mock_logging, mock_init_db, mock_migrations,
        mock_recover, mock_get_redis, mock_sm, mock_em, mock_bb_cls,
        mock_pm_cls, mock_is_cls, mock_close_redis, mock_release_lock,
    ):
        """Test lifespan startup and shutdown."""
        mock_db = AsyncMock()
        mock_db.close = AsyncMock()
        mock_init_db.return_value = mock_db

        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock()
        mock_get_redis.return_value = mock_redis

        mock_bridge = MagicMock()
        mock_bridge.start = AsyncMock()
        mock_bridge.stop = AsyncMock()
        mock_bb_cls.return_value = mock_bridge

        mock_monitor = MagicMock()
        mock_monitor.start = AsyncMock()
        mock_monitor.stop = AsyncMock()
        mock_monitor._running = True
        mock_pm_cls.return_value = mock_monitor

        mock_scanner = MagicMock()
        mock_scanner.start = AsyncMock()
        mock_scanner.stop = AsyncMock()
        mock_scanner._running = True
        mock_is_cls.return_value = mock_scanner

        mock_settings.return_value = _mock_settings()
        mock_sm.set_db = MagicMock()
        mock_em.start = AsyncMock()
        mock_em.stop = AsyncMock()

        ctx = lifespan(MagicMock())
        await ctx.__aenter__()

        mock_bridge.start.assert_called_once()
        mock_monitor.start.assert_called_once()
        mock_scanner.start.assert_called_once()
        mock_em.start.assert_called_once()

        await ctx.__aexit__(None, None, None)
        mock_db.close.assert_called_once()

        set_bot_bridge(None)
        set_position_monitor(None)
        set_intent_scanner(None)

    @pytest.mark.asyncio
    @patch('backend.dashboard.main._release_service_lock', new_callable=AsyncMock)
    @patch('shared.redis_client.close_redis', new_callable=AsyncMock)
    @patch('backend.dashboard.main.IntentScanner')
    @patch('backend.dashboard.main.PositionMonitorService')
    @patch('backend.dashboard.main.BotBridge', side_effect=Exception("Connection refused"))
    @patch('backend.dashboard.main.event_manager')
    @patch('backend.dashboard.auth.session_manager')
    @patch('shared.redis_client.get_redis', new_callable=AsyncMock)
    @patch('backend.dashboard.main._recover_stuck_jobs', new_callable=AsyncMock, return_value=0)
    @patch('backend.dashboard.main.run_migrations', new_callable=AsyncMock, return_value="v1.0")
    @patch('backend.dashboard.main.init_db', new_callable=AsyncMock)
    @patch('backend.dashboard.main._configure_logging')
    @patch('backend.dashboard.main.get_dashboard_settings')
    async def test_lifespan_bot_bridge_failure_non_fatal(
        self, mock_settings, mock_logging, mock_init_db, mock_migrations,
        mock_recover, mock_get_redis, mock_sm, mock_em, mock_bb_cls,
        mock_pm_cls, mock_is_cls, mock_close_redis, mock_release_lock,
    ):
        """Test lifespan when bot bridge fails to connect."""
        mock_db = AsyncMock()
        mock_db.close = AsyncMock()
        mock_init_db.return_value = mock_db

        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock()
        mock_get_redis.return_value = mock_redis

        mock_monitor = MagicMock()
        mock_monitor.start = AsyncMock()
        mock_monitor.stop = AsyncMock()
        mock_pm_cls.return_value = mock_monitor

        mock_scanner = MagicMock()
        mock_scanner.start = AsyncMock()
        mock_scanner.stop = AsyncMock()
        mock_is_cls.return_value = mock_scanner

        mock_settings.return_value = _mock_settings()
        mock_sm.set_db = MagicMock()
        mock_em.start = AsyncMock()
        mock_em.stop = AsyncMock()

        ctx = lifespan(MagicMock())
        await ctx.__aenter__()  # Should not raise

        await ctx.__aexit__(None, None, None)

        set_bot_bridge(None)
        set_position_monitor(None)
        set_intent_scanner(None)

    @pytest.mark.asyncio
    @patch('backend.dashboard.main.run_migrations', new_callable=AsyncMock, side_effect=Exception("Migration failed"))
    @patch('backend.dashboard.main.init_db', new_callable=AsyncMock)
    @patch('backend.dashboard.main._configure_logging')
    @patch('backend.dashboard.main.get_dashboard_settings')
    async def test_lifespan_migration_failure(
        self, mock_settings, mock_logging, mock_init_db, mock_migrations,
    ):
        """Test lifespan when migration fails."""
        mock_settings.return_value = _mock_settings()
        mock_init_db.return_value = AsyncMock()

        ctx = lifespan(MagicMock())

        with pytest.raises(Exception, match="Migration failed"):
            await ctx.__aenter__()


class TestRecoverStuckJobs:
    """Tests for _recover_stuck_jobs."""

    @pytest.mark.asyncio
    async def test_recovers_stuck_jobs(self):
        db = AsyncMock()
        db.fetchall = AsyncMock(return_value=[
            {"job_id": "job_1"},
            {"job_id": "job_2"},
        ])
        db.execute = AsyncMock()

        count = await _recover_stuck_jobs(db)
        assert count == 2
        assert db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_no_stuck_jobs(self):
        db = AsyncMock()
        db.fetchall = AsyncMock(return_value=[])

        count = await _recover_stuck_jobs(db)
        assert count == 0
        db.execute.assert_not_called()


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_returns_ok(self):
        """Test /health liveness probe."""
        app = _create_test_app()
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_live_returns_ok(self):
        """Test /health/live liveness probe."""
        app = _create_test_app()
        client = TestClient(app)
        response = client.get("/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @patch('shared.redis_client.get_redis', new_callable=AsyncMock)
    @patch('backend.dashboard.main.get_db')
    def test_health_ready_all_healthy(self, mock_get_db, mock_get_redis):
        """Test /health/ready when everything is healthy."""
        app = _create_test_app()

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_get_db.return_value = mock_db

        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock()
        mock_get_redis.return_value = mock_redis

        mock_bridge = MagicMock()
        mock_bridge.health_check = AsyncMock(return_value=True)
        mock_monitor = MagicMock()
        mock_monitor._running = True
        mock_scanner = MagicMock()
        mock_scanner._running = True

        set_bot_bridge(mock_bridge)
        set_position_monitor(mock_monitor)
        set_intent_scanner(mock_scanner)

        try:
            client = TestClient(app)
            response = client.get("/health/ready")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["database"] == "healthy"
            assert data["redis"] == "healthy"
            assert data["bot_connected"] is True
            assert data["position_monitor"] == "running"
            assert data["intent_scanner"] == "running"
        finally:
            set_bot_bridge(None)
            set_position_monitor(None)
            set_intent_scanner(None)

    def test_health_ready_db_error(self):
        """Test /health/ready when database has error."""
        app = _create_test_app()

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock()

        set_bot_bridge(None)
        set_position_monitor(None)
        set_intent_scanner(None)

        with patch('backend.dashboard.main.get_db', return_value=mock_db):
            with patch('shared.redis_client.get_redis', new_callable=AsyncMock, return_value=mock_redis):
                client = TestClient(app)
                response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "error"

    def test_health_ready_bot_disconnected(self):
        """Test /health/ready when bot is disconnected."""
        app = _create_test_app()

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock()

        set_bot_bridge(None)
        set_position_monitor(None)
        set_intent_scanner(None)

        with patch('backend.dashboard.main.get_db', return_value=mock_db):
            with patch('shared.redis_client.get_redis', new_callable=AsyncMock, return_value=mock_redis):
                client = TestClient(app)
                response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["bot_connected"] is False


class TestSecurityHeaders:
    """Tests for security headers middleware."""

    def test_security_headers_present(self):
        """Test that security headers are added to responses."""
        app = _create_test_app()

        @app.get("/test-security")
        async def test_route():
            return {"test": "ok"}

        client = TestClient(app)
        response = client.get("/test-security")

        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert "X-XSS-Protection" in response.headers
        assert "Strict-Transport-Security" in response.headers
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


class TestCORS:
    """Tests for CORS configuration."""

    def test_cors_development(self):
        """Test CORS middleware is configured in development mode."""
        app = _create_test_app(dashboard_env="development")

        client = TestClient(app)
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 200
        # CORS middleware adds credentials header
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_cors_production(self):
        """Test CORS configuration in production mode."""
        app = _create_test_app(dashboard_env="production")

        @app.get("/test-cors-prod")
        async def test_route():
            return {"test": "ok"}

        client = TestClient(app)
        response = client.get("/test-cors-prod")

        assert response.status_code == 200


class TestGlobalApp:
    """Tests for the global app instance."""

    def test_global_app_exists(self):
        """Test that global app instance exists."""
        from backend.dashboard.main import app

        assert app is not None
        assert isinstance(app, FastAPI)
