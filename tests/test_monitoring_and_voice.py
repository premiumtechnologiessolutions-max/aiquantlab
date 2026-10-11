from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ai_quant_lab.broker import MT5DemoGateway
from ai_quant_lab.monitoring import DemoMarketMonitor, MonitorConfig, MonitorStore
from ai_quant_lab.runtime import LabRuntime, LabRuntimeConfig
from ai_quant_lab.simulation import SimulationLedger
from ai_quant_lab.web.controller import DashboardController
from ai_quant_lab.web.server import RunningVoiceDashboard, VoiceDashboardServer
from tests.test_mt5_demo_gateway import FakeTradingApi, demo_config


def make_controller(tmp_path: Path, *, connected: bool = False) -> DashboardController:
    now = datetime.now(UTC).replace(microsecond=0)
    gateway = MT5DemoGateway(demo_config(tmp_path), api=FakeTradingApi(now=now))

    if connected:
        gateway.connect()

    monitor = DemoMarketMonitor(
        gateway,
        MonitorConfig(
            pairs=("EURUSD",),
            timeframe="M15",
            strategy_names=(
                "ema_crossover",
                "macd_momentum",
                "donchian_breakout",
            ),
            lookback_bars=80,
            regime_window=20,
            minimum_agreement=1,
        ),
        simulation_ledger=SimulationLedger(tmp_path / "simulation.sqlite3"),
        store=MonitorStore(tmp_path / "monitor.sqlite3"),
    )
    runtime = LabRuntime(
        LabRuntimeConfig(
            operational_database=tmp_path / "operational.sqlite3",
            market_data_root=tmp_path / "processed",
            report_root=tmp_path / "reports",
        )
    )

    return DashboardController(
        runtime,
        gateway,
        monitor,
        campaign_root=tmp_path / "campaigns",
    )


def test_monitor_persists_ensemble_scan_and_agents_explain_it(tmp_path: Path) -> None:
    controller = make_controller(tmp_path, connected=True)
    payload = controller.scan_market()
    scan = controller.monitor.store.latest("EURUSD")

    assert len(payload["scans"]) == 1
    assert scan is not None
    assert len(scan.strategy_signals) == 3
    assert scan.simulation.mode.value == "shadow"

    response = controller.chat("يا Iris شو حالة السوق؟")

    assert response["matched_agent_key"] == "iris"
    assert "EURUSD" in str(response["reply"])
    assert scan.regime.value in str(response["reply"])


def test_voice_conversation_keeps_active_agent_for_short_follow_ups(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)

    greeting = controller.chat("مرحبا Atlas")
    reason = controller.chat("ليش؟")
    next_step = controller.chat("وبعدين؟")
    switched = controller.chat("يا Iris شو حالة السوق؟")
    repeated = controller.chat("عيدها")

    assert greeting["matched_agent_key"] == "atlas"
    assert reason["matched_agent_key"] == "atlas"
    assert "لوحة المهام" in str(reason["reply"])
    assert next_step["matched_agent_key"] == "atlas"
    assert switched["matched_agent_key"] == "iris"
    assert repeated["matched_agent_key"] == "iris"
    assert repeated["reply"] == switched["reply"]



def test_health_snapshot_marks_disconnected_mt5_as_degraded(tmp_path: Path) -> None:
    controller = make_controller(tmp_path, connected=False)

    health = controller.health_snapshot()

    assert health["status"] == "degraded"
    assert health["mt5_connected"] is False
    assert health["live_trading_authorized"] is False


def test_voice_dashboard_is_local_token_protected_and_serves_chat(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    server = VoiceDashboardServer(("127.0.0.1", 0), controller)

    with RunningVoiceDashboard(server):
        host, port = server.server_address
        root = f"http://{host}:{port}"

        with urlopen(f"{root}/api/health", timeout=5) as response:
            health = json.loads(response.read().decode())

        assert health["localhost_only"] is True

        with urlopen(root, timeout=5) as response:
            html = response.read().decode()

        assert "غرفة التحكم الصوتية" in html
        assert "استماع مستمر" in html
        assert "QUANT COMMAND CENTER" in html
        assert "AGENT DETAIL" in html
        assert server.session_token in html

        with urlopen(f"{root}/static/app.js", timeout=5) as response:
            javascript = response.read().decode()

        assert "recognition.continuous = true" in javascript
        assert "AGENT_VOICE_PROFILES" in javascript
        assert "showAgentDetail" in javascript

        unauthorized = Request(
            f"{root}/api/chat",
            data=json.dumps({"text": "حالة الفريق"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            urlopen(unauthorized, timeout=5)
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("Dashboard accepted a POST without its session token.")

        authorized = Request(
            f"{root}/api/chat",
            data=json.dumps({"text": "يا Atlas شو وضع الفريق؟"}).encode(),
            headers={
                "Content-Type": "application/json",
                "X-AIQL-Session": server.session_token,
            },
            method="POST",
        )

        with urlopen(authorized, timeout=5) as response:
            reply = json.loads(response.read().decode())

        assert reply["matched_agent_key"] == "atlas"
        assert reply["reply"]
