from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class BlueprintAvailability(StrEnum):
    """Truthful implementation/data state of an institutional strategy blueprint."""

    EXECUTABLE = "executable"
    RESEARCH_ENGINE = "research_engine"
    REQUIRES_ALIGNED_ASSETS = "requires_aligned_assets"
    REQUIRES_EXTERNAL_DATA = "requires_external_data"


class StrategyBlueprint(BaseModel):
    """A strategy family member with explicit data and implementation requirements."""

    model_config = ConfigDict(frozen=True)

    key: str
    family: str
    title: str
    hypothesis_class: str
    required_inputs: tuple[str, ...]
    suitable_regimes: tuple[str, ...]
    availability: BlueprintAvailability
    executable_strategy_name: str | None = None


def _blueprint(
    key: str,
    family: str,
    title: str,
    hypothesis_class: str,
    required_inputs: tuple[str, ...],
    suitable_regimes: tuple[str, ...],
    availability: BlueprintAvailability,
    executable_strategy_name: str | None = None,
) -> StrategyBlueprint:
    return StrategyBlueprint(
        key=key,
        family=family,
        title=title,
        hypothesis_class=hypothesis_class,
        required_inputs=required_inputs,
        suitable_regimes=suitable_regimes,
        availability=availability,
        executable_strategy_name=executable_strategy_name,
    )


INSTITUTIONAL_STRATEGY_BLUEPRINTS: tuple[StrategyBlueprint, ...] = (
    _blueprint(
        "tsmom",
        "trend",
        "Time-series momentum",
        "behavioral persistence",
        ("ohlcv",),
        ("trending_up", "trending_down"),
        BlueprintAvailability.EXECUTABLE,
        "time_series_momentum",
    ),
    _blueprint(
        "dual_momentum",
        "trend",
        "Dual momentum",
        "absolute and relative persistence",
        ("aligned_assets",),
        ("trending_up", "risk_on"),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
    _blueprint(
        "adaptive_donchian",
        "trend",
        "Adaptive Donchian breakout",
        "slow information diffusion",
        ("ohlcv",),
        ("trending_up", "trending_down", "high_volatility"),
        BlueprintAvailability.EXECUTABLE,
        "donchian_breakout",
    ),
    _blueprint(
        "vol_adjusted_trend",
        "trend",
        "Volatility-adjusted trend",
        "persistence under stable risk",
        ("ohlcv",),
        ("trending_up", "trending_down"),
        BlueprintAvailability.EXECUTABLE,
        "multi_horizon_vol_trend",
    ),
    _blueprint(
        "ma_ensemble",
        "trend",
        "Moving-average ensemble",
        "multi-horizon persistence",
        ("ohlcv",),
        ("trending_up", "trending_down"),
        BlueprintAvailability.EXECUTABLE,
        "ema_crossover",
    ),
    _blueprint(
        "kalman_trend",
        "trend",
        "Kalman latent trend",
        "state-space persistence",
        ("ohlcv",),
        ("trending_up", "trending_down", "transition"),
        BlueprintAvailability.EXECUTABLE,
        "kalman_adaptive_trend",
    ),
    _blueprint(
        "adaptive_zscore",
        "mean_reversion",
        "Adaptive Z-score reversion",
        "temporary price dislocation",
        ("ohlcv",),
        ("mean_reverting", "low_volatility"),
        BlueprintAvailability.EXECUTABLE,
        "zscore_mean_reversion",
    ),
    _blueprint(
        "ou_process",
        "mean_reversion",
        "Ornstein–Uhlenbeck process",
        "stationary spread convergence",
        ("ohlcv",),
        ("mean_reverting", "low_volatility"),
        BlueprintAvailability.RESEARCH_ENGINE,
        "kalman_mean_reversion",
    ),
    _blueprint(
        "kalman_reversion",
        "mean_reversion",
        "Kalman residual reversion",
        "latent fair-value convergence",
        ("ohlcv",),
        ("mean_reverting", "low_volatility"),
        BlueprintAvailability.EXECUTABLE,
        "kalman_mean_reversion",
    ),
    _blueprint(
        "vwap_reversion",
        "mean_reversion",
        "Intraday VWAP reversion",
        "inventory and execution pressure",
        ("trades", "real_volume"),
        ("mean_reverting",),
        BlueprintAvailability.REQUIRES_EXTERNAL_DATA,
    ),
    _blueprint(
        "residual_reversion",
        "mean_reversion",
        "Factor residual reversion",
        "temporary idiosyncratic dislocation",
        ("aligned_assets",),
        ("mean_reverting",),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
    _blueprint(
        "cointegration_eg",
        "statistical_arbitrage",
        "Engle–Granger pairs",
        "stable long-run relation",
        ("aligned_assets",),
        ("mean_reverting", "low_volatility"),
        BlueprintAvailability.RESEARCH_ENGINE,
    ),
    _blueprint(
        "cointegration_johansen",
        "statistical_arbitrage",
        "Johansen basket",
        "multi-asset equilibrium",
        ("aligned_assets",),
        ("mean_reverting",),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
    _blueprint(
        "kalman_hedge_ratio",
        "statistical_arbitrage",
        "Kalman hedge ratio",
        "time-varying relative value",
        ("aligned_assets",),
        ("mean_reverting", "transition"),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
    _blueprint(
        "pca_residual",
        "statistical_arbitrage",
        "PCA residual arbitrage",
        "common-factor residual convergence",
        ("aligned_assets",),
        ("mean_reverting",),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
    _blueprint(
        "lead_lag",
        "statistical_arbitrage",
        "Lead–lag relationships",
        "asynchronous information diffusion",
        ("trade_flow", "aligned_assets"),
        ("trending_up", "trending_down"),
        BlueprintAvailability.REQUIRES_EXTERNAL_DATA,
    ),
    _blueprint(
        "vol_breakout",
        "volatility",
        "Volatility breakout",
        "compression followed by expansion",
        ("ohlcv", "spread"),
        ("high_volatility", "transition"),
        BlueprintAvailability.EXECUTABLE,
        "volatility_breakout",
    ),
    _blueprint(
        "garch_forecast",
        "volatility",
        "GARCH forecast",
        "volatility clustering",
        ("ohlcv",),
        ("high_volatility", "low_volatility"),
        BlueprintAvailability.RESEARCH_ENGINE,
    ),
    _blueprint(
        "har_rv",
        "volatility",
        "HAR-RV forecast",
        "heterogeneous volatility horizons",
        ("intraday_bars",),
        ("high_volatility", "low_volatility"),
        BlueprintAvailability.RESEARCH_ENGINE,
    ),
    _blueprint(
        "garman_klass",
        "volatility",
        "Garman–Klass range breakout",
        "range-based volatility shock",
        ("ohlcv",),
        ("high_volatility",),
        BlueprintAvailability.EXECUTABLE,
        "garman_klass_vol_breakout",
    ),
    _blueprint(
        "realized_implied",
        "volatility",
        "Realized versus implied volatility",
        "variance risk premium",
        ("options_volatility", "ohlcv"),
        ("high_volatility", "low_volatility"),
        BlueprintAvailability.REQUIRES_EXTERNAL_DATA,
    ),
    _blueprint(
        "cross_momentum",
        "cross_sectional",
        "Cross-sectional momentum rank",
        "relative persistence",
        ("aligned_assets",),
        ("risk_on", "trending_up"),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
    _blueprint(
        "cross_reversal",
        "cross_sectional",
        "Cross-sectional reversal",
        "temporary relative dislocation",
        ("aligned_assets",),
        ("mean_reverting",),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
    _blueprint(
        "factor_neutral",
        "cross_sectional",
        "Factor-neutral portfolio",
        "idiosyncratic alpha isolation",
        ("aligned_assets", "factor_data"),
        ("risk_on", "risk_off"),
        BlueprintAvailability.REQUIRES_EXTERNAL_DATA,
    ),
    _blueprint(
        "cluster_rotation",
        "cross_sectional",
        "Cluster rotation",
        "relative regime leadership",
        ("aligned_assets",),
        ("risk_on", "transition"),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
    _blueprint(
        "order_book_imbalance",
        "microstructure",
        "Order-book imbalance",
        "short-horizon supply/demand pressure",
        ("order_book",),
        ("high_volatility", "liquidity_stress"),
        BlueprintAvailability.REQUIRES_EXTERNAL_DATA,
    ),
    _blueprint(
        "trade_flow_imbalance",
        "microstructure",
        "Trade-flow imbalance",
        "aggressive-flow persistence",
        ("trade_flow",),
        ("high_volatility",),
        BlueprintAvailability.REQUIRES_EXTERNAL_DATA,
    ),
    _blueprint(
        "spread_reversion",
        "microstructure",
        "Spread reversion",
        "liquidity normalization",
        ("bid_ask", "order_book"),
        ("liquidity_stress", "transition"),
        BlueprintAvailability.REQUIRES_EXTERNAL_DATA,
    ),
    _blueprint(
        "price_impact",
        "microstructure",
        "Short-term price impact",
        "temporary impact decay",
        ("trade_flow", "order_book"),
        ("high_volatility",),
        BlueprintAvailability.REQUIRES_EXTERNAL_DATA,
    ),
    _blueprint(
        "risk_parity",
        "portfolio",
        "Risk parity",
        "balanced marginal risk",
        ("aligned_assets",),
        ("risk_on", "risk_off", "transition"),
        BlueprintAvailability.RESEARCH_ENGINE,
    ),
    _blueprint(
        "hrp",
        "portfolio",
        "Hierarchical Risk Parity",
        "cluster-aware diversification",
        ("aligned_assets",),
        ("risk_on", "risk_off"),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
    _blueprint(
        "minimum_variance",
        "portfolio",
        "Minimum variance",
        "covariance-efficient allocation",
        ("aligned_assets",),
        ("low_volatility", "risk_off"),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
    _blueprint(
        "maximum_diversification",
        "portfolio",
        "Maximum diversification",
        "low-correlated risk allocation",
        ("aligned_assets",),
        ("risk_on", "risk_off"),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
    _blueprint(
        "black_litterman",
        "portfolio",
        "Black–Litterman",
        "uncertainty-weighted views",
        ("aligned_assets", "market_weights"),
        ("risk_on", "risk_off"),
        BlueprintAvailability.REQUIRES_EXTERNAL_DATA,
    ),
    _blueprint(
        "dynamic_correlation",
        "portfolio",
        "Dynamic correlation allocation",
        "regime-dependent diversification",
        ("aligned_assets",),
        ("transition", "risk_off"),
        BlueprintAvailability.REQUIRES_ALIGNED_ASSETS,
    ),
)


def strategy_blueprint_payload() -> tuple[dict[str, object], ...]:
    """Return every blueprint with its real implementation/data availability."""

    return tuple(item.model_dump(mode="json") for item in INSTITUTIONAL_STRATEGY_BLUEPRINTS)
