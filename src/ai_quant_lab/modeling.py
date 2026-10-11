from __future__ import annotations

from collections.abc import Iterable
from threading import RLock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class ModelConfiguration(BaseModel):
    """Provider-independent model selection and request limits."""

    model_config = ConfigDict(frozen=True)

    provider_key: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    maximum_output_tokens: int = Field(default=1_000, ge=1, le=32_000)
    maximum_requests_per_turn: int = Field(default=1, ge=1, le=5)
    input_cost_per_million_usd: float = Field(default=0.0, ge=0)
    output_cost_per_million_usd: float = Field(default=0.0, ge=0)
    maximum_cost_per_request_usd: float = Field(default=0.10, gt=0)


class AgentPermissions(BaseModel):
    """Explicit safety boundary applied before an agent receives tools."""

    model_config = ConfigDict(frozen=True)

    allowed_tools: tuple[str, ...] = ()
    may_write_research_code: bool = False
    may_run_backtests: bool = False
    may_access_blind_validation: bool = False
    may_trade_live: bool = False


class AgentModelProfile(BaseModel):
    """Agent identity-specific prompt, tools, permissions, and model choice."""

    model_config = ConfigDict(frozen=True)

    agent_key: str
    system_prompt: str = Field(min_length=1)
    permissions: AgentPermissions
    model: ModelConfiguration | None = None


class ModelRequest(BaseModel):
    """Sanitized request passed to a configured language-model provider."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    agent_key: str
    system_prompt: str
    user_prompt: str
    context: str = ""
    allowed_tools: tuple[str, ...] = ()
    maximum_output_tokens: int = Field(ge=1)


class ModelUsage(BaseModel):
    """Provider-reported token and cost accounting for one response."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)


class ModelBudget(BaseModel):
    """Hard process-level ceiling for explicitly enabled paid model calls."""

    model_config = ConfigDict(frozen=True)

    maximum_total_cost_usd: float = Field(default=1.0, gt=0)
    maximum_input_tokens: int = Field(default=100_000, ge=1)
    maximum_output_tokens: int = Field(default=20_000, ge=1)


class ModelBudgetLedger:
    """Thread-safe usage ledger that refuses calls beyond configured ceilings."""

    def __init__(self, budget: ModelBudget | None = None) -> None:
        self.budget = budget or ModelBudget()
        self._lock = RLock()
        self._cost_usd = 0.0
        self._input_tokens = 0
        self._output_tokens = 0

    @property
    def cost_usd(self) -> float:
        """Return recorded provider cost for this process."""

        with self._lock:
            return self._cost_usd

    def authorize_estimate(
        self,
        *,
        estimated_cost_usd: float,
        estimated_input_tokens: int,
        maximum_output_tokens: int,
    ) -> None:
        """Reject a request whose worst-case estimate crosses any hard ceiling."""

        with self._lock:
            if self._cost_usd + estimated_cost_usd > self.budget.maximum_total_cost_usd:
                raise ModelProviderUnavailable("The configured model cost budget is exhausted.")

            if (
                self._input_tokens + estimated_input_tokens
                > self.budget.maximum_input_tokens
            ):
                raise ModelProviderUnavailable("The configured input-token budget is exhausted.")

            if (
                self._output_tokens + maximum_output_tokens
                > self.budget.maximum_output_tokens
            ):
                raise ModelProviderUnavailable("The configured output-token budget is exhausted.")

    def record(self, usage: ModelUsage) -> None:
        """Record actual usage returned by a provider response."""

        with self._lock:
            self._cost_usd += usage.estimated_cost_usd
            self._input_tokens += usage.input_tokens
            self._output_tokens += usage.output_tokens


class ModelResponse(BaseModel):
    """Provider-independent text response with auditable usage."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    provider_key: str
    model_name: str
    text: str = Field(min_length=1)
    usage: ModelUsage = Field(default_factory=ModelUsage)


class ModelProvider(Protocol):
    """Replaceable boundary around any future local or remote AI model."""

    @property
    def key(self) -> str:
        """Return the stable provider key."""

        ...  # pragma: no cover

    def complete(
        self,
        request: ModelRequest,
        configuration: ModelConfiguration,
    ) -> ModelResponse:
        """Produce one bounded response without receiving credentials in prompts."""

        ...  # pragma: no cover


class ModelProviderUnavailable(RuntimeError):
    """Raised when an agent requests a model that is not configured."""


class DisabledModelProvider:
    """Safe default that makes missing AI configuration explicit."""

    @property
    def key(self) -> str:
        """Return the provider registry key."""

        return "disabled"

    def complete(
        self,
        request: ModelRequest,
        configuration: ModelConfiguration,
    ) -> ModelResponse:
        """Reject paid/model calls until the owner explicitly configures one."""

        del request, configuration
        raise ModelProviderUnavailable(
            "No AI model provider is configured. Runtime facts and deterministic "
            "research tools remain available without paid API calls.",
        )


class ModelProviderRegistry:
    """Registry that permits provider changes without agent-logic changes."""

    def __init__(self, providers: Iterable[ModelProvider] = ()) -> None:
        self._providers: dict[str, ModelProvider] = {}

        for provider in providers:
            self.register(provider)

    def register(self, provider: ModelProvider) -> None:
        """Register one uniquely keyed provider."""

        if provider.key in self._providers:
            raise ValueError(f"Model provider '{provider.key}' already exists.")

        self._providers[provider.key] = provider

    def get(self, provider_key: str) -> ModelProvider:
        """Return one provider or explain the missing configuration."""

        provider = self._providers.get(provider_key)

        if provider is None:
            raise ModelProviderUnavailable(
                f"Model provider '{provider_key}' is not registered.",
            )

        return provider


def default_agent_model_profiles() -> tuple[AgentModelProfile, ...]:
    """Return safe prompts and least-privilege defaults for the core team."""

    roles = {
        "atlas": "Coordinate bounded tasks and report only recorded facts.",
        "vega": "Inspect market data provenance and quality without altering history.",
        "nova": "Turn research hypotheses into testable deterministic strategy rules.",
        "chronos": "Run reproducible backtests and chronological validation.",
        "iris": "Classify regimes using causal observations and explain uncertainty.",
        "sentinel": "Independently detect leakage, look-ahead, and overfitting risks.",
        "aegis": "Enforce immutable risk limits and prohibit real-money live trading.",
        "oracle": "Analyze time-valid macro inputs and cite their publication time.",
        "echo": "Explain recorded work and results without inventing activity.",
        "forge": "Version challengers and preserve failed experiments and lessons.",
    }

    return tuple(
        AgentModelProfile(
            agent_key=agent_key,
            system_prompt=(
                "You are an AI Quant Lab research agent. "
                f"{role} Never promise profits, expose credentials, or authorize live trading."
            ),
            permissions=AgentPermissions(
                allowed_tools=("task_board", "message_bus", "journal"),
                may_write_research_code=agent_key in {"nova", "forge"},
                may_run_backtests=agent_key in {"chronos", "sentinel"},
                may_access_blind_validation=agent_key == "sentinel",
            ),
        )
        for agent_key, role in roles.items()
    )
