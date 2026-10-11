from __future__ import annotations

import pytest

from ai_quant_lab.agents.base import (
    AgentIdentity,
    AgentState,
    BaseAgent,
)
from ai_quant_lab.agents.coordination import AtlasCoordinator
from ai_quant_lab.agents.tasks import TaskPriority, TaskStatus
from ai_quant_lab.agents.team import AgentTeam, create_default_agent_team


def make_coordinator() -> AtlasCoordinator:
    """Create an Atlas coordinator over the standard agent team."""

    return AtlasCoordinator(
        create_default_agent_team(),
    )


def test_coordinator_requires_a_registered_coordinator_agent() -> None:
    team = AgentTeam(
        [
            BaseAgent(
                AgentIdentity(
                    key="vega",
                    name="Vega",
                    role="بيانات",
                )
            )
        ]
    )

    with pytest.raises(
        KeyError,
        match="Coordinator agent 'atlas' is not registered",
    ):
        AtlasCoordinator(team)


def test_coordinator_rejects_invalid_coordinator_key() -> None:
    with pytest.raises(
        ValueError,
        match="Coordinator key must start with a letter",
    ):
        AtlasCoordinator(
            create_default_agent_team(),
            coordinator_key="9atlas",
        )


def test_coordinator_uses_the_shared_team_board() -> None:
    coordinator = make_coordinator()

    assert coordinator.task_board is coordinator.team.task_board
    assert coordinator.coordinator.identity.key == "atlas"


def test_atlas_delegates_a_task_to_a_named_agent() -> None:
    coordinator = make_coordinator()

    task = coordinator.delegate(
        agent_key="Vega",
        title="تدقيق بيانات EURUSD M15",
        description="فحص الفجوات والجودة",
        priority=TaskPriority.HIGH,
        tags=("data-quality", "eurusd"),
    )

    assert task.status is TaskStatus.ASSIGNED
    assert task.assigned_agent_key == "vega"
    assert task.required_agent_key == "vega"
    assert task.priority is TaskPriority.HIGH
    assert task.tags == ("data_quality", "eurusd")

    vega = coordinator.team.get_agent("vega")

    assert vega.snapshot().state is AgentState.ASSIGNED
    assert vega.snapshot().current_task == "تدقيق بيانات EURUSD M15"


@pytest.mark.parametrize(
    "agent_key",
    [
        "unknown",
        "atlas_two",
        "vegaa",
    ],
)
def test_atlas_rejects_delegation_to_unknown_agent(
    agent_key: str,
) -> None:
    coordinator = make_coordinator()

    with pytest.raises(
        KeyError,
        match="is not registered in the team",
    ):
        coordinator.delegate(
            agent_key=agent_key,
            title="مهمة",
        )

    assert coordinator.task_board.all_tasks() == ()


def test_atlas_rejects_invalid_agent_key_format() -> None:
    coordinator = make_coordinator()

    with pytest.raises(
        ValueError,
        match="Agent key must start with a letter",
    ):
        coordinator.delegate(
            agent_key="1vega",
            title="مهمة",
        )


def test_atlas_plans_backlog_and_dispatches_it() -> None:
    coordinator = make_coordinator()

    planned = coordinator.plan_task(
        title="بحث عن استراتيجية جديدة",
        required_agent_key="nova",
        priority=TaskPriority.CRITICAL,
    )

    unrouted = coordinator.plan_task(
        title="مهمة بدون Agent محدد",
    )

    assert planned.status is TaskStatus.PENDING
    assert len(coordinator.task_board.pending_tasks()) == 2

    dispatched = coordinator.dispatch_backlog()

    assert [task.task_id for task in dispatched] == [planned.task_id]
    assert coordinator.task_board.get_task(
        planned.task_id,
    ).assigned_agent_key == "nova"

    assert coordinator.task_board.get_task(
        unrouted.task_id,
    ).status is TaskStatus.PENDING


def test_atlas_rejects_planning_for_unknown_agent() -> None:
    coordinator = make_coordinator()

    with pytest.raises(
        KeyError,
        match="is not registered in the team",
    ):
        coordinator.plan_task(
            title="مهمة",
            required_agent_key="ghost",
        )


def test_atlas_assigns_and_reassigns_existing_tasks() -> None:
    coordinator = make_coordinator()

    planned = coordinator.plan_task(title="تحليل حالة السوق")

    assigned = coordinator.assign(planned.task_id, "iris")

    assert assigned.assigned_agent_key == "iris"

    reassigned = coordinator.reassign(planned.task_id, "chronos")

    assert reassigned.assigned_agent_key == "chronos"
    assert reassigned.status is TaskStatus.ASSIGNED

    assert coordinator.tasks_for_agent("iris") == ()
    assert len(coordinator.tasks_for_agent("chronos")) == 1


def test_atlas_rejects_assignment_to_unknown_agent() -> None:
    coordinator = make_coordinator()

    planned = coordinator.plan_task(title="مهمة")

    with pytest.raises(
        KeyError,
        match="is not registered in the team",
    ):
        coordinator.assign(planned.task_id, "ghost")

    with pytest.raises(
        KeyError,
        match="is not registered in the team",
    ):
        coordinator.reassign(planned.task_id, "ghost")


def test_atlas_builds_a_task_tree_and_cancels_it() -> None:
    coordinator = make_coordinator()

    parent = coordinator.delegate(
        agent_key="atlas",
        title="خطة بحث EURUSD",
    )

    child = coordinator.delegate(
        agent_key="vega",
        title="تحضير البيانات",
        parent_task_id=parent.task_id,
    )

    assert child.parent_task_id == parent.task_id

    coordinator.cancel(parent.task_id)

    assert coordinator.task_board.get_task(
        child.task_id,
    ).status is TaskStatus.CANCELLED

    vega = coordinator.team.get_agent("vega")

    assert vega.active_task() is None


def test_atlas_lists_unassigned_agents() -> None:
    coordinator = make_coordinator()

    coordinator.delegate(agent_key="vega", title="مهمة بيانات")

    free_keys = {
        agent.identity.key
        for agent in coordinator.unassigned_agents()
    }

    assert "vega" not in free_keys
    assert "nova" in free_keys
    assert len(free_keys) == 9


def test_atlas_reports_one_agent_workload() -> None:
    coordinator = make_coordinator()

    first = coordinator.delegate(agent_key="vega", title="مهمة أولى")
    coordinator.delegate(agent_key="vega", title="مهمة تانية")

    board = coordinator.task_board
    board.start_task(first.task_id)
    board.update_progress(first.task_id, 60.0)

    workload = coordinator.workload("vega")

    assert workload.agent_key == "vega"
    assert workload.agent_name == "Vega"
    assert workload.active_tasks == 2
    assert workload.completed_tasks == 0
    assert workload.total_tasks == 2
    assert workload.is_busy is True
    assert workload.current_task_id == first.task_id
    assert workload.current_task_title == "مهمة أولى"
    assert workload.current_progress_percent == 60.0


def test_atlas_rejects_workload_for_unknown_agent() -> None:
    coordinator = make_coordinator()

    with pytest.raises(
        KeyError,
        match="is not registered in the team",
    ):
        coordinator.workload("ghost")


def test_atlas_progress_report_counts_every_status() -> None:
    coordinator = make_coordinator()
    board = coordinator.task_board

    completed = coordinator.delegate(agent_key="vega", title="مخلّصة")
    board.start_task(completed.task_id)
    board.complete_task(completed.task_id, result_summary="خلصت")

    failed = coordinator.delegate(agent_key="nova", title="فاشلة")
    board.start_task(failed.task_id)
    board.update_progress(failed.task_id, 40.0)
    board.fail_task(failed.task_id, error_message="خطأ")

    cancelled = coordinator.delegate(agent_key="iris", title="ملغاة")
    board.cancel_task(cancelled.task_id)

    running = coordinator.delegate(agent_key="chronos", title="شغّالة")
    board.start_task(running.task_id)
    board.update_progress(running.task_id, 20.0)

    coordinator.plan_task(title="بالانتظار")

    report = coordinator.progress_report()

    assert report.total_tasks == 5
    assert report.completed_tasks == 1
    assert report.failed_tasks == 1
    assert report.cancelled_tasks == 1
    assert report.active_tasks == 1
    assert report.pending_tasks == 1

    # Mean of 100, 40, 20, and 0 across the four non-cancelled tasks.
    assert report.progress_percent == 40.0

    assert len(report.workloads) == 10
    assert {
        workload.agent_key
        for workload in report.busy_agents
    } == {"chronos"}

    assert len(report.idle_agents) == 9


def test_atlas_progress_report_is_empty_for_a_fresh_team() -> None:
    coordinator = make_coordinator()

    report = coordinator.progress_report()

    assert report.total_tasks == 0
    assert report.progress_percent == 0.0
    assert report.busy_agents == ()
    assert len(report.idle_agents) == 10


def test_atlas_progress_reply_reads_real_task_state() -> None:
    coordinator = make_coordinator()

    assert coordinator.progress_reply() == (
        "Atlas: ما في أي مهمة مسجّلة على لوحة الفريق حاليًا."
    )

    task = coordinator.delegate(
        agent_key="chronos",
        title="باكتيست EURUSD",
    )

    coordinator.task_board.start_task(task.task_id)
    coordinator.task_board.update_progress(task.task_id, 50.0)

    lines = coordinator.progress_reply().splitlines()

    assert lines[0] == (
        "Atlas: مجموع المهام 1، شغّالة 1، بالانتظار 0، "
        "مخلّصة 0، فاشلة 0، ملغاة 0. التقدّم العام 50%."
    )

    assert lines[1] == (
        "- Chronos: 1 مهمة شغّالة (باكتيست EURUSD, 50%)"
    )


def test_atlas_progress_reply_reports_an_idle_team() -> None:
    coordinator = make_coordinator()
    board = coordinator.task_board

    task = coordinator.delegate(agent_key="vega", title="مهمة")
    board.start_task(task.task_id)
    board.complete_task(task.task_id, result_summary="خلصت")

    lines = coordinator.progress_reply().splitlines()

    assert lines[-1] == "ما في أي Agent عم يشتغل على مهمة هلق."


def test_atlas_active_tasks_reply_lists_real_rows() -> None:
    coordinator = make_coordinator()

    assert coordinator.active_tasks_reply() == (
        "Atlas: ما في أي مهمة شغّالة عند الفريق هلق."
    )

    task = coordinator.delegate(
        agent_key="sentinel",
        title="تدقيق مستقل",
        priority=TaskPriority.CRITICAL,
    )

    lines = coordinator.active_tasks_reply().splitlines()

    assert lines == [
        "Atlas: في 1 مهمة شغّالة:",
        (
            f"- [{task.task_id}] تدقيق مستقل → sentinel "
            "(assigned, critical, 0%)"
        ),
    ]
