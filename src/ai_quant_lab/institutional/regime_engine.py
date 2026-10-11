from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from itertools import pairwise
from math import exp, log, pi, sqrt
from statistics import median

from pydantic import BaseModel, ConfigDict, Field

from ai_quant_lab.config import ForexPair, Timeframe
from ai_quant_lab.data.models import MarketBar
from ai_quant_lab.institutional.data_intelligence import DatasetQualityReport


class InstitutionalRegime(StrEnum):
    """Regime states used for research selection and risk throttling."""

    INSUFFICIENT_DATA = "insufficient_data"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    MEAN_REVERTING = "mean_reverting"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    LIQUIDITY_STRESS = "liquidity_stress"
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    TRANSITION = "transition"


class RegimeModelEvidence(BaseModel):
    """Named model output retained so Iris can explain its classification."""

    model_config = ConfigDict(frozen=True)

    model_name: str
    value: float
    interpretation: str
    parameters: dict[str, object] = Field(default_factory=dict)


class InstitutionalRegimeAssessment(BaseModel):
    """Probabilistic, causal regime assessment for one exact dataset version."""

    model_config = ConfigDict(frozen=True)

    assessment_id: str
    pair: ForexPair
    timeframe: Timeframe
    dataset_version_id: str
    regime: InstitutionalRegime
    confidence: float = Field(ge=0, le=1)
    transition_probability: float = Field(ge=0, le=1)
    probabilities: dict[InstitutionalRegime, float]
    estimated_started_at: datetime
    compatible_strategy_families: tuple[str, ...]
    evidence: tuple[RegimeModelEvidence, ...]
    unavailable_inputs: tuple[str, ...]
    generated_at: datetime


class InstitutionalRegimeEngine:
    """Blend causal HMM, GMM, change-point, Kalman, and liquidity evidence."""

    def assess(
        self,
        bars: Sequence[MarketBar],
        dataset: DatasetQualityReport,
        *,
        cross_asset_risk_score: float | None = None,
        macro_risk_score: float | None = None,
    ) -> InstitutionalRegimeAssessment:
        """Classify the latest completed bar using observations available by then."""

        if len(bars) < 40:
            return self._insufficient(bars, dataset)

        ordered = tuple(sorted(bars, key=lambda bar: bar.timestamp))
        log_prices = [log(bar.close) for bar in ordered]
        returns = [current - previous for previous, current in pairwise(log_prices)]
        recent_returns = returns[-min(160, len(returns)) :]
        normalized_returns = _robust_zscores(recent_returns)
        hmm_calibration = _hmm_filter(normalized_returns)
        hmm = hmm_calibration.probabilities
        high_volatility_probability = _gmm_high_volatility_probability(
            [abs(value) for value in returns],
        )
        change_probability = _bayesian_change_probability(recent_returns)
        kalman_slope = _kalman_normalized_slope(log_prices[-min(200, len(log_prices)) :])
        autocorrelation = _lag_one_autocorrelation(recent_returns)
        spread_stress = _spread_stress_probability(
            [bar.spread_points for bar in ordered[-min(200, len(ordered)) :]],
        )
        probabilities = {regime: 0.0 for regime in InstitutionalRegime}
        probabilities[InstitutionalRegime.TRENDING_UP] = hmm[2] * _sigmoid(kalman_slope)
        probabilities[InstitutionalRegime.TRENDING_DOWN] = hmm[0] * _sigmoid(-kalman_slope)
        probabilities[InstitutionalRegime.MEAN_REVERTING] = max(
            0.0,
            hmm[1] * (0.55 + max(0.0, -autocorrelation)),
        )
        probabilities[InstitutionalRegime.HIGH_VOLATILITY] = high_volatility_probability
        probabilities[InstitutionalRegime.LOW_VOLATILITY] = 1.0 - high_volatility_probability
        probabilities[InstitutionalRegime.LIQUIDITY_STRESS] = spread_stress
        probabilities[InstitutionalRegime.TRANSITION] = change_probability
        unavailable_inputs: list[str] = []

        if cross_asset_risk_score is None or macro_risk_score is None:
            unavailable_inputs.extend(
                name
                for name, value in (
                    ("cross_asset_risk_score", cross_asset_risk_score),
                    ("macro_risk_score", macro_risk_score),
                )
                if value is None
            )
        else:
            combined_risk = max(0.0, min(1.0, (cross_asset_risk_score + macro_risk_score) / 2))
            probabilities[InstitutionalRegime.RISK_OFF] = combined_risk
            probabilities[InstitutionalRegime.RISK_ON] = 1.0 - combined_risk

        regime = _select_regime(
            probabilities,
            change_probability=change_probability,
            spread_stress=spread_stress,
        )
        normalized_probabilities = _normalize_probabilities(probabilities)
        confidence = normalized_probabilities[regime]
        started_at = _estimate_regime_start(
            ordered,
            regime,
            high_volatility_probability=high_volatility_probability,
        )
        generated_at = datetime.now(UTC)
        assessment_key = (
            f"{dataset.dataset_version_id}|{regime.value}|{ordered[-1].timestamp.isoformat()}"
        )

        return InstitutionalRegimeAssessment(
            assessment_id=f"regime_{_stable_short_hash(assessment_key)}",
            pair=dataset.pair,
            timeframe=dataset.timeframe,
            dataset_version_id=dataset.dataset_version_id,
            regime=regime,
            confidence=confidence,
            transition_probability=change_probability,
            probabilities=normalized_probabilities,
            estimated_started_at=started_at,
            compatible_strategy_families=_compatible_families(regime),
            evidence=(
                RegimeModelEvidence(
                    model_name="three_state_gaussian_hmm",
                    value=max(hmm),
                    interpretation=(
                        "Pair-specific Baum-Welch calibration; filtered down/range/up "
                        f"probabilities = {hmm[0]:.3f}/{hmm[1]:.3f}/{hmm[2]:.3f}; "
                        f"means = {hmm_calibration.means[0]:.3f}/"
                        f"{hmm_calibration.means[1]:.3f}/{hmm_calibration.means[2]:.3f}; "
                        f"iterations = {hmm_calibration.iterations}."
                    ),
                    parameters={
                        "means": hmm_calibration.means,
                        "sigmas": hmm_calibration.sigmas,
                        "transition": hmm_calibration.transition,
                        "iterations": hmm_calibration.iterations,
                        "log_likelihood": hmm_calibration.log_likelihood,
                        "calibration_scope": f"{dataset.pair}:{dataset.timeframe}",
                    },
                ),
                RegimeModelEvidence(
                    model_name="two_component_gmm_volatility",
                    value=high_volatility_probability,
                    interpretation="Posterior probability of the high-volatility component.",
                ),
                RegimeModelEvidence(
                    model_name="bayesian_change_point",
                    value=change_probability,
                    interpretation=(
                        "Posterior odds of a mean shift between adjacent trailing windows."
                    ),
                ),
                RegimeModelEvidence(
                    model_name="local_linear_kalman_filter",
                    value=kalman_slope,
                    interpretation="Latent slope normalized by trailing innovation volatility.",
                ),
                RegimeModelEvidence(
                    model_name="lag_one_return_autocorrelation",
                    value=autocorrelation,
                    interpretation="Negative values support short-horizon mean reversion.",
                ),
                RegimeModelEvidence(
                    model_name="spread_liquidity_stress",
                    value=spread_stress,
                    interpretation=(
                        "Current spread stress relative to its trailing robust distribution."
                    ),
                ),
            ),
            unavailable_inputs=tuple(unavailable_inputs),
            generated_at=generated_at,
        )

    def _insufficient(
        self,
        bars: Sequence[MarketBar],
        dataset: DatasetQualityReport,
    ) -> InstitutionalRegimeAssessment:
        timestamp = bars[-1].timestamp if bars else datetime.now(UTC)

        return InstitutionalRegimeAssessment(
            assessment_id=f"regime_{_stable_short_hash(dataset.dataset_version_id + '|short')}",
            pair=dataset.pair,
            timeframe=dataset.timeframe,
            dataset_version_id=dataset.dataset_version_id,
            regime=InstitutionalRegime.INSUFFICIENT_DATA,
            confidence=1.0,
            transition_probability=0.0,
            probabilities={
                regime: (1.0 if regime is InstitutionalRegime.INSUFFICIENT_DATA else 0.0)
                for regime in InstitutionalRegime
            },
            estimated_started_at=timestamp,
            compatible_strategy_families=(),
            evidence=(
                RegimeModelEvidence(
                    model_name="minimum_history_gate",
                    value=float(len(bars)),
                    interpretation="At least 40 completed bars are required.",
                ),
            ),
            unavailable_inputs=("cross_asset_risk_score", "macro_risk_score"),
            generated_at=datetime.now(UTC),
        )


@dataclass(frozen=True)
class _GaussianHMMCalibration:
    probabilities: tuple[float, float, float]
    means: tuple[float, float, float]
    sigmas: tuple[float, float, float]
    transition: tuple[tuple[float, float, float], ...]
    iterations: int
    log_likelihood: float


def _hmm_filter(values: Sequence[float]) -> _GaussianHMMCalibration:
    """Fit and filter a pair-specific three-state Gaussian HMM with Baum-Welch."""

    sample = list(values[-min(400, len(values)) :])

    if len(sample) < 6:
        return _GaussianHMMCalibration(
            probabilities=(1 / 3, 1 / 3, 1 / 3),
            means=(-0.75, 0.0, 0.75),
            sigmas=(1.1, 0.75, 1.1),
            transition=(
                (0.94, 0.05, 0.01),
                (0.04, 0.92, 0.04),
                (0.01, 0.05, 0.94),
            ),
            iterations=0,
            log_likelihood=0.0,
        )

    ordered = sorted(sample)
    means = [
        ordered[max(0, int((len(ordered) - 1) * fraction))]
        for fraction in (0.2, 0.5, 0.8)
    ]
    overall_sigma = max(0.25, _standard_deviation(sample))
    sigmas = [overall_sigma, max(0.20, overall_sigma * 0.75), overall_sigma]
    transition = [
        [0.92, 0.07, 0.01],
        [0.04, 0.92, 0.04],
        [0.01, 0.07, 0.92],
    ]
    initial = [1 / 3, 1 / 3, 1 / 3]
    previous_log_likelihood = float("-inf")
    completed_iterations = 0

    for iteration in range(1, 31):
        emissions = [
            [max(1e-300, _normal_density(value, means[state], sigmas[state])) for state in range(3)]
            for value in sample
        ]
        alpha, scales = _scaled_forward(initial, transition, emissions)
        beta = _scaled_backward(transition, emissions, scales)
        gamma = [
            _normalize_row(
                [alpha[t][state] * beta[t][state] for state in range(3)]
            )
            for t in range(len(sample))
        ]
        xi_sums = [[0.0 for _ in range(3)] for _ in range(3)]

        for t in range(len(sample) - 1):
            raw = [
                [
                    alpha[t][source]
                    * transition[source][target]
                    * emissions[t + 1][target]
                    * beta[t + 1][target]
                    for target in range(3)
                ]
                for source in range(3)
            ]
            denominator = sum(sum(row) for row in raw)

            if denominator <= 0:
                continue

            for source in range(3):
                for target in range(3):
                    xi_sums[source][target] += raw[source][target] / denominator

        initial = list(gamma[0])

        for state in range(3):
            denominator = sum(gamma[t][state] for t in range(len(sample) - 1))
            row = [xi_sums[state][target] + 1e-4 for target in range(3)]
            row_total = denominator + 3e-4
            transition[state] = (
                [value / row_total for value in row]
                if row_total > 0
                else [1 / 3, 1 / 3, 1 / 3]
            )
            responsibility = sum(gamma[t][state] for t in range(len(sample)))

            if responsibility <= 1e-12:
                continue

            means[state] = (
                sum(gamma[t][state] * sample[t] for t in range(len(sample))) / responsibility
            )
            variance = (
                sum(
                    gamma[t][state] * (sample[t] - means[state]) ** 2
                    for t in range(len(sample))
                )
                / responsibility
            )
            sigmas[state] = max(0.10, sqrt(max(variance, 1e-8)))

        initial, transition, means, sigmas = _order_hmm_states(
            initial,
            transition,
            means,
            sigmas,
        )
        log_likelihood = sum(log(max(scale, 1e-300)) for scale in scales)
        completed_iterations = iteration

        if abs(log_likelihood - previous_log_likelihood) < 1e-6:
            previous_log_likelihood = log_likelihood
            break

        previous_log_likelihood = log_likelihood

    emissions = [
        [max(1e-300, _normal_density(value, means[state], sigmas[state])) for state in range(3)]
        for value in sample
    ]
    alpha, _ = _scaled_forward(initial, transition, emissions)
    latest = tuple(_normalize_row(alpha[-1]))

    return _GaussianHMMCalibration(
        probabilities=(latest[0], latest[1], latest[2]),
        means=(means[0], means[1], means[2]),
        sigmas=(sigmas[0], sigmas[1], sigmas[2]),
        transition=tuple(tuple(row) for row in transition),
        iterations=completed_iterations,
        log_likelihood=previous_log_likelihood,
    )


def _scaled_forward(
    initial: Sequence[float],
    transition: Sequence[Sequence[float]],
    emissions: Sequence[Sequence[float]],
) -> tuple[list[list[float]], list[float]]:
    alpha: list[list[float]] = []
    scales: list[float] = []
    first_raw = [initial[state] * emissions[0][state] for state in range(3)]
    first_scale = max(sum(first_raw), 1e-300)
    alpha.append([value / first_scale for value in first_raw])
    scales.append(first_scale)

    for t in range(1, len(emissions)):
        raw = [
            emissions[t][target]
            * sum(alpha[t - 1][source] * transition[source][target] for source in range(3))
            for target in range(3)
        ]
        scale = max(sum(raw), 1e-300)
        alpha.append([value / scale for value in raw])
        scales.append(scale)

    return alpha, scales


def _scaled_backward(
    transition: Sequence[Sequence[float]],
    emissions: Sequence[Sequence[float]],
    scales: Sequence[float],
) -> list[list[float]]:
    beta = [[1.0, 1.0, 1.0] for _ in emissions]

    for t in range(len(emissions) - 2, -1, -1):
        beta[t] = [
            sum(
                transition[source][target]
                * emissions[t + 1][target]
                * beta[t + 1][target]
                for target in range(3)
            )
            / max(scales[t + 1], 1e-300)
            for source in range(3)
        ]

    return beta


def _order_hmm_states(
    initial: list[float],
    transition: list[list[float]],
    means: list[float],
    sigmas: list[float],
) -> tuple[list[float], list[list[float]], list[float], list[float]]:
    order = sorted(range(3), key=lambda state: (means[state], state))

    return (
        [initial[state] for state in order],
        [[transition[source][target] for target in order] for source in order],
        [means[state] for state in order],
        [sigmas[state] for state in order],
    )


def _normalize_row(values: Sequence[float]) -> list[float]:
    total = sum(max(0.0, value) for value in values)

    if total <= 0:
        return [1 / len(values) for _ in values]

    return [max(0.0, value) / total for value in values]


def _gmm_high_volatility_probability(values: Sequence[float]) -> float:
    if len(values) < 20:
        return 0.5

    sample = list(values[-min(400, len(values)) :])
    ordered = sorted(sample)
    means = [ordered[len(ordered) // 3], ordered[(len(ordered) * 2) // 3]]
    overall_scale = max(1e-12, _standard_deviation(sample))
    sigmas = [overall_scale, overall_scale]
    weights = [0.5, 0.5]

    for _ in range(20):
        responsibilities: list[tuple[float, float]] = []

        for value in sample:
            raw = [
                weights[index] * _normal_density(value, means[index], sigmas[index])
                for index in range(2)
            ]
            total = sum(raw)
            responsibilities.append((raw[0] / total, raw[1] / total) if total > 0 else (0.5, 0.5))

        for component in range(2):
            responsibility_sum = sum(row[component] for row in responsibilities)

            if responsibility_sum <= 1e-12:
                continue

            weights[component] = responsibility_sum / len(sample)
            means[component] = (
                sum(
                    row[component] * value
                    for row, value in zip(responsibilities, sample, strict=True)
                )
                / responsibility_sum
            )
            variance = (
                sum(
                    row[component] * (value - means[component]) ** 2
                    for row, value in zip(responsibilities, sample, strict=True)
                )
                / responsibility_sum
            )
            sigmas[component] = max(1e-12, sqrt(variance))

    high_component = 0 if means[0] > means[1] else 1
    latest = sample[-1]
    raw = [
        weights[index] * _normal_density(latest, means[index], sigmas[index]) for index in range(2)
    ]
    total = sum(raw)

    return raw[high_component] / total if total > 0 else 0.5


def _bayesian_change_probability(values: Sequence[float]) -> float:
    if len(values) < 20:
        return 0.0

    window = min(40, len(values) // 2)
    previous = values[-2 * window : -window]
    recent = values[-window:]
    pooled = [*previous, *recent]
    variance = max(1e-16, _variance(pooled))
    previous_mean = sum(previous) / len(previous)
    recent_mean = sum(recent) / len(recent)
    pooled_mean = sum(pooled) / len(pooled)
    no_change_log_likelihood = -sum((value - pooled_mean) ** 2 for value in pooled) / (2 * variance)
    changed_log_likelihood = -(
        sum((value - previous_mean) ** 2 for value in previous)
        + sum((value - recent_mean) ** 2 for value in recent)
    ) / (2 * variance)
    complexity_penalty = log(max(2.0, len(pooled)))
    log_bayes_factor = changed_log_likelihood - no_change_log_likelihood - complexity_penalty

    if log_bayes_factor >= 40:
        return 1.0

    if log_bayes_factor <= -40:
        return 0.0

    bayes_factor = exp(log_bayes_factor)

    return bayes_factor / (1.0 + bayes_factor)


def _kalman_normalized_slope(log_prices: Sequence[float]) -> float:
    level = log_prices[0]
    slope = 0.0
    p00, p01, p10, p11 = 1.0, 0.0, 0.0, 1.0
    innovations: list[float] = []

    for observation in log_prices[1:]:
        predicted_level = level + slope
        predicted_p00 = p00 + p01 + p10 + p11 + 1e-7
        predicted_p01 = p01 + p11
        predicted_p10 = p10 + p11
        predicted_p11 = p11 + 1e-7
        innovation = observation - predicted_level
        innovation_variance = predicted_p00 + 1e-5
        level_gain = predicted_p00 / innovation_variance
        slope_gain = predicted_p10 / innovation_variance
        level = predicted_level + level_gain * innovation
        slope = slope + slope_gain * innovation
        p00 = (1 - level_gain) * predicted_p00
        p01 = (1 - level_gain) * predicted_p01
        p10 = predicted_p10 - slope_gain * predicted_p00
        p11 = predicted_p11 - slope_gain * predicted_p01
        innovations.append(innovation)

    scale = _standard_deviation(innovations[-40:])

    return slope / max(scale, 1e-12)


def _lag_one_autocorrelation(values: Sequence[float]) -> float:
    if len(values) < 3:
        return 0.0

    left = values[:-1]
    right = values[1:]
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    denominator = sqrt(
        sum((value - left_mean) ** 2 for value in left)
        * sum((value - right_mean) ** 2 for value in right)
    )

    return numerator / denominator if denominator > 0 else 0.0


def _spread_stress_probability(spreads: Sequence[float]) -> float:
    if not spreads:
        return 0.0

    current = spreads[-1]
    center = median(spreads)
    deviation = median(abs(value - center) for value in spreads)

    if center <= 0 and current <= 0:
        return 0.0

    ratio_score = current / max(center, 1e-12)
    robust_z = (current - center) / max(1.4826 * deviation, 1e-12)

    return max(_sigmoid((ratio_score - 2.0) * 2.0), _sigmoid(robust_z - 4.0))


def _select_regime(
    probabilities: dict[InstitutionalRegime, float],
    *,
    change_probability: float,
    spread_stress: float,
) -> InstitutionalRegime:
    if spread_stress >= 0.70:
        return InstitutionalRegime.LIQUIDITY_STRESS

    if change_probability >= 0.65:
        return InstitutionalRegime.TRANSITION

    candidates = {
        regime: value
        for regime, value in probabilities.items()
        if regime
        not in {
            InstitutionalRegime.INSUFFICIENT_DATA,
            InstitutionalRegime.LIQUIDITY_STRESS,
            InstitutionalRegime.TRANSITION,
            InstitutionalRegime.RISK_ON,
            InstitutionalRegime.RISK_OFF,
        }
    }

    return max(candidates, key=lambda item: (candidates[item], item.value))


def _normalize_probabilities(
    probabilities: dict[InstitutionalRegime, float],
) -> dict[InstitutionalRegime, float]:
    clipped = {key: max(0.0, value) for key, value in probabilities.items()}
    total = sum(clipped.values())

    if total <= 0:
        return {
            regime: (1.0 if regime is InstitutionalRegime.INSUFFICIENT_DATA else 0.0)
            for regime in InstitutionalRegime
        }

    return {key: value / total for key, value in clipped.items()}


def _estimate_regime_start(
    bars: Sequence[MarketBar],
    regime: InstitutionalRegime,
    *,
    high_volatility_probability: float,
) -> datetime:
    if regime in {InstitutionalRegime.HIGH_VOLATILITY, InstitutionalRegime.LIQUIDITY_STRESS}:
        lookback = 20 if high_volatility_probability >= 0.5 else 10
    elif regime is InstitutionalRegime.TRANSITION:
        lookback = 5
    else:
        lookback = 30

    return bars[max(0, len(bars) - lookback)].timestamp


def _compatible_families(regime: InstitutionalRegime) -> tuple[str, ...]:
    mapping = {
        InstitutionalRegime.TRENDING_UP: ("trend", "momentum", "adaptive", "breakout"),
        InstitutionalRegime.TRENDING_DOWN: ("trend", "momentum", "adaptive", "breakout"),
        InstitutionalRegime.MEAN_REVERTING: ("mean_reversion", "statistical", "pairs"),
        InstitutionalRegime.HIGH_VOLATILITY: ("volatility", "breakout", "adaptive"),
        InstitutionalRegime.LOW_VOLATILITY: ("mean_reversion", "statistical", "relative_value"),
        InstitutionalRegime.RISK_ON: ("cross_sectional", "momentum", "portfolio"),
        InstitutionalRegime.RISK_OFF: ("defensive", "volatility", "portfolio"),
        InstitutionalRegime.TRANSITION: ("adaptive", "capital_preservation"),
        InstitutionalRegime.LIQUIDITY_STRESS: ("capital_preservation",),
        InstitutionalRegime.INSUFFICIENT_DATA: (),
    }

    return mapping[regime]


def _robust_zscores(values: Sequence[float]) -> list[float]:
    if not values:
        return []

    center = median(values)
    deviation = median(abs(value - center) for value in values)
    scale = max(1e-12, 1.4826 * deviation)

    return [(value - center) / scale for value in values]


def _variance(values: Sequence[float]) -> float:
    if not values:
        return 0.0

    center = sum(values) / len(values)

    return sum((value - center) ** 2 for value in values) / len(values)


def _standard_deviation(values: Sequence[float]) -> float:
    return sqrt(_variance(values))


def _normal_density(value: float, mean: float, sigma: float) -> float:
    scale = max(sigma, 1e-12)
    z_score = (value - mean) / scale

    return exp(-0.5 * z_score * z_score) / (scale * sqrt(2 * pi))


def _sigmoid(value: float) -> float:
    if value >= 40:
        return 1.0

    if value <= -40:
        return 0.0

    return 1.0 / (1.0 + exp(-value))


def _stable_short_hash(value: str) -> str:
    from hashlib import sha256

    return sha256(value.encode("utf-8")).hexdigest()[:20]
