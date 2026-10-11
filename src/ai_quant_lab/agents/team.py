from __future__ import annotations

import re
from collections.abc import Iterable
from threading import RLock

from ai_quant_lab.agents.base import (
    AgentIdentity,
    AgentSnapshot,
    BaseAgent,
)
from ai_quant_lab.agents.identifiers import (
    normalize_identifier_text,
    normalize_spoken_text,
)
from ai_quant_lab.agents.tasks import AgentTask, TaskBoard

DEFAULT_AGENT_IDENTITIES: tuple[AgentIdentity, ...] = (
    AgentIdentity(
        key="atlas",
        name="Atlas",
        role=(
            "Chief Quant Orchestrator: يحدد الأولويات ويوزع المهام "
            "ويمنع تكرار التجارب ويراقب سلسلة الأدلة"
        ),
        wake_names=(
            "أطلس",
            "اطلس",
            "يا أطلس",
            "يا اطلس",
            "Hey Atlas",
        ),
    ),
    AgentIdentity(
        key="vega",
        name="Vega",
        role=(
            "Data Engineer: يجمع البيانات وينظفها ويفحص جودتها "
            "وينشئ نسخاً ثابتة ويمنع الاختبار على بيانات تالفة"
        ),
        wake_names=(
            "فيغا",
            "يا فيغا",
            "Hey Vega",
        ),
    ),
    AgentIdentity(
        key="nova",
        name="Nova",
        role=(
            "Hypothesis Researcher: يقترح فرضيات اقتصادية أو سلوكية "
            "قابلة للدحض ويقفلها قبل رؤية نتائج الاختبار"
        ),
        wake_names=(
            "نوفا",
            "يا نوفا",
            "Hey Nova",
        ),
    ),
    AgentIdentity(
        key="chronos",
        name="Chronos",
        role=(
            "Backtest & Validation: ينفذ OOS وWalk-forward وcost stress "
            "ويقيس الثبات من دون تسريب بيانات"
        ),
        wake_names=(
            "كرونوس",
            "يا كرونوس",
            "Hey Chronos",
        ),
    ),
    AgentIdentity(
        key="iris",
        name="Iris",
        role=(
            "Regime Analyst: يصنف احتمالات حالات السوق والتحولات "
            "ويربط كل حالة بعائلات الاستراتيجيات المناسبة"
        ),
        wake_names=(
            "آيرس",
            "ايرس",
            "يا آيرس",
            "يا ايرس",
            "Hey Iris",
        ),
    ),
    AgentIdentity(
        key="sentinel",
        name="Sentinel",
        role=(
            "تدقيق النتائج وكشف الـOverfitting "
            "وتسريب البيانات والأخطاء البحثية"
        ),
        wake_names=(
            "سنتينل",
            "يا سنتينل",
            "Hey Sentinel",
        ),
    ),
    AgentIdentity(
        key="aegis",
        name="Aegis",
        role=(
            "Risk Manager: يرفض المخاطر ويخفض الحجم ويمتلك "
            "صلاحية الإيقاف الطارئ قبل أي ترقية"
        ),
        wake_names=(
            "إيجس",
            "ايجس",
            "يا إيجس",
            "يا ايجس",
            "Hey Aegis",
        ),
    ),
    AgentIdentity(
        key="oracle",
        name="Oracle",
        role=(
            "Macro & Cross-Asset: يدقق الفائدة والدولار والسندات والسيولة، "
            "ولا يخترع قيماً عندما تكون المصادر غير متاحة"
        ),
        wake_names=(
            "أوراكل",
            "اوراكل",
            "يا أوراكل",
            "يا اوراكل",
            "Hey Oracle",
        ),
    ),
    AgentIdentity(
        key="echo",
        name="Echo",
        role=(
            "Reporting & Voice: يلخص الأدلة والقرارات ويشرحها صوتياً "
            "ويميز الحقيقة التجريبية عن الاقتراح"
        ),
        wake_names=(
            "إيكو",
            "ايكو",
            "يا إيكو",
            "يا ايكو",
            "Hey Echo",
        ),
    ),
    AgentIdentity(
        key="forge",
        name="Forge",
        role=(
            "Strategy Evolution: ينشئ نسخاً مقيدة وقابلة للتدقيق "
            "ويسجل Challenger أو رفضاً من دون ترقية تلقائية"
        ),
        wake_names=(
            "فورج",
            "يا فورج",
            "Hey Forge",
        ),
    ),
)


class AgentTeam:
    """Thread-safe registry and call router for named agents.

    The team owns exactly one shared :class:`TaskBoard`. Every registered
    agent is bound to that board, so team status, agent status, and task
    reports all read the same rows.
    """

    def __init__(
        self,
        agents: Iterable[BaseAgent] = (),
        task_board: TaskBoard | None = None,
    ) -> None:
        self._lock = RLock()
        self._agents_by_key: dict[str, BaseAgent] = {}
        self._aliases_to_key: dict[str, str] = {}
        self._task_board = (
            task_board
            if task_board is not None
            else TaskBoard()
        )

        for agent in agents:
            self.register(agent)

    @property
    def task_board(self) -> TaskBoard:
        """Return the single task board shared by the whole team."""

        return self._task_board

    def register(
        self,
        agent: BaseAgent,
    ) -> None:
        """Register one agent and all its configured call names."""

        key = agent.identity.key

        with self._lock:
            if key in self._agents_by_key:
                raise ValueError(
                    f"Agent key '{key}' is already registered.",
                )

            aliases = self._identity_aliases(
                agent.identity,
            )

            for alias in aliases:
                existing_key = self._aliases_to_key.get(alias)

                if existing_key is not None:
                    raise ValueError(
                        f"Agent call name '{alias}' is already used "
                        f"by agent '{existing_key}'.",
                    )

            agent.bind_task_board(
                self._task_board,
            )

            self._agents_by_key[key] = agent

            for alias in aliases:
                self._aliases_to_key[alias] = key

    def has_agent(
        self,
        key: str,
    ) -> bool:
        """Return whether one agent key is registered in this team."""

        normalized_key = normalize_identifier_text(key)

        with self._lock:
            return normalized_key in self._agents_by_key

    def get_agent(
        self,
        key: str,
    ) -> BaseAgent:
        """Return one agent using its internal key."""

        normalized_key = normalize_identifier_text(key)

        with self._lock:
            agent = self._agents_by_key.get(
                normalized_key,
            )

        if agent is None:
            raise KeyError(
                f"Agent '{key}' is not registered.",
            )

        return agent

    def resolve_agent(
        self,
        spoken_text: str,
    ) -> BaseAgent | None:
        """Find the named agent addressed inside a sentence."""

        normalized_text = self._normalize_text(
            spoken_text,
        )

        if not normalized_text:
            return None

        with self._lock:
            aliases = sorted(
                self._aliases_to_key,
                key=len,
                reverse=True,
            )

            for alias in aliases:
                pattern = (
                    rf"(?<!\w)"
                    rf"{re.escape(alias)}"
                    rf"(?!\w)"
                )

                if re.search(
                    pattern,
                    normalized_text,
                ) is None:
                    continue

                agent_key = self._aliases_to_key[alias]

                return self._agents_by_key[agent_key]

        return None

    def call(
        self,
        spoken_text: str,
    ) -> str | None:
        """Call an agent by name and receive its current status reply."""

        agent = self.resolve_agent(
            spoken_text,
        )

        if agent is None:
            return None

        return agent.status_reply()

    def all_agents(
        self,
    ) -> tuple[BaseAgent, ...]:
        """Return all registered agents in registration order."""

        with self._lock:
            return tuple(
                self._agents_by_key.values(),
            )

    def all_snapshots(
        self,
    ) -> tuple[AgentSnapshot, ...]:
        """Return current status snapshots for the complete team."""

        return tuple(
            agent.snapshot()
            for agent in self.all_agents()
        )

    def status_summary(
        self,
    ) -> str:
        """Return a readable status report for the entire team."""

        agents = self.all_agents()

        if not agents:
            return "ما في أي Agent مسجّل حاليًا."

        return "\n".join(
            agent.status_reply()
            for agent in agents
        )

    def active_tasks(self) -> tuple[AgentTask, ...]:
        """Return every unfinished team task, most urgent first."""

        return self._task_board.active_tasks()

    def pending_tasks(self) -> tuple[AgentTask, ...]:
        """Return every unassigned backlog task, most urgent first."""

        return self._task_board.pending_tasks()

    def tasks_for_agent(
        self,
        key: str,
    ) -> tuple[AgentTask, ...]:
        """Return every task assigned to one registered agent."""

        return self.get_agent(key).assigned_tasks()

    @staticmethod
    def _identity_aliases(
        identity: AgentIdentity,
    ) -> set[str]:
        """Return all normalized call names for one identity."""

        raw_aliases = {
            identity.key,
            identity.name,
            *identity.wake_names,
        }

        return {
            AgentTeam._normalize_text(alias)
            for alias in raw_aliases
        }

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        """Normalize user text for reliable agent-name matching."""

        return normalize_spoken_text(value)


def create_default_agent_team(
    task_board: TaskBoard | None = None,
) -> AgentTeam:
    """Create the standard AI Quant Lab agent team."""

    agents = (
        BaseAgent(identity)
        for identity in DEFAULT_AGENT_IDENTITIES
    )

    return AgentTeam(
        agents,
        task_board=task_board,
    )
