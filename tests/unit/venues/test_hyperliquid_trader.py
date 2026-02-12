"""
Tests for Hyperliquid Trader.

These tests verify:
- Leverage updates
- Opening short positions with retry
- Closing short positions
- Position monitoring
- Stop-loss logic
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.venues.hyperliquid.client import HyperliquidClient
from bot.venues.hyperliquid.signer import HyperliquidSigner
from bot.venues.hyperliquid.trader import (
    HyperliquidTrader,
    OrderResult,
    PositionInfo,
    StopLossTrigger,
)


class TestHyperliquidTraderInit:
    """Tests for trader initialization."""
    
    def test_init_with_explicit_clients(self):
        """Test initialization with provided clients."""
        client = MagicMock(spec=HyperliquidClient)
        trader = HyperliquidTrader(client=client)
        assert trader.client is client
    
    def test_init_creates_client(self):
        """Test that client is created if not provided."""
        with patch("bot.venues.hyperliquid.trader.HyperliquidClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            
            trader = HyperliquidTrader()
            assert trader.client is mock_instance
    
    @patch("bot.venues.hyperliquid.trader.get_settings")
    def test_init_loads_signer_from_settings(self, mock_get_settings):
        """Test that signer is loaded from settings."""
        mock_settings = MagicMock()
        mock_settings.wallet_address = "0x" + "a" * 40
        mock_settings.privy_app_id = "test-app-id"
        mock_get_settings.return_value = mock_settings
        
        with patch("bot.venues.hyperliquid.trader.HyperliquidSigner") as mock_signer:
            mock_signer_instance = MagicMock()
            mock_signer.return_value = mock_signer_instance
            
            trader = HyperliquidTrader()
            assert trader.signer is mock_signer_instance


class TestUpdateLeverage:
    """Tests for leverage updates."""
    
    @pytest.mark.asyncio
    async def test_update_leverage_no_signer(self):
        """Test leverage update without signer."""
        trader = HyperliquidTrader()
        trader.signer = None
        
        result = await trader.update_leverage("SOL", 5)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_update_leverage_not_implemented(self):
        """Test leverage update returns False (not implemented with Privy)."""
        signer = MagicMock(spec=HyperliquidSigner)
        signer.wallet_address = "0x" + "a" * 40

        client = MagicMock(spec=HyperliquidClient)

        trader = HyperliquidTrader(client=client, signer=signer)
        
        result = await trader.update_leverage("SOL", 5)
        
        assert result is False


class TestGetPosition:
    """Tests for position queries."""
    
    @pytest.mark.asyncio
    async def test_get_position_exists(self):
        """Test getting existing position."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_clearinghouse_state = AsyncMock(return_value={
            "assetPositions": [
                {
                    "position": {
                        "coin": "SOL",
                        "szi": "-10.5",
                        "entryPx": "100.0",
                        "leverage": {"value": "3"},
                        "marginUsed": "350.0",
                        "marginFraction": "0.25",
                        "unrealizedPnl": "50.0",
                        "liquidationPx": "150.0",
                    }
                }
            ]
        })

        trader = HyperliquidTrader(client=client, wallet_address="0x123")
        position = await trader.get_position("SOL")

        assert position is not None
        assert position.coin == "SOL"
        assert position.size == -10.5
        assert position.entry_px == 100.0
        assert position.leverage == 3

    @pytest.mark.asyncio
    async def test_get_position_not_exists(self):
        """Test getting non-existent position."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_clearinghouse_state = AsyncMock(return_value={
            "assetPositions": []
        })

        trader = HyperliquidTrader(client=client, wallet_address="0x123")
        position = await trader.get_position("SOL")

        assert position is None

    @pytest.mark.asyncio
    async def test_get_position_no_address(self):
        """Test getting position without wallet address."""
        trader = HyperliquidTrader(wallet_address=None)
        trader.signer = None
        trader.wallet_address = None
        position = await trader.get_position("SOL")

        assert position is None


class TestCloseShort:
    """Tests for closing short positions."""
    
    @pytest.mark.asyncio
    async def test_close_short_success(self):
        """Test successful close."""
        signer = MagicMock(spec=HyperliquidSigner)
        signer.wallet_address = "0x" + "a" * 40
        signer.sign_order = AsyncMock(return_value=MagicMock(
            coin="SOL",
            is_buy=True,
            sz="10.0",
            limit_px="0",
            order_type={"market": {}},
            reduce_only=True,
            signature="0xsignature",
            nonce=123456,
        ))

        client = MagicMock(spec=HyperliquidClient)
        client.exchange = AsyncMock(return_value={
            "status": "ok",
            "response": {"filledSz": "10.0"}
        })

        trader = HyperliquidTrader(client=client, signer=signer)
        
        result = await trader.close_short("SOL", "10.0")
        
        assert result.success is True
        assert result.filled_sz == "10.0"
    
    @pytest.mark.asyncio
    async def test_close_short_no_signer(self):
        """Test close without signer."""
        trader = HyperliquidTrader()
        trader.signer = None
        
        result = await trader.close_short("SOL", "10.0")
        
        assert result.success is False
        assert "Signer not configured" in result.error


class TestStopLossLogic:
    """Tests for stop-loss logic."""
    
    @pytest.mark.asyncio
    async def test_check_stop_loss_not_triggered(self):
        """Test stop-loss not triggered."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_all_mids = AsyncMock(return_value={"SOL": 95.0})
        
        trader = HyperliquidTrader(client=client)
        
        result = await trader._check_stop_loss(
            coin="SOL",
            entry_price=100.0,
            stop_loss_price=105.0,  # 5% stop for short
            is_short=True,
        )
        
        assert result.triggered is False
        assert result.current_price == 95.0
    
    @pytest.mark.asyncio
    async def test_check_stop_loss_triggered(self):
        """Test stop-loss triggered for short."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_all_mids = AsyncMock(return_value={"SOL": 106.0})
        
        trader = HyperliquidTrader(client=client)
        
        result = await trader._check_stop_loss(
            coin="SOL",
            entry_price=100.0,
            stop_loss_price=105.0,  # 5% stop
            is_short=True,
        )
        
        assert result.triggered is True
        assert result.current_price == 106.0
        assert result.move_pct == pytest.approx(0.06, abs=0.01)  # 6% move


class TestGetCurrentPrice:
    """Tests for price fetching."""
    
    @pytest.mark.asyncio
    async def test_get_current_price_success(self):
        """Test successful price fetch."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_all_mids = AsyncMock(return_value={"SOL": 100.5, "ETH": 2000.0})
        
        trader = HyperliquidTrader(client=client)
        
        price = await trader._get_current_price("SOL")
        
        assert price == 100.5
    
    @pytest.mark.asyncio
    async def test_get_current_price_not_found(self):
        """Test price not available."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_all_mids = AsyncMock(return_value={"ETH": 2000.0})
        
        trader = HyperliquidTrader(client=client)
        
        price = await trader._get_current_price("SOL")
        
        assert price is None


class TestPositionInfo:
    """Tests for PositionInfo dataclass."""
    
    def test_position_info_creation(self):
        """Test PositionInfo creation."""
        pos = PositionInfo(
            coin="SOL",
            size=-10.5,
            entry_px=100.0,
            leverage=3,
            margin_used=350.0,
            margin_fraction=0.25,
            unrealized_pnl=50.0,
            liquidation_px=150.0,
        )
        
        assert pos.coin == "SOL"
        assert pos.size == -10.5  # Negative for short
        assert pos.liquidation_px == 150.0
    
    def test_position_info_optional_liquidation(self):
        """Test PositionInfo without liquidation price."""
        pos = PositionInfo(
            coin="ETH",
            size=5.0,
            entry_px=2000.0,
            leverage=2,
            margin_used=5000.0,
            margin_fraction=0.30,
            unrealized_pnl=-100.0,
            liquidation_px=None,
        )
        
        assert pos.liquidation_px is None


class TestStopLossTrigger:
    """Tests for StopLossTrigger dataclass."""
    
    def test_stop_loss_trigger_creation(self):
        """Test StopLossTrigger creation."""
        trigger = StopLossTrigger(
            triggered=True,
            trigger_price=105.0,
            current_price=106.0,
            move_pct=0.06,
        )
        
        assert trigger.triggered is True
        assert trigger.trigger_price == 105.0
        assert trigger.current_price == 106.0
        assert trigger.move_pct == 0.06


class TestOrderResult:
    """Tests for OrderResult dataclass."""
    
    def test_order_result_success(self):
        """Test successful OrderResult."""
        result = OrderResult(
            success=True,
            order_id="order123",
            filled_sz="10.0",
            avg_px="100.0",
        )
        
        assert result.success is True
        assert result.order_id == "order123"
        assert result.error is None
    
    def test_order_result_failure(self):
        """Test failed OrderResult."""
        result = OrderResult(
            success=False,
            error="Insufficient margin",
        )

        assert result.success is False
        assert result.error == "Insufficient margin"


class TestPerUserWallet:
    """Tests for per-user wallet address support."""

    def test_init_with_wallet_address(self):
        """Test initialization with explicit wallet address."""
        client = MagicMock(spec=HyperliquidClient)
        with patch("bot.venues.hyperliquid.trader.HyperliquidSigner") as mock_signer_cls:
            mock_signer_instance = MagicMock()
            mock_signer_instance.wallet_address = "0xUserWallet"
            mock_signer_cls.return_value = mock_signer_instance

            trader = HyperliquidTrader(
                client=client,
                wallet_address="0xUserWallet",
                user_id="user_123",
            )

            assert trader.wallet_address == "0xUserWallet"
            assert trader.user_id == "user_123"
            mock_signer_cls.assert_called_once_with(
                wallet_address="0xUserWallet",
                user_id="user_123",
            )

    def test_init_with_signer_inherits_wallet(self):
        """Test that wallet_address is inherited from signer when not provided."""
        signer = MagicMock(spec=HyperliquidSigner)
        signer.wallet_address = "0xSignerWallet"

        client = MagicMock(spec=HyperliquidClient)
        trader = HyperliquidTrader(client=client, signer=signer)

        assert trader.wallet_address == "0xSignerWallet"

    def test_init_wallet_address_overrides_signer(self):
        """Test that explicit wallet_address takes priority over signer's."""
        signer = MagicMock(spec=HyperliquidSigner)
        signer.wallet_address = "0xSignerWallet"

        client = MagicMock(spec=HyperliquidClient)
        trader = HyperliquidTrader(
            client=client,
            signer=signer,
            wallet_address="0xExplicitWallet",
        )

        assert trader.wallet_address == "0xExplicitWallet"

    @pytest.mark.asyncio
    async def test_get_position_uses_instance_wallet(self):
        """Test that get_position uses the instance wallet, not settings."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_clearinghouse_state = AsyncMock(return_value={
            "assetPositions": [
                {"position": {
                    "coin": "SOL", "szi": "-5.0", "entryPx": "100.0",
                    "leverage": {"value": "3"}, "marginUsed": "166.0",
                    "marginFraction": "0.30", "unrealizedPnl": "10.0",
                }}
            ]
        })

        trader = HyperliquidTrader(client=client, wallet_address="0xMyWallet")
        position = await trader.get_position("SOL")

        client.get_clearinghouse_state.assert_called_once_with("0xMyWallet")
        assert position is not None
        assert position.size == -5.0

    @pytest.mark.asyncio
    async def test_get_deposited_balance_uses_instance_wallet(self):
        """Test that get_deposited_balance uses the instance wallet."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_clearinghouse_state = AsyncMock(return_value={
            "balances": [{"coin": "USDC", "total": 5000000000}]
        })

        trader = HyperliquidTrader(client=client, wallet_address="0xMyWallet")
        balance = await trader.get_deposited_balance()

        client.get_clearinghouse_state.assert_called_once_with("0xMyWallet")
        assert balance == 5000.0


class TestTransferSpotToPerp:
    """Tests for the renamed transfer_spot_to_perp (formerly deposit_usdc)."""

    @pytest.mark.asyncio
    async def test_transfer_spot_to_perp_success(self):
        """Test successful spot-to-perp transfer."""
        signer = MagicMock(spec=HyperliquidSigner)
        signer.wallet_address = "0x" + "a" * 40
        signer.address = "0x" + "a" * 40
        signer.sign_spot_transfer = AsyncMock(return_value=MagicMock(
            usdc_amount="1000000000",
            signature="0xsignature",
            nonce=123456,
        ))

        client = MagicMock(spec=HyperliquidClient)
        client.exchange = AsyncMock(return_value={
            "status": "ok",
        })

        trader = HyperliquidTrader(client=client, signer=signer)
        result = await trader.transfer_spot_to_perp(1000.0)

        assert result is True
        signer.sign_spot_transfer.assert_called_once()

    @pytest.mark.asyncio
    async def test_transfer_spot_to_perp_no_signer(self):
        """Test that transfer fails without signer."""
        trader = HyperliquidTrader()
        trader.signer = None

        result = await trader.transfer_spot_to_perp(1000.0)

        assert result is False

    @pytest.mark.asyncio
    async def test_transfer_spot_to_perp_exchange_error(self):
        """Test transfer fails when exchange returns error."""
        signer = MagicMock(spec=HyperliquidSigner)
        signer.wallet_address = "0x" + "a" * 40
        signer.address = "0x" + "a" * 40
        signer.sign_spot_transfer = AsyncMock(return_value=MagicMock(
            usdc_amount="1000000000",
            signature="0xsignature",
            nonce=123456,
        ))

        client = MagicMock(spec=HyperliquidClient)
        client.exchange = AsyncMock(return_value={
            "status": "error",
            "response": "insufficient balance",
        })

        trader = HyperliquidTrader(client=client, signer=signer)
        result = await trader.transfer_spot_to_perp(1000.0)

        assert result is False

    def test_deposit_usdc_no_longer_exists(self):
        """Verify the old deposit_usdc name no longer exists."""
        assert not hasattr(HyperliquidTrader, "deposit_usdc")
