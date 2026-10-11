from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_quant_lab.agents.base import (
    AgentIdentity,
    AgentSnapshot,
    AgentState,
    BaseAgent,
)


def make_atlas() -> BaseAgent:
    """Create a controlled Atlas agent for automated tests."""

    identity = AgentIdentity(
        key="atlas",
        name="Atlas",
        role="مدير فريق الوكلاء",
        wake_names=(
            "أطلس",
            "يا أطلس",
            "Hey Atlas",
        ),
    )

    return BaseAgent(identity)


def test_agent_identity_normalizes_key_and_text() -> None:
    identity = AgentIdentity(
        key=" Atlas-Prime ",
        name=" Atlas ",
        role=" المدير الرئيسي ",
        wake_names=(
            " أطلس ",
            "ATLAS",
            "atlas",
            "يا أطلس",
        ),
    )

    assert identity.key == "atlas_prime"
    assert identity.name == "Atlas"
    assert identity.role == "المدير الرئيسي"

    assert identity.wake_names == (
        "أطلس",
        "ATLAS",
        "يا أطلس",
    )


def test_agent_identity_rejects_invalid_key() -> None:
    with pytest.raises(
        ValidationError,
        match="Agent key must start with a letter",
    ):
        AgentIdentity(
            key="123-atlas",
            name="Atlas",
            role="Manager",
        )


def test_agent_identity_rejects_empty_wake_name() -> None:
    with pytest.raises(
        ValidationError,
        match="wake names cannot be empty",
    ):
        AgentIdentity(
            key="atlas",
            name="Atlas",
            role="Manager",
            wake_names=(
                "Atlas",
                "   ",
            ),
        )


def test_new_agent_starts_idle() -> None:
    agent = make_atlas()
    snapshot = agent.snapshot()

    assert snapshot.identity.name == "Atlas"
    assert snapshot.state is AgentState.IDLE
    assert snapshot.current_task is None
    assert snapshot.progress_percent == 0.0
    assert snapshot.updated_at.tzinfo == UTC

    assert agent.status_reply() == (
        "Atlas: أنا حاضر. ما عندي مهمة شغّالة هلق."
    )


@pytest.mark.parametrize(
    "spoken_name",
    [
        "Atlas",
        "atlas",
        "ATLAS",
        "أطلس",
        "يا أطلس",
        "Hey Atlas",
        " atlas ",
    ],
)
def test_agent_recognizes_all_configured_names(
    spoken_name: str,
) -> None:
    agent = make_atlas()

    assert agent.is_addressed_by(spoken_name) is True
    assert agent.reply_when_called(spoken_name) is not None


def test_agent_ignores_another_name() -> None:
    agent = make_atlas()

    assert agent.is_addressed_by("Nova") is False
    assert agent.reply_when_called("Nova") is None
    assert agent.reply_when_called("   ") is None


def test_agent_starts_and_updates_task() -> None:
    agent = make_atlas()

    started = agent.start_task(
        "  توزيع مهام الفريق  ",
        message="عم وزّع المهام على الوكلاء.",
    )

    assert started.state is AgentState.WORKING
    assert started.current_task == "توزيع مهام الفريق"
    assert started.progress_percent == 0.0

    updated = agent.update_progress(
        42.5,
        message="خلصت توزيع أول مجموعة.",
    )

    assert updated.state is AgentState.WORKING
    assert updated.progress_percent == 42.5
    assert updated.current_task == "توزيع مهام الفريق"

    assert agent.status_reply() == (
        "Atlas: أنا عم اشتغل على توزيع مهام الفريق. "
        "التقدّم 42%. خلصت توزيع أول مجموعة."
    )


def test_agent_can_wait_and_resume_progress() -> None:
    agent = make_atlas()

    agent.start_task(
        "مراجعة نتائج Chronos",
    )

    agent.update_progress(
        60,
        message="راجعت معظم النتائج.",
    )

    waiting = agent.wait(
        message="ناطر تقرير Sentinel.",
    )

    assert waiting.state is AgentState.WAITING
    assert waiting.current_task == "مراجعة نتائج Chronos"
    assert waiting.progress_percent == 60

    assert agent.status_reply() == (
        "Atlas: أنا ناطر بخصوص مراجعة نتائج Chronos. "
        "ناطر تقرير Sentinel."
    )

    resumed = agent.update_progress(
        75,
        message="وصل التقرير ورجعت كمّلت.",
    )

    assert resumed.state is AgentState.WORKING
    assert resumed.progress_percent == 75


def test_agent_completes_task() -> None:
    agent = make_atlas()

    agent.start_task(
        "تحضير خطة التجارب",
    )

    completed = agent.complete_task(
        message="الخطة صارت جاهزة.",
    )

    assert completed.state is AgentState.COMPLETED
    assert completed.progress_percent == 100.0

    assert agent.status_reply() == (
        "Atlas: خلّصت تحضير خطة التجارب. "
        "الخطة صارت جاهزة."
    )


def test_agent_reports_task_failure() -> None:
    agent = make_atlas()

    agent.start_task(
        "تشغيل فريق البحث",
    )

    agent.update_progress(
        30,
    )

    failed = agent.fail_task(
        message="تعذّر تشغيل أحد الوكلاء.",
    )

    assert failed.state is AgentState.ERROR
    assert failed.progress_percent == 30

    assert agent.status_reply() == (
        "Atlas: صار معي خطأ خلال تشغيل فريق البحث. "
        "تعذّر تشغيل أحد الوكلاء."
    )


def test_agent_can_stop_and_reset() -> None:
    agent = make_atlas()

    agent.start_task(
        "فحص حالة النظام",
    )

    agent.update_progress(
        25,
    )

    stopped = agent.stop(
        message="تم الإيقاف بطلب المستخدم.",
    )

    assert stopped.state is AgentState.STOPPED
    assert stopped.current_task == "فحص حالة النظام"
    assert stopped.progress_percent == 25

    assert agent.status_reply() == (
        "Atlas: أنا موقوف حاليًا. "
        "تم الإيقاف بطلب المستخدم."
    )

    reset = agent.reset()

    assert reset.state is AgentState.IDLE
    assert reset.current_task is None
    assert reset.progress_percent == 0.0


def test_agent_rejects_empty_task() -> None:
    agent = make_atlas()

    with pytest.raises(
        ValueError,
        match="task cannot be empty",
    ):
        agent.start_task("   ")


def test_agent_rejects_progress_without_active_task() -> None:
    agent = make_atlas()

    with pytest.raises(
        RuntimeError,
        match="no active task",
    ):
        agent.update_progress(25)


def test_agent_rejects_completion_without_active_task() -> None:
    agent = make_atlas()

    with pytest.raises(
        RuntimeError,
        match="no active task",
    ):
        agent.complete_task()


def test_snapshot_rejects_naive_timestamp() -> None:
    identity = AgentIdentity(
        key="atlas",
        name="Atlas",
        role="Manager",
    )

    with pytest.raises(
        ValidationError,
        match="timezone information",
    ):
        AgentSnapshot(
            identity=identity,
            state=AgentState.IDLE,
            message="Ready",
            # Intentionally naive to verify timestamp validation.
            updated_at=datetime(2026, 8, 1, 12),  # noqa: DTZ001
        )