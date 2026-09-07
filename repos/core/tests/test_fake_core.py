from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from layoutsee_core.generated_contracts import CoreInfo, FakeCoreScenario


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SCENARIO = WORKSPACE_ROOT / "repos/contracts/fixtures/valid/fake-core-scenario.json"
FAKE_CORE = Path(__file__).parent / "fake_core/server.py"


class FakeCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="layoutsee-fake-core-")
        self.socket_path = str(Path(self.temp.name) / "control.sock")
        self.token = "control-test-token"
        self.nonce = "a" * 64
        self.process = subprocess.Popen(
            [sys.executable, str(FAKE_CORE), "--nonce", self.nonce, "--scenario", str(SCENARIO), "--control-socket", self.socket_path, "--control-token", self.token],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        assert self.process.stdout
        line = self.process.stdout.readline().strip()
        self.assertTrue(line.startswith("READY "), line)
        self.ready = CoreInfo.model_validate_json(line[6:])

    def tearDown(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.stderr:
            self.process.stderr.close()
        self.temp.cleanup()

    def request(self, path: str):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.ready.port}{path}", timeout=2) as response:
            return response, response.read()

    def control(self, command: str) -> dict[str, object]:
        deadline = time.monotonic() + 2
        while not Path(self.socket_path).exists():
            if time.monotonic() > deadline: self.fail("控制 socket 未创建")
            time.sleep(.01)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(self.socket_path)
            client.sendall((json.dumps({"token": self.token, "command": command}) + "\n").encode())
            return json.loads(client.makefile().readline())

    def test_ready_and_info_use_same_contract(self) -> None:
        response, body = self.request("/api/v1/info")
        payload = json.loads(body)
        info = CoreInfo.model_validate(payload["data"])
        self.assertEqual(response.status, 200)
        self.assertEqual(info, self.ready)
        self.assertEqual(info.nonce, self.nonce)

    def test_security_headers_and_loopback_binding(self) -> None:
        response, _ = self.request("/health/ready")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(self.ready.port >= 33299, True)

    def test_scenario_uses_generated_model_and_control_socket(self) -> None:
        fixture = json.loads(SCENARIO.read_text())["value"]
        scenario = FakeCoreScenario.model_validate(fixture)
        self.assertEqual(scenario.schemaVersion, "1.0")
        metrics = self.control("metrics")
        self.assertTrue(metrics["ok"])
        events = self.control("get-events")
        self.assertEqual([event["command"] for event in events["events"]], ["metrics", "get-events"])


class RealCoreContractTest(unittest.TestCase):
    def test_real_core_uses_the_same_ready_and_info_contract(self) -> None:
        nonce = "b" * 64
        process = subprocess.Popen(
            [sys.executable, "-m", "layoutsee_core", "--nonce", nonce, "--port-start", "33309"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert process.stdout
            ready = CoreInfo.model_validate_json(process.stdout.readline().strip()[6:])
            with urllib.request.urlopen(f"http://127.0.0.1:{ready.port}/api/v1/info", timeout=2) as response:
                payload = json.loads(response.read())
            self.assertEqual(CoreInfo.model_validate(payload["data"]), ready)
            self.assertEqual(ready.nonce, nonce)
        finally:
            process.terminate()
            process.wait(timeout=3)
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
