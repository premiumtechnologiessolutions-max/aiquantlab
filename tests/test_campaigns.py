from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from ai_quant_lab.campaigns import latest_campaign, run_research_campaign
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.data.storage import ParquetMarketStore
from ai_quant_lab.validation import ValidationPolicy


def make_campaign_bars(count: int = 100) -> tuple[MarketBar, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars: list[MarketBar] = []

    for index in range(count):
        wave = ((index % 16) - 8) * 0.00012
        close = 1.1 + index * 0.00002 + wave
        open_price = close - 0.00003
        bars.append(
            MarketBar(
                pair="EURUSD",
                timeframe="M15",
                timestamp=start + timedelta(minutes=15 * index),
                open=open_price,
                high=max(open_price, close) + 0.0002,
                low=min(open_price, close) - 0.0002,
                close=close,
                tick_volume=1_000,
                spread_points=5,
            )
        )

    return tuple(bars)


def test_campaign_runs_ranks_and_persists_multiple_strategies(tmp_path: Path) -> None:
    data_root = tmp_path / "processed"
    campaign_root = tmp_path / "campaigns"
    ParquetMarketStore(data_root).write_bars(make_campaign_bars())
    result = run_research_campaign(
        pair="EURUSD",
        timeframe="M15",
        strategy_names=("ema_crossover", "rsi_mean_reversion"),
        data_root=data_root,
        experiment_root=tmp_path / "experiments",
        campaign_root=campaign_root,
        validation_policy=ValidationPolicy(
            minimum_trades=1,
            minimum_profit_factor=0,
            minimum_sharpe_ratio=-100,
            maximum_drawdown_percent=100,
        ),
    )

    assert len(result.entries) == 2
    assert tuple(entry.rank for entry in result.entries) == (1, 2)
    assert result.research_leader == result.entries[0].strategy_name
    assert result.live_trading_eligible is False
    assert result.json_path.exists()
    assert result.markdown_path.exists()
    assert latest_campaign(campaign_root) == result
