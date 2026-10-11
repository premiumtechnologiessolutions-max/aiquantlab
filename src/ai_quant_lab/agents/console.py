from __future__ import annotations

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from ai_quant_lab.agents.base import BaseAgent
from ai_quant_lab.agents.coordination import (
    DEFAULT_COORDINATOR_KEY,
    AtlasCoordinator,
)
from ai_quant_lab.agents.identifiers import normalize_spoken_text
from ai_quant_lab.agents.team import (
    AgentTeam,
    create_default_agent_team,
)


class AgentConsoleResult(BaseModel):
    """Immutable result produced by the agent command console."""

    model_config = ConfigDict(frozen=True)

    input_text: str
    reply: str = Field(min_length=1)

    matched_agent_key: str | None = None
    success: bool = True

    @field_validator("input_text")
    @classmethod
    def normalize_input_text(
        cls,
        value: str,
    ) -> str:
        """Normalize the original command text."""

        return value.strip()

    @field_validator("reply")
    @classmethod
    def normalize_reply(
        cls,
        value: str,
    ) -> str:
        """Reject empty console replies."""

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "Agent console reply cannot be empty.",
            )

        return normalized


class AgentConsole:
    """Text interface for calling and checking named agents."""

    _TEAM_STATUS_COMMANDS = frozenset(
        {
            "team status",
            "status team",
            "status all",
            "all status",
            "حالة الفريق",
            "وضع الفريق",
            "شو عم يعمل الفريق",
            "شو عم تعملوا",
            "خبرني عن الفريق",
        }
    )

    _TEAM_LIST_COMMANDS = frozenset(
        {
            "team",
            "agents",
            "list agents",
            "show agents",
            "الفريق",
            "الوكلاء",
            "الايجنتس",
            "الإيجنتس",
            "اسماء الفريق",
            "أسماء الفريق",
        }
    )

    _HELP_COMMANDS = frozenset(
        {
            "help",
            "commands",
            "مساعدة",
            "ساعدني",
            "الاوامر",
            "الأوامر",
            "شو فيني قول",
        }
    )

    _ACTIVE_TASK_COMMANDS = frozenset(
        {
            "tasks",
            "active tasks",
            "task board",
            "المهام",
            "المهام الشغالة",
            "المهام الشغّالة",
            "لوحة المهام",
            "شو المهام",
        }
    )

    _TEAM_PROGRESS_COMMANDS = frozenset(
        {
            "progress",
            "team progress",
            "التقدم",
            "التقدّم",
            "تقدم الفريق",
            "تقدّم الفريق",
            "شو انجزتوا",
        }
    )

    _AGENT_TASK_KEYWORDS: tuple[str, ...] = (
        "مهامك",
        "مهامه",
        "مهاما",
        "المهام",
        "مهام",
        "tasks",
    )

    def __init__(
        self,
        team: AgentTeam | None = None,
    ) -> None:
        self._team = (
            team
            if team is not None
            else create_default_agent_team()
        )

        self._coordinator = (
            AtlasCoordinator(self._team)
            if self._team.has_agent(DEFAULT_COORDINATOR_KEY)
            else None
        )

    @property
    def team(self) -> AgentTeam:
        """Return the agent team used by this console."""

        return self._team

    @property
    def coordinator(self) -> AtlasCoordinator | None:
        """Return the Atlas coordinator when the team registers one."""

        return self._coordinator

    def handle(
        self,
        text: str,
    ) -> AgentConsoleResult:
        """Process one written command and return a readable reply."""

        original_text = text.strip()

        if not original_text:
            return AgentConsoleResult(
                input_text="",
                reply=(
                    "اكتب اسم الـAgent أو اكتب «مساعدة» "
                    "لحتى أعرضلك الأوامر المتاحة."
                ),
                success=False,
            )

        matched_agent = self._team.resolve_agent(
            original_text,
        )

        if matched_agent is not None:
            return AgentConsoleResult(
                input_text=original_text,
                reply=self._agent_reply(
                    matched_agent,
                    original_text,
                ),
                matched_agent_key=matched_agent.identity.key,
            )

        normalized_text = self._normalize_text(
            original_text,
        )

        if normalized_text in self._ACTIVE_TASK_COMMANDS:
            return AgentConsoleResult(
                input_text=original_text,
                reply=self.active_tasks_reply(),
            )

        if normalized_text in self._TEAM_PROGRESS_COMMANDS:
            return AgentConsoleResult(
                input_text=original_text,
                reply=self.team_progress_reply(),
            )

        if normalized_text in self._TEAM_STATUS_COMMANDS:
            return AgentConsoleResult(
                input_text=original_text,
                reply=self._team.status_summary(),
            )

        if normalized_text in self._TEAM_LIST_COMMANDS:
            return AgentConsoleResult(
                input_text=original_text,
                reply=self.agent_list_reply(),
            )

        if normalized_text in self._HELP_COMMANDS:
            return AgentConsoleResult(
                input_text=original_text,
                reply=self.help_reply(),
            )

        return AgentConsoleResult(
            input_text=original_text,
            reply=(
                "ما عرفت أي Agent عم تنادي. "
                "اكتب «الفريق» لأعرض الأسماء، أو نادِ واحد باسمه، "
                "مثل: يا Atlas شو عم تعمل؟"
            ),
            success=False,
        )

    def active_tasks_reply(self) -> str:
        """Return every unfinished team task straight from the task board."""

        if self._coordinator is not None:
            return self._coordinator.active_tasks_reply()

        tasks = self._team.active_tasks()

        if not tasks:
            return "ما في أي مهمة شغّالة عند الفريق هلق."

        lines = [
            f"في {len(tasks)} مهمة شغّالة:",
        ]

        lines.extend(
            (
                f"- [{task.task_id}] {task.title} "
                f"→ {task.assigned_agent_key} "
                f"({task.status.value}, {task.priority.value}, "
                f"{task.progress_percent:.0f}%)"
            )
            for task in tasks
        )

        return "\n".join(lines)

    def team_progress_reply(self) -> str:
        """Return the real progress of the team from the shared task board."""

        if self._coordinator is not None:
            return self._coordinator.progress_reply()

        tasks = self._team.task_board.all_tasks()

        if not tasks:
            return "ما في أي مهمة مسجّلة على لوحة الفريق حاليًا."

        return (
            f"مجموع المهام {len(tasks)}، "
            f"شغّالة {len(self._team.active_tasks())}."
        )

    def _agent_reply(
        self,
        agent: BaseAgent,
        original_text: str,
    ) -> str:
        """Return the status or the task list requested from one agent."""

        normalized_text = self._normalize_text(original_text)

        if any(
            keyword in normalized_text
            for keyword in self._AGENT_TASK_KEYWORDS
        ):
            return agent.tasks_reply()

        return agent.status_reply()

    def agent_list_reply(self) -> str:
        """Return all agent names with their current specializations."""

        agents = self._team.all_agents()

        if not agents:
            return "ما في أي Agent مسجّل حاليًا."

        lines = [
            "فريق AI Quant Lab:",
        ]

        lines.extend(
            (
                f"- {agent.identity.name} "
                f"({agent.identity.key}): "
                f"{agent.identity.role}"
            )
            for agent in agents
        )

        return "\n".join(lines)

    @staticmethod
    def help_reply() -> str:
        """Return examples of commands accepted by the console."""

        return (
            "الأوامر المتاحة:\n"
            "- يا Atlas شو عم تعمل؟\n"
            "- Chronos status\n"
            "- يا Nova شو مهمتك؟\n"
            "- يا Vega شو مهامك؟\n"
            "- المهام\n"
            "- تقدّم الفريق\n"
            "- حالة الفريق\n"
            "- الفريق\n"
            "- مساعدة"
        )

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        """Normalize command text for reliable comparison."""

        return normalize_spoken_text(value)