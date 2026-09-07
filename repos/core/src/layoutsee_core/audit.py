from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

SENSITIVE_ACTION_TYPES = {"input_text", "device_shell"}


def sanitize_action(action_type: str, payload: dict[str, object]) -> dict[str, object]:
    """审计与日志共用：文本类输入只保留长度与哈希，不落敏感内容。"""
    if action_type in SENSITIVE_ACTION_TYPES:
        text = str(payload.get("text", payload.get("command", "")))
        return {"chars": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]}
    safe: dict[str, object] = {}
    for key, value in payload.items():
        if isinstance(value, (str, int, float, bool)):
            safe[key] = value
    return safe


class ActionLog:
    """ActionLog：追加 JSONL 并 fsync；按天滚动。"""

    def __init__(self, audit_dir: Path) -> None:
        self.audit_dir = audit_dir
        self._lock = threading.Lock()

    def record(self, event: dict[str, object]) -> None:
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.audit_dir / f"action-{day}.jsonl"
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                try:
                    import os

                    os.fsync(handle.fileno())
                except OSError:
                    pass

    def requested(self, *, action_id: str, source: str, device_id: str, action_type: str, payload: dict[str, object], request_id: str, decision: str, plugin_id: str | None = None) -> None:
        event: dict[str, object] = {
            "kind": "requested",
            "actionId": action_id,
            "timestampMs": int(time.time() * 1000),
            "source": source,
            "deviceIdHash": hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:12],
            "actionType": action_type,
            "params": sanitize_action(action_type, payload),
            "decision": decision,
            "requestId": request_id,
        }
        if plugin_id:
            event["pluginId"] = plugin_id
        self.record(event)

    def result(self, *, action_id: str, result_code: str, duration_ms: int, request_id: str) -> None:
        self.record({
            "kind": "result",
            "actionId": action_id,
            "timestampMs": int(time.time() * 1000),
            "resultCode": result_code,
            "durationMs": duration_ms,
            "requestId": request_id,
        })
