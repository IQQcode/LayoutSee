"""手动复现 scrcpy 会话：同时观察 shell 输出与视频帧，定位断流原因。"""
from __future__ import annotations

import struct
import sys
import time

sys.path.insert(0, "repos/core/src")
from layoutsee_core.adb import AdbClient
from layoutsee_core.media import AdbConnection, ScrcpySession, scrcpy_jar_path

SERIAL = "RFCY41B0EVZ"

adb = AdbClient(resolver=lambda: "/opt/local/bin/adb")
print("jar:", scrcpy_jar_path())
print("== push ==")
adb.run(["push", str(scrcpy_jar_path()), "/data/local/tmp/layoutsee_scrcpy_server.jar"], serial=SERIAL, timeout=20)

command = "CLASSPATH=/data/local/tmp/layoutsee_scrcpy_server.jar app_process / com.genymobile.scrcpy.Server 2.7 log_level=info max_fps=24 max_size=1024 video_bit_rate=8000000 tunnel_forward=true send_frame_meta=true control=false audio=false show_touches=false stay_awake=false power_off_on_close=false clipboard_autosync=false"
print("== spawn shell ==", command[:80], "...")
shell = AdbConnection(SERIAL, f"shell:{command}")

video = None
deadline = time.monotonic() + 8
while time.monotonic() < deadline:
    try:
        video = AdbConnection(SERIAL, "localabstract:scrcpy")
        break
    except Exception as error:
        time.sleep(0.2)
if video is None:
    print("隧道失败")
    sys.exit(1)
print("== 隧道已连 ==")


def read_exactly(conn, size, timeout=2.0):
    conn.sock.settimeout(timeout)
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = conn.read(remaining)
        if not chunk:
            raise ConnectionError("EOF")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


try:
    dummy = read_exactly(video, 1)
    print("dummy:", dummy.hex())
    name = read_exactly(video, 64)
    print("device:", name.rstrip(b"\x00").decode("utf-8", "replace"))
    codec = read_exactly(video, 4)
    print("codec:", codec)
    w, h = struct.unpack(">II", read_exactly(video, 8))
    print(f"size: {w}x{h}")
    frames = 0
    started = time.monotonic()
    while frames < 40 and time.monotonic() - started < 10:
        pts = struct.unpack(">Q", read_exactly(video, 8))[0]
        length = struct.unpack(">I", read_exactly(video, 4))[0]
        payload = read_exactly(video, length, timeout=5.0)
        frames += 1
        nalu_type = payload[4] & 0x1F if payload[:4] == b"\x00\x00\x00\x01" else payload[0] & 0x1F
        print(f"帧 {frames}: pts={pts:#x} len={len(payload)} nalu={nalu_type}")
    print(f"== 完成 {frames} 帧 ==")
except Exception as error:
    print(f"!! 断流: {error}")

# 读 shell 残留输出（server 错误会在这里）
shell.sock.settimeout(2.0)
try:
    leftover = shell.read(8192)
    print("shell 输出:", leftover.decode("utf-8", "replace")[:800] or "(空)")
except Exception as error:
    print("shell 无输出:", error)
finally:
    shell.close()
    if video:
        video.close()
