from pathlib import Path

from ai_quant_lab.config import load_config


def test_load_base_config() -> None:
    config = load_config()

    assert config.project_name == "AI Quant Lab"
    assert config.mode == "research"
    assert config.timezone == "UTC"
    assert config.data_dir == Path("data")

    assert config.pairs == (
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "USDCHF",
        "USDCAD",
        "AUDUSD",
        "NZDUSD",
    )

    assert config.timeframes == ("M1", "M5", "M15", "H1", "H4", "D1")
