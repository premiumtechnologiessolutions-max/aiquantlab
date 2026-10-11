from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread

import pytest
from pydantic import ValidationError

from ai_quant_lab.agents.tasks import (
    ACTIVE_TASK_STATUSES,
    TERMINAL_TASK_STATUSES,
    AgentTask,
    TaskBoard,
    TaskPriority,
    TaskStatus,
)


class RecordingListener:
    """Collect every committed task change for assertions."""

    def __init__(self) -> None:
        self.events: list[tuple[str | None, str]] = []

    def on_task_changed(
        self,
        previous: AgentTask | None,
        current: AgentTask,
    ) -> None:
        """Record one committed task transition."""

        self.events.append(
            (
                previous.status.value if previous is not None else None,
                current.status.value,
            )
        )


def make_running_task(
    board: TaskBoard,
    *,
    agent_key: str = "chronos",
) -> AgentTask:
    """Create, assign, and start one task for lifecycle tests."""

    task = board.create_task(
        title="تشغيل باكتيست EURUSD M15",
    )

    board.assign_task(task.task_id, agent_key)

    return board.start_task(task.task_id)


def test_task_normalizes_identifiers_and_text() -> None:
    task = AgentTask(
        task_id="  Task-One  ",
        title="  تحليل البيانات  ",
        description="  تحليل جودة بيانات EURUSD  ",
        required_agent_key="  Vega  ",
        tags=(
            " Data Quality ",
            "data-quality",
            "EURUSD",
        ),
    )

    assert task.task_id == "task_one"
    assert task.title == "تحليل البيانات"
    assert task.description == "تحليل جودة بيانات EURUSD"
    assert task.required_agent_key == "vega"
    assert task.tags == ("data_quality", "eurusd")
    assert task.status is TaskStatus.PENDING
    assert task.is_pending is True
    assert task.is_active is False
    assert task.is_terminal is False


@pytest.mark.parametrize(
    "task_id",
    [
        "1task",
        "task!",
        "   ",
        "_task",
    ],
)
def test_task_rejects_invalid_identifier(
    task_id: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="Task ID must start with a letter",
    ):
        AgentTask(
            task_id=task_id,
            title="مهمة",
            description="وصف المهمة",
        )


def test_task_rejects_empty_text() -> None:
    with pytest.raises(
        ValidationError,
        match="Task text cannot be empty",
    ):
        AgentTask(
            task_id="task_one",
            title="   ",
            description="وصف",
        )


def test_task_rejects_empty_tag() -> None:
    with pytest.raises(
        ValidationError,
        match="Task tags cannot be empty",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            tags=("data", "   "),
        )


def test_task_rejects_naive_timestamp() -> None:
    with pytest.raises(
        ValidationError,
        match="timezone information",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            # Intentionally naive to verify timestamp validation.
            created_at=datetime(2026, 8, 1, 12),  # noqa: DTZ001
        )


def test_task_normalizes_timestamp_to_utc() -> None:
    created = datetime(
        2026,
        8,
        1,
        12,
        tzinfo=UTC,
    ).astimezone(
        tz=None,
    )

    task = AgentTask(
        task_id="task_one",
        title="مهمة",
        description="وصف",
        created_at=created,
        updated_at=created,
    )

    assert task.created_at.tzinfo == UTC
    assert task.created_at == datetime(2026, 8, 1, 12, tzinfo=UTC)


def test_task_rejects_update_before_creation() -> None:
    created = datetime(2026, 8, 1, 12, tzinfo=UTC)

    with pytest.raises(
        ValidationError,
        match="cannot be earlier than creation time",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            created_at=created,
            updated_at=created - timedelta(seconds=1),
        )


def test_task_rejects_self_parent() -> None:
    with pytest.raises(
        ValidationError,
        match="cannot be its own parent",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            parent_task_id="task_one",
        )


def test_pending_task_rejects_assigned_agent() -> None:
    with pytest.raises(
        ValidationError,
        match="pending task cannot have an assigned agent",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            status=TaskStatus.PENDING,
            assigned_agent_key="vega",
        )


def test_pending_task_rejects_progress() -> None:
    with pytest.raises(
        ValidationError,
        match="pending task must have zero progress",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            status=TaskStatus.PENDING,
            progress_percent=10.0,
        )


@pytest.mark.parametrize(
    "status",
    sorted(
        ACTIVE_TASK_STATUSES
        | {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
        }
    ),
)
def test_task_requires_assigned_agent_for_active_status(
    status: TaskStatus,
) -> None:
    with pytest.raises(
        ValidationError,
        match="requires an assigned agent",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            status=status,
            progress_percent=(
                100.0
                if status is TaskStatus.COMPLETED
                else 0.0
            ),
            result_summary=(
                "خلصت"
                if status is TaskStatus.COMPLETED
                else None
            ),
            error_message=(
                "خطأ"
                if status is TaskStatus.FAILED
                else None
            ),
        )


def test_task_rejects_assignment_conflicting_with_requirement() -> None:
    with pytest.raises(
        ValidationError,
        match="must match the required agent",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            status=TaskStatus.ASSIGNED,
            required_agent_key="vega",
            assigned_agent_key="nova",
        )


def test_assigned_task_rejects_progress() -> None:
    with pytest.raises(
        ValidationError,
        match="newly assigned task must have zero progress",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            status=TaskStatus.ASSIGNED,
            assigned_agent_key="vega",
            progress_percent=25.0,
        )


def test_completed_task_requires_full_progress_and_summary() -> None:
    with pytest.raises(
        ValidationError,
        match="must have 100 percent progress",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            status=TaskStatus.COMPLETED,
            assigned_agent_key="vega",
            progress_percent=90.0,
            result_summary="خلصت",
        )

    with pytest.raises(
        ValidationError,
        match="requires a result summary",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            status=TaskStatus.COMPLETED,
            assigned_agent_key="vega",
            progress_percent=100.0,
        )


def test_only_completed_task_may_carry_result_summary() -> None:
    with pytest.raises(
        ValidationError,
        match="Only a completed task can contain a result summary",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            status=TaskStatus.RUNNING,
            assigned_agent_key="vega",
            result_summary="خلصت",
        )


def test_only_failed_task_may_carry_error_message() -> None:
    with pytest.raises(
        ValidationError,
        match="requires an error message",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            status=TaskStatus.FAILED,
            assigned_agent_key="vega",
        )

    with pytest.raises(
        ValidationError,
        match="Only a failed task can contain an error message",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            status=TaskStatus.RUNNING,
            assigned_agent_key="vega",
            error_message="خطأ",
        )


def test_task_rejects_full_progress_without_completion() -> None:
    with pytest.raises(
        ValidationError,
        match="Use completed status when task progress reaches",
    ):
        AgentTask(
            task_id="task_one",
            title="مهمة",
            description="وصف",
            status=TaskStatus.RUNNING,
            assigned_agent_key="vega",
            progress_percent=100.0,
        )


def test_task_is_immutable() -> None:
    task = AgentTask(
        task_id="task_one",
        title="مهمة",
        description="وصف",
    )

    with pytest.raises(ValidationError):
        task.title = "مهمة تانية"  # type: ignore[misc]


def test_board_creates_sequential_task_identifiers() -> None:
    board = TaskBoard()

    first = board.create_task(title="أولى")
    second = board.create_task(title="تانية")

    assert first.task_id == "task_000001"
    assert second.task_id == "task_000002"
    assert first.description == "أولى"
    assert board.all_tasks() == (first, second)


def test_board_accepts_explicit_task_identifier() -> None:
    board = TaskBoard()

    task = board.create_task(
        title="مهمة مخصصة",
        description="وصف مفصّل",
        task_id="Audit-Vega",
    )

    assert task.task_id == "audit_vega"
    assert task.description == "وصف مفصّل"
    assert board.get_task("AUDIT VEGA") is task


def test_board_rejects_duplicate_task_identifier() -> None:
    board = TaskBoard()

    board.create_task(title="أولى", task_id="audit")

    with pytest.raises(
        ValueError,
        match="already exists",
    ):
        board.create_task(title="تانية", task_id="audit")


def test_board_rejects_unknown_task() -> None:
    board = TaskBoard()

    with pytest.raises(
        KeyError,
        match="does not exist",
    ):
        board.get_task("missing")


def test_board_completes_the_full_task_lifecycle() -> None:
    board = TaskBoard()

    created = board.create_task(
        title="تدقيق بيانات EURUSD",
        priority=TaskPriority.HIGH,
    )

    assert created.status is TaskStatus.PENDING

    assigned = board.assign_task(created.task_id, "Vega")

    assert assigned.status is TaskStatus.ASSIGNED
    assert assigned.assigned_agent_key == "vega"
    assert assigned.progress_percent == 0.0

    started = board.start_task(
        created.task_id,
        note="بلّشت التدقيق.",
    )

    assert started.status is TaskStatus.RUNNING
    assert started.status_note == "بلّشت التدقيق."

    progressed = board.update_progress(
        created.task_id,
        40.0,
        note="خلّصت أول فحص.",
    )

    assert progressed.progress_percent == 40.0
    assert progressed.status_note == "خلّصت أول فحص."

    waiting = board.wait_task(
        created.task_id,
        note="ناطر بيانات من MT5.",
    )

    assert waiting.status is TaskStatus.WAITING
    assert waiting.progress_percent == 40.0

    resumed = board.update_progress(created.task_id, 80.0)

    assert resumed.status is TaskStatus.RUNNING
    assert resumed.progress_percent == 80.0
    assert resumed.status_note == "ناطر بيانات من MT5."

    completed = board.complete_task(
        created.task_id,
        result_summary="  البيانات نظيفة.  ",
    )

    assert completed.status is TaskStatus.COMPLETED
    assert completed.progress_percent == 100.0
    assert completed.result_summary == "البيانات نظيفة."
    assert completed.is_terminal is True
    assert completed.updated_at >= completed.created_at


def test_board_rejects_assignment_of_non_pending_task() -> None:
    board = TaskBoard()
    task = make_running_task(board)

    with pytest.raises(
        RuntimeError,
        match="Only a pending task can be assigned",
    ):
        board.assign_task(task.task_id, "chronos")


def test_board_enforces_required_agent_on_assignment() -> None:
    board = TaskBoard()

    task = board.create_task(
        title="تدقيق مستقل",
        required_agent_key="sentinel",
    )

    with pytest.raises(
        ValueError,
        match="requires agent 'sentinel'",
    ):
        board.assign_task(task.task_id, "nova")

    assigned = board.assign_task(task.task_id, "sentinel")

    assert assigned.assigned_agent_key == "sentinel"


def test_board_rejects_invalid_agent_key_on_assignment() -> None:
    board = TaskBoard()
    task = board.create_task(title="مهمة")

    with pytest.raises(
        ValueError,
        match="Agent key must start with a letter",
    ):
        board.assign_task(task.task_id, "9nova")


def test_board_reassigns_active_task_and_restarts_it() -> None:
    board = TaskBoard()
    task = make_running_task(board, agent_key="chronos")

    board.update_progress(task.task_id, 55.0, note="نص الشغل.")

    reassigned = board.reassign_task(task.task_id, "Nova")

    assert reassigned.assigned_agent_key == "nova"
    assert reassigned.status is TaskStatus.ASSIGNED
    assert reassigned.progress_percent == 0.0
    assert reassigned.status_note is None

    assert board.tasks_for_agent("chronos") == ()
    assert board.tasks_for_agent("nova") == (reassigned,)


def test_board_rejects_pointless_and_illegal_reassignment() -> None:
    board = TaskBoard()
    task = make_running_task(board, agent_key="chronos")

    with pytest.raises(
        ValueError,
        match="already assigned to agent 'chronos'",
    ):
        board.reassign_task(task.task_id, "chronos")

    board.complete_task(task.task_id, result_summary="خلص")

    with pytest.raises(
        RuntimeError,
        match="Only an active task can be reassigned",
    ):
        board.reassign_task(task.task_id, "nova")


def test_board_rejects_reassignment_against_required_agent() -> None:
    board = TaskBoard()

    task = board.create_task(
        title="تدقيق مستقل",
        required_agent_key="sentinel",
    )

    board.assign_task(task.task_id, "sentinel")

    with pytest.raises(
        ValueError,
        match="requires agent 'sentinel'",
    ):
        board.reassign_task(task.task_id, "nova")


def test_board_releases_task_back_to_backlog() -> None:
    board = TaskBoard()
    task = make_running_task(board, agent_key="chronos")

    board.update_progress(task.task_id, 30.0, note="شغل جزئي.")

    released = board.release_task(task.task_id)

    assert released.status is TaskStatus.PENDING
    assert released.assigned_agent_key is None
    assert released.progress_percent == 0.0
    assert released.status_note is None
    assert board.pending_tasks() == (released,)


def test_board_rejects_release_of_terminal_task() -> None:
    board = TaskBoard()
    task = make_running_task(board)

    board.complete_task(task.task_id, result_summary="خلص")

    with pytest.raises(
        RuntimeError,
        match="Only an active task can be released",
    ):
        board.release_task(task.task_id)


def test_board_rejects_start_of_pending_or_terminal_task() -> None:
    board = TaskBoard()
    pending = board.create_task(title="مهمة")

    with pytest.raises(
        RuntimeError,
        match="Only an assigned or waiting task can be started",
    ):
        board.start_task(pending.task_id)

    running = make_running_task(board)

    with pytest.raises(
        RuntimeError,
        match="Only an assigned or waiting task can be started",
    ):
        board.start_task(running.task_id)


def test_board_rejects_invalid_progress_values() -> None:
    board = TaskBoard()
    task = make_running_task(board)

    with pytest.raises(
        ValueError,
        match="cannot be below zero",
    ):
        board.update_progress(task.task_id, -1.0)

    with pytest.raises(
        ValueError,
        match="Use complete_task when progress reaches",
    ):
        board.update_progress(task.task_id, 100.0)

    board.update_progress(task.task_id, 60.0)

    with pytest.raises(
        ValueError,
        match="cannot move backwards",
    ):
        board.update_progress(task.task_id, 59.9)


def test_board_rejects_progress_on_inactive_task() -> None:
    board = TaskBoard()
    assigned = board.create_task(title="مهمة")

    board.assign_task(assigned.task_id, "vega")

    with pytest.raises(
        RuntimeError,
        match="Only a running or waiting task can receive",
    ):
        board.update_progress(assigned.task_id, 10.0)


def test_board_rejects_wait_on_non_running_task() -> None:
    board = TaskBoard()
    task = board.create_task(title="مهمة")

    board.assign_task(task.task_id, "vega")

    with pytest.raises(
        RuntimeError,
        match="Only a running task can be placed in waiting",
    ):
        board.wait_task(task.task_id)


def test_board_completes_a_waiting_task() -> None:
    board = TaskBoard()
    task = make_running_task(board)

    board.wait_task(task.task_id)

    completed = board.complete_task(
        task.task_id,
        result_summary="وصلت المعلومات وخلّصت.",
    )

    assert completed.status is TaskStatus.COMPLETED


def test_board_rejects_empty_completion_and_failure_text() -> None:
    board = TaskBoard()
    task = make_running_task(board)

    with pytest.raises(
        ValueError,
        match="result cannot be empty",
    ):
        board.complete_task(task.task_id, result_summary="   ")

    with pytest.raises(
        ValueError,
        match="error message cannot be empty",
    ):
        board.fail_task(task.task_id, error_message="   ")


def test_board_rejects_completion_of_non_active_task() -> None:
    board = TaskBoard()
    pending = board.create_task(title="مهمة")

    with pytest.raises(
        RuntimeError,
        match="Only a running or waiting task can be completed",
    ):
        board.complete_task(pending.task_id, result_summary="خلص")


def test_board_fails_an_assigned_task() -> None:
    board = TaskBoard()
    task = board.create_task(title="مهمة")

    board.assign_task(task.task_id, "vega")

    failed = board.fail_task(
        task.task_id,
        error_message="  مصدر البيانات مقطوع.  ",
    )

    assert failed.status is TaskStatus.FAILED
    assert failed.error_message == "مصدر البيانات مقطوع."
    assert failed.progress_percent == 0.0


def test_board_preserves_progress_when_task_fails() -> None:
    board = TaskBoard()
    task = make_running_task(board)

    board.update_progress(task.task_id, 35.0)

    failed = board.fail_task(
        task.task_id,
        error_message="انقطع الاتصال بـMT5.",
    )

    assert failed.progress_percent == 35.0


def test_board_rejects_failure_of_terminal_task() -> None:
    board = TaskBoard()
    task = make_running_task(board)

    board.complete_task(task.task_id, result_summary="خلص")

    with pytest.raises(
        RuntimeError,
        match="cannot be marked as failed",
    ):
        board.fail_task(task.task_id, error_message="خطأ")


def test_board_cancels_pending_and_active_tasks() -> None:
    board = TaskBoard()

    pending = board.create_task(title="مهمة بالانتظار")
    running = make_running_task(board)

    board.update_progress(running.task_id, 20.0)

    cancelled_pending = board.cancel_task(pending.task_id)
    cancelled_running = board.cancel_task(running.task_id)

    assert cancelled_pending.status is TaskStatus.CANCELLED
    assert cancelled_running.status is TaskStatus.CANCELLED
    assert cancelled_running.progress_percent == 20.0


@pytest.mark.parametrize(
    "status",
    sorted(TERMINAL_TASK_STATUSES),
)
def test_board_rejects_cancelling_terminal_task(
    status: TaskStatus,
) -> None:
    board = TaskBoard()
    task = make_running_task(board)

    if status is TaskStatus.COMPLETED:
        board.complete_task(task.task_id, result_summary="خلص")
    elif status is TaskStatus.FAILED:
        board.fail_task(task.task_id, error_message="خطأ")
    else:
        board.cancel_task(task.task_id)

    with pytest.raises(
        RuntimeError,
        match="terminal task cannot be cancelled",
    ):
        board.cancel_task(task.task_id)


def test_board_links_parent_and_child_tasks() -> None:
    board = TaskBoard()

    parent = board.create_task(title="خطة بحث EURUSD")

    first_child = board.create_task(
        title="جمع البيانات",
        parent_task_id=parent.task_id,
    )

    second_child = board.create_task(
        title="تشغيل الباكتيست",
        parent_task_id=parent.task_id,
    )

    grandchild = board.create_task(
        title="تدقيق نتائج الباكتيست",
        parent_task_id=second_child.task_id,
    )

    assert board.child_tasks(parent.task_id) == (
        first_child,
        second_child,
    )

    assert board.descendant_tasks(parent.task_id) == (
        first_child,
        second_child,
        grandchild,
    )

    assert board.child_tasks(first_child.task_id) == ()


def test_board_rejects_unknown_parent_task() -> None:
    board = TaskBoard()

    with pytest.raises(
        KeyError,
        match="does not exist",
    ):
        board.create_task(
            title="مهمة فرعية",
            parent_task_id="missing_parent",
        )


def test_board_blocks_parent_completion_while_subtask_runs() -> None:
    board = TaskBoard()

    parent = board.create_task(title="خطة بحث")
    board.assign_task(parent.task_id, "atlas")
    board.start_task(parent.task_id)

    child = board.create_task(
        title="جمع البيانات",
        parent_task_id=parent.task_id,
    )

    board.assign_task(child.task_id, "vega")
    board.start_task(child.task_id)

    with pytest.raises(
        RuntimeError,
        match=f"subtask '{child.task_id}' is not finished",
    ):
        board.complete_task(parent.task_id, result_summary="خلصت الخطة")

    board.complete_task(child.task_id, result_summary="البيانات جاهزة")

    completed_parent = board.complete_task(
        parent.task_id,
        result_summary="خلصت الخطة",
    )

    assert completed_parent.status is TaskStatus.COMPLETED


def test_board_cancels_subtasks_together_with_parent() -> None:
    board = TaskBoard()

    parent = board.create_task(title="خطة بحث")
    board.assign_task(parent.task_id, "atlas")
    board.start_task(parent.task_id)

    child = board.create_task(
        title="جمع البيانات",
        parent_task_id=parent.task_id,
    )

    board.assign_task(child.task_id, "vega")
    board.start_task(child.task_id)

    grandchild = board.create_task(
        title="تدقيق البيانات",
        parent_task_id=child.task_id,
    )

    finished_child = board.create_task(
        title="مهمة خلصانة",
        parent_task_id=parent.task_id,
    )

    board.assign_task(finished_child.task_id, "iris")
    board.start_task(finished_child.task_id)
    board.complete_task(finished_child.task_id, result_summary="خلصت")

    board.cancel_task(parent.task_id)

    assert board.get_task(parent.task_id).status is TaskStatus.CANCELLED
    assert board.get_task(child.task_id).status is TaskStatus.CANCELLED
    assert board.get_task(grandchild.task_id).status is TaskStatus.CANCELLED
    assert board.get_task(finished_child.task_id).status is TaskStatus.COMPLETED


def test_board_can_cancel_one_task_without_cascade() -> None:
    board = TaskBoard()

    parent = board.create_task(title="خطة بحث")
    child = board.create_task(
        title="جمع البيانات",
        parent_task_id=parent.task_id,
    )

    board.cancel_task(parent.task_id, cascade=False)

    assert board.get_task(parent.task_id).status is TaskStatus.CANCELLED
    assert board.get_task(child.task_id).status is TaskStatus.PENDING


def test_board_orders_active_tasks_by_attention_rules() -> None:
    board = TaskBoard()

    low = board.create_task(title="مهمة منخفضة", priority=TaskPriority.LOW)
    critical = board.create_task(
        title="مهمة حرجة",
        priority=TaskPriority.CRITICAL,
    )
    normal = board.create_task(title="مهمة عادية")

    for task in (low, critical, normal):
        board.assign_task(task.task_id, "vega")

    board.start_task(normal.task_id)

    ordered = board.active_tasks("vega")

    assert [task.task_id for task in ordered] == [
        normal.task_id,
        critical.task_id,
        low.task_id,
    ]

    primary = board.primary_active_task("vega")

    assert primary is not None
    assert primary.task_id == normal.task_id


def test_board_filters_tasks_by_agent_and_status() -> None:
    board = TaskBoard()

    vega_task = board.create_task(title="بيانات")
    nova_task = board.create_task(title="استراتيجية")
    backlog = board.create_task(title="بحث لاحق")

    board.assign_task(vega_task.task_id, "vega")
    board.assign_task(nova_task.task_id, "nova")

    assert [task.task_id for task in board.tasks_for_agent("vega")] == [
        vega_task.task_id,
    ]

    assert [task.task_id for task in board.pending_tasks()] == [
        backlog.task_id,
    ]

    assert [
        task.task_id
        for task in board.tasks_by_status(TaskStatus.ASSIGNED)
    ] == [
        vega_task.task_id,
        nova_task.task_id,
    ]

    assert board.active_tasks("iris") == ()
    assert board.primary_active_task("iris") is None


def test_board_notifies_listeners_on_every_change() -> None:
    listener = RecordingListener()
    board = TaskBoard([listener])

    task = board.create_task(title="مهمة")
    board.assign_task(task.task_id, "vega")
    board.start_task(task.task_id)
    board.complete_task(task.task_id, result_summary="خلصت")

    assert listener.events == [
        (None, "pending"),
        ("pending", "assigned"),
        ("assigned", "running"),
        ("running", "completed"),
    ]


def test_board_supports_listeners_added_later() -> None:
    board = TaskBoard()
    listener = RecordingListener()

    board.create_task(title="قبل المراقب")
    board.add_listener(listener)
    board.create_task(title="بعد المراقب")

    assert listener.events == [(None, "pending")]


def test_board_creates_unique_identifiers_under_concurrency() -> None:
    board = TaskBoard()
    thread_count = 16
    per_thread = 25
    barrier = Barrier(thread_count)

    def worker() -> None:
        barrier.wait()

        for _ in range(per_thread):
            board.create_task(title="مهمة متزامنة")

    threads = [
        Thread(target=worker)
        for _ in range(thread_count)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    tasks = board.all_tasks()

    assert len(tasks) == thread_count * per_thread
    assert len({task.task_id for task in tasks}) == len(tasks)


def test_board_serializes_concurrent_lifecycle_transitions() -> None:
    board = TaskBoard()
    thread_count = 12
    barrier = Barrier(thread_count)

    tasks = [
        board.create_task(title=f"مهمة {index}")
        for index in range(thread_count)
    ]

    def worker(task_id: str) -> None:
        barrier.wait()

        board.assign_task(task_id, "chronos")
        board.start_task(task_id)
        board.update_progress(task_id, 50.0)
        board.complete_task(task_id, result_summary="خلصت")

    threads = [
        Thread(target=worker, args=(task.task_id,))
        for task in tasks
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    completed = board.tasks_by_status(TaskStatus.COMPLETED)

    assert len(completed) == thread_count
    assert all(task.progress_percent == 100.0 for task in completed)


def test_board_allows_only_one_winner_for_a_contested_task() -> None:
    board = TaskBoard()
    task = board.create_task(title="مهمة واحدة")

    thread_count = 20
    barrier = Barrier(thread_count)
    winners: list[str] = []
    losers: list[str] = []

    def worker(index: int) -> None:
        barrier.wait()

        try:
            board.assign_task(task.task_id, f"agent_{index}")
        except RuntimeError:
            losers.append(f"agent_{index}")
        else:
            winners.append(f"agent_{index}")

    threads = [
        Thread(target=worker, args=(index,))
        for index in range(thread_count)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert len(winners) == 1
    assert len(losers) == thread_count - 1
    assert board.get_task(task.task_id).assigned_agent_key == winners[0]
