"""
Tests for dashboard positions API.
"""
import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal
from datetime import datetime

from fastapi import HTTPException


class TestListPositions:
    """Tests for GET /positions endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.positions.require_bot_bridge')
    async def test_list_positions_success(self, mock_require_bridge):
        """Test listing positions successfully."""
        from src.dashboard.api.positions import list_positions
        from src.shared.schemas import PositionSummary
        
        mock_bridge = AsyncMock()
        
        # Create mock positions
        pos1 = PositionSummary(
            position_id="pos1",
            asset="SOL",
            status="open",
            leverage=Decimal("3.0"),
            deployed_usd=Decimal("10000"),
            long_value_usd=Decimal("10000"),
            short_value_usd=Decimal("30000"),
            delta=Decimal("100"),
            delta_ratio=Decimal("0.01"),
            asgard_hf=Decimal("1.2"),
            hyperliquid_mf=Decimal("0.15"),
            total_pnl_usd=Decimal("50"),
            funding_pnl_usd=Decimal("30"),
            opened_at=datetime.utcnow(),
            hold_duration_hours=24.5
        )
        
        mock_bridge.get_positions.return_value = {"pos1": pos1}
        mock_require_bridge.return_value = mock_bridge
        
        result = await list_positions()
        
        assert len(result) == 1
        assert result[0].position_id == "pos1"
        assert result[0].asset == "SOL"
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.positions.require_bot_bridge')
    async def test_list_positions_empty(self, mock_require_bridge):
        """Test listing positions when none exist."""
        from src.dashboard.api.positions import list_positions
        
        mock_bridge = AsyncMock()
        mock_bridge.get_positions.return_value = {}
        mock_require_bridge.return_value = mock_bridge
        
        result = await list_positions()
        
        assert result == []
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.positions.require_bot_bridge')
    async def test_list_positions_exception(self, mock_require_bridge):
        """Test handling exception when listing positions."""
        from src.dashboard.api.positions import list_positions
        
        mock_bridge = AsyncMock()
        mock_bridge.get_positions.side_effect = Exception("Connection error")
        mock_require_bridge.return_value = mock_bridge
        
        with pytest.raises(HTTPException) as exc_info:
            await list_positions()
        
        assert exc_info.value.status_code == 503


class TestGetPosition:
    """Tests for GET /positions/{position_id} endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.positions.require_bot_bridge')
    async def test_get_position_success(self, mock_require_bridge):
        """Test getting position detail successfully."""
        from src.dashboard.api.positions import get_position
        from src.shared.schemas import PositionDetail
        
        mock_bridge = AsyncMock()
        
        pos = PositionDetail(
            position_id="pos1",
            asset="SOL",
            status="open",
            leverage=Decimal("3.0"),
            deployed_usd=Decimal("10000"),
            long_value_usd=Decimal("10000"),
            short_value_usd=Decimal("30000"),
            delta=Decimal("100"),
            delta_ratio=Decimal("0.01"),
            asgard_hf=Decimal("1.2"),
            hyperliquid_mf=Decimal("0.15"),
            total_pnl_usd=Decimal("50"),
            funding_pnl_usd=Decimal("30"),
            opened_at=datetime.utcnow(),
            hold_duration_hours=24.5,
            sizing={},
            asgard={},
            hyperliquid={},
            pnl={},
            risk={}
        )
        
        mock_bridge.get_position_detail.return_value = pos
        mock_require_bridge.return_value = mock_bridge
        
        result = await get_position("pos1")
        
        assert result.position_id == "pos1"
        assert result.asset == "SOL"
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.positions.require_bot_bridge')
    async def test_get_position_not_found(self, mock_require_bridge):
        """Test handling position not found."""
        from src.dashboard.api.positions import get_position
        
        mock_bridge = AsyncMock()
        mock_bridge.get_position_detail.side_effect = Exception("404 Not Found")
        mock_require_bridge.return_value = mock_bridge
        
        with pytest.raises(HTTPException) as exc_info:
            await get_position("nonexistent")
        
        assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.positions.require_bot_bridge')
    async def test_get_position_exception(self, mock_require_bridge):
        """Test handling other exceptions."""
        from src.dashboard.api.positions import get_position
        
        mock_bridge = AsyncMock()
        mock_bridge.get_position_detail.side_effect = Exception("Connection error")
        mock_require_bridge.return_value = mock_bridge
        
        with pytest.raises(HTTPException) as exc_info:
            await get_position("pos1")
        
        assert exc_info.value.status_code == 503


class TestOpenPosition:
    """Tests for POST /positions/open endpoint."""
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.positions.uuid')
    async def test_open_position_success(self, mock_uuid):
        """Test initiating position open successfully."""
        import asyncio
        from src.dashboard.api.positions import open_position, OpenPositionRequest
        
        mock_uuid.uuid4.return_value = "test-job-id"
        
        mock_db = AsyncMock()
        mock_db._connection = MagicMock()
        mock_db._connection.commit = AsyncMock()
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        request = OpenPositionRequest(asset="SOL", leverage=3.0, size_usd=10000)
        
        result = await open_position(request, user=mock_user, db=mock_db)
        
        assert result.success is True
        assert result.job_id == "test-job-id"
        assert "initiated" in result.message.lower()
        
        mock_db.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_open_position_with_venue(self):
        """Test opening position with specific venue."""
        from src.dashboard.api.positions import OpenPositionRequest
        
        request = OpenPositionRequest(
            asset="SOL",
            leverage=3.0,
            size_usd=10000,
            venue="kamino"
        )
        
        assert request.asset == "SOL"
        assert request.leverage == 3.0
        assert request.size_usd == 10000
        assert request.venue == "kamino"
    
    @pytest.mark.asyncio
    @patch('src.dashboard.api.positions.uuid')
    async def test_open_position_db_error(self, mock_uuid):
        """Test handling database error."""
        from src.dashboard.api.positions import open_position, OpenPositionRequest
        
        mock_uuid.uuid4.return_value = "test-job-id"
        
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Database error")
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        request = OpenPositionRequest(asset="SOL", leverage=3.0, size_usd=10000)
        
        with pytest.raises(HTTPException) as exc_info:
            await open_position(request, user=mock_user, db=mock_db)
        
        assert exc_info.value.status_code == 500


class TestGetJobStatus:
    """Tests for GET /positions/jobs/{job_id} endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_job_status_pending(self):
        """Test getting pending job status."""
        from src.dashboard.api.positions import get_job_status
        
        mock_db = AsyncMock()
        mock_db.fetchone.return_value = {
            "job_id": "job1",
            "status": "pending",
            "position_id": None,
            "error": None,
            "error_stage": None,
            "created_at": "2024-01-01T00:00:00",
            "completed_at": None,
            "params": '{"asset": "SOL", "leverage": 3.0, "size_usd": 10000}'
        }
        
        result = await get_job_status("job1", db=mock_db)
        
        assert result.job_id == "job1"
        assert result.status == "pending"
        assert result.params["asset"] == "SOL"
    
    @pytest.mark.asyncio
    async def test_get_job_status_completed(self):
        """Test getting completed job status."""
        from src.dashboard.api.positions import get_job_status
        
        mock_db = AsyncMock()
        mock_db.fetchone.return_value = {
            "job_id": "job1",
            "status": "completed",
            "position_id": "pos123",
            "error": None,
            "error_stage": None,
            "created_at": "2024-01-01T00:00:00",
            "completed_at": "2024-01-01T00:01:00",
            "params": '{"asset": "SOL", "leverage": 3.0, "size_usd": 10000}'
        }
        
        result = await get_job_status("job1", db=mock_db)
        
        assert result.status == "completed"
        assert result.position_id == "pos123"
    
    @pytest.mark.asyncio
    async def test_get_job_status_failed(self):
        """Test getting failed job status."""
        from src.dashboard.api.positions import get_job_status
        
        mock_db = AsyncMock()
        mock_db.fetchone.return_value = {
            "job_id": "job1",
            "status": "failed",
            "position_id": None,
            "error": "Insufficient funds",
            "error_stage": "asgard_open",
            "created_at": "2024-01-01T00:00:00",
            "completed_at": "2024-01-01T00:00:30",
            "params": '{"asset": "SOL", "leverage": 3.0, "size_usd": 10000}'
        }
        
        result = await get_job_status("job1", db=mock_db)
        
        assert result.status == "failed"
        assert result.error == "Insufficient funds"
        assert result.error_stage == "asgard_open"
    
    @pytest.mark.asyncio
    async def test_get_job_status_not_found(self):
        """Test handling job not found."""
        from src.dashboard.api.positions import get_job_status
        
        mock_db = AsyncMock()
        mock_db.fetchone.return_value = None
        
        with pytest.raises(HTTPException) as exc_info:
            await get_job_status("nonexistent", db=mock_db)
        
        assert exc_info.value.status_code == 404


class TestListJobs:
    """Tests for GET /positions/jobs endpoint."""
    
    @pytest.mark.asyncio
    async def test_list_jobs_success(self):
        """Test listing jobs successfully."""
        from src.dashboard.api.positions import list_jobs
        
        mock_db = AsyncMock()
        mock_db.fetchall.return_value = [
            {
                "job_id": "job1",
                "status": "completed",
                "position_id": "pos1",
                "error": None,
                "error_stage": None,
                "created_at": "2024-01-01T00:00:00",
                "completed_at": "2024-01-01T00:01:00",
                "params": '{"asset": "SOL"}'
            },
            {
                "job_id": "job2",
                "status": "pending",
                "position_id": None,
                "error": None,
                "error_stage": None,
                "created_at": "2024-01-01T00:02:00",
                "completed_at": None,
                "params": '{"asset": "jitoSOL"}'
            }
        ]
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        result = await list_jobs(user=mock_user, db=mock_db, limit=10)
        
        assert len(result) == 2
        assert result[0].job_id == "job1"
        assert result[0].status == "completed"
        assert result[1].job_id == "job2"
        assert result[1].status == "pending"
    
    @pytest.mark.asyncio
    async def test_list_jobs_empty(self):
        """Test listing jobs when none exist."""
        from src.dashboard.api.positions import list_jobs
        
        mock_db = AsyncMock()
        mock_db.fetchall.return_value = []
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        result = await list_jobs(user=mock_user, db=mock_db)
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_list_jobs_with_limit(self):
        """Test listing jobs with custom limit."""
        from src.dashboard.api.positions import list_jobs
        
        mock_db = AsyncMock()
        mock_db.fetchall.return_value = [
            {"job_id": f"job{i}", "status": "completed", "position_id": None,
             "error": None, "error_stage": None, "created_at": "2024-01-01T00:00:00",
             "completed_at": None, "params": None}
            for i in range(5)
        ]
        
        mock_user = MagicMock()
        mock_user.user_id = "test_user"
        
        result = await list_jobs(user=mock_user, db=mock_db, limit=5)
        
        assert len(result) == 5
        # Verify correct limit passed to query
        mock_db.fetchall.assert_called_once()
        call_args = mock_db.fetchall.call_args
        assert call_args[0][1] == ("test_user", 5)


class TestOpenPositionRequest:
    """Tests for OpenPositionRequest model."""
    
    def test_valid_request(self):
        """Test creating valid request."""
        from src.dashboard.api.positions import OpenPositionRequest
        
        request = OpenPositionRequest(asset="SOL", leverage=3.0, size_usd=10000)
        
        assert request.asset == "SOL"
        assert request.leverage == 3.0
        assert request.size_usd == 10000
        assert request.venue is None
    
    def test_default_leverage(self):
        """Test default leverage value."""
        from src.dashboard.api.positions import OpenPositionRequest
        
        request = OpenPositionRequest(asset="SOL", size_usd=10000)
        
        assert request.leverage == 3.0
    
    def test_leverage_validation(self):
        """Test leverage validation."""
        from src.dashboard.api.positions import OpenPositionRequest
        from pydantic import ValidationError
        
        # Too low
        with pytest.raises(ValidationError):
            OpenPositionRequest(asset="SOL", leverage=1.5, size_usd=10000)
        
        # Too high
        with pytest.raises(ValidationError):
            OpenPositionRequest(asset="SOL", leverage=4.5, size_usd=10000)
        
        # Valid boundaries
        req_min = OpenPositionRequest(asset="SOL", leverage=2.0, size_usd=10000)
        assert req_min.leverage == 2.0
        
        req_max = OpenPositionRequest(asset="SOL", leverage=4.0, size_usd=10000)
        assert req_max.leverage == 4.0
    
    def test_size_validation(self):
        """Test size_usd validation."""
        from src.dashboard.api.positions import OpenPositionRequest
        from pydantic import ValidationError
        
        # Too low
        with pytest.raises(ValidationError):
            OpenPositionRequest(asset="SOL", leverage=3.0, size_usd=500)
        
        # Valid
        request = OpenPositionRequest(asset="SOL", leverage=3.0, size_usd=1000)
        assert request.size_usd == 1000


class TestOpenPositionResponse:
    """Tests for OpenPositionResponse model."""
    
    def test_success_response(self):
        """Test successful response."""
        from src.dashboard.api.positions import OpenPositionResponse
        
        response = OpenPositionResponse(
            success=True,
            message="Position opened",
            job_id="job123"
        )
        
        assert response.success is True
        assert response.job_id == "job123"
    
    def test_failure_response(self):
        """Test failure response."""
        from src.dashboard.api.positions import OpenPositionResponse
        
        response = OpenPositionResponse(
            success=False,
            message="Failed to open position"
        )
        
        assert response.success is False
        assert response.job_id is None


class TestJobStatusResponse:
    """Tests for JobStatusResponse model."""
    
    def test_pending_status(self):
        """Test pending job status."""
        from src.dashboard.api.positions import JobStatusResponse
        
        response = JobStatusResponse(
            job_id="job1",
            status="pending"
        )
        
        assert response.job_id == "job1"
        assert response.status == "pending"
        assert response.position_id is None
    
    def test_completed_status(self):
        """Test completed job status."""
        from src.dashboard.api.positions import JobStatusResponse
        
        response = JobStatusResponse(
            job_id="job1",
            status="completed",
            position_id="pos123"
        )
        
        assert response.status == "completed"
        assert response.position_id == "pos123"
    
    def test_failed_status(self):
        """Test failed job status."""
        from src.dashboard.api.positions import JobStatusResponse
        
        response = JobStatusResponse(
            job_id="job1",
            status="failed",
            error="Insufficient funds",
            error_stage="asgard_open"
        )
        
        assert response.status == "failed"
        assert response.error == "Insufficient funds"
