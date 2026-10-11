"""Named AI agent team, shared task board, and coordination APIs."""

from __future__ import annotations

from ai_quant_lab.agents.activity import (
    ActivityEvent,
    ActivityJournal,
    ActivityType,
)
from ai_quant_lab.agents.base import (
    DEFAULT_STOP_MESSAGE,
    IDLE_AGENT_MESSAGE,
    AgentIdentity,
    AgentSnapshot,
    AgentState,
    BaseAgent,
)
from ai_quant_lab.agents.console import (
    AgentConsole,
    AgentConsoleResult,
)
from ai_quant_lab.agents.coordination import (
    DEFAULT_COORDINATOR_KEY,
    AgentWorkload,
    AtlasCoordinator,
    TeamProgress,
)
from ai_quant_lab.agents.identifiers import (
    normalize_identifier,
    normalize_identifier_text,
    normalize_spoken_text,
)
from ai_quant_lab.agents.messages import (
    AgentMessage,
    AgentMessageBus,
    AgentMessageBusListener,
)
from ai_quant_lab.agents.tasks import (
    ACTIVE_TASK_STATUSES,
    TERMINAL_TASK_STATUSES,
    AgentTask,
    TaskBoard,
    TaskBoardListener,
    TaskPriority,
    TaskStatus,
)
from ai_quant_lab.agents.team import (
    DEFAULT_AGENT_IDENTITIES,
    AgentTeam,
    create_default_agent_team,
)

__all__ = [
    "ACTIVE_TASK_STATUSES",
    "DEFAULT_AGENT_IDENTITIES",
    "DEFAULT_COORDINATOR_KEY",
    "DEFAULT_STOP_MESSAGE",
    "IDLE_AGENT_MESSAGE",
    "TERMINAL_TASK_STATUSES",
    "ActivityEvent",
    "ActivityJournal",
    "ActivityType",
    "AgentConsole",
    "AgentConsoleResult",
    "AgentIdentity",
    "AgentMessage",
    "AgentMessageBus",
    "AgentMessageBusListener",
    "AgentSnapshot",
    "AgentState",
    "AgentTask",
    "AgentTeam",
    "AgentWorkload",
    "AtlasCoordinator",
    "BaseAgent",
    "TaskBoard",
    "TaskBoardListener",
    "TaskPriority",
    "TaskStatus",
    "TeamProgress",
    "create_default_agent_team",
    "normalize_identifier",
    "normalize_identifier_text",
    "normalize_spoken_text",
]
