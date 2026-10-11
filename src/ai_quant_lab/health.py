from __future__ import annotations


def project_status() -> dict[str, str]:
    """Return the basic health status of AI Quant Lab."""
    return {
        "name": "AI Quant Lab",
        "version": "0.4.0",
        "status": "ready",
    }
