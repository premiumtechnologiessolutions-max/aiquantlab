from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ai_quant_lab.agents import (
    ActivityJournal,
    AgentMessageBus,
    TaskBoard,
    TaskStatus,
)
from ai_quant_lab.agents.conversation import AgentConversationService
from ai_quant_lab.modeling import (
    DisabledModelProvider,
    ModelConfiguration,
    ModelProviderUnavailable,
    ModelRequest,
    default_agent_model_profiles,
)
from ai_quant_lab.runtime import (
    LabRuntime,
    LabRuntimeConfig,
    RuntimeScheduler,
    ScheduledJob,
    SQLiteOperationalStore,
)


def test_message_bus_supports_inbox_outbox_and_read_permissions() -> None:
    journal = ActivityJournal()
    bus = AgentMessageBus(listeners=(journal,))
    message = bus.send(
        sender_key="atlas",
        recipient_key="vega",
        subject="Data audit",
        body="Check EURUSD M15 provenance.",
        task_id="task_000001",
    )

    assert bus.inbox("vega") == (message,)
    assert bus.outbox("atlas") == (message,)
    assert bus.inbox("vega", unread_only=True) == (message,)

    with pytest.raises(PermissionError):
        bus.mark_read(message.message_id, reader_key="nova")

    read = bus.mark_read(message.message_id, reader_key="vega")

    assert read.read_at is not None
    assert bus.inbox("vega", unread_only=True) == ()
    assert len(journal.all_events()) == 2


def test_sqlite_store_restores_tasks_messages_events_and_heartbeat(
    tmp_path: Path,
) -> None:
    store = SQLiteOperationalStore(tmp_path / "operational.sqlite3")
    journal = ActivityJournal(persist=store.append_event)
    board = TaskBoard(listeners=(store, journal))
    bus = AgentMessageBus(listeners=(store, journal))
    created = board.create_task(
        title="Persistent research task",
        required_agent_key="nova",
    )
    assigned = board.assign_task(created.task_id, "nova")
    message = bus.send(
        sender_key="atlas",
        recipient_key="nova",
        subject="Assignment",
        body="Start the persisted task.",
        task_id=assigned.task_id,
    )
    heartbeat = store.save_heartbeat("lab_runtime")

    assert store.load_tasks() == (assigned,)
    assert store.load_messages() == (message,)
    assert len(store.load_events()) == 3
    assert store.load_heartbeats() == (heartbeat,)


def test_task_board_restore_preserves_ids_and_parent_relationships() -> None:
    original = TaskBoard()
    parent = original.create_task(title="Parent")
    child = original.create_task(title="Child", parent_task_id=parent.task_id)
    restored = TaskBoard()
    restored.restore_tasks((parent, child))

    next_task = restored.create_task(title="Next")

    assert restored.child_tasks(parent.task_id) == (child,)
    assert next_task.task_id == "task_000003"


def test_scheduler_isolates_failures_and_reschedules() -> None:
    calls: list[str] = []
    now = datetime(2026, 8, 1, tzinfo=UTC)
    scheduler = RuntimeScheduler()
    scheduler.register(
        ScheduledJob(
            job_key="healthy_job",
            interval_seconds=60,
            callback=lambda: calls.append("healthy"),
            first_run_at=now,
        )
    )

    def fail() -> None:
        raise RuntimeError("controlled failure")

    scheduler.register(
        ScheduledJob(
            job_key="failing_job",
            interval_seconds=60,
            callback=fail,
            first_run_at=now,
        )
    )

    snapshots = scheduler.run_due(now)

    assert calls == ["healthy"]
    assert snapshots[0].last_error is None
    assert snapshots[1].last_error == "RuntimeError: controlled failure"
    assert scheduler.run_due(now + timedelta(seconds=30)) == ()


def test_lab_runtime_plans_idempotent_work_and_recovers_after_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "lab.sqlite3"
    config = LabRuntimeConfig(
        operational_database=database,
        daily_planning_interval_seconds=60,
    )
    runtime = LabRuntime(config)
    runtime.start()

    assert len(runtime.task_board.all_tasks()) == 5
    assert runtime.ensure_daily_work() == ()
    assert all(task.status is TaskStatus.ASSIGNED for task in runtime.task_board.all_tasks())
    runtime.stop()

    recovered = LabRuntime(config)
    recovered.start()

    assert len(recovered.task_board.all_tasks()) == 5
    assert recovered.ensure_daily_work() == ()
    assert len(recovered.journal.all_events()) > 0


def test_conversation_reads_real_runtime_state_and_persists_messages(
    tmp_path: Path,
) -> None:
    runtime = LabRuntime(
        LabRuntimeConfig(operational_database=tmp_path / "conversation.sqlite3")
    )
    runtime.start()
    conversation = AgentConversationService(runtime)

    result = conversation.ask("يا Vega شو مهامك؟")

    assert result.success is True
    assert result.matched_agent_key == "vega"
    assert "تدقيق تحديث وجودة بيانات السوق اليومية" in result.reply
    assert len(runtime.message_bus.inbox("vega")) == 1
    assert len(runtime.message_bus.outbox("vega")) == 1

    recovered_store = SQLiteOperationalStore(runtime.config.operational_database)

    assert len(recovered_store.load_messages()) == 2


def test_runtime_tick_executes_real_handlers_and_writes_daily_report(
    tmp_path: Path,
) -> None:
    runtime = LabRuntime(
        LabRuntimeConfig(
            operational_database=tmp_path / "tick.sqlite3",
            market_data_root=tmp_path / "processed",
            report_root=tmp_path / "reports",
        )
    )

    snapshots = runtime.run_once(datetime.now(UTC))

    assert len(snapshots) == 2
    assert all(snapshot.last_error is None for snapshot in snapshots)
    assert all(
        task.status is TaskStatus.COMPLETED
        for task in runtime.task_board.all_tasks()
    )
    assert (tmp_path / "reports" / f"{datetime.now(UTC).date().isoformat()}.md").exists()


def test_model_boundary_is_configurable_and_disabled_by_default() -> None:
    profiles = default_agent_model_profiles()

    assert len(profiles) == 10
    assert all(profile.permissions.may_trade_live is False for profile in profiles)
    assert next(
        profile
        for profile in profiles
        if profile.agent_key == "sentinel"
    ).permissions.may_access_blind_validation is True

    provider = DisabledModelProvider()
    request = ModelRequest(
        request_id="request_000001",
        agent_key="atlas",
        system_prompt="Use recorded facts only.",
        user_prompt="What is the team doing?",
        maximum_output_tokens=100,
    )

    with pytest.raises(ModelProviderUnavailable, match="No AI model provider"):
        provider.complete(
            request,
            ModelConfiguration(
                provider_key="disabled",
                model_name="none",
            ),
        )
