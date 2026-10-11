from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_quant_lab.modeling import (
    AgentModelProfile,
    ModelProviderRegistry,
    ModelProviderUnavailable,
    ModelRequest,
)


class HypothesisDraft(BaseModel):
    """Qualitative Nova output that cannot alter deterministic strategy parameters."""

    model_config = ConfigDict(frozen=True)

    statement: str = Field(min_length=20, max_length=1_000)
    economic_rationale: str = Field(min_length=20, max_length=2_000)
    falsification_criteria: tuple[str, ...] = Field(min_length=3, max_length=6)
    compatible_regimes: tuple[str, ...] = Field(min_length=1, max_length=4)


class ResearchBrain:
    """Optional bounded LLM layer for proposing and explaining, never gating."""

    def __init__(
        self,
        profiles: tuple[AgentModelProfile, ...] = (),
        providers: ModelProviderRegistry | None = None,
    ) -> None:
        self._profiles = {profile.agent_key: profile for profile in profiles}
        self._providers = providers or ModelProviderRegistry()

    def propose_hypothesis(
        self,
        *,
        campaign_id: str,
        pair: str,
        timeframe: str,
        regime: str,
        strategy_name: str,
        parameters: dict[str, int | float | str],
        history: tuple[dict[str, object], ...],
    ) -> HypothesisDraft | None:
        """Ask Nova for a frozen qualitative claim around a preselected strategy arm."""

        prompt = (
            "Return JSON only with keys statement, economic_rationale, "
            "falsification_criteria, compatible_regimes. Propose one falsifiable hypothesis "
            "for the already selected strategy and locked parameters. Do not calculate metrics, "
            "change parameters, approve risk, recommend an order, or refer to unseen OOS results. "
            f"The compatible_regimes list must include {regime}."
        )
        context = json.dumps(
            {
                "campaign_id": campaign_id,
                "pair": pair,
                "timeframe": timeframe,
                "regime": regime,
                "selected_strategy": strategy_name,
                "locked_parameters": parameters,
                "recorded_prior_campaigns": history,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        text = self._complete(
            "nova",
            request_id=f"{campaign_id}_nova_hypothesis",
            user_prompt=prompt,
            context=context,
            maximum_output_tokens=500,
        )

        if text is None:
            return None

        try:
            draft = HypothesisDraft.model_validate(_parse_json_object(text))
        except (TypeError, ValueError, ValidationError, json.JSONDecodeError):
            return None

        if regime not in draft.compatible_regimes:
            return None

        return draft

    def audit_commentary(
        self,
        *,
        campaign_id: str,
        audit: dict[str, object],
        failure_reasons: tuple[str, ...],
    ) -> str | None:
        """Let Sentinel explain anomalies without changing any audit field."""

        return self._complete(
            "sentinel",
            request_id=f"{campaign_id}_sentinel_commentary",
            user_prompt=(
                "Explain the supplied deterministic audit in at most 160 words. Distinguish facts "
                "from interpretation. Do not recalculate numbers, modify gates, or authorize risk."
            ),
            context=json.dumps(
                {"audit": audit, "failure_reasons": failure_reasons},
                ensure_ascii=False,
                sort_keys=True,
            ),
            maximum_output_tokens=260,
        )

    def report_commentary(
        self,
        *,
        campaign_id: str,
        facts: dict[str, object],
    ) -> str | None:
        """Let Echo add a bounded narrative while preserving the factual report."""

        return self._complete(
            "echo",
            request_id=f"{campaign_id}_echo_commentary",
            user_prompt=(
                "Write a concise qualitative research commentary from the supplied facts. "
                "Do not invent evidence, promise returns, change a decision, or suggest an order."
            ),
            context=json.dumps(facts, ensure_ascii=False, sort_keys=True),
            maximum_output_tokens=320,
        )

    def _complete(
        self,
        agent_key: str,
        *,
        request_id: str,
        user_prompt: str,
        context: str,
        maximum_output_tokens: int,
    ) -> str | None:
        profile = self._profiles.get(agent_key)

        if profile is None or profile.model is None:
            return None

        request = ModelRequest(
            request_id=request_id,
            agent_key=agent_key,
            system_prompt=(
                profile.system_prompt
                + " You are in the non-authoritative Brain layer. The deterministic Execution "
                "layer owns every number, gate, size, and final decision."
            ),
            user_prompt=user_prompt,
            context=context,
            allowed_tools=(),
            maximum_output_tokens=min(
                maximum_output_tokens,
                profile.model.maximum_output_tokens,
            ),
        )

        try:
            provider = self._providers.get(profile.model.provider_key)
            return provider.complete(request, profile.model).text.strip()
        except (ModelProviderUnavailable, RuntimeError, TypeError, ValueError):
            return None


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()

    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]).strip()

        if stripped.casefold().startswith("json\n"):
            stripped = stripped[5:].strip()

    payload = json.loads(stripped)

    if not isinstance(payload, dict):
        raise TypeError("Model hypothesis output must be a JSON object.")

    return payload
