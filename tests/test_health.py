from ai_quant_lab.health import project_status


def test_project_status() -> None:
    status = project_status()

    assert status["name"] == "AI Quant Lab"
    assert status["version"] == "0.4.0"
    assert status["status"] == "ready"
