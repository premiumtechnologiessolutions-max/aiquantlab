"""Localhost-only voice dashboard for the persistent agent team."""

from ai_quant_lab.web.controller import DashboardContextProvider, DashboardController
from ai_quant_lab.web.server import serve_voice_dashboard

__all__ = [
    "DashboardContextProvider",
    "DashboardController",
    "serve_voice_dashboard",
]
