from __future__ import annotations

import json

import httpx
import pytest

from ai_quant_lab.modeling import (
    ModelBudget,
    ModelBudgetLedger,
    ModelConfiguration,
    ModelProviderUnavailable,
    ModelRequest,
)
from ai_quant_lab.providers import AnthropicModelProvider


def make_request(maximum_output_tokens: int = 100) -> ModelRequest:
    """Build one controlled provider request without credentials."""

    return ModelRequest(
        request_id="request_000001",
        agent_key="atlas",
        system_prompt="Report recorded facts only.",
        user_prompt="What is the team doing?",
        context="Vega has one assigned data task.",
        maximum_output_tokens=maximum_output_tokens,
    )


def make_configuration(**changes: object) -> ModelConfiguration:
    """Build an explicitly priced Anthropic model configuration."""

    values: dict[str, object] = {
        "provider_key": "anthropic",
        "model_name": "controlled-test-model",
        "input_cost_per_million_usd": 3.0,
        "output_cost_per_million_usd": 15.0,
        "maximum_cost_per_request_usd": 0.10,
    }
    values.update(changes)

    return ModelConfiguration.model_validate(values)


def test_provider_requires_environment_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = AnthropicModelProvider()

    with pytest.raises(ModelProviderUnavailable, match="ANTHROPIC_API_KEY"):
        provider.complete(make_request(), make_configuration())


def test_provider_uses_messages_api_and_records_usage() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["payload"] = json.loads(request.content)

        return httpx.Response(
            200,
            json={
                "id": "message_test",
                "model": "controlled-test-model",
                "content": [{"type": "text", "text": "Vega has one real task."}],
                "usage": {"input_tokens": 40, "output_tokens": 10},
            },
        )

    ledger = ModelBudgetLedger(
        ModelBudget(
            maximum_total_cost_usd=1,
            maximum_input_tokens=1_000,
            maximum_output_tokens=1_000,
        )
    )
    provider = AnthropicModelProvider(
        api_key="controlled-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        budget_ledger=ledger,
    )
    response = provider.complete(make_request(), make_configuration())

    headers = captured["headers"]
    payload = captured["payload"]
    assert isinstance(headers, httpx.Headers)
    assert isinstance(payload, dict)
    assert headers["x-api-key"] == "controlled-secret"
    assert headers["anthropic-version"] == "2023-06-01"
    assert payload["model"] == "controlled-test-model"
    assert payload["max_tokens"] == 100
    assert "Recorded runtime context" in payload["messages"][0]["content"]
    assert response.text == "Vega has one real task."
    assert response.usage.input_tokens == 40
    assert response.usage.output_tokens == 10
    assert ledger.cost_usd == response.usage.estimated_cost_usd


def test_provider_rejects_worst_case_cost_before_network_call() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        return httpx.Response(500)

    provider = AnthropicModelProvider(
        api_key="controlled-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ModelProviderUnavailable, match="per-request limit"):
        provider.complete(
            make_request(maximum_output_tokens=1_000),
            make_configuration(maximum_cost_per_request_usd=0.0001),
        )

    assert calls == 0
