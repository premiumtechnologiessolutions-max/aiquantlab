from __future__ import annotations

from pathlib import Path

from ai_quant_lab.model_config import load_model_runtime


def test_default_agent_config_disables_paid_models() -> None:
    runtime = load_model_runtime("configs/agents.toml")

    assert len(runtime.profiles) == 10
    assert all(profile.model is None for profile in runtime.profiles)


def test_config_can_enable_anthropic_without_storing_api_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / "agents.toml"
    path.write_text(
        """
[model_budget]
maximum_total_cost_usd = 0.50
maximum_input_tokens = 10000
maximum_output_tokens = 2000

[providers.anthropic]
enabled = true
model_name = "controlled-model"
input_cost_per_million_usd = 1.0
output_cost_per_million_usd = 2.0
maximum_cost_per_request_usd = 0.02

[agents.atlas]
provider = "anthropic"
""".strip(),
        encoding="utf-8",
    )

    runtime = load_model_runtime(path)
    atlas = next(profile for profile in runtime.profiles if profile.agent_key == "atlas")

    assert atlas.model is not None
    assert atlas.model.model_name == "controlled-model"
    assert runtime.providers.get("anthropic").key == "anthropic"
    assert "api_key" not in path.read_text(encoding="utf-8").casefold()
