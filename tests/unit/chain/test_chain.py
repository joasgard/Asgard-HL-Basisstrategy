"""
Tests for chain connection modules.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.common import Chain, ChainStatus
from src.chain.outage_detector import OutageDetector, ChainHealth


class TestOutageDetector:
    """Test outage detection logic."""
    
    def test_initialization(self):
        """Test detector initializes with healthy status."""
        detector = OutageDetector()
        
        for chain in [Chain.SOLANA, Chain.ARBITRUM]:
            health = detector.get_status(chain)
            assert health.status == ChainStatus.HEALTHY
            assert health.chain == chain
    
    def test_record_success(self):
        """Test successful health check recording."""
        detector = OutageDetector()
        
        from datetime import datetime
        
        health = detector._record_success(Chain.SOLANA, 100.0)
        
        assert health.status == ChainStatus.HEALTHY
        assert health.consecutive_failures == 0
        assert health.latency_ms == 100.0
        assert health.last_success is not None
    
    def test_record_failure_degraded(self):
        """Test degraded status after first failures."""
        detector = OutageDetector()
        
        # First failure
        health = detector._record_failure(Chain.SOLANA, "RPC timeout")
        assert health.status == ChainStatus.DEGRADED
        assert health.consecutive_failures == 1
        
        # Second failure
        health = detector._record_failure(Chain.SOLANA, "RPC timeout")
        assert health.status == ChainStatus.DEGRADED
        assert health.consecutive_failures == 2
    
    def test_record_failure_outage(self):
        """Test outage status after 3 failures."""
        detector = OutageDetector()
        
        # 3 failures in window = outage
        detector._record_failure(Chain.SOLANA, "Error 1")
        detector._record_failure(Chain.SOLANA, "Error 2")
        health = detector._record_failure(Chain.SOLANA, "Error 3")
        
        assert health.status == ChainStatus.OUTAGE
        assert health.consecutive_failures == 3
    
    def test_recovery_from_outage(self):
        """Test recovery after outage."""
        detector = OutageDetector()
        
        # Trigger outage
        detector._record_failure(Chain.SOLANA, "Error 1")
        detector._record_failure(Chain.SOLANA, "Error 2")
        detector._record_failure(Chain.SOLANA, "Error 3")
        
        assert detector.get_status(Chain.SOLANA).status == ChainStatus.OUTAGE
        
        # Recovery
        health = detector._record_success(Chain.SOLANA, 50.0)
        assert health.status == ChainStatus.HEALTHY
        assert detector.is_healthy(Chain.SOLANA) is True
    
    def test_failure_window_expiration(self):
        """Test old failures are cleaned from window."""
        detector = OutageDetector()
        
        from datetime import datetime, timedelta
        
        # Add old failure (outside 15s window)
        old_time = datetime.utcnow() - timedelta(seconds=20)
        detector._failure_timestamps[Chain.SOLANA].append(old_time)
        
        # Add recent failures
        detector._record_failure(Chain.SOLANA, "Recent error")
        
        # Old failure should be cleaned, so only 1 in window
        health = detector.get_status(Chain.SOLANA)
        assert health.consecutive_failures == 1
    
    def test_callback_registration(self):
        """Test status change callbacks."""
        detector = OutageDetector()
        
        callback_called = False
        received_chain = None
        received_status = None
        
        def callback(chain: Chain, status: ChainStatus):
            nonlocal callback_called, received_chain, received_status
            callback_called = True
            received_chain = chain
            received_status = status
        
        detector.register_callback(callback)
        
        # Trigger status change to outage
        detector._record_failure(Chain.SOLANA, "Error 1")
        detector._record_failure(Chain.SOLANA, "Error 2")
        detector._record_failure(Chain.SOLANA, "Error 3")
        
        assert callback_called is True
        assert received_chain == Chain.SOLANA
        assert received_status == ChainStatus.OUTAGE
    
    @pytest.mark.asyncio
    async def test_check_chain_health_success(self):
        """Test health check with mocked success."""
        detector = OutageDetector()
        
        with patch("src.chain.outage_detector.SolanaClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.health_check = AsyncMock(return_value=True)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            health = await detector.check_chain_health(Chain.SOLANA)
            
            assert health.status == ChainStatus.HEALTHY
            assert health.consecutive_failures == 0
    
    @pytest.mark.asyncio
    async def test_check_chain_health_failure(self):
        """Test health check with mocked failure."""
        detector = OutageDetector()
        
        with patch("src.chain.outage_detector.SolanaClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.health_check = AsyncMock(return_value=False)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            health = await detector.check_chain_health(Chain.SOLANA)
            
            assert health.status == ChainStatus.DEGRADED
            assert health.consecutive_failures == 1


class TestChainStatusEnum:
    """Test chain status enum."""
    
    def test_status_values(self):
        """Test status enum values."""
        assert ChainStatus.HEALTHY.value == "healthy"
        assert ChainStatus.DEGRADED.value == "degraded"
        assert ChainStatus.OUTAGE.value == "outage"
    
    def test_chain_enum(self):
        """Test chain enum values."""
        assert Chain.SOLANA.value == "solana"
        assert Chain.ARBITRUM.value == "arbitrum"
