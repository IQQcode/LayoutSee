"""Logcat 读取层：把 `adb logcat -d` 的重复 dump 折叠成带游标的增量行。

为什么不开常驻 `adb logcat` 子进程：全部 adb 交互必须收敛到 AdbClient.run（Mimosa hook 约束），
常驻进程还要额外管生命周期与背压。这里改成周期性 dump + 重叠对齐：
每次取尾部若干行，用上一次结尾的若干行作为锚点在新 dump 里找位置，锚点之后的才是新行。
锚点找不到说明设备环形缓冲已滚过（日志量大于 dump 窗口），置 dropped 让 UI 提示丢日志。
"""

from __future__ import annotations

import re
import threading
from collections import deque

DUMP_LINES = 1200
MAX_BUFFER = 4000
ANCHOR_LINES = 8
MAX_LIMIT = 1000
MAX_MESSAGE_CHARS = 4000

LEVELS = ("V", "D", "I", "W", "E", "F", "S")

# threadtime 格式：09-03 10:12:13.123  1234  1256 D TagName: message
LOGCAT_LINE = re.compile(
    r"^(?P<ts>\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+(?P<pid>\d+)\s+(?P<tid>\d+)\s+"
    r"(?P<level>[VDIWEFS])\s+(?P<tag>.*?)\s*:\s?(?P<message>.*)$"
)


def parse_line(raw: str, previous: dict[str, object] | None) -> dict[str, object] | None:
    """解析一行 threadtime 日志；无法解析的行视为上一条的续行（堆栈），分隔行返回 None。"""
    if raw.startswith("--------- "):
        return None
    match = LOGCAT_LINE.match(raw)
    if match:
        return {
            "time": match.group("ts"),
            "pid": int(match.group("pid")),
            "tid": int(match.group("tid")),
            "level": match.group("level"),
            "tag": match.group("tag")[:120],
            "message": match.group("message")[:MAX_MESSAGE_CHARS],
            "continuation": False,
        }
    if previous is None:
        return None
    return {
        "time": previous.get("time", ""),
        "pid": previous.get("pid", 0),
        "tid": previous.get("tid", 0),
        "level": previous.get("level", "I"),
        "tag": previous.get("tag", ""),
        "message": raw.strip()[:MAX_MESSAGE_CHARS],
        "continuation": True,
    }


def align(previous_anchor: list[str], dumped: list[str]) -> tuple[list[str], bool]:
    """返回 (新增行, 是否丢过日志)。锚点为空表示首次读取，全部视为新增。"""
    if not previous_anchor:
        return dumped, False
    size = len(previous_anchor)
    for start in range(len(dumped) - size, -1, -1):
        if dumped[start:start + size] == previous_anchor:
            return dumped[start + size:], False
    return dumped, True


class LogcatHub:
    """每设备一份游标与环形缓冲；多个消费者按 after 游标各取所需。"""

    def __init__(self, adb, dump_lines: int = DUMP_LINES, max_buffer: int = MAX_BUFFER) -> None:
        self.adb = adb
        self.dump_lines = dump_lines
        self.max_buffer = max_buffer
        self._lock = threading.RLock()
        self._states: dict[str, dict[str, object]] = {}

    def _state(self, device_id: str) -> dict[str, object]:
        state = self._states.get(device_id)
        if state is None:
            state = {"cursor": 0, "anchor": [], "entries": deque(maxlen=self.max_buffer), "dropped": False}
            self._states[device_id] = state
        return state

    def read(self, device_id: str, serial: str, *, after: int | None = None, limit: int = 500) -> dict[str, object]:
        limit = max(1, min(int(limit), MAX_LIMIT))
        text = self.adb.logcat_dump(serial, self.dump_lines)
        dumped = [line.rstrip("\r") for line in text.splitlines() if line.strip()]
        with self._lock:
            state = self._state(device_id)
            fresh, dropped = align(list(state["anchor"]), dumped)
            state["anchor"] = dumped[-ANCHOR_LINES:]
            entries: deque = state["entries"]
            previous = entries[-1] if entries else None
            for raw in fresh:
                parsed = parse_line(raw, previous)
                if parsed is None:
                    continue
                state["cursor"] = int(state["cursor"]) + 1
                parsed["seq"] = state["cursor"]
                entries.append(parsed)
                previous = parsed
            cursor = int(state["cursor"])
            # 客户端游标比 Core 还新只可能是清空过日志，让它重置本地缓冲
            reset = after is not None and after > cursor
            if after is None or reset:
                selected = list(entries)[-limit:]
            else:
                selected = [entry for entry in entries if int(entry["seq"]) > after][:limit]
            return {
                "deviceId": device_id,
                "lines": [dict(entry) for entry in selected],
                "cursor": cursor,
                "dropped": dropped,
                "reset": reset,
                "buffered": len(entries),
            }

    def clear(self, device_id: str, serial: str) -> dict[str, object]:
        self.adb.logcat_clear(serial)
        with self._lock:
            self._states.pop(device_id, None)
        return {"deviceId": device_id, "cleared": True, "cursor": 0}
