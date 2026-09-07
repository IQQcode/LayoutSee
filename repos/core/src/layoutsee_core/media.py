from __future__ import annotations

import logging
import queue
import re
import socket
import struct
import threading
import time
from pathlib import Path

from .adb import AdbClient
from .errors import CoreError

logger = logging.getLogger("layoutsee.media")

SCRCPY_VERSION = "2.7"
SCRCPY_JAR = f"scrcpy-server-v{SCRCPY_VERSION}.jar"
REMOTE_JAR = "/data/local/tmp/layoutsee_scrcpy_server.jar"
ADB_SERVER_PORT = 5037
CONNECT_TIMEOUT_S = 8.0
SUBSCRIBER_QUEUE_DEPTH = 30
IDLE_KEEP_S = 3.0
# serial 仅用于 adb 目标选择；白名单校验后才进入任何协议参数
SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def scrcpy_jar_path() -> Path | None:
    candidate = Path(__file__).parent / "resources" / SCRCPY_JAR
    return candidate if candidate.is_file() else None


def server_command(fps_cap: int) -> str:
    """设备端 scrcpy server 启动命令；组成部分全部为常量或经范围约束的整数。"""
    capped = max(5, min(60, int(fps_cap)))
    parts = [
        f"CLASSPATH={REMOTE_JAR}",
        "app_process", "/", "com.genymobile.scrcpy.Server", SCRCPY_VERSION,
        "log_level=error",
        f"max_fps={capped}",
        "max_size=1024",
        "video_bit_rate=8000000",
        # 短 GOP：丢帧/解码异常后 2 秒内有关键帧恢复，避免画面污染长期不消
        "video_codec_options=i-frame-interval=2",
        "tunnel_forward=true",
        "send_frame_meta=true",
        "control=false",
        "audio=false",
        "show_touches=false",
        "stay_awake=false",
        "power_off_on_close=false",
        "clipboard_autosync=false",
    ]
    return " ".join(parts)


class _Subscriber:
    def __init__(self) -> None:
        self.queue: queue.Queue[bytes | None] = queue.Queue(maxsize=SUBSCRIBER_QUEUE_DEPTH)
        self.alive = True

    def publish(self, record: bytes) -> None:
        if not self.alive:
            return
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            # 丢弃最旧的一帧，保持实时性
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.queue.put_nowait(record)
            except queue.Full:
                pass

    def close(self) -> None:
        self.alive = False
        try:
            self.queue.put_nowait(None)
        except queue.Full:
            pass


class AdbConnection:
    """最小 ADB wire 协议连接：host:transport → 服务名，得到原始字节流。"""

    def __init__(self, serial: str, service: str, timeout: float = CONNECT_TIMEOUT_S) -> None:
        if not SERIAL_PATTERN.match(serial):
            raise CoreError("INVALID_ARGUMENT", "设备序列号格式非法。")
        self.sock = self._connect(timeout)
        try:
            self._request(f"host:transport:{serial}")
            self._request(service)
        except Exception:
            self.sock.close()
            raise

    @staticmethod
    def _connect(timeout: float) -> socket.socket:
        try:
            sock = socket.create_connection(("127.0.0.1", ADB_SERVER_PORT), timeout=timeout)
        except OSError as error:
            raise ConnectionError(f"无法连接 adb server：{error}") from error
        sock.settimeout(timeout)
        return sock

    def _read_exactly(self, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            try:
                chunk = self.sock.recv(remaining)
            except OSError as error:
                raise ConnectionError(f"ADB 连接中断：{error}") from error
            if not chunk:
                raise ConnectionError("ADB 连接中断")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _request(self, payload: str) -> None:
        message = payload.encode("utf-8")
        self.sock.sendall(f"{len(message):04x}".encode("ascii") + message)
        status = self._read_exactly(4)
        if status != b"OKAY":
            length = int(self._read_exactly(4), 16)
            reason = self._read_exactly(length).decode("utf-8", errors="replace") if length else "未知错误"
            raise ConnectionError(f"ADB 服务 {payload} 失败：{reason}")

    def read(self, size: int, timeout: float | None = None) -> bytes:
        if timeout is not None:
            self.sock.settimeout(timeout)
        return self.sock.recv(size)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class ScrcpySession:
    """单设备 scrcpy 会话：推送 jar → shell 服务启动 → localabstract 隧道取流并扇出。"""

    def __init__(self, adb: AdbClient, serial: str, fps_cap: int = 24) -> None:
        if not SERIAL_PATTERN.match(serial):
            raise CoreError("INVALID_ARGUMENT", "设备序列号格式非法。")
        self.adb = adb
        self.serial = serial
        self.fps_cap = max(5, min(60, int(fps_cap)))
        self.state = "starting"
        self.last_error: str | None = None
        self.stream_width = 0
        self.stream_height = 0
        self._subscribers: set[_Subscriber] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._shell: AdbConnection | None = None
        self._video: AdbConnection | None = None

    # ---------- 生命周期 ----------

    def start(self) -> None:
        jar = scrcpy_jar_path()
        if jar is None:
            raise CoreError("MEDIA_UNAVAILABLE", "scrcpy server 组件缺失，无法启动实时投屏。")
        self.adb.run(["push", str(jar), REMOTE_JAR], serial=self.serial, timeout=20)
        self._shell = AdbConnection(self.serial, f"shell:{server_command(self.fps_cap)}")
        monitor = threading.Thread(target=self._watch_shell, name=f"layoutsee-scrcpy-shell-{self.serial}", daemon=True)
        monitor.start()
        self._threads.append(monitor)
        worker = threading.Thread(target=self._run_video, name=f"layoutsee-scrcpy-{self.serial}", daemon=True)
        worker.start()
        self._threads.append(worker)

    def close(self) -> None:
        self._stop.set()
        self._close_sockets()
        for thread in self._threads:
            thread.join(timeout=2.0)
        with self._lock:
            for subscriber in list(self._subscribers):
                subscriber.close()
            self._subscribers.clear()
        if self.state not in ("error",):
            self.state = "stopped"

    def _close_sockets(self) -> None:
        for connection in (self._video, self._shell):
            if connection is not None:
                connection.close()

    def _watch_shell(self) -> None:
        # 设备端 server 退出时 shell 流 EOF；log_level=error 时正常路径没有任何输出
        try:
            while not self._stop.is_set():
                try:
                    chunk = self._shell.read(4096, timeout=1.0)
                except TimeoutError:
                    continue  # 静默属正常状态
                except (OSError, ConnectionError, CoreError):
                    break
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace").strip()
                if text:
                    self.last_error = text[:500]
        finally:
            if not self._stop.is_set():
                # shell 流关闭 = 设备端 server 已退出，主动断开视频隧道并通知订阅者
                self.state = "stopped"
                self._close_sockets()
                self._fanout(None)

    # ---------- 视频流 ----------

    def _run_video(self) -> None:
        try:
            video = self._await_tunnel()
            if video is None:
                return
            try:
                self._video = video
                self._read_stream(video)
            finally:
                video.close()
        except (OSError, ConnectionError, CoreError) as error:
            self.last_error = str(error) if self.last_error is None else self.last_error
            if self.state != "stopped":
                self.state = "error"
        finally:
            if self.state == "running":
                self.state = "stopped"
            self._fanout(None)

    def _await_tunnel(self) -> AdbConnection | None:
        deadline = time.monotonic() + CONNECT_TIMEOUT_S
        last_error: Exception | None = None
        while time.monotonic() < deadline and not self._stop.is_set():
            if self.state == "error":
                break
            try:
                tunnel = AdbConnection(self.serial, "localabstract:scrcpy")
                logger.info("scrcpy tunnel connected: %s", self.serial)
                return tunnel
            except (OSError, ConnectionError, CoreError) as error:
                last_error = error
                time.sleep(0.15)
        self.last_error = self.last_error or f"连接 scrcpy 隧道超时：{last_error}"
        if self.state != "stopped":
            self.state = "error"
        self._fanout(None)
        return None

    def _read_exactly(self, connection: AdbConnection, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            if self._stop.is_set():
                raise ConnectionError("会话已停止")
            # 静止画面可能长时间无新帧，超时须远大于帧间隔；close() 会先关 socket 打断阻塞
            chunk = connection.read(remaining, timeout=15.0)
            if not chunk:
                raise ConnectionError("视频流已断开")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _read_stream(self, connection: AdbConnection) -> None:
        dummy = self._read_exactly(connection, 1)
        if dummy != b"\x00":
            raise ConnectionError("scrcpy 协议握手失败（dummy byte）")
        self._read_exactly(connection, 64)  # device name
        codec = self._read_exactly(connection, 4)
        if codec != b"h264":
            raise ConnectionError(f"不支持的编码：{codec!r}")
        self.stream_width, self.stream_height = struct.unpack(">II", self._read_exactly(connection, 8))
        header = struct.pack(">4sIII", b"LSS1", self.stream_width, self.stream_height, self.fps_cap)
        with self._lock:
            self.state = "running"
            for subscriber in list(self._subscribers):
                subscriber.publish(header)
        logger.info("scrcpy streaming %s @ %dx%d", self.serial, self.stream_width, self.stream_height)
        while not self._stop.is_set():
            pts = self._read_exactly(connection, 8)
            length = struct.unpack(">I", self._read_exactly(connection, 4))[0]
            if length <= 0 or length > 4 * 1024 * 1024:
                raise ConnectionError(f"非法帧长度：{length}")
            payload = self._read_exactly(connection, length)
            self._fanout(pts + struct.pack(">I", length) + payload)
        self.state = "stopped"

    def _fanout(self, record: bytes | None) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            if record is None:
                subscriber.close()
            else:
                subscriber.publish(record)

    # ---------- 订阅 ----------

    def subscribe(self) -> _Subscriber:
        subscriber = _Subscriber()
        with self._lock:
            self._subscribers.add(subscriber)
        # 会话已在运行时，补发一次头信息，避免晚到的观众缺少分辨率
        if self.state == "running" and self.stream_width:
            header = struct.pack(">4sIII", b"LSS1", self.stream_width, self.stream_height, self.fps_cap)
            subscriber.publish(header)
        return subscriber

    def unsubscribe(self, subscriber: _Subscriber) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)
        subscriber.close()


class MediaHub:
    """设备级 scrcpy 会话管理：懒启动、无观众自动回收、失败可重试。"""

    def __init__(self, adb: AdbClient) -> None:
        self.adb = adb
        self._lock = threading.Lock()
        self._sessions: dict[str, ScrcpySession] = {}
        self._last_used: dict[str, float] = {}

    def capabilities(self) -> dict[str, object]:
        jar = scrcpy_jar_path()
        return {
            "mode": "scrcpy" if jar else "screenshot",
            "live": jar is not None,
            "reason": "" if jar else "scrcpy server 组件缺失，当前为截图轮询模式。",
            "scrcpyVersion": SCRCPY_VERSION if jar else None,
            "screenshotIntervalMs": 800,
        }

    def stream(self, serial: str, fps_cap: int) -> tuple[ScrcpySession, _Subscriber]:
        """返回 (session, subscriber)；失败抛 CoreError。"""
        if not self.adb.available():
            raise CoreError("ADB_NOT_FOUND", "未找到 adb，无法启动实时投屏。")
        with self._lock:
            session = self._sessions.get(serial)
            if session is not None and session.state in ("error", "stopped"):
                session.close()
                self._sessions.pop(serial, None)
                session = None
            if session is None:
                session = ScrcpySession(self.adb, serial, fps_cap)
                try:
                    session.start()
                except CoreError:
                    session.close()
                    raise
                self._sessions[serial] = session
            self._last_used[serial] = time.monotonic()
            return session, session.subscribe()

    def release(self, serial: str, subscriber: _Subscriber) -> None:
        with self._lock:
            session = self._sessions.get(serial)
            self._last_used[serial] = time.monotonic()
        if session is not None:
            session.unsubscribe(subscriber)

    def reap_idle(self) -> None:
        """由后台线程周期调用：无观众或已结束的会话及时回收。"""
        now = time.monotonic()
        with self._lock:
            for serial, session in list(self._sessions.items()):
                idle = now - self._last_used.get(serial, now)
                if session.state in ("error", "stopped") or (not session._subscribers and idle > IDLE_KEEP_S):
                    session.close()
                    self._sessions.pop(serial, None)
                    self._last_used.pop(serial, None)

    def stop_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.close()
