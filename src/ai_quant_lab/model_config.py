from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from ai_quant_lab.modeling import (
    AgentModelProfile,
    ModelBudget,
    ModelBudgetLedger,
    ModelConfiguration,
    ModelProviderRegistry,
    default_agent_model_profiles,
)
from ai_quant_lab.providers import AnthropicModelProvider


@dataclass(frozen=True)
class ConfiguredModelRuntime:
    """Profiles and provider registry loaded from one credential-free TOML file."""

    profiles: tuple[AgentModelProfile, ...]
    providers: ModelProviderRegistry


def load_model_runtime(
    path: str | Path = "configs/agents.toml",
) -> ConfiguredModelRuntime:
    """Load agent/model choices while keeping API keys in environment variables."""

    config_path = Path(path)

    with config_path.open("rb") as stream:
        payload = tomllib.load(stream)

    budget_payload = payload.get("model_budget", {})
    ledger = ModelBudgetLedger(ModelBudget.model_validate(budget_payload))
    provider_payloads = payload.get("providers", {})
    registry = ModelProviderRegistry()
    enabled_providers: set[str] = set()
    anthropic_payload = provider_payloads.get("anthropic", {})

    if bool(anthropic_payload.get("enabled", False)):
        registry.register(AnthropicModelProvider(budget_ledger=ledger))
        enabled_providers.add("anthropic")

    defaults = {
        profile.agent_key: profile
        for profile in default_agent_model_profiles()
    }
    configured_agents = payload.get("agents", {})
    profiles: list[AgentModelProfile] = []

    for agent_key, default in defaults.items():
        agent_payload = configured_agents.get(agent_key, {})
        provider_key = str(agent_payload.get("provider", "disabled"))
        model: ModelConfiguration | None = None

        if provider_key != "disabled" and provider_key in enabled_providers:
            provider_payload = provider_payloads[provider_key]
            model = ModelConfiguration(
                provider_key=provider_key,
                model_name=str(provider_payload.get("model_name", "")),
                timeout_seconds=float(provider_payload.get("timeout_seconds", 60)),
                maximum_output_tokens=int(
                    provider_payload.get("maximum_output_tokens", 1_000)
                ),
                maximum_requests_per_turn=1,
                input_cost_per_million_usd=float(
                    provider_payload.get("input_cost_per_million_usd", 0)
                ),
                output_cost_per_million_usd=float(
                    provider_payload.get("output_cost_per_million_usd", 0)
                ),
                maximum_cost_per_request_usd=float(
                    provider_payload.get("maximum_cost_per_request_usd", 0.10)
                ),
            )

        profiles.append(
            default.model_copy(
                update={
                    "system_prompt": str(
                        agent_payload.get("system_prompt", default.system_prompt)
                    ),
                    "model": model,
                }
            )
        )

    return ConfiguredModelRuntime(
        profiles=tuple(profiles),
        providers=registry,
    )
