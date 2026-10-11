from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from threading import RLock
from urllib.parse import urlparse

import httpx

from ai_quant_lab.agents import ActivityType
from ai_quant_lab.runtime import LabRuntime


class OperationalAlertDispatcher:
    """Persist health failures and optionally push them to a configured HTTPS webhook."""

    def __init__(
        self,
        runtime: LabRuntime,
        *,
        webhook_url: str | None = None,
        cooldown_seconds: float = 900.0,
    ) -> None:
        self.runtime = runtime
        self.webhook_url = webhook_url or os.environ.get("AI_QUANT_ALERT_WEBHOOK_URL")
        self.cooldown = timedelta(seconds=max(60.0, cooldown_seconds))
        self._last_sent: dict[tuple[str, str], datetime] = {}
        self._lock = RLock()

    def failure(self, component_key: str, message: str) -> None:
        """Record a degraded heartbeat and send one deduplicated alert when configured."""

        message = _sanitize_alert_message(message)
        now = datetime.now(UTC)
        self.runtime.store.save_heartbeat(
            component_key,
            status="degraded",
            observed_at=now,
        )
        key = (component_key, message)

        with self._lock:
            previous = self._last_sent.get(key)

            if previous is not None and now - previous < self.cooldown:
                return

            self._last_sent[key] = now

        self.runtime.journal.record(
            event_type=ActivityType.JOB_FAILED,
            actor_key="aegis",
            message=f"Health alert [{component_key}]: {message}",
            metadata={"component": component_key},
        )
        self._post_webhook(component_key, message, now)

    def healthy(self, component_key: str) -> None:
        """Refresh one component heartbeat after a successful bounded cycle."""

        self.runtime.store.save_heartbeat(component_key, status="healthy")

    def _post_webhook(self, component_key: str, message: str, observed_at: datetime) -> None:
        if not self.webhook_url:
            return

        parsed = urlparse(self.webhook_url)

        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            self.runtime.journal.record(
                event_type=ActivityType.JOB_FAILED,
                actor_key="aegis",
                message="Alert webhook was ignored because it is not a credential-free HTTPS URL.",
            )
            return

        try:
            httpx.post(
                self.webhook_url,
                json={
                    "project": "AI Quant Lab",
                    "component": component_key,
                    "status": "degraded",
                    "message": message,
                    "observed_at": observed_at.isoformat(),
                    "live_trading_authorized": False,
                },
                timeout=5.0,
            ).raise_for_status()
        except httpx.HTTPError:
            self.runtime.journal.record(
                event_type=ActivityType.JOB_FAILED,
                actor_key="aegis",
                message=f"Could not deliver the configured health webhook for {component_key}.",
            )


def _sanitize_alert_message(message: str) -> str:
    """Bound alert text and redact known process credentials before persistence."""

    sanitized = " ".join(message.strip().split()) or "Unspecified operational failure."

    for name in (
        "ANTHROPIC_API_KEY",
        "AI_QUANT_MT5_PASSWORD",
        "AI_QUANT_MT5_LOGIN",
    ):
        value = os.environ.get(name)

        if value:
            sanitized = sanitized.replace(value, "[REDACTED]")

    return sanitized[:500]
