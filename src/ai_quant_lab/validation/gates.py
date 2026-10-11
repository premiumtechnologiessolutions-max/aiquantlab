from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.backtesting import BacktestResult


class CheckStatus(StrEnum):
    """Outcome of one independent research validation check."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


class ValidationPolicy(BaseModel):
    """Minimum quantitative gates for a strategy research candidate."""

    model_config = ConfigDict(frozen=True)

    minimum_trades: int = Field(default=30, ge=1)
    minimum_profit_factor: float = Field(default=1.05, ge=0)
    minimum_sharpe_ratio: float = 0.25
    maximum_drawdown_percent: float = Field(default=20.0, gt=0, le=100)


class ValidationCheck(BaseModel):
    """Auditable result of one named validation gate."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    status: CheckStatus
    detail: str = Field(min_length=1)


class ValidationReport(BaseModel):
    """Independent summary that never promotes a backtest directly to live."""

    model_config = ConfigDict(frozen=True)

    passed_quantitative_gates: bool
    eligible_for_shadow: bool = False
    eligible_for_paper: bool = False
    eligible_for_live_trading: bool = False
    checks: tuple[ValidationCheck, ...]


def validate_backtest(
    result: BacktestResult,
    policy: ValidationPolicy | None = None,
    *,
    stage_evidence: tuple[ValidationCheck, ...] = (),
) -> ValidationReport:
    """Evaluate basic metrics and record every still-required safety stage."""

    resolved_policy = policy or ValidationPolicy()
    metrics = result.metrics
    checks = [
        _threshold_check(
            name="minimum_trades",
            passed=metrics.trade_count >= resolved_policy.minimum_trades,
            detail=(
                f"Observed {metrics.trade_count}; required at least "
                f"{resolved_policy.minimum_trades}."
            ),
        ),
        _threshold_check(
            name="profit_factor",
            passed=metrics.profit_factor >= resolved_policy.minimum_profit_factor,
            detail=(
                f"Observed {metrics.profit_factor:.4f}; required at least "
                f"{resolved_policy.minimum_profit_factor:.4f}."
            ),
        ),
        _threshold_check(
            name="sharpe_ratio",
            passed=metrics.sharpe_ratio >= resolved_policy.minimum_sharpe_ratio,
            detail=(
                f"Observed {metrics.sharpe_ratio:.4f}; required at least "
                f"{resolved_policy.minimum_sharpe_ratio:.4f}."
            ),
        ),
        _threshold_check(
            name="maximum_drawdown",
            passed=(
                metrics.maximum_drawdown_percent
                <= resolved_policy.maximum_drawdown_percent
            ),
            detail=(
                f"Observed {metrics.maximum_drawdown_percent:.4f}%; allowed at most "
                f"{resolved_policy.maximum_drawdown_percent:.4f}%."
            ),
        ),
        ValidationCheck(
            name="look_ahead_execution",
            status=(CheckStatus.PASSED if result.signal_lag_bars >= 1 else CheckStatus.FAILED),
            detail=f"Signals are executed with a {result.signal_lag_bars}-bar lag.",
        ),
    ]

    quantitative_passed = all(check.status is CheckStatus.PASSED for check in checks)

    stage_defaults = (
            (
                "out_of_sample",
                "A dedicated chronological out-of-sample run is required before promotion.",
            ),
            (
                "walk_forward",
                "Walk-forward testing is required before promotion.",
            ),
            (
                "monte_carlo",
                "Monte Carlo trade-order analysis is required before promotion.",
            ),
            (
                "parameter_stability",
                "Neighboring parameter sets must be tested before promotion.",
            ),
            (
                "shadow_trading",
                "Shadow trading has not been completed.",
            ),
            (
                "paper_trading",
                "Paper trading and human approval are still required.",
            ),
        )
    evidence_by_name = {check.name: check for check in stage_evidence}
    allowed_stage_names = {name for name, _ in stage_defaults}
    unsupported = evidence_by_name.keys() - allowed_stage_names

    if unsupported:
        raise ValueError(
            "Unsupported validation stage evidence: "
            f"{', '.join(sorted(unsupported))}.",
        )

    checks.extend(
        evidence_by_name.get(name)
        or ValidationCheck(
            name=name,
            status=CheckStatus.NOT_RUN,
            detail=detail,
        )
        for name, detail in stage_defaults
    )
    completed_by_name = {check.name: check.status for check in checks}
    eligible_for_shadow = quantitative_passed and all(
        completed_by_name[name] is CheckStatus.PASSED
        for name in (
            "out_of_sample",
            "walk_forward",
            "monte_carlo",
            "parameter_stability",
        )
    )
    eligible_for_paper = (
        eligible_for_shadow
        and completed_by_name["shadow_trading"] is CheckStatus.PASSED
    )

    return ValidationReport(
        passed_quantitative_gates=quantitative_passed,
        eligible_for_shadow=eligible_for_shadow,
        eligible_for_paper=eligible_for_paper,
        checks=tuple(checks),
    )


def _threshold_check(
    *,
    name: str,
    passed: bool,
    detail: str,
) -> ValidationCheck:
    """Build one readable pass/fail threshold result."""

    return ValidationCheck(
        name=name,
        status=(CheckStatus.PASSED if passed else CheckStatus.FAILED),
        detail=detail,
    )
