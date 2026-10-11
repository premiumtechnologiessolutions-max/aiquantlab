from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast, get_args

from ai_quant_lab.agents import ActivityType
from ai_quant_lab.agents.conversation import AgentContextProvider, AgentConversationService
from ai_quant_lab.agents.identifiers import normalize_spoken_text
from ai_quant_lab.broker import (
    DemoOrderIntent,
    DemoOrderSide,
    MT5DemoGateway,
)
from ai_quant_lab.campaigns import latest_campaign
from ai_quant_lab.config import ForexPair
from ai_quant_lab.institutional import ContinuousResearchProgram
from ai_quant_lab.institutional.brain import ResearchBrain
from ai_quant_lab.model_config import ConfiguredModelRuntime
from ai_quant_lab.monitoring import DemoMarketMonitor, MonitorStore, strategy_catalog_payload
from ai_quant_lab.runtime import LabRuntime
from ai_quant_lab.strategies.blueprints import strategy_blueprint_payload


class DashboardContextProvider(AgentContextProvider):
    """Answer agent questions from real MT5, monitor, and campaign state."""

    _ACCOUNT_WORDS = (
        "mt5",
        "account",
        "balance",
        "equity",
        "حساب",
        "رصيد",
        "ميتاتريدر",
    )
    _MARKET_WORDS = (
        "market",
        "price",
        "quote",
        "signal",
        "regime",
        "سوق",
        "سعر",
        "اشارة",
        "إشارة",
        "حالة السوق",
    )
    _STRATEGY_WORDS = (
        "strategy",
        "strategies",
        "algorithm",
        "campaign",
        "experiment",
        "quant score",
        "استراتيجية",
        "استراتيجيات",
        "خوارزمية",
        "تجربة",
        "بحث",
        "حملة",
        "سكور",
        "تقييم كمي",
    )
    _POSITION_WORDS = (
        "position",
        "positions",
        "trade",
        "trades",
        "صفقة",
        "صفقات",
        "مراكز",
    )

    def __init__(
        self,
        gateway: MT5DemoGateway,
        monitor_store: MonitorStore,
        *,
        campaign_root: str | Path = "data/campaigns",
        research_program: ContinuousResearchProgram | None = None,
    ) -> None:
        self.gateway = gateway
        self.monitor_store = monitor_store
        self.campaign_root = Path(campaign_root)
        self.research_program = research_program

    def answer(self, agent_key: str, user_text: str) -> str | None:
        """Return a direct factual reply when local state can answer it."""

        normalized = normalize_spoken_text(user_text)

        if any(word in normalized for word in self._ACCOUNT_WORDS):
            return self._account_reply(agent_key)

        if any(word in normalized for word in self._POSITION_WORDS):
            return self._positions_reply(agent_key)

        if any(word in normalized for word in self._MARKET_WORDS):
            return self._market_reply(agent_key)

        if any(word in normalized for word in self._STRATEGY_WORDS):
            return self._strategy_reply(agent_key)

        return None

    def context(self, agent_key: str) -> str:
        """Build concise local context for an optional bounded model provider."""

        return "\n".join(
            (
                self._account_reply(agent_key),
                self._market_reply(agent_key),
                self._strategy_reply(agent_key),
            )
        )

    def _account_reply(self, agent_key: str) -> str:
        status = self.gateway.status()
        prefix = _agent_name(agent_key)

        if not status.connected or status.account is None:
            return f"{prefix}: حساب MT5 Demo مش موصول هلق."

        account = status.account
        return (
            f"{prefix}: حساب Demo موصول على {account.server}. "
            f"الرصيد {account.balance:.2f} {account.currency}، "
            f"Equity {account.equity:.2f}، والهامش الحر {account.margin_free:.2f}."
        )

    def _positions_reply(self, agent_key: str) -> str:
        prefix = _agent_name(agent_key)

        if not self.gateway.status().connected:
            return f"{prefix}: ما فيني اقرأ الصفقات لأن حساب MT5 Demo مش موصول."

        try:
            positions = self.gateway.positions()
        except RuntimeError as error:
            return f"{prefix}: تعذر قراءة صفقات الـDemo: {error}"

        if not positions:
            return f"{prefix}: ما في صفقات مفتوحة على حساب الـDemo حاليًا."

        total_profit = sum(position.profit for position in positions)
        return (
            f"{prefix}: في {len(positions)} صفقة Demo مفتوحة، "
            f"والربح/الخسارة العائمة {total_profit:.2f}."
        )

    def _market_reply(self, agent_key: str) -> str:
        prefix = _agent_name(agent_key)
        scan = self.monitor_store.latest()

        if scan is None:
            return f"{prefix}: بعد ما في Market Scan مسجّل؛ وصّل MT5 وشغّل أول فحص."

        signal = {
            -1: "بيع",
            0: "حياد",
            1: "شراء",
        }[int(scan.consensus)]
        return (
            f"{prefix}: آخر فحص {scan.pair} {scan.timeframe}: "
            f"السوق {scan.regime.value}، الإجماع {signal}، "
            f"Bid {scan.quote.bid:.5f} وAsk {scan.quote.ask:.5f}، "
            f"أصوات الشراء {scan.long_votes} والبيع {scan.short_votes}."
        )

    def _strategy_reply(self, agent_key: str) -> str:
        prefix = _agent_name(agent_key)
        institutional = (
            self.research_program.overview() if self.research_program is not None else None
        )

        if institutional is not None:
            active = institutional.get("active_campaign")

            if isinstance(active, dict):
                score = active.get("quant_score")
                score_text = f"، Quant Score {float(score):.1f}" if score is not None else ""
                return (
                    f"{prefix}: الحملة المؤسساتية {active.get('campaign_id')} "
                    f"بحالة {active.get('status')}{score_text}. "
                    "كل محاولة، حتى الفاشلة، محفوظة بالسجل."
                )

        campaign = latest_campaign(self.campaign_root)

        if campaign is None:
            return (
                f"{prefix}: عندنا {len(strategy_catalog_payload())} استراتيجيات سببية، "
                "بس بعد ما شغّلنا حملة مقارنة مسجّلة."
            )

        leader = campaign.research_leader or "none"
        return (
            f"{prefix}: آخر حملة على {campaign.pair} {campaign.timeframe} "
            f"قارنت {len(campaign.entries)} استراتيجيات. "
            f"متصدر البحث حاليًا {leader}، وهيدا مش تصريح تداول Live."
        )


class DashboardController:
    """Framework-free application layer shared by HTTP routes and tests."""

    def __init__(
        self,
        runtime: LabRuntime,
        gateway: MT5DemoGateway,
        monitor: DemoMarketMonitor,
        *,
        campaign_root: str | Path = "data/campaigns",
        model_runtime: ConfiguredModelRuntime | None = None,
    ) -> None:
        self.runtime = runtime
        self.gateway = gateway
        self.monitor = monitor
        self.campaign_root = Path(campaign_root)
        profiles = model_runtime.profiles if model_runtime is not None else ()
        providers = model_runtime.providers if model_runtime is not None else None
        self.research = ContinuousResearchProgram(
            runtime,
            monitor,
            brain=ResearchBrain(profiles, providers),
        )
        self.context_provider = DashboardContextProvider(
            gateway,
            monitor.store,
            campaign_root=self.campaign_root,
            research_program=self.research,
        )
        self.conversation = AgentConversationService(
            runtime,
            profiles=profiles,
            providers=providers,
            context_provider=self.context_provider,
        )
        self.last_monitor_error: str | None = None

    def health_snapshot(self) -> dict[str, object]:
        """Return real component liveness rather than a static HTTP-only health flag."""

        now = datetime.now(UTC)
        heartbeats = self.runtime.store.load_heartbeats()
        components = {
            heartbeat.component_key: {
                "status": heartbeat.status,
                "observed_at": heartbeat.observed_at.isoformat(),
                "age_seconds": max(0.0, (now - heartbeat.observed_at).total_seconds()),
                "stale": now - heartbeat.observed_at > timedelta(seconds=30),
            }
            for heartbeat in heartbeats
        }
        mt5_connected = self.gateway.status().connected
        degraded = any(
            item["status"] != "healthy" or bool(item["stale"])
            for item in components.values()
        )

        return {
            "status": (
                "degraded"
                if degraded or self.last_monitor_error or not mt5_connected
                else "healthy"
            ),
            "localhost_only": True,
            "components": components,
            "mt5_connected": mt5_connected,
            "last_monitor_error": self.last_monitor_error,
            "research_control": self.research.store.control().model_dump(mode="json"),
            "live_trading_authorized": False,
        }

    def overview(self) -> dict[str, object]:
        """Return the complete current UI snapshot from local persisted state."""

        events = self.runtime.journal.all_events()[-30:]
        task_history = self.runtime.task_board.all_tasks()[-150:]
        messages = self.runtime.message_bus.all_messages()[-150:]
        campaign = latest_campaign(self.campaign_root)
        scans = self.monitor.store.recent(limit=20)

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "agents": [
                snapshot.model_dump(mode="json") for snapshot in self.runtime.team.all_snapshots()
            ],
            "tasks": [
                task.model_dump(mode="json") for task in self.runtime.task_board.active_tasks()
            ],
            "task_history": [task.model_dump(mode="json") for task in task_history],
            "messages": [message.model_dump(mode="json") for message in messages],
            "events": [event.model_dump(mode="json") for event in events],
            "heartbeats": [
                heartbeat.model_dump(mode="json")
                for heartbeat in self.runtime.store.load_heartbeats()
            ],
            "team_progress": self.runtime.coordinator.progress_reply(),
            "mt5": self.gateway.status().model_dump(mode="json"),
            "scans": [scan.model_dump(mode="json") for scan in scans],
            "campaign": campaign.model_dump(mode="json") if campaign is not None else None,
            "strategies": strategy_catalog_payload(),
            "strategy_blueprints": strategy_blueprint_payload(),
            "institutional_research": self.research.overview(),
            "last_monitor_error": self.last_monitor_error,
            "safety": {
                "real_account_blocked": True,
                "live_trading_allowed": False,
                "demo_orders_enabled": self.gateway.config.demo_orders_enabled,
            },
        }

    def chat(self, text: str) -> dict[str, object]:
        """Send typed or spoken text to a named persisted agent."""

        result = self.conversation.ask(text)

        return result.model_dump(mode="json")

    def connect_mt5(self) -> dict[str, object]:
        """Connect to MT5 and record only sanitized demo-account facts."""

        account = self.gateway.connect()
        self.runtime.journal.record(
            event_type=ActivityType.JOB_COMPLETED,
            actor_key="vega",
            message="Verified and connected to an MT5 demo account.",
            metadata={"server": account.server},
        )

        return self.gateway.status().model_dump(mode="json")

    def disconnect_mt5(self) -> dict[str, object]:
        """Disconnect the demo terminal safely."""

        self.gateway.disconnect()
        self.runtime.journal.record(
            event_type=ActivityType.JOB_COMPLETED,
            actor_key="vega",
            message="Disconnected from the MT5 demo account.",
        )

        return self.gateway.status().model_dump(mode="json")

    def scan_market(self) -> dict[str, object]:
        """Run one bounded ensemble scan and expose its persisted results."""

        try:
            scans = self.monitor.scan_once()
        except Exception as error:
            self.last_monitor_error = str(error)
            self.runtime.journal.record(
                event_type=ActivityType.JOB_FAILED,
                actor_key="vega",
                message=f"MT5 demo market scan failed: {error}",
            )
            raise

        self.last_monitor_error = None

        for scan in scans:
            self.runtime.journal.record(
                event_type=ActivityType.JOB_COMPLETED,
                actor_key="iris",
                message=(
                    f"Scanned {scan.pair} {scan.timeframe}; "
                    f"regime {scan.regime.value}, consensus {scan.consensus.name.lower()}."
                ),
                metadata={
                    "pair": scan.pair,
                    "timeframe": scan.timeframe,
                    "consensus": int(scan.consensus),
                },
            )

        self.research.tick()

        return {"scans": [scan.model_dump(mode="json") for scan in scans]}

    def runtime_tick(self) -> dict[str, object]:
        """Run one scheduler tick and deterministic ready-task pass."""

        jobs = self.runtime.run_once()
        completed = self.runtime.execute_ready_tasks()
        research = self.research.tick()

        return {
            "jobs": [job.model_dump(mode="json") for job in jobs],
            "completed_tasks": completed,
            "institutional_research": research,
        }

    def start_research(self) -> dict[str, object]:
        """Enable the one-campaign-per-completed-bar institutional loop."""

        return self.research.start()

    def pause_research(self) -> dict[str, object]:
        """Pause research without deleting active evidence or tasks."""

        return self.research.pause()

    def emergency_stop(self, reason: str) -> dict[str, object]:
        """Trigger the Aegis kill switch across the research command center."""

        return self.research.emergency_stop(reason)

    def reset_emergency_stop(self) -> dict[str, object]:
        """Clear the kill switch while leaving research paused."""

        return self.research.reset_emergency_stop()

    def quote(self, pair: str) -> dict[str, object]:
        """Read one current quote from the verified demo connection."""

        return self.gateway.latest_quote(_pair(pair)).model_dump(mode="json")

    def positions(self) -> dict[str, object]:
        """Read all currently open demo positions."""

        positions = self.gateway.positions()

        return {"positions": [position.model_dump(mode="json") for position in positions]}

    def place_demo_order(self, payload: dict[str, object]) -> dict[str, object]:
        """Place one manually confirmed demo order through every gateway guard."""

        confirmation = payload.pop("confirmation", "")

        if not isinstance(confirmation, str):
            raise TypeError("Demo confirmation must be text.")

        raw_side = payload.get("side")

        if not isinstance(raw_side, str):
            raise TypeError("Demo order side must be text.")

        raw_pair = payload.get("pair")

        if not isinstance(raw_pair, str):
            raise TypeError("Demo order pair must be text.")

        normalized_payload = dict(payload)
        normalized_payload["pair"] = _pair(raw_pair)
        normalized_payload["side"] = DemoOrderSide(raw_side.casefold())
        intent = DemoOrderIntent.model_validate(normalized_payload)
        receipt = self.gateway.place_market_order(intent, confirmation=confirmation)
        self.runtime.journal.record(
            event_type=ActivityType.JOB_COMPLETED,
            actor_key="aegis",
            message=(
                f"Guarded MT5 demo order accepted: {receipt.side.value} "
                f"{receipt.volume_lots:.2f} {receipt.pair}."
            ),
            metadata={"order_id": receipt.order_id, "pair": receipt.pair},
        )

        return receipt.model_dump(mode="json")


def _pair(value: str) -> ForexPair:
    normalized = value.strip().upper()

    if normalized not in get_args(ForexPair):
        raise ValueError(f"Unsupported forex pair '{value}'.")

    return cast(ForexPair, normalized)


def _agent_name(agent_key: str) -> str:
    return {
        "atlas": "Atlas",
        "vega": "Vega",
        "nova": "Nova",
        "chronos": "Chronos",
        "iris": "Iris",
        "sentinel": "Sentinel",
        "aegis": "Aegis",
        "oracle": "Oracle",
        "echo": "Echo",
        "forge": "Forge",
    }.get(agent_key, agent_key)
