from __future__ import annotations

import argparse
import json
import os
import signal
import socketserver
import threading
import time
from pathlib import Path

from layoutsee_core.bootstrap import build_core
from layoutsee_core.generated_contracts import FakeCoreScenario
from layoutsee_core.server import ready_line


class ControlHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        for raw in self.rfile:
            try:
                request = json.loads(raw)
                if request.get("token") != self.server.control_token:
                    response = {"ok": False, "error": "CONTROL_UNAUTHORIZED"}
                else:
                    response = self.server.dispatch(request)
            except (json.JSONDecodeError, TypeError):
                response = {"ok": False, "error": "CONTROL_INVALID_REQUEST"}
            self.wfile.write((json.dumps(response, separators=(",", ":")) + "\n").encode())


class ControlServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, path: str, token: str, http_server, scenario: dict[str, object]):
        self.control_token = token
        self.http_server = http_server
        self.scenario = scenario
        self.events: list[dict[str, object]] = []
        super().__init__(path, ControlHandler)

    def dispatch(self, request: dict[str, object]) -> dict[str, object]:
        command = request.get("command")
        self.events.append({"command": command, "at": time.time_ns() // 1_000_000})
        if command == "get-events": return {"ok": True, "events": self.events}
        if command == "metrics": return {"ok": True, "requests": len(self.events), "pid": os.getpid()}
        if command in {"set-device-state", "drop-media", "set-response", "spawn-child", "ignore-sigterm"}: return {"ok": True}
        if command == "shutdown":
            threading.Thread(target=self._shutdown, daemon=True).start()
            return {"ok": True}
        if command == "crash": os.kill(os.getpid(), signal.SIGKILL)
        return {"ok": False, "error": "CONTROL_UNKNOWN_COMMAND"}

    def _shutdown(self) -> None:
        self.http_server.shutdown()
        self.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="LayoutSee 可控假 Core")
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--control-socket", required=True)
    parser.add_argument("--control-token", required=True)
    parser.add_argument("--static-dir", type=Path)
    parser.add_argument("--port-start", type=int, default=11663)
    args = parser.parse_args()

    fixture = json.loads(args.scenario.read_text())
    scenario = FakeCoreScenario.model_validate(fixture["value"]).model_dump()
    nonce = args.nonce if scenario["boot"]["nonceMode"] == "echo" else "f" * 64
    context, http_server = build_core(nonce, args.static_dir, None, args.port_start)
    control_path = Path(args.control_socket)
    control_path.unlink(missing_ok=True)
    control_server = ControlServer(str(control_path), args.control_token, http_server, scenario)
    control_thread = threading.Thread(target=control_server.serve_forever, daemon=True)
    control_thread.start()
    delay = scenario["boot"]["readyDelayMs"] / 1000
    if delay: time.sleep(delay)
    print(ready_line(context.info), flush=True)
    try:
        http_server.serve_forever(poll_interval=0.05)
    finally:
        control_server.shutdown()
        control_server.server_close()
        http_server.server_close()
        control_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
