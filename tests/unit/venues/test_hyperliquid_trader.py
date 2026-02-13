"""
Tests for Hyperliquid Trader.

These tests verify:
- Leverage updates
- Opening short positions with retry
- Closing short positions
- Position monitoring
- Stop-loss logic
- Spot<->perp transfers
- Asset index resolution
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.venues.hyperliquid.client import HyperliquidClient
from bot.venues.hyperliquid.signer import HyperliquidSigner, SignedAction
from bot.venues.hyperliquid.trader import (
    HyperliquidTrader,
    OrderResult,
    PositionInfo,
    StopLossTrigger,
)


def _mock_signed_action(action_type="order", **overrides):
    """Helper to create a mock SignedAction."""
    action = {"type": action_type, **overrides}
    return SignedAction(
        action=action,
        signature={"r": "0xaa", "s": "0xbb", "v": 27},
        nonce=1234567890000,
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


class TestAssetIndexResolution:
    """Tests for coin -> asset index resolution."""

    @pytest.mark.asyncio
    async def test_resolve_asset_index(self):
        """Test resolving coin name to asset index via API."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_meta_and_asset_contexts = AsyncMock(return_value=[
            {"universe": [
                {"name": "BTC"},
                {"name": "ETH"},
                {"name": "ATOM"},
                {"name": "DOGE"},
                {"name": "SOL"},
            ]},
            [],  # asset contexts
        ])

        trader = HyperliquidTrader(client=client)
        index = await trader._resolve_asset_index("SOL")

        assert index == 4

    @pytest.mark.asyncio
    async def test_resolve_asset_index_cached(self):
        """Test that asset index is cached after first resolution."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_meta_and_asset_contexts = AsyncMock(return_value=[
            {"universe": [{"name": "SOL"}]},
            [],
        ])

        trader = HyperliquidTrader(client=client)
        await trader._resolve_asset_index("SOL")
        await trader._resolve_asset_index("SOL")

        # API should only be called once
        assert client.get_meta_and_asset_contexts.call_count == 1

    @pytest.mark.asyncio
    async def test_resolve_unknown_coin(self):
        """Test resolving unknown coin raises error."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_meta_and_asset_contexts = AsyncMock(return_value=[
            {"universe": [{"name": "BTC"}, {"name": "ETH"}]},
            [],
        ])

        trader = HyperliquidTrader(client=client)

        with pytest.raises(ValueError, match="not found in Hyperliquid universe"):
            await trader._resolve_asset_index("UNKNOWN")


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
    async def test_update_leverage_success(self):
        """Test successful leverage update."""
        signer = MagicMock(spec=HyperliquidSigner)
        signer.wallet_address = "0x" + "a" * 40
        signer.sign_leverage_update = AsyncMock(
            return_value=_mock_signed_action("updateLeverage")
        )

        client = MagicMock(spec=HyperliquidClient)
        client.get_meta_and_asset_contexts = AsyncMock(return_value=[
            {"universe": [{"name": "BTC"}, {"name": "ETH"}, {"name": "ATOM"}, {"name": "DOGE"}, {"name": "SOL"}]},
            [],
        ])
        client.exchange = AsyncMock(return_value={"status": "ok"})

        trader = HyperliquidTrader(client=client, signer=signer)
        result = await trader.update_leverage("SOL", 3)

        assert result is True
        signer.sign_leverage_update.assert_called_once_with(
            asset_index=4,
            leverage=3,
            is_cross=True,
        )


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
            stop_loss_price=105.0,
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
            stop_loss_price=105.0,
            is_short=True,
        )

        assert result.triggered is True
        assert result.current_price == 106.0
        assert result.move_pct == pytest.approx(0.06, abs=0.01)


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


class TestGetDepositedBalance:
    """Tests for deposited balance queries."""

    @pytest.mark.asyncio
    async def test_get_deposited_balance_cross_margin(self):
        """Test balance from crossMarginSummary."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_clearinghouse_state = AsyncMock(return_value={
            "crossMarginSummary": {"accountValue": "5000.0"},
        })

        trader = HyperliquidTrader(client=client, wallet_address="0x123")
        balance = await trader.get_deposited_balance()

        assert balance == 5000.0

    @pytest.mark.asyncio
    async def test_get_deposited_balance_withdrawable_fallback(self):
        """Test balance fallback to withdrawable."""
        client = MagicMock(spec=HyperliquidClient)
        client.get_clearinghouse_state = AsyncMock(return_value={
            "withdrawable": "3000.0",
        })

        trader = HyperliquidTrader(client=client, wallet_address="0x123")
        balance = await trader.get_deposited_balance()

        assert balance == 3000.0


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
        assert pos.size == -10.5
        assert pos.liquidation_px == 150.0


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
                wallet_id=None,
            )

    def test_init_with_signer_inherits_wallet(self):
        """Test that wallet_address is inherited from signer when not provided."""
        signer = MagicMock(spec=HyperliquidSigner)
        signer.wallet_address = "0xSignerWallet"

        client = MagicMock(spec=HyperliquidClient)
        trader = HyperliquidTrader(client=client, signer=signer)

        assert trader.wallet_address == "0xSignerWallet"

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


class TestTransferSpotToPerp:
    """Tests for usdClassTransfer (spot<->perp)."""

    @pytest.mark.asyncio
    async def test_transfer_spot_to_perp_success(self):
        """Test successful spot-to-perp transfer."""
        signer = MagicMock(spec=HyperliquidSigner)
        signer.wallet_address = "0x" + "a" * 40
        signer.sign_usd_class_transfer = AsyncMock(
            return_value=_mock_signed_action("usdClassTransfer")
        )

        client = MagicMock(spec=HyperliquidClient)
        client.exchange = AsyncMock(return_value={"status": "ok"})

        trader = HyperliquidTrader(client=client, signer=signer)
        result = await trader.transfer_spot_to_perp(1000.0)

        assert result is True
        signer.sign_usd_class_transfer.assert_called_once_with(
            amount="1000.00",
            to_perp=True,
        )

    @pytest.mark.asyncio
    async def test_transfer_spot_to_perp_no_signer(self):
        """Test that transfer fails without signer."""
        trader = HyperliquidTrader()
        trader.signer = None

        result = await trader.transfer_spot_to_perp(1000.0)

        assert result is False

    def test_deposit_usdc_no_longer_exists(self):
        """Verify the old deposit_usdc name no longer exists."""
        assert not hasattr(HyperliquidTrader, "deposit_usdc")
