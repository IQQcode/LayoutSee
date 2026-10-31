r"""syslog 抓取层：vis 解码、真机行解析、模拟器 JSON 提取与 SyslogHub 双端 Hub。

协议事实源：libimobiledevice idevicesyslog.c（行格式与 vis(3) 转义，MIT）、
pymobiledevice3 syslog.py（MIT，syslog_relay 服务用法）、Apple lockdown 惯例；
模拟器侧为 `xcrun simctl spawn <udid> log stream --style json` 的公开输出格式。
- 真机链路：lockdown StartService("com.apple.syslog_relay") 拿端口 → usbmux 隧道 →
  裸流按 `\n\x00` 分行 → vis(3) 解码 → 行解析。syslog_relay 只有实时流没有 dump，
  因此 Hub 用「每设备一条持续读取线程 + 环形缓冲」代替 Android 的周期 dump + 锚点对齐
  （懒启动、断流自愈：线程退出后由下一次 read 重新拉起，无独立 reap 线程）。
- 真机行格式（idevicesyslog.c 解析逻辑）：前 16 字符为 `MMM DD HH:MM:SS ` 时间戳 →
  设备名 → 进程`[PID]`（可带 `(image)` 后缀）→ `<Notice>:` 等级别标记 → 消息；
  短于 16 字符或不匹配的行视为上一条的续行（continuation=true）。
- vis(3) 解码只还原高位字节（`\M-x`/`\M^X`）与可显示/UTF-8 高位段的八进制转义和 `\\`；
  控制字符转义保留原样，防止日志内容注入终端控制序列（中文日志必经此步否则乱码）。
- 模拟器链路：SimctlClient.log_stream 产出 JSON 事件流，顶层对象用深度计数 + 字符串感知
  提取（eventMessage 可能含 `},{` 与花括号），仅 eventType=="logEvent" 入列。
- 条目形状与 logcat.py 完全同构：time/pid/tid/level/tag/message/continuation/seq，
  tag 承载 iOS 进程名；read/clear 返回形状与 LogcatHub 一致。
"""
from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import threading
from collections import deque
from collections.abc import Callable, Iterator

from ..errors import CoreError
from .driver import IOS_SIMULATOR_PREFIX
from .lockdown import LockdownClient
from .usbmux import UsbmuxClient

SYSLOG_SERVICE = "com.apple.syslog_relay"
MAX_BUFFER = 4000
MAX_LIMIT = 1000
MAX_MESSAGE_CHARS = 4000
MAX_PENDING_BYTES = 256 * 1024  # 行未终结的残余超限即丢弃，防内存膨胀
STREAM_TIMEOUT = 10.0  # 日志空闲期 recv 超时属正常，读取处按继续等待处理
SIMULATOR_PREFIX = IOS_SIMULATOR_PREFIX

# 真机级别映射（doc 决策 8）：Notice/Info→I、Warning→W、Error→E、Debug→D、其余→I
RELAY_LEVELS = {"Notice": "I", "Info": "I", "Warning": "W", "Error": "E", "Debug": "D"}
# 模拟器 messageType 映射：Default/Info→I、Debug→D、Error→E、Fault→F
SIM_LEVELS = {"Default": "I", "Info": "I", "Debug": "D", "Error": "E", "Fault": "F"}

# 真机行格式：MMM DD HH:MM:SS 设备名 进程[PID] (可选 (image)) <Level>: 消息（级别与分隔可缺省）
RELAY_LINE = re.compile(
    r"^(?P<ts>[A-Z][a-z]{2} [ \d]\d \d{2}:\d{2}:\d{2}) (?P<device>\S+) "
    r"(?P<tag>[^\s\[]+)\[(?P<pid>\d+)\](?: \([^)]*\))?"
    r"(?: <(?P<level>[A-Za-z]+)>: |: | )?"
    r"(?P<message>.*)$"
)


def decode_vis(line: bytes) -> bytes:
    r"""还原 syslog 流里的 vis(3) 转义；控制字符转义保留原样（防终端控制序列注入）。

    还原范围（doc 决策）：`\M-x`/`\M^X`（高位字节，中文 UTF-8 必经此路）、
    `\ddd` 八进制（值落在可显示/UTF-8 高位段才还原）、`\\`。
    """
    out = bytearray()
    index = 0
    size = len(line)
    while index < size:
        byte = line[index]
        if byte != 0x5C:  # '\\'
            out.append(byte)
            index += 1
            continue
        rest = line[index + 1:]
        if rest[:1] == b"\\":  # \\ → \
            out.append(0x5C)
            index += 2
            continue
        if rest[:2] == b"M-":  # \M-x / \M^X：meta 字节 = 0x80 | 去位后的字符
            if rest[2:3] == b"^" and len(rest) >= 4:
                out.append(0x80 | _control_value(rest[3]))
                index += 5
            elif len(rest) >= 3:
                out.append(0x80 | rest[2])
                index += 4
            else:  # 残缺的 \M- 保留原样
                out.extend(line[index:index + 3])
                index += 3
            continue
        if rest[:1] == b"^":  # \^X 控制转义：保留原样
            keep = 3 if len(rest) >= 2 else 2
            out.extend(line[index:index + keep])
            index += keep
            continue
        if len(rest) >= 3 and all(0x30 <= rest[offset] <= 0x37 for offset in range(3)):
            value = (rest[0] - 0x30) * 64 + (rest[1] - 0x30) * 8 + (rest[2] - 0x30)
            if value <= 0xFF and (value >= 0x80 or 0x20 <= value <= 0x7E):  # 只还原可显示/UTF-8 高位段
                out.append(value)
            else:  # 控制字符的八进制转义同样保留原样
                out.extend(line[index:index + 4])
            index += 4
            continue
        out.append(0x5C)  # 未知转义：保留反斜杠，后续字符按普通字节处理
        index += 1
    return bytes(out)


def _control_value(byte: int) -> int:
    """控制记法值：^A→1 … ^Z→26、^?→0x7F、^@→0。"""
    if byte == 0x3F:  # '?'
        return 0x7F
    return byte & 0x1F


def parse_relay_line(raw: str, previous: dict[str, object] | None) -> dict[str, object] | None:
    """解析一行 syslog_relay 文本；不匹配/短行视为上一条的续行（堆栈），空行丢弃。"""
    if not raw.strip():
        return None
    match = RELAY_LINE.match(raw)
    if match:
        return {
            "time": match.group("ts"),
            "pid": int(match.group("pid")),
            "tid": 0,  # 经典 syslog_relay 无线程信息
            "level": RELAY_LEVELS.get(match.group("level") or "", "I"),
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


def extract_sim_json_objects(buf: bytes) -> tuple[list[dict[str, object]], bytes]:
    """从字节流提取顶层 JSON 对象，返回 (对象列表, 未完结残余)。

    深度计数 + 字符串感知：花括号出现在字符串内不参与计数，`},{` 对抗样本不串条目；
    对象外的引号/杂讯直接丢弃，残余从未闭合对象的 `{` 起保留。
    """
    objects: list[dict[str, object]] = []
    depth = 0
    in_string = False
    escaped = False
    start: int | None = None
    for index, byte in enumerate(buf):
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:  # '\\'
                escaped = True
            elif byte == 0x22:  # '"'
                in_string = False
            continue
        if byte == 0x22 and depth > 0:
            in_string = True
            continue
        if byte == 0x7B:  # '{'
            if depth == 0:
                start = index
            depth += 1
        elif byte == 0x7D:  # '}'
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        obj = json.loads(buf[start:index + 1].decode("utf-8", "replace"))
                    except ValueError:
                        obj = None
                    if isinstance(obj, dict):
                        objects.append(obj)
                    start = None
    if start is None or depth == 0:
        return objects, b""
    return objects, buf[start:]


def sim_event_entry(event: object) -> dict[str, object] | None:
    """模拟器 log stream JSON 事件 → 同构条目；非 logEvent 丢弃。"""
    if not isinstance(event, dict) or event.get("eventType") != "logEvent":
        return None
    image_path = event.get("processImagePath")
    tag = str(image_path).rsplit("/", 1)[-1] if isinstance(image_path, str) else ""
    pid = event.get("processID")
    tid = event.get("threadID")
    return {
        "time": str(event.get("timestamp") or ""),
        "pid": pid if isinstance(pid, int) and not isinstance(pid, bool) else 0,
        "tid": tid if isinstance(tid, int) and not isinstance(tid, bool) else 0,
        "level": SIM_LEVELS.get(str(event.get("messageType") or ""), "I"),
        "tag": tag[:120],
        "message": str(event.get("eventMessage") or "")[:MAX_MESSAGE_CHARS],
        "continuation": False,
    }


class SyslogRelayClient:
    """真机 syslog_relay 客户端：lockdown 握手 → usbmux 隧道 → 解码行流。"""

    def __init__(self, usbmux: UsbmuxClient, *, timeout: float = STREAM_TIMEOUT) -> None:
        self.usbmux = usbmux
        self.lockdown = LockdownClient(usbmux)
        self.timeout = timeout

    def stream(self, udid: str) -> RelayStream:
        """打开 syslog_relay 隧道并返回可迭代行流；握手失败当场抛 CoreError。"""
        sock = self.lockdown.open_service_stream(udid, SYSLOG_SERVICE)
        return RelayStream(sock, self.timeout)


class RelayStream(Iterator[str]):
    """syslog_relay 行流：按 `\n\x00` 分行后做 vis 解码 + UTF-8 容错。

    close() 供 clear() 从其他线程打断阻塞中的 recv（先 shutdown 再 close）。
    """

    def __init__(self, sock: socket.socket, timeout: float) -> None:
        self.sock = sock
        self._buffer = b""
        try:
            sock.settimeout(timeout)
        except OSError:
            pass

    def __iter__(self) -> Iterator[str]:
        return self

    def __next__(self) -> str:
        while True:
            index = self._buffer.find(b"\n\x00")
            if index >= 0:
                raw = self._buffer[:index]
                self._buffer = self._buffer[index + 2:]
                return decode_vis(raw).decode("utf-8", "replace")
            if len(self._buffer) > MAX_PENDING_BYTES:
                self._buffer = b""  # 行迟迟不终结：丢弃残余防内存膨胀
            try:
                chunk = self.sock.recv(65536)
            except TimeoutError:
                continue  # 日志空闲期不视为断流
            except OSError as error:
                raise CoreError("LOOKIN_UNAVAILABLE", f"syslog 流中断：{error}", retryable=True) from error
            if not chunk:
                raise CoreError("LOOKIN_UNAVAILABLE", "syslog 流已结束。", retryable=True)
            self._buffer += chunk

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)  # 打断可能阻塞中的 recv
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class SimLogStream(Iterator[dict[str, object]]):
    """模拟器 log stream JSON 事件流；close() 终止子进程，供 clear() 从其他线程打断。"""

    def __init__(self, process: subprocess.Popen) -> None:
        self.process = process
        self._buffer = b""
        self._pending: deque[dict[str, object]] = deque()

    def __iter__(self) -> Iterator[dict[str, object]]:
        return self

    def __next__(self) -> dict[str, object]:
        while not self._pending:
            if self.process.stdout is None:  # pragma: no cover —— log_stream 恒带 stdout=PIPE
                raise CoreError("LOOKIN_UNAVAILABLE", "模拟器日志流缺少 stdout。")
            chunk = self.process.stdout.read1(65536)
            if not chunk:
                raise StopIteration  # 子进程退出 = 断流（正常结束，不算错误）
            self._buffer += chunk
            objects, self._buffer = extract_sim_json_objects(self._buffer)
            if len(self._buffer) > MAX_PENDING_BYTES:
                self._buffer = b""  # 对象迟迟不闭合：丢弃残余防内存膨胀（与 RelayStream 对称）
            self._pending.extend(objects)
        return self._pending.popleft()

    def close(self) -> None:
        terminate_process(self.process)


class SyslogHub:
    """iOS 双端日志 Hub：每设备一条持续流读取线程（懒启动、断流自愈、环形缓冲）。

    read/clear 返回形状与 LogcatHub 一致；区别是这里没有「事后 dump」：
    线程把流内容持续搬进环形缓冲，read 只做游标切片；clear 重置游标与缓冲并重连流。
    """

    def __init__(self, relay: SyslogRelayClient, simctl: object, max_buffer: int = MAX_BUFFER) -> None:
        self.relay = relay
        self.simctl = simctl
        self.max_buffer = max_buffer
        self._lock = threading.RLock()
        self._states: dict[str, dict[str, object]] = {}

    def read(self, device_id: str, serial: str, *, after: int | None = None, limit: int = 500) -> dict[str, object]:
        limit = max(1, min(int(limit), MAX_LIMIT))
        self._ensure_reader(device_id, serial)
        with self._lock:
            state = self._state(device_id)
            cursor = int(state["cursor"])
            entries: deque = state["entries"]
            # 客户端游标比 Core 还新只可能是清空过显示，让它重置本地缓冲
            reset = after is not None and after > cursor
            if after is None or reset:
                selected = list(entries)[-limit:]
            else:
                selected = [entry for entry in entries if int(entry["seq"]) > after][:limit]
            dropped = bool(state["dropped"])
            state["dropped"] = False  # 边沿触发：每次读只提示一次丢日志
            return {
                "deviceId": device_id,
                "lines": [dict(entry) for entry in selected],
                "cursor": cursor,
                "dropped": dropped,
                "reset": reset,
                "buffered": len(entries),
            }

    def clear(self, device_id: str, serial: str) -> dict[str, object]:
        """本地缓冲重置 + 流重连：不触碰设备状态（iOS 恒只读）。"""
        with self._lock:
            state = self._state(device_id)
            state["entries"].clear()
            state["cursor"] = 0
            state["dropped"] = False
            state["generation"] = int(state["generation"]) + 1  # 读取线程检测到代际变化后重开流
            closer = state["stream"]
        if closer is not None:
            try:
                closer()  # 关闭当前流（socket/子进程），打断阻塞中的读取
            except Exception:  # noqa: BLE001 —— clear 不因流清理失败而失败
                pass
        return {"deviceId": device_id, "cleared": True, "cursor": 0}

    # ---------- 读取线程 ----------

    def _state(self, device_id: str) -> dict[str, object]:
        state = self._states.get(device_id)
        if state is None:
            state = {
                "cursor": 0,
                "entries": deque(maxlen=self.max_buffer),
                "dropped": False,
                "generation": 0,
                "thread": None,
                "stream": None,
            }
            self._states[device_id] = state
        return state

    def _generation(self, device_id: str) -> int:
        with self._lock:
            return int(self._state(device_id)["generation"])

    def _ensure_reader(self, device_id: str, serial: str) -> None:
        """线程不在场时同步拉起：开流失败当场抛给调用方（未配对/多台模拟器等）。"""
        with self._lock:
            thread = self._state(device_id)["thread"]
            alive = thread is not None and thread.is_alive()
        if alive:
            return
        # 开流不持锁：TLS 握手与 simctl 子进程可能耗时，别堵其他设备的 read
        iterator, closer, generation = self._open_stream(device_id, serial)
        with self._lock:
            state = self._state(device_id)
            thread = state["thread"]
            if thread is not None and thread.is_alive():
                closer()  # 并发拉起竞态：另一个线程已就位，关掉多余的流
                return
            state["stream"] = closer
            thread = threading.Thread(
                target=self._pump,
                args=(device_id, serial, iterator, closer, generation),
                daemon=True,
                name=f"layoutsee-syslog-{device_id}",
            )
            state["thread"] = thread
            thread.start()

    def _open_stream(self, device_id: str, serial: str) -> tuple[object, Callable[[], None], int]:
        with self._lock:
            generation = int(self._state(device_id)["generation"])
        if serial.startswith(SIMULATOR_PREFIX):
            # 模拟器 serial 是 simulator:端口，无法反查 UDID：约定 booted 恰好一台（doc 边界）
            udids = self.simctl.booted_udids()
            if len(udids) > 1:
                raise CoreError(
                    "CORE_UNAVAILABLE",
                    f"检测到 {len(udids)} 台 booted 模拟器，无法定位日志流设备，请仅保留一台。",
                    details={"booted": len(udids)},
                )
            if not udids:
                raise CoreError("CORE_UNAVAILABLE", "没有 booted 的 iOS 模拟器，无法读取日志。")
            stream = SimLogStream(self.simctl.log_stream(udids[0]))
            return stream, stream.close, generation
        stream = self.relay.stream(serial)
        return stream, stream.close, generation

    def _pump(self, device_id: str, serial: str, iterator: object, closer: Callable[[], None], generation: int) -> None:
        simulator = serial.startswith(SIMULATOR_PREFIX)
        while True:
            interrupted = False
            try:
                for item in iterator:
                    if self._generation(device_id) != generation:
                        interrupted = True  # clear() 要求重连
                        break
                    self._store(device_id, simulator, item)
            except CoreError as error:
                if self._generation(device_id) != generation:
                    interrupted = True  # clear() 主动关流引发的异常，不算断流
                else:
                    return  # 断流：线程退出，错误经下一次 _ensure_reader 重开失败暴露给调用方
            except Exception as error:  # noqa: BLE001 —— 读取线程兜底，异常同样按断流处理
                if self._generation(device_id) != generation:
                    interrupted = True
                else:
                    return
            finally:
                try:
                    closer()
                except Exception:  # noqa: BLE001 —— 清理失败不影响主流程
                    pass
            if not interrupted:
                return  # 正常断流（EOF/异常）：线程退出，下一次 read 重新拉起（自愈）
            # clear() 触发的重连：重开流继续泵
            try:
                iterator, closer, generation = self._open_stream(device_id, serial)
            except CoreError:
                return
            with self._lock:
                self._state(device_id)["stream"] = closer

    def _store(self, device_id: str, simulator: bool, item: object) -> None:
        with self._lock:
            state = self._state(device_id)
            entries: deque = state["entries"]
            if simulator:
                entry = sim_event_entry(item)
            else:
                entry = parse_relay_line(str(item), entries[-1] if entries else None)
            if entry is None:
                return
            if len(entries) == entries.maxlen:
                state["dropped"] = True  # 环形缓冲滚过：消费不及时的条目被挤出
            state["cursor"] = int(state["cursor"]) + 1
            entry["seq"] = int(state["cursor"])
            entries.append(entry)


def terminate_process(process: subprocess.Popen) -> None:
    """终止模拟器日志进程树（killpg 覆盖 xcrun→simctl→log 链；幂等）。"""
    if process.poll() is None:
        _signal_group(process, signal.SIGTERM)
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            _signal_group(process, signal.SIGKILL)
            try:
                process.wait(timeout=1.0)
            except subprocess.SubprocessError:
                pass
        except subprocess.SubprocessError:
            pass
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass


def _signal_group(process: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(os.getpgid(process.pid), sig)
    except OSError:
        try:
            process.send_signal(sig)
        except OSError:
            pass
