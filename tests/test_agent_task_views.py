from __future__ import annotations

import pytest

from ai_quant_lab.agents.base import (
    AgentIdentity,
    AgentState,
    BaseAgent,
)
from ai_quant_lab.agents.tasks import (
    TaskBoard,
    TaskPriority,
    TaskStatus,
)
from ai_quant_lab.agents.team import (
    AgentTeam,
    create_default_agent_team,
)


def make_agent(
    key: str = "vega",
    name: str = "Vega",
    task_board: TaskBoard | None = None,
) -> BaseAgent:
    """Create one controlled agent for task-view tests."""

    identity = AgentIdentity(
        key=key,
        name=name,
        role="جمع وتدقيق بيانات السوق",
    )

    return BaseAgent(identity, task_board)


def test_standalone_agent_owns_a_private_task_board() -> None:
    first = make_agent("vega", "Vega")
    second = make_agent("nova", "Nova")

    assert first.task_board is not second.task_board

    first.start_task("تدقيق بيانات EURUSD")

    assert len(first.task_board.all_tasks()) == 1
    assert second.task_board.all_tasks() == ()


def test_agent_start_task_writes_a_real_board_row() -> None:
    agent = make_agent()

    agent.start_task(
        "تدقيق بيانات EURUSD",
        message="بلّشت الفحص.",
        priority=TaskPriority.HIGH,
    )

    tasks = agent.assigned_tasks()

    assert len(tasks) == 1

    task = tasks[0]

    assert task.title == "تدقيق بيانات EURUSD"
    assert task.status is TaskStatus.RUNNING
    assert task.priority is TaskPriority.HIGH
    assert task.assigned_agent_key == "vega"
    assert task.required_agent_key == "vega"
    assert task.status_note == "بلّشت الفحص."


def test_agent_snapshot_tracks_board_changes_made_elsewhere() -> None:
    board = TaskBoard()
    agent = make_agent(task_board=board)

    task = board.create_task(
        title="تدقيق جودة البيانات",
        required_agent_key="vega",
    )

    board.assign_task(task.task_id, "vega")

    snapshot = agent.snapshot()

    assert snapshot.state is AgentState.ASSIGNED
    assert snapshot.current_task == "تدقيق جودة البيانات"
    assert snapshot.current_task_id == task.task_id
    assert snapshot.active_task_count == 1
    assert snapshot.progress_percent == 0.0

    assert agent.status_reply() == (
        "Vega: عندي مهمة مسندة إلي: تدقيق جودة البيانات. "
        "لسا ما بلّشت فيها."
    )

    board.start_task(task.task_id, note="بلّشت.")
    board.update_progress(task.task_id, 70.0, note="خلّصت أغلب الفحص.")

    assert agent.status_reply() == (
        "Vega: أنا عم اشتغل على تدقيق جودة البيانات. "
        "التقدّم 70%. خلّصت أغلب الفحص."
    )


def test_agent_reports_cancelled_task_truthfully() -> None:
    board = TaskBoard()
    agent = make_agent(task_board=board)

    agent.start_task("مهمة انلغت")
    task = agent.active_task()

    assert task is not None

    board.cancel_task(task.task_id)

    snapshot = agent.snapshot()

    assert snapshot.state is AgentState.CANCELLED
    assert snapshot.active_task_count == 0

    assert agent.status_reply() == (
        "Vega: انلغت مهمة مهمة انلغت. المهمة انلغت."
    )


def test_agent_refuses_a_second_concurrent_task() -> None:
    agent = make_agent()

    agent.start_task("المهمة الأولى")

    with pytest.raises(
        RuntimeError,
        match="already has an active task",
    ):
        agent.start_task("المهمة التانية")


def test_agent_can_start_a_task_assigned_by_the_board() -> None:
    board = TaskBoard()
    agent = make_agent(task_board=board)

    task = board.create_task(
        title="تحديث بيانات GBPUSD",
        required_agent_key="vega",
    )

    board.assign_task(task.task_id, "vega")

    snapshot = agent.start_assigned_task(message="بلّشت التحديث.")

    assert snapshot.state is AgentState.WORKING
    assert board.get_task(task.task_id).status is TaskStatus.RUNNING


def test_agent_rejects_starting_a_task_of_another_agent() -> None:
    board = TaskBoard()
    agent = make_agent(task_board=board)

    task = board.create_task(title="مهمة نوفا")
    board.assign_task(task.task_id, "nova")

    with pytest.raises(
        ValueError,
        match="is not assigned to agent 'vega'",
    ):
        agent.start_assigned_task(task.task_id)


def test_agent_without_assigned_task_cannot_start_one() -> None:
    agent = make_agent()

    with pytest.raises(
        RuntimeError,
        match="has no assigned task to start",
    ):
        agent.start_assigned_task()


def test_agent_progress_auto_starts_an_assigned_task() -> None:
    board = TaskBoard()
    agent = make_agent(task_board=board)

    task = board.create_task(
        title="مهمة مسندة",
        required_agent_key="vega",
    )

    board.assign_task(task.task_id, "vega")

    snapshot = agent.update_progress(25.0, message="بلّشت وتقدّمت.")

    assert snapshot.state is AgentState.WORKING
    assert snapshot.progress_percent == 25.0
    assert board.get_task(task.task_id).status is TaskStatus.RUNNING


def test_agent_selects_the_most_urgent_task_as_current_work() -> None:
    board = TaskBoard()
    agent = make_agent(task_board=board)

    low = board.create_task(
        title="مهمة منخفضة",
        priority=TaskPriority.LOW,
        required_agent_key="vega",
    )

    critical = board.create_task(
        title="مهمة حرجة",
        priority=TaskPriority.CRITICAL,
        required_agent_key="vega",
    )

    for task in (low, critical):
        board.assign_task(task.task_id, "vega")

    snapshot = agent.snapshot()

    assert snapshot.active_task_count == 2
    assert snapshot.current_task == "مهمة حرجة"

    board.start_task(low.task_id)

    assert agent.snapshot().current_task == "مهمة منخفضة"


def test_agent_reset_cancels_outstanding_work() -> None:
    board = TaskBoard()
    agent = make_agent(task_board=board)

    first = board.create_task(title="أولى", required_agent_key="vega")
    second = board.create_task(title="تانية", required_agent_key="vega")

    for task in (first, second):
        board.assign_task(task.task_id, "vega")

    snapshot = agent.reset()

    assert snapshot.state is AgentState.IDLE
    assert snapshot.current_task is None
    assert snapshot.active_task_count == 0

    assert board.get_task(first.task_id).status is TaskStatus.CANCELLED
    assert board.get_task(second.task_id).status is TaskStatus.CANCELLED


def test_agent_reset_acknowledges_finished_work() -> None:
    agent = make_agent()

    agent.start_task("مهمة خلصانة")
    agent.complete_task(message="خلصت.")

    assert agent.snapshot().state is AgentState.COMPLETED
    assert agent.last_finished_task() is not None

    agent.reset()

    assert agent.snapshot().state is AgentState.IDLE
    assert agent.last_finished_task() is None
    assert len(agent.assigned_tasks()) == 1


def test_agent_stop_preserves_task_context_and_resumes() -> None:
    agent = make_agent()

    agent.start_task("فحص حالة النظام")
    agent.update_progress(25.0)

    stopped = agent.stop(message="تم الإيقاف بطلب المستخدم.")

    assert stopped.state is AgentState.STOPPED
    assert stopped.current_task == "فحص حالة النظام"
    assert stopped.progress_percent == 25.0

    resumed = agent.update_progress(40.0, message="رجعت اشتغل.")

    assert resumed.state is AgentState.WORKING
    assert resumed.progress_percent == 40.0


def test_agent_reports_latest_finished_task() -> None:
    agent = make_agent()

    agent.start_task("المهمة الأولى")
    agent.complete_task(message="خلصت الأولى.")

    agent.start_task("المهمة التانية")
    agent.fail_task(message="وقفت التانية.")

    latest = agent.last_finished_task()

    assert latest is not None
    assert latest.title == "المهمة التانية"
    assert agent.snapshot().state is AgentState.ERROR


def test_agent_tasks_reply_is_truthful_when_idle() -> None:
    agent = make_agent()

    assert agent.tasks_reply() == (
        "Vega: ما عندي أي مهمة مسندة إلي هلق."
    )


def test_agent_tasks_reply_lists_real_tasks() -> None:
    board = TaskBoard()
    agent = make_agent(task_board=board)

    first = board.create_task(
        title="تحديث EURUSD",
        required_agent_key="vega",
        priority=TaskPriority.HIGH,
    )

    second = board.create_task(
        title="تحديث GBPUSD",
        required_agent_key="vega",
    )

    for task in (first, second):
        board.assign_task(task.task_id, "vega")

    board.start_task(first.task_id)
    board.update_progress(first.task_id, 30.0)

    reply = agent.tasks_reply()

    assert reply.splitlines() == [
        "Vega: عندي 2 مهمة شغّالة:",
        f"- [{first.task_id}] تحديث EURUSD (running, high, 30%)",
        f"- [{second.task_id}] تحديث GBPUSD (assigned, normal, 0%)",
    ]


def test_agent_tasks_reply_mentions_last_finished_task() -> None:
    agent = make_agent()

    agent.start_task("تدقيق قديم")
    agent.complete_task(message="خلصت.")

    assert agent.tasks_reply() == (
        "Vega: ما عندي مهمة شغّالة. آخر مهمة: تدقيق قديم (completed)."
    )


def test_team_shares_one_task_board_across_all_agents() -> None:
    team = create_default_agent_team()
    board = team.task_board

    for agent in team.all_agents():
        assert agent.task_board is board

    vega = team.get_agent("vega")
    chronos = team.get_agent("chronos")

    vega.start_task("تدقيق بيانات")
    chronos.start_task("تشغيل باكتيست")

    assert len(board.all_tasks()) == 2
    assert len(team.active_tasks()) == 2
    assert len(team.tasks_for_agent("vega")) == 1


def test_team_registration_binds_the_shared_board() -> None:
    board = TaskBoard()
    team = AgentTeam(task_board=board)
    agent = make_agent()

    assert agent.task_board is not board

    team.register(agent)

    assert agent.task_board is board


def test_agent_with_existing_tasks_cannot_be_rebound() -> None:
    agent = make_agent()

    agent.start_task("مهمة موجودة")

    with pytest.raises(
        RuntimeError,
        match="already owns tasks",
    ):
        AgentTeam([agent])


def test_rebinding_to_the_same_board_is_a_no_operation() -> None:
    board = TaskBoard()
    agent = make_agent(task_board=board)

    agent.start_task("مهمة موجودة")
    agent.bind_task_board(board)

    assert agent.task_board is board


def test_team_reports_pending_backlog() -> None:
    team = create_default_agent_team()

    team.task_board.create_task(
        title="بحث لاحق",
        required_agent_key="nova",
    )

    assert len(team.pending_tasks()) == 1
    assert team.active_tasks() == ()


def test_team_rejects_task_lookup_for_unknown_agent() -> None:
    team = create_default_agent_team()

    assert team.has_agent("vega") is True
    assert team.has_agent("unknown") is False

    with pytest.raises(
        KeyError,
        match="is not registered",
    ):
        team.tasks_for_agent("unknown")
