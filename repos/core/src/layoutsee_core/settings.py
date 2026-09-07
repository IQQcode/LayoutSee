from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .errors import CoreError

DEFAULTS: dict[str, object] = {
    "schemaVersion": "1.0",
    "theme": "system",
    "adbPath": "",
    "pollIntervalMs": 5000,
    "screenshotFallbackIntervalMs": 800,
    "videoFpsCap": 30,
    "mediaReconnectAttempts": 3,
    "defaultReadonly": False,
}

UPDATABLE_KEYS = {
    "theme": ("light", "dark", "system"),
    "adbPath": None,
    "pollIntervalMs": (1_000, 60_000),
    "screenshotFallbackIntervalMs": (400, 5_000),
    "videoFpsCap": (5, 60),
    "mediaReconnectAttempts": (1, 10),
    "defaultReadonly": None,
}

# 文件格式版本等系统字段随持久化自动维护，不在用户可改范围；提交补丁时静默忽略
SYSTEM_KEYS = frozenset({"schemaVersion"})


def default_data_dir() -> Path:
    override = os.environ.get("LAYOUTSEE_DATA_DIR")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "LayoutSee"


class SettingsStore:
    """原子 JSON 设置存储；0600 权限；未知字段不落盘。"""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        self.settings_path = self.data_dir / "settings.json"
        self._lock = threading.Lock()
        self._cache: dict[str, object] | None = None

    def get(self) -> dict[str, object]:
        with self._lock:
            if self._cache is None:
                self._cache = self._load_locked()
            return dict(self._cache)

    def _load_locked(self) -> dict[str, object]:
        merged = dict(DEFAULTS)
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if key in DEFAULTS and isinstance(value, type(DEFAULTS[key])):
                        merged[key] = value
        except (OSError, ValueError):
            pass
        return merged

    def update(self, patch: dict[str, object]) -> dict[str, object]:
        allowed: dict[str, object] = {}
        for key, value in patch.items():
            if key in SYSTEM_KEYS:
                continue
            if key not in UPDATABLE_KEYS:
                raise CoreError("INVALID_ARGUMENT", f"不允许修改的设置：{key}")
            constraint = UPDATABLE_KEYS[key]
            if constraint is None:
                if not isinstance(value, (str, bool)):
                    raise CoreError("INVALID_ARGUMENT", f"设置值类型错误：{key}")
            elif isinstance(constraint, tuple) and len(constraint) == 2 and all(isinstance(item, int) for item in constraint):
                if not isinstance(value, int) or isinstance(value, bool) or not (constraint[0] <= value <= constraint[1]):
                    raise CoreError("INVALID_ARGUMENT", f"设置值超出范围：{key}")
            elif isinstance(constraint, tuple):
                if value not in constraint:
                    raise CoreError("INVALID_ARGUMENT", f"设置值超出范围：{key}")
            allowed[key] = value
        with self._lock:
            if self._cache is None:
                self._cache = self._load_locked()
            current = dict(self._cache)
            current.update(allowed)
            self._atomic_write(current)
            self._cache = current
        return dict(current)

    def adb_path(self) -> str | None:
        value = self.get().get("adbPath")
        return str(value) if value else None

    def _atomic_write(self, payload: dict[str, object]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.settings_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.settings_path)
