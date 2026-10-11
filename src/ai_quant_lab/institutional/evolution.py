from __future__ import annotations

from hashlib import sha256

from ai_quant_lab.institutional.registry import StrategyCandidateRecord
from ai_quant_lab.strategies import StrategyName, build_strategy, neighboring_variants


def evolve_parameters(
    parents: tuple[StrategyCandidateRecord, ...],
    *,
    identity: str,
) -> dict[str, int | float | str] | None:
    """Create one reproducible crossover/mutation child from validated challengers.

    The result is only a proposal. It receives no research status until a later campaign
    freezes it and sends it through Chronos, Sentinel, and Aegis.
    """

    if not parents:
        return None

    ordered = tuple(sorted(parents, key=lambda item: (-item.quant_score, item.version_id)))
    strategy_name = _strategy_name(ordered[0].strategy_name)

    if any(parent.strategy_name != strategy_name for parent in ordered):
        raise ValueError("Genetic crossover requires parents from the same strategy arm.")

    base_parameters = dict(ordered[0].parameters)

    if len(ordered) >= 2:
        second = ordered[1].parameters
        crossed: dict[str, int | float | str] = {}

        for key, first_value in sorted(base_parameters.items()):
            second_value = second.get(key, first_value)

            if (
                isinstance(first_value, (int, float))
                and not isinstance(first_value, bool)
                and isinstance(second_value, (int, float))
                and not isinstance(second_value, bool)
            ):
                midpoint = (float(first_value) + float(second_value)) / 2.0
                crossed[key] = int(round(midpoint)) if isinstance(first_value, int) else midpoint
            else:
                crossed[key] = first_value

        try:
            base_parameters = dict(build_strategy(strategy_name, crossed).descriptor.parameters)
        except (TypeError, ValueError):
            base_parameters = dict(ordered[0].parameters)

    variants = tuple(
        dict(variant.descriptor.parameters)
        for variant in neighboring_variants(strategy_name, base_parameters)
        if dict(variant.descriptor.parameters) != base_parameters
    )

    if not variants:
        return None

    seed = sha256(
        (identity + "|" + "|".join(parent.version_id for parent in ordered)).encode("utf-8")
    ).hexdigest()
    child = variants[int(seed[:8], 16) % len(variants)]
    validated = build_strategy(strategy_name, child)

    return dict(validated.descriptor.parameters)


def _strategy_name(value: str) -> StrategyName:
    from ai_quant_lab.strategies import normalize_strategy_name

    return normalize_strategy_name(value)
