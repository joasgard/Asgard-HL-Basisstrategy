"""
Tests for dashboard main.py FastAPI application.
"""
import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dashboard.main import create_app, lifespan
from src.dashboard.dependencies import get_bot_bridge, set_bot_bridge


class TestCreateApp:
    """Tests for create_app function."""
    
    def test_create_app_returns_fastapi(self):
        """Test that create_app returns a FastAPI instance."""
        with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                dashboard_env="development",
                bot_api_url="http://bot:8000",
                internal_token="test_token"
            )
            
            application = create_app()
            
            assert isinstance(application, FastAPI)
            assert application.title == "Delta Neutral Bot Dashboard"
    
    def test_create_app_includes_routers(self):
        """Test that create_app includes all API routers."""
        with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                dashboard_env="development",
                bot_api_url="http://bot:8000",
                internal_token="test_token"
            )
            
            application = create_app()
            
            # Check that routes are registered
            routes = [route.path for route in application.routes]
            # Should have various routes including API and page routes
            assert len(routes) > 0
    
    def test_create_app_security_headers(self):
        """Test that security headers middleware is configured."""
        with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                dashboard_env="development",
                bot_api_url="http://bot:8000",
                internal_token="test_token"
            )
            
            application = create_app()
            
            # Add a test route
            @application.get("/test-headers")
            async def test_headers():
                return {"test": "ok"}
            
            client = TestClient(application)
            response = client.get("/test-headers")
            
            assert response.headers.get("X-Content-Type-Options") == "nosniff"
            assert response.headers.get("X-Frame-Options") == "DENY"


class TestLifespan:
    """Tests for lifespan context manager."""
    
    @pytest.mark.asyncio
    async def test_lifespan_startup_shutdown(self):
        """Test lifespan startup and shutdown."""
        mock_app = MagicMock()
        
        with patch('src.dashboard.main.init_db', new_callable=AsyncMock) as mock_init_db:
            with patch('src.dashboard.main.run_migrations', new_callable=AsyncMock) as mock_migrations:
                with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
                    with patch('src.dashboard.main.session_manager') as mock_session_mgr:
                        with patch('src.dashboard.main.BotBridge') as mock_bridge_class:
                            mock_settings.return_value = MagicMock(
                                bot_api_url="http://bot:8000",
                                internal_token="test_token"
                            )
                            mock_db = AsyncMock()
                            mock_db.get_config = AsyncMock(return_value="true")
                            mock_db.close = AsyncMock()
                            mock_init_db.return_value = mock_db
                            mock_migrations.return_value = "v1.0"
                            
                            mock_bridge = AsyncMock()
                            mock_bridge.start = AsyncMock()
                            mock_bridge.stop = AsyncMock()
                            mock_bridge_class.return_value = mock_bridge
                            
                            # Create lifespan context
                            ctx = lifespan(mock_app)
                            
                            # Enter context (startup)
                            await ctx.__aenter__()
                            
                            mock_init_db.assert_called_once()
                            mock_migrations.assert_called_once()
                            mock_session_mgr.set_db.assert_called_once_with(mock_db)
                            mock_bridge.start.assert_called_once()
                            
                            # Exit context (shutdown)
                            await ctx.__aexit__(None, None, None)
                            
                            mock_bridge.stop.assert_called_once()
                            mock_db.close.assert_called_once()
                            
                            set_bot_bridge(None)
    
    @pytest.mark.asyncio
    async def test_lifespan_setup_not_complete(self):
        """Test lifespan when setup is not complete."""
        mock_app = MagicMock()
        
        with patch('src.dashboard.main.init_db', new_callable=AsyncMock) as mock_init_db:
            with patch('src.dashboard.main.run_migrations', new_callable=AsyncMock) as mock_migrations:
                with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
                    with patch('src.dashboard.main.session_manager') as mock_session_mgr:
                        with patch('src.dashboard.main.BotBridge') as mock_bridge_class:
                            mock_settings.return_value = MagicMock(
                                bot_api_url="http://bot:8000",
                                internal_token="test_token"
                            )
                            mock_db = AsyncMock()
                            mock_db.get_config = AsyncMock(return_value=None)  # Setup not complete
                            mock_db.close = AsyncMock()
                            mock_init_db.return_value = mock_db
                            
                            ctx = lifespan(mock_app)
                            await ctx.__aenter__()
                            
                            # Bot bridge should not be created
                            mock_bridge_class.assert_not_called()
                            
                            await ctx.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_lifespan_migration_failure(self):
        """Test lifespan when migration fails."""
        mock_app = MagicMock()
        
        with patch('src.dashboard.main.init_db', new_callable=AsyncMock) as mock_init_db:
            with patch('src.dashboard.main.run_migrations', new_callable=AsyncMock) as mock_migrations:
                with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
                    mock_settings.return_value = MagicMock()
                    mock_db = AsyncMock()
                    mock_init_db.return_value = mock_db
                    mock_migrations.side_effect = Exception("Migration failed")
                    
                    ctx = lifespan(mock_app)
                    
                    with pytest.raises(Exception, match="Migration failed"):
                        await ctx.__aenter__()


class TestHealthEndpoint:
    """Tests for health check endpoint."""
    
    @pytest.mark.asyncio
    async def test_health_endpoint_bot_connected(self):
        """Test health endpoint when bot is connected."""
        with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                dashboard_env="development",
                bot_api_url="http://bot:8000",
                internal_token="test_token"
            )
            
            application = create_app()
            
            # Mock bot bridge
            mock_bridge = AsyncMock()
            mock_bridge.health_check = AsyncMock(return_value=True)
            set_bot_bridge(mock_bridge)
            
            client = TestClient(application)
            response = client.get("/health")
            
            # Database might be mocked differently, just check bot status
            assert response.status_code == 200
            data = response.json()
            assert data["bot_connected"] is True
            
            set_bot_bridge(None)
    
    @pytest.mark.asyncio
    async def test_health_endpoint_bot_disconnected(self):
        """Test health endpoint when bot is disconnected."""
        with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                dashboard_env="development",
                bot_api_url="http://bot:8000",
                internal_token="test_token"
            )
            
            application = create_app()
            set_bot_bridge(None)
            
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock()
            
            with patch('src.dashboard.main.get_db', return_value=mock_db):
                client = TestClient(application)
                response = client.get("/health")
                
                assert response.status_code == 200
                data = response.json()
                assert data["bot_connected"] is False
    
    @pytest.mark.asyncio
    async def test_health_endpoint_db_error(self):
        """Test health endpoint when database has error."""
        with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                dashboard_env="development",
                bot_api_url="http://bot:8000",
                internal_token="test_token"
            )
            
            application = create_app()
            set_bot_bridge(None)
            
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))
            
            with patch('src.dashboard.main.get_db', return_value=mock_db):
                client = TestClient(application)
                response = client.get("/health")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "unhealthy"
                assert data["database"] == "error"


class TestSecurityHeaders:
    """Tests for security headers middleware."""
    
    def test_security_headers_present(self):
        """Test that security headers are added to responses."""
        with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                dashboard_env="development",
                bot_api_url="http://bot:8000",
                internal_token="test_token"
            )
            
            application = create_app()
            
            # Add a simple test route
            @application.get("/test-security")
            async def test_route():
                return {"test": "ok"}
            
            client = TestClient(application)
            response = client.get("/test-security")
            
            # Check security headers
            assert response.headers.get("X-Content-Type-Options") == "nosniff"
            assert response.headers.get("X-Frame-Options") == "DENY"
            assert "X-XSS-Protection" in response.headers
            assert "Strict-Transport-Security" in response.headers
            assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


class TestCORS:
    """Tests for CORS configuration."""
    
    def test_cors_development(self):
        """Test CORS configuration in development mode."""
        with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                dashboard_env="development",
                bot_api_url="http://bot:8000",
                internal_token="test_token"
            )
            
            application = create_app()
            
            @application.get("/test-cors")
            async def test_route():
                return {"test": "ok"}
            
            client = TestClient(application)
            
            # Test preflight request
            response = client.options(
                "/test-cors",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET"
                }
            )
            
            assert response.status_code == 200
    
    def test_cors_production(self):
        """Test CORS configuration in production mode."""
        with patch('src.dashboard.main.get_dashboard_settings') as mock_settings:
            mock_settings.return_value = MagicMock(
                dashboard_env="production",
                bot_api_url="http://bot:8000",
                internal_token="test_token"
            )
            
            application = create_app()
            
            @application.get("/test-cors-prod")
            async def test_route():
                return {"test": "ok"}
            
            client = TestClient(application)
            response = client.get("/test-cors-prod")
            
            assert response.status_code == 200


class TestGlobalApp:
    """Tests for the global app instance."""
    
    def test_global_app_exists(self):
        """Test that global app instance exists."""
        from src.dashboard.main import app
        
        assert app is not None
        assert isinstance(app, FastAPI)
