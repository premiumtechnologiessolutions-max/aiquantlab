from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ai_quant_lab.broker import (
    DemoGatewayConfig,
    DemoOrderIntent,
    DemoOrderSide,
    DemoTradingBlockedError,
    MT5DemoGateway,
)


class FakeTradingApi:
    """Deterministic MT5 API double covering demo connection and orders."""

    ACCOUNT_TRADE_MODE_DEMO = 0
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_PLACED = 10008
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440

    def __init__(self, *, trade_mode: int = 0, now: datetime | None = None) -> None:
        self.trade_mode = trade_mode
        self.now = now or datetime.now(UTC)
        self.shutdown_count = 0
        self.order_requests: list[dict[str, object]] = []

    def initialize(self, *args: object, **kwargs: object) -> bool:
        del args, kwargs
        return True

    def shutdown(self) -> None:
        self.shutdown_count += 1

    def last_error(self) -> tuple[int, str]:
        return (0, "ok")

    def account_info(self) -> SimpleNamespace:
        return SimpleNamespace(
            trade_mode=self.trade_mode,
            login=12345678,
            server="Broker-Demo",
            name="Test User",
            currency="USD",
            balance=10_000.0,
            equity=10_025.0,
            margin_free=9_800.0,
            leverage=100,
            trade_allowed=True,
        )

    def terminal_info(self) -> SimpleNamespace:
        return SimpleNamespace(connected=True)

    def symbol_select(self, symbol: str, enable: bool) -> bool:
        del symbol, enable
        return True

    def symbol_info(self, symbol: str) -> SimpleNamespace:
        del symbol
        return SimpleNamespace(
            point=0.00001,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
        )

    def symbol_info_tick(self, symbol: str) -> SimpleNamespace:
        del symbol
        return SimpleNamespace(
            time=int(self.now.timestamp()),
            bid=1.10000,
            ask=1.10010,
        )

    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe: int,
        start_pos: int,
        count: int,
    ) -> list[dict[str, float | int]]:
        del symbol, timeframe, start_pos
        start = self.now - timedelta(minutes=15 * count)

        return [
            {
                "time": int((start + timedelta(minutes=15 * index)).timestamp()),
                "open": 1.1 + index * 0.00005,
                "high": 1.1003 + index * 0.00005,
                "low": 1.0998 + index * 0.00005,
                "close": 1.1001 + index * 0.00005,
                "tick_volume": 1_000 + index,
                "real_volume": 100,
                "spread": 10,
            }
            for index in range(count)
        ]

    def positions_get(self, *args: object, **kwargs: object) -> tuple[SimpleNamespace, ...]:
        del args, kwargs
        return (
            SimpleNamespace(
                ticket=77,
                symbol="EURUSD",
                type=self.ORDER_TYPE_BUY,
                volume=0.01,
                price_open=1.1,
                price_current=1.1002,
                sl=1.099,
                tp=1.102,
                profit=2.0,
            ),
        )

    def order_check(self, request: dict[str, object]) -> SimpleNamespace:
        self.order_requests.append(request)
        return SimpleNamespace(retcode=0, comment="check passed")

    def order_send(self, request: dict[str, object]) -> SimpleNamespace:
        self.order_requests.append(request)
        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE,
            comment="done",
            order=501,
            deal=502,
            price=request["price"],
        )


class StructuredRateTradingApi(FakeTradingApi):
    """MT5 double returning the NumPy structured rows used by the real package."""

    def copy_rates_from_pos(
        self,
        symbol: str,
        timeframe: int,
        start_pos: int,
        count: int,
    ) -> np.ndarray:
        mapping_rates = super().copy_rates_from_pos(symbol, timeframe, start_pos, count)
        field_names = (
            "time",
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
            "spread",
            "real_volume",
        )
        dtype = [
            ("time", "<i8"),
            ("open", "<f8"),
            ("high", "<f8"),
            ("low", "<f8"),
            ("close", "<f8"),
            ("tick_volume", "<u8"),
            ("spread", "<i4"),
            ("real_volume", "<u8"),
        ]

        return np.array(
            [tuple(rate[name] for name in field_names) for rate in mapping_rates],
            dtype=dtype,
        )


def demo_config(tmp_path: Path, *, orders: bool = False) -> DemoGatewayConfig:
    return DemoGatewayConfig(
        login=12345678,
        password="never-persist-this",
        server="Broker-Demo",
        demo_orders_enabled=orders,
        audit_database=tmp_path / "audit.sqlite3",
    )


def test_gateway_blocks_non_demo_accounts_before_reading_market(tmp_path: Path) -> None:
    api = FakeTradingApi(trade_mode=2)
    gateway = MT5DemoGateway(demo_config(tmp_path), api=api)

    with pytest.raises(DemoTradingBlockedError, match="demo accounts only"):
        gateway.connect()

    assert api.shutdown_count == 1
    assert gateway.status().connected is False
    assert gateway.audit.recent()[0].event_type == "real_account_blocked"


def test_gateway_rechecks_mode_and_blocks_account_switch(tmp_path: Path) -> None:
    api = FakeTradingApi()
    gateway = MT5DemoGateway(demo_config(tmp_path), api=api)
    gateway.connect()
    api.trade_mode = 2

    with pytest.raises(DemoTradingBlockedError, match="demo accounts only"):
        gateway.latest_quote("EURUSD")

    assert gateway.status().connected is False
    assert api.shutdown_count == 1


def test_gateway_reads_sanitized_demo_account_quote_bars_and_positions(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC)
    gateway = MT5DemoGateway(demo_config(tmp_path), api=FakeTradingApi(now=now))
    account = gateway.connect()
    quote = gateway.latest_quote("EURUSD")
    bars = gateway.recent_bars("EURUSD", "M15", count=60)
    positions = gateway.positions()

    assert account.account_type == "demo"
    assert account.login_last_four == "5678"
    assert quote.spread_points == pytest.approx(10)
    assert len(bars) == 60
    assert bars == tuple(sorted(bars, key=lambda bar: bar.timestamp))
    assert positions[0].ticket == 77
    assert "password" not in gateway.config.model_dump()


def test_gateway_reads_real_mt5_numpy_structured_rate_rows(tmp_path: Path) -> None:
    gateway = MT5DemoGateway(demo_config(tmp_path), api=StructuredRateTradingApi())
    gateway.connect()

    bars = gateway.recent_bars("EURUSD", "M15", count=60)

    assert len(bars) == 60
    assert bars[0].timestamp < bars[-1].timestamp
    assert bars[-1].tick_volume > 0


def test_demo_order_requires_switch_phrase_risk_limits_and_verified_account(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    api = FakeTradingApi(now=now)
    disabled = MT5DemoGateway(demo_config(tmp_path, orders=False), api=api)
    disabled.connect()
    intent = DemoOrderIntent(
        pair="EURUSD",
        side=DemoOrderSide.BUY,
        volume_lots=0.01,
        stop_loss_points=100,
        take_profit_points=150,
    )

    with pytest.raises(DemoTradingBlockedError, match="disabled"):
        disabled.place_market_order(intent, confirmation="DEMO ONLY", observed_at=now)

    enabled = MT5DemoGateway(
        demo_config(tmp_path / "enabled", orders=True),
        api=FakeTradingApi(now=now),
    )
    enabled.connect()

    with pytest.raises(DemoTradingBlockedError, match="confirmation"):
        enabled.place_market_order(intent, confirmation="yes", observed_at=now)

    receipt = enabled.place_market_order(intent, confirmation="DEMO ONLY", observed_at=now)

    assert receipt.order_id == 501
    assert receipt.deal_id == 502
    assert receipt.side is DemoOrderSide.BUY
    assert enabled.audit.recent()[0].event_type == "demo_order_sent"
