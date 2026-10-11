from __future__ import annotations

import pytest

from ai_quant_lab.agents.base import (
    AgentIdentity,
    BaseAgent,
)
from ai_quant_lab.agents.console import AgentConsole
from ai_quant_lab.agents.tasks import TaskPriority
from ai_quant_lab.agents.team import AgentTeam


def test_console_calls_agent_by_arabic_name() -> None:
    console = AgentConsole()

    result = console.handle(
        "  يا أطلس شو عم تعمل؟  ",
    )

    assert result.success is True
    assert result.input_text == "يا أطلس شو عم تعمل؟"
    assert result.matched_agent_key == "atlas"

    assert result.reply == (
        "Atlas: أنا حاضر. "
        "ما عندي مهمة شغّالة هلق."
    )


def test_console_calls_agent_by_english_name() -> None:
    console = AgentConsole()

    result = console.handle(
        "Chronos status",
    )

    assert result.success is True
    assert result.matched_agent_key == "chronos"
    assert result.reply.startswith("Chronos:")


def test_console_reports_live_agent_work() -> None:
    console = AgentConsole()
    nova = console.team.get_agent("nova")

    nova.start_task(
        "ابتكار استراتيجية EURUSD",
        message="عم حلّل سلوك السعر.",
    )

    nova.update_progress(
        45,
        message="أنجزت أول نموذج للاستراتيجية.",
    )

    result = console.handle(
        "يا نوفا شو عم تعملي؟",
    )

    assert result.success is True
    assert result.matched_agent_key == "nova"

    assert result.reply == (
        "Nova: أنا عم اشتغل على "
        "ابتكار استراتيجية EURUSD. "
        "التقدّم 45%. "
        "أنجزت أول نموذج للاستراتيجية."
    )


@pytest.mark.parametrize(
    "command",
    [
        "حالة الفريق",
        "وضع الفريق",
        "team status",
        "status all",
    ],
)
def test_console_returns_team_status(
    command: str,
) -> None:
    console = AgentConsole()

    result = console.handle(command)

    assert result.success is True
    assert result.matched_agent_key is None

    lines = result.reply.splitlines()

    assert len(lines) == 10
    assert lines[0].startswith("Atlas:")
    assert lines[-1].startswith("Forge:")


@pytest.mark.parametrize(
    "command",
    [
        "الفريق",
        "الوكلاء",
        "agents",
        "list agents",
    ],
)
def test_console_lists_agents_and_roles(
    command: str,
) -> None:
    console = AgentConsole()

    result = console.handle(command)

    assert result.success is True
    assert result.reply.startswith(
        "فريق AI Quant Lab:",
    )

    assert "- Atlas (atlas):" in result.reply
    assert "- Vega (vega):" in result.reply
    assert "- Nova (nova):" in result.reply
    assert "- Chronos (chronos):" in result.reply
    assert "- Aegis (aegis):" in result.reply
    assert "- Forge (forge):" in result.reply


@pytest.mark.parametrize(
    "command",
    [
        "مساعدة",
        "ساعدني",
        "help",
        "commands",
    ],
)
def test_console_returns_help(
    command: str,
) -> None:
    console = AgentConsole()

    result = console.handle(command)

    assert result.success is True
    assert result.matched_agent_key is None
    assert result.reply.startswith(
        "الأوامر المتاحة:",
    )

    assert "يا Atlas شو عم تعمل؟" in result.reply
    assert "Chronos status" in result.reply
    assert "حالة الفريق" in result.reply


def test_console_rejects_empty_input() -> None:
    console = AgentConsole()

    result = console.handle("   ")

    assert result.success is False
    assert result.input_text == ""
    assert result.matched_agent_key is None

    assert result.reply == (
        "اكتب اسم الـAgent أو اكتب «مساعدة» "
        "لحتى أعرضلك الأوامر المتاحة."
    )


def test_console_rejects_unknown_agent() -> None:
    console = AgentConsole()

    result = console.handle(
        "يا مجهول شو عم تعمل؟",
    )

    assert result.success is False
    assert result.matched_agent_key is None

    assert result.reply == (
        "ما عرفت أي Agent عم تنادي. "
        "اكتب «الفريق» لأعرض الأسماء، أو نادِ واحد باسمه، "
        "مثل: يا Atlas شو عم تعمل؟"
    )


def test_console_uses_custom_team() -> None:
    custom_agent = BaseAgent(
        AgentIdentity(
            key="euro",
            name="Euro",
            role="متخصص بعملة اليورو",
            wake_names=(
                "يورو",
                "يا يورو",
            ),
        )
    )

    team = AgentTeam(
        [
            custom_agent,
        ]
    )

    console = AgentConsole(team)

    result = console.handle(
        "يا يورو شو عم تعمل؟",
    )

    assert result.success is True
    assert result.matched_agent_key == "euro"

    assert result.reply == (
        "Euro: أنا حاضر. "
        "ما عندي مهمة شغّالة هلق."
    )


def test_console_lists_empty_custom_team() -> None:
    console = AgentConsole(
        AgentTeam(),
    )

    result = console.handle(
        "الفريق",
    )

    assert result.success is True
    assert result.reply == (
        "ما في أي Agent مسجّل حاليًا."
    )


def test_console_team_status_for_empty_team() -> None:
    console = AgentConsole(
        AgentTeam(),
    )

    result = console.handle(
        "حالة الفريق",
    )

    assert result.success is True
    assert result.reply == (
        "ما في أي Agent مسجّل حاليًا."
    )


def test_console_exposes_the_atlas_coordinator() -> None:
    console = AgentConsole()

    assert console.coordinator is not None
    assert console.coordinator.team is console.team

    assert AgentConsole(AgentTeam()).coordinator is None


@pytest.mark.parametrize(
    "command",
    [
        "المهام",
        "tasks",
        "لوحة المهام",
        "active tasks",
    ],
)
def test_console_lists_active_tasks_from_the_board(
    command: str,
) -> None:
    console = AgentConsole()
    coordinator = console.coordinator

    assert coordinator is not None

    empty_result = console.handle(command)

    assert empty_result.success is True
    assert empty_result.matched_agent_key is None
    assert empty_result.reply == (
        "Atlas: ما في أي مهمة شغّالة عند الفريق هلق."
    )

    task = coordinator.delegate(
        agent_key="vega",
        title="تدقيق بيانات EURUSD",
        priority=TaskPriority.HIGH,
    )

    result = console.handle(command)

    assert result.success is True
    assert result.reply.splitlines() == [
        "Atlas: في 1 مهمة شغّالة:",
        (
            f"- [{task.task_id}] تدقيق بيانات EURUSD → vega "
            "(assigned, high, 0%)"
        ),
    ]


@pytest.mark.parametrize(
    "command",
    [
        "التقدّم",
        "تقدّم الفريق",
        "progress",
        "team progress",
    ],
)
def test_console_reports_real_team_progress(
    command: str,
) -> None:
    console = AgentConsole()
    coordinator = console.coordinator

    assert coordinator is not None

    empty_result = console.handle(command)

    assert empty_result.reply == (
        "Atlas: ما في أي مهمة مسجّلة على لوحة الفريق حاليًا."
    )

    task = coordinator.delegate(
        agent_key="chronos",
        title="باكتيست EURUSD",
    )

    console.team.task_board.start_task(task.task_id)
    console.team.task_board.update_progress(task.task_id, 25.0)

    result = console.handle(command)

    assert result.success is True
    assert result.reply.splitlines()[0] == (
        "Atlas: مجموع المهام 1، شغّالة 1، بالانتظار 0، "
        "مخلّصة 0، فاشلة 0، ملغاة 0. التقدّم العام 25%."
    )


def test_console_answers_task_questions_for_one_agent() -> None:
    console = AgentConsole()
    coordinator = console.coordinator

    assert coordinator is not None

    idle_result = console.handle("يا فيغا شو مهامك؟")

    assert idle_result.success is True
    assert idle_result.matched_agent_key == "vega"
    assert idle_result.reply == (
        "Vega: ما عندي أي مهمة مسندة إلي هلق."
    )

    task = coordinator.delegate(
        agent_key="vega",
        title="تحديث بيانات GBPUSD",
    )

    result = console.handle("يا فيغا شو مهامك؟")

    assert result.reply.splitlines() == [
        "Vega: عندي 1 مهمة شغّالة:",
        (
            f"- [{task.task_id}] تحديث بيانات GBPUSD "
            "(assigned, normal, 0%)"
        ),
    ]


def test_console_status_question_still_returns_agent_status() -> None:
    console = AgentConsole()
    coordinator = console.coordinator

    assert coordinator is not None

    coordinator.delegate(
        agent_key="nova",
        title="ابتكار استراتيجية EURUSD",
    )

    result = console.handle("يا نوفا شو عم تعملي؟")

    assert result.success is True
    assert result.reply == (
        "Nova: عندي مهمة مسندة إلي: ابتكار استراتيجية EURUSD. "
        "لسا ما بلّشت فيها."
    )


def test_console_reports_idle_agent_truthfully() -> None:
    console = AgentConsole()

    result = console.handle("يا إيكو شو عم تعمل؟")

    assert result.success is True
    assert result.reply == (
        "Echo: أنا حاضر. ما عندي مهمة شغّالة هلق."
    )


def test_console_help_mentions_the_task_commands() -> None:
    console = AgentConsole()

    result = console.handle("مساعدة")

    assert "المهام" in result.reply
    assert "تقدّم الفريق" in result.reply
    assert "يا Vega شو مهامك؟" in result.reply
