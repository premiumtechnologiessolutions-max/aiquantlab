from __future__ import annotations

import pytest

from ai_quant_lab.agents.base import (
    AgentIdentity,
    AgentState,
    BaseAgent,
)
from ai_quant_lab.agents.team import (
    AgentTeam,
    create_default_agent_team,
)


def test_default_team_contains_all_named_agents() -> None:
    team = create_default_agent_team()
    agents = team.all_agents()

    assert len(agents) == 10

    assert tuple(
        agent.identity.key
        for agent in agents
    ) == (
        "atlas",
        "vega",
        "nova",
        "chronos",
        "iris",
        "sentinel",
        "aegis",
        "oracle",
        "echo",
        "forge",
    )

    assert all(
        agent.snapshot().state is AgentState.IDLE
        for agent in agents
    )


@pytest.mark.parametrize(
    (
        "spoken_text",
        "expected_key",
    ),
    [
        (
            "Atlas",
            "atlas",
        ),
        (
            "يا أطلس شو عم تعمل؟",
            "atlas",
        ),
        (
            "يا اطلس خبرني عن الفريق",
            "atlas",
        ),
        (
            "Hey Vega, check the data",
            "vega",
        ),
        (
            "يا نوفا شو الاستراتيجيات الجديدة؟",
            "nova",
        ),
        (
            "كرونوس خبرني عن الباكتيست",
            "chronos",
        ),
        (
            "يا آيرس شو حالة السوق؟",
            "iris",
        ),
        (
            "Sentinel check the results",
            "sentinel",
        ),
        (
            "يا إيجس خبرني عن المخاطر",
            "aegis",
        ),
        (
            "يا أوراكل شو الأخبار؟",
            "oracle",
        ),
        (
            "يا إيكو اعطيني التقرير",
            "echo",
        ),
        (
            "Hey Forge, status",
            "forge",
        ),
    ],
)
def test_team_resolves_agent_inside_sentence(
    spoken_text: str,
    expected_key: str,
) -> None:
    team = create_default_agent_team()

    agent = team.resolve_agent(
        spoken_text,
    )

    assert agent is not None
    assert agent.identity.key == expected_key


def test_team_calls_agent_and_returns_status() -> None:
    team = create_default_agent_team()

    reply = team.call(
        "يا Atlas شو عم تعمل؟",
    )

    assert reply == (
        "Atlas: أنا حاضر. "
        "ما عندي مهمة شغّالة هلق."
    )


def test_team_reports_live_agent_task_status() -> None:
    team = create_default_agent_team()
    chronos = team.get_agent("chronos")

    chronos.start_task(
        "تشغيل باكتيست EURUSD M15",
        message="عم حضّر بيانات التجربة.",
    )

    chronos.update_progress(
        35,
        message="أنجزت أول مجموعة تجارب.",
    )

    reply = team.call(
        "يا كرونوس شو عم تعمل؟",
    )

    assert reply == (
        "Chronos: أنا عم اشتغل على "
        "تشغيل باكتيست EURUSD M15. "
        "التقدّم 35%. "
        "أنجزت أول مجموعة تجارب."
    )


def test_team_returns_none_for_unknown_name() -> None:
    team = create_default_agent_team()

    assert team.resolve_agent(
        "يا شخص مجهول شو عم تعمل؟",
    ) is None

    assert team.call(
        "يا شخص مجهول شو عم تعمل؟",
    ) is None

    assert team.call("   ") is None


def test_team_gets_agent_using_normalized_key() -> None:
    identity = AgentIdentity(
        key="Risk-Agent",
        name="Guardian",
        role="Risk control",
    )

    agent = BaseAgent(identity)
    team = AgentTeam([agent])

    assert team.get_agent(
        "RISK-AGENT",
    ) is agent

    assert team.get_agent(
        " risk agent ",
    ) is agent


def test_team_rejects_unknown_agent_key() -> None:
    team = create_default_agent_team()

    with pytest.raises(
        KeyError,
        match="is not registered",
    ):
        team.get_agent(
            "unknown",
        )


def test_team_rejects_duplicate_agent_key() -> None:
    first_agent = BaseAgent(
        AgentIdentity(
            key="atlas",
            name="Atlas",
            role="Main manager",
        )
    )

    second_agent = BaseAgent(
        AgentIdentity(
            key="atlas",
            name="Atlas Two",
            role="Second manager",
        )
    )

    team = AgentTeam([first_agent])

    with pytest.raises(
        ValueError,
        match="already registered",
    ):
        team.register(
            second_agent,
        )


def test_team_rejects_duplicate_call_name() -> None:
    first_agent = BaseAgent(
        AgentIdentity(
            key="first",
            name="First",
            role="First role",
            wake_names=(
                "Shared Name",
            ),
        )
    )

    second_agent = BaseAgent(
        AgentIdentity(
            key="second",
            name="Second",
            role="Second role",
            wake_names=(
                "shared name",
            ),
        )
    )

    team = AgentTeam([first_agent])

    with pytest.raises(
        ValueError,
        match="already used",
    ):
        team.register(
            second_agent,
        )


def test_team_preserves_registration_order() -> None:
    first_agent = BaseAgent(
        AgentIdentity(
            key="first",
            name="First",
            role="First role",
        )
    )

    second_agent = BaseAgent(
        AgentIdentity(
            key="second",
            name="Second",
            role="Second role",
        )
    )

    team = AgentTeam()

    team.register(first_agent)
    team.register(second_agent)

    assert team.all_agents() == (
        first_agent,
        second_agent,
    )


def test_team_returns_all_current_snapshots() -> None:
    team = create_default_agent_team()
    atlas = team.get_agent("atlas")

    atlas.start_task(
        "توزيع مهام الفريق",
        message="عم حضّر خطة العمل.",
    )

    snapshots = team.all_snapshots()

    assert len(snapshots) == 10

    atlas_snapshot = next(
        snapshot
        for snapshot in snapshots
        if snapshot.identity.key == "atlas"
    )

    assert atlas_snapshot.state is AgentState.WORKING
    assert atlas_snapshot.current_task == "توزيع مهام الفريق"

    idle_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.identity.key != "atlas"
    ]

    assert all(
        snapshot.state is AgentState.IDLE
        for snapshot in idle_snapshots
    )


def test_team_status_summary_contains_every_agent() -> None:
    team = create_default_agent_team()

    summary = team.status_summary()
    lines = summary.splitlines()

    assert len(lines) == 10
    assert lines[0].startswith("Atlas:")
    assert any(
        line.startswith("Chronos:")
        for line in lines
    )
    assert any(
        line.startswith("Echo:")
        for line in lines
    )
    assert lines[-1].startswith("Forge:")


def test_empty_team_has_readable_status() -> None:
    team = AgentTeam()

    assert team.all_agents() == ()
    assert team.all_snapshots() == ()

    assert team.status_summary() == (
        "ما في أي Agent مسجّل حاليًا."
    )