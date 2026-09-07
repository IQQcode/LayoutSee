from __future__ import annotations

import threading
import time
from pathlib import Path

RETENTION_DAYS = 7


class UiLogStore:
    """前端 UI 日志按天落盘（logs/ui-YYYY-MM-DD.log），保留 7 天；单行制表符分隔。"""

    def __init__(self, data_dir: Path) -> None:
        self.log_dir = data_dir / "logs"
        self._lock = threading.Lock()
        self._cleanup_old()

    def _cleanup_old(self) -> None:
        try:
            if not self.log_dir.is_dir():
                return
            cutoff = time.time() - RETENTION_DAYS * 86400
            for path in self.log_dir.glob("ui-*.log"):
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
        except OSError:
            pass

    def append(self, entries: list[dict[str, object]]) -> None:
        if not entries:
            return
        lines: list[str] = []
        for entry in entries:
            timestamp = int(entry.get("timestampMs", 0) or 0) / 1000
            moment = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(timestamp))
            fields = (
                moment,
                str(entry.get("level", "info")),
                str(entry.get("tag", "")),
                str(entry.get("message", "")).replace("\n", "\\n").replace("\t", " "),
            )
            lines.append("\t".join(fields))
        try:
            with self._lock:
                self.log_dir.mkdir(parents=True, exist_ok=True)
                path = self.log_dir / f"ui-{time.strftime('%Y-%m-%d')}.log"
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("\n".join(lines) + "\n")
        except OSError:
            pass
