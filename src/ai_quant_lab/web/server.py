from __future__ import annotations

import json
import secrets
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from types import TracebackType
from typing import Self, cast
from urllib.parse import parse_qs, urlparse

from pydantic import ValidationError

from ai_quant_lab.broker import DemoTradingBlockedError, MT5DemoGateway
from ai_quant_lab.model_config import load_model_runtime
from ai_quant_lab.monitoring import DemoMarketMonitor, MonitorConfig
from ai_quant_lab.operational_alerts import OperationalAlertDispatcher
from ai_quant_lab.runtime import LabRuntime, LabRuntimeConfig
from ai_quant_lab.web.controller import DashboardController

MAXIMUM_REQUEST_BYTES = 32_768
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


class DashboardBackgroundWorker:
    """Bounded background scheduler and optional recurring demo-market monitor."""

    def __init__(
        self,
        controller: DashboardController,
        *,
        auto_monitor: bool,
        monitor_interval_seconds: float,
    ) -> None:
        if monitor_interval_seconds < 5 or monitor_interval_seconds > 3_600:
            raise ValueError("Monitor interval must be between 5 and 3600 seconds.")

        self.controller = controller
        self.auto_monitor = auto_monitor
        self.monitor_interval_seconds = monitor_interval_seconds
        self._stop = threading.Event()
        self._alerts = OperationalAlertDispatcher(controller.runtime)
        self._thread = threading.Thread(
            target=self._run,
            name="ai-quant-lab-dashboard-worker",
            daemon=True,
        )

    def start(self) -> None:
        """Start one worker thread after the runtime is ready."""

        self.controller.runtime.start()
        self._thread.start()

    def stop(self) -> None:
        """Stop monitoring, disconnect MT5, and preserve runtime state."""

        self._stop.set()
        self._thread.join(timeout=10)
        self.controller.gateway.disconnect()
        self.controller.runtime.stop()

    def _run(self) -> None:
        next_monitor_at = time.monotonic()

        while not self._stop.is_set():
            try:
                self.controller.runtime_tick()
                self._alerts.healthy("research_scheduler")
            except Exception as error:  # noqa: BLE001 - the worker must stay alive
                self.controller.last_monitor_error = f"Runtime tick failed: {error}"
                self._alerts.failure("research_scheduler", str(error))

            if self.auto_monitor and time.monotonic() >= next_monitor_at:
                try:
                    self.controller.scan_market()
                    self._alerts.healthy("mt5_monitor")
                except Exception as error:  # noqa: BLE001 - next scan must still run
                    self.controller.last_monitor_error = str(error)
                    self._alerts.failure("mt5_monitor", str(error))

                next_monitor_at = time.monotonic() + self.monitor_interval_seconds

            self._alerts.healthy("dashboard_worker")
            self._stop.wait(2.0)


class VoiceDashboardServer(ThreadingHTTPServer):
    """Typed localhost-only HTTP server carrying one dashboard controller."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        controller: DashboardController,
    ) -> None:
        self.controller = controller
        self.session_token = secrets.token_urlsafe(32)
        super().__init__(address, VoiceDashboardRequestHandler)


class VoiceDashboardRequestHandler(BaseHTTPRequestHandler):
    """Small JSON and static-file router with no third-party web framework."""

    server: VoiceDashboardServer

    def do_GET(self) -> None:
        """Serve the dashboard and read-only local JSON endpoints."""

        if not self._valid_host():
            self._json_error(HTTPStatus.FORBIDDEN, "Only localhost requests are accepted.")
            return

        parsed = urlparse(self.path)

        try:
            if parsed.path == "/":
                self._static("index.html", inject_token=True)
            elif parsed.path.startswith("/static/"):
                self._static(parsed.path.removeprefix("/static/"))
            elif parsed.path == "/api/health":
                self._json(HTTPStatus.OK, self.server.controller.health_snapshot())
            elif parsed.path == "/api/overview":
                self._json(HTTPStatus.OK, self.server.controller.overview())
            elif parsed.path == "/api/mt5/positions":
                self._json(HTTPStatus.OK, self.server.controller.positions())
            elif parsed.path == "/api/mt5/quote":
                pair = parse_qs(parsed.query).get("pair", ["EURUSD"])[0]
                self._json(HTTPStatus.OK, self.server.controller.quote(pair))
            else:
                self._json_error(HTTPStatus.NOT_FOUND, "Route not found.")
        except (
            DemoTradingBlockedError,
            RuntimeError,
            TypeError,
            ValueError,
            ValidationError,
        ) as error:
            self._json_error(HTTPStatus.BAD_REQUEST, str(error))
        except Exception:  # noqa: BLE001 - HTTP boundary hides unexpected details
            self._json_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Unexpected local server error.")

    def do_POST(self) -> None:
        """Handle token-protected local mutations and agent conversations."""

        if not self._valid_host():
            self._json_error(HTTPStatus.FORBIDDEN, "Only localhost requests are accepted.")
            return

        if self.headers.get("X-AIQL-Session") != self.server.session_token:
            self._json_error(HTTPStatus.FORBIDDEN, "Invalid local dashboard session.")
            return

        parsed = urlparse(self.path)

        try:
            payload = self._json_body()

            if parsed.path == "/api/chat":
                text = payload.get("text")

                if not isinstance(text, str):
                    raise TypeError("Chat text must be a string.")

                result = self.server.controller.chat(text)
            elif parsed.path == "/api/mt5/connect":
                result = self.server.controller.connect_mt5()
            elif parsed.path == "/api/mt5/disconnect":
                result = self.server.controller.disconnect_mt5()
            elif parsed.path == "/api/monitor/scan":
                result = self.server.controller.scan_market()
            elif parsed.path == "/api/runtime/tick":
                result = self.server.controller.runtime_tick()
            elif parsed.path == "/api/research/start":
                result = self.server.controller.start_research()
            elif parsed.path == "/api/research/pause":
                result = self.server.controller.pause_research()
            elif parsed.path == "/api/research/emergency-stop":
                reason = payload.get("reason", "Operator emergency stop from dashboard.")

                if not isinstance(reason, str):
                    raise TypeError("Emergency stop reason must be text.")

                result = self.server.controller.emergency_stop(reason)
            elif parsed.path == "/api/research/reset-emergency":
                result = self.server.controller.reset_emergency_stop()
            elif parsed.path == "/api/mt5/order":
                result = self.server.controller.place_demo_order(payload)
            else:
                self._json_error(HTTPStatus.NOT_FOUND, "Route not found.")
                return

            self._json(HTTPStatus.OK, result)
        except (
            DemoTradingBlockedError,
            RuntimeError,
            TypeError,
            ValueError,
            ValidationError,
        ) as error:
            self._json_error(HTTPStatus.BAD_REQUEST, str(error))
        except Exception:  # noqa: BLE001 - HTTP boundary hides unexpected details
            self._json_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Unexpected local server error.")

    def do_OPTIONS(self) -> None:
        """Refuse cross-origin preflight because the dashboard is local-only."""

        self._json_error(HTTPStatus.METHOD_NOT_ALLOWED, "Cross-origin access is disabled.")

    def log_message(self, format_string: str, *args: object) -> None:
        """Keep local request logs concise and credential-free."""

        del format_string, args

    def _json_body(self) -> dict[str, object]:
        length_text = self.headers.get("Content-Length", "0")

        try:
            length = int(length_text)
        except ValueError as error:
            raise ValueError("Invalid Content-Length header.") from error

        if length < 0 or length > MAXIMUM_REQUEST_BYTES:
            raise ValueError("Request body is too large.")

        if length == 0:
            return {}

        raw = self.rfile.read(length)

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Request body must be valid UTF-8 JSON.") from error

        if not isinstance(payload, dict):
            raise TypeError("Request JSON must be an object.")

        return cast(dict[str, object], payload)

    def _static(self, name: str, *, inject_token: bool = False) -> None:
        if name not in {"index.html", "app.js", "styles.css"}:
            self._json_error(HTTPStatus.NOT_FOUND, "Static asset not found.")
            return

        resource = files("ai_quant_lab.web").joinpath("static", name)
        content = resource.read_bytes()

        if inject_token:
            content = content.replace(b"__SESSION_TOKEN__", self.server.session_token.encode())

        content_type = {
            "index.html": "text/html; charset=utf-8",
            "app.js": "text/javascript; charset=utf-8",
            "styles.css": "text/css; charset=utf-8",
        }[name]
        self.send_response(HTTPStatus.OK)
        self._security_headers(content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status: HTTPStatus, payload: object) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._security_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _json_error(self, status: HTTPStatus, message: str) -> None:
        self._json(status, {"error": message})

    def _security_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'",
        )

    def _valid_host(self) -> bool:
        host_header = self.headers.get("Host", "")
        host = host_header.rsplit(":", 1)[0].strip("[]").casefold()
        return host in LOCAL_HOSTS


def serve_voice_dashboard(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    auto_monitor: bool = True,
    monitor_interval_seconds: float = 30.0,
    operational_database: str | Path = "data/operational/lab.sqlite3",
    monitor_config: MonitorConfig | None = None,
    model_config_path: str | Path = "configs/agents.toml",
) -> None:
    """Run the voice dashboard on localhost until Ctrl+C."""

    if host.casefold() not in LOCAL_HOSTS:
        raise ValueError("The voice dashboard may bind to localhost only.")

    if port < 1 or port > 65_535:
        raise ValueError("Dashboard port must be between 1 and 65535.")

    runtime = LabRuntime(
        LabRuntimeConfig(operational_database=Path(operational_database)),
    )
    gateway = MT5DemoGateway()
    monitor = DemoMarketMonitor(gateway, monitor_config or MonitorConfig())
    model_path = Path(model_config_path)
    model_runtime = load_model_runtime(model_path) if model_path.exists() else None
    controller = DashboardController(
        runtime,
        gateway,
        monitor,
        model_runtime=model_runtime,
    )
    worker = DashboardBackgroundWorker(
        controller,
        auto_monitor=auto_monitor,
        monitor_interval_seconds=monitor_interval_seconds,
    )
    server = VoiceDashboardServer((host, port), controller)
    worker.start()
    url = f"http://{host}:{server.server_address[1]}"

    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()

    print(f"AI Quant Lab voice dashboard: {url}")
    print("Press Ctrl+C to stop safely.")

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        worker.stop()


class RunningVoiceDashboard:
    """Test helper context that owns server and worker lifecycle."""

    def __init__(
        self,
        server: VoiceDashboardServer,
        worker: DashboardBackgroundWorker | None = None,
    ) -> None:
        self.server = server
        self.worker = worker
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)

    def __enter__(self) -> Self:
        if self.worker is not None:
            self.worker.start()

        self.thread.start()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception_type, exception, traceback
        self.server.shutdown()
        self.server.server_close()

        if self.worker is not None:
            self.worker.stop()
