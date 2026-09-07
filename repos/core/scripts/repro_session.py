"""进程内复现：直接用 Core 的 ScrcpySession，观察状态与 last_error。"""
from __future__ import annotations

import queue
import sys
import time

sys.path.insert(0, "repos/core/src")
from layoutsee_core.adb import AdbClient
from layoutsee_core.media import ScrcpySession, scrcpy_jar_path

SERIAL = "RFCY41B0EVZ"
adb = AdbClient(resolver=lambda: "/opt/local/bin/adb")
session = ScrcpySession(adb, SERIAL, 24)
print("== start ==")
session.start()
subscriber = session.subscribe()
frames = 0
started = time.monotonic()
try:
    while time.monotonic() - started < 12:
        try:
            record = subscriber.queue.get(timeout=1.0)
        except queue.Empty:
            print(f"[{time.monotonic()-started:.1f}s] 无数据 state={session.state} last_error={session.last_error!r}")
            continue
        if record is None:
            print(f"[{time.monotonic()-started:.1f}s] 流结束 state={session.state} last_error={session.last_error!r}")
            break
        if len(record) == 16 and record[:4] == b"LSS1":
            print("头部到达")
            continue
        frames += 1
        if frames <= 5 or frames % 24 == 0:
            print(f"帧 {frames}: len={len(record)-12} state={session.state}")
finally:
    session.close()
    print(f"共 {frames} 帧; 最终 state={session.state} last_error={session.last_error!r}")
