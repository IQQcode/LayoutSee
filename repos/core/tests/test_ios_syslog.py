"""iOS syslog 链路单测：vis 解码、真机行解析、模拟器 JSON 提取、SyslogHub 游标语义与 lockdown 握手。

全部零硬件依赖：socket 行为用脚本化替身（对齐 test_ios_capture.py 的 socket_factory 注入思路），
子进程用 duck-typing Popen 替身。
"""

from __future__ import annotations

import json
import plistlib
import struct
import subprocess
import threading
import time
import unittest
from collections.abc import Callable
from threading import Event

from layoutsee_core.errors import CoreError
from layoutsee_core.ios.lockdown import LockdownClient, wrap_tls
from layoutsee_core.ios.simctl import SimctlClient
from layoutsee_core.ios.syslog import (
    MAX_LIMIT,
    SyslogHub,
    decode_vis,
    extract_sim_json_objects,
    parse_relay_line,
    sim_event_entry,
)
from layoutsee_core.ios.usbmux import (
    MESSAGE_PLIST,
    USBMUX_HEADER,
    USBMUX_VERSION,
    UsbmuxClient,
    swap_port,
)

UDID = "00008101-000A1111222233334444"
SIM_UDID = "3249070E-B6EE-48BC-9674-E3C93E1C91CB"


def relay_line(index: int, level: str = "Notice") -> str:
    return f"Nov  1 00:07:{index:02d} iPhone LookinDemo[1234] <{level}>: msg{index}"


def _read_until(hub: SyslogHub, device_id: str, serial: str, predicate: Callable[[dict], bool], timeout: float = 5.0) -> dict:
    """轮询读取直到谓词成立（读取线程异步入库），超时返回最后一次结果供断言展示差异。"""
    payload: dict = {}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = hub.read(device_id, serial)
        if predicate(payload):
            return payload
        time.sleep(0.01)
    return payload


# ---------- vis 解码 ----------


class DecodeVisTest(unittest.TestCase):
    def test_restores_meta_escapes_to_utf8_chinese(self) -> None:
        # 你好 = E4 BD A0 E5 A5 BD → \M-d \M-= \M-（meta 空格） \M-e \M-% \M-=
        self.assertEqual(decode_vis(b"\\M-d\\M-=\\M- \\M-e\\M-%\\M-="), "你好".encode("utf-8"))

    def test_restores_meta_control_escape(self) -> None:
        self.assertEqual(decode_vis(b"\\M-^C"), b"\x83")
        self.assertEqual(decode_vis(b"\\M-^?"), b"\xff")

    def test_keeps_control_escape_literal(self) -> None:
        self.assertEqual(decode_vis(b"a\\^Ab"), b"a\\^Ab")

    def test_restores_backslash_escape(self) -> None:
        self.assertEqual(decode_vis(b"x\\\\y"), b"x\\y")

    def test_restores_octal_high_and_printable_keeps_control(self) -> None:
        # 一 = E4 B8 A0
        self.assertEqual(decode_vis(b"\\344\\270\\200"), "一".encode("utf-8"))
        self.assertEqual(decode_vis(b"\\101\\102"), b"AB")  # 可显示段还原
        self.assertEqual(decode_vis(b"a\\001b"), b"a\\001b")  # 控制段保留原样

    def test_octal_beyond_one_byte_keeps_literal(self) -> None:
        # \777 = 0x1FF 超出字节范围：保留原样，不抛 ValueError（对抗样本回归）
        self.assertEqual(decode_vis(b"a\\777b"), b"a\\777b")

    def test_truncated_meta_escape_keeps_literal(self) -> None:
        self.assertEqual(decode_vis(b"tail\\M-"), b"tail\\M-")

    def test_mixed_ascii_and_chinese(self) -> None:
        # 第二个空格是普通字节：meta 空格（\M- ）占用第一个空格还原 0xA0
        self.assertEqual(decode_vis(b"id=\\M-d\\M-=\\M-  end"), "id=你 end".encode("utf-8"))


# ---------- 真机行解析 ----------


class ParseRelayLineTest(unittest.TestCase):
    def test_parses_standard_line(self) -> None:
        entry = parse_relay_line("Nov  1 00:07:32 iPhone LookinDemo[1234] <Notice>: 你好", None)
        self.assertEqual(entry["time"], "Nov  1 00:07:32")
        self.assertEqual(entry["tag"], "LookinDemo")
        self.assertEqual(entry["pid"], 1234)
        self.assertEqual(entry["tid"], 0)
        self.assertEqual(entry["level"], "I")
        self.assertEqual(entry["message"], "你好")
        self.assertFalse(entry["continuation"])

    def test_maps_known_levels(self) -> None:
        cases = {"Notice": "I", "Info": "I", "Warning": "W", "Error": "E", "Debug": "D"}
        for marker, level in cases.items():
            entry = parse_relay_line(relay_line(1, marker), None)
            self.assertEqual(entry["level"], level, marker)

    def test_unknown_level_maps_to_info(self) -> None:
        entry = parse_relay_line("Nov  1 00:07:32 iPhone LookinDemo[1234] <Critical>: boom", None)
        self.assertEqual(entry["level"], "I")

    def test_image_suffix_is_not_tag(self) -> None:
        entry = parse_relay_line("Jun  4 14:30:41 Dphone-2 com.apple.xpc.launchd[1] (com.apple.imf) <Error>: boom", None)
        self.assertEqual(entry["tag"], "com.apple.xpc.launchd")
        self.assertEqual(entry["pid"], 1)
        self.assertEqual(entry["level"], "E")

    def test_stack_trace_becomes_continuation(self) -> None:
        previous = parse_relay_line("Nov  1 00:07:32 iPhone LookinDemo[1234] <Error>: crash", None)
        entry = parse_relay_line("    at com.foo.Bar(Foo.m:12)", previous)
        self.assertTrue(entry["continuation"])
        self.assertEqual(entry["tag"], "LookinDemo")
        self.assertEqual(entry["pid"], 1234)
        self.assertEqual(entry["level"], "E")
        self.assertEqual(entry["message"], "at com.foo.Bar(Foo.m:12)")

    def test_unmatched_line_without_previous_is_dropped(self) -> None:
        self.assertIsNone(parse_relay_line("    at com.foo.Bar(Foo.m:12)", None))

    def test_blank_line_is_dropped(self) -> None:
        self.assertIsNone(parse_relay_line("   ", None))


# ---------- 模拟器 JSON 提取 ----------


class ExtractSimJsonTest(unittest.TestCase):
    def test_braces_inside_strings_do_not_break_objects(self) -> None:
        first = {"eventMessage": "x }, { y"}
        second = {"eventMessage": "{brace} }"}
        blob = json.dumps(first).encode("utf-8") + b"\n" + json.dumps(second).encode("utf-8") + b"\n"
        objects, residual = extract_sim_json_objects(blob)
        self.assertEqual(objects, [first, second])
        self.assertEqual(residual, b"")

    def test_incomplete_object_is_residual(self) -> None:
        objects, residual = extract_sim_json_objects(b'{"a": 1} {"b": ')
        self.assertEqual(objects, [{"a": 1}])
        self.assertEqual(residual, b'{"b": ')

    def test_prefix_junk_is_dropped(self) -> None:
        objects, residual = extract_sim_json_objects(b'noise {"a": 1}')
        self.assertEqual(objects, [{"a": 1}])
        self.assertEqual(residual, b"")

    def test_escaped_quotes_inside_strings(self) -> None:
        # 字符串内的 \" 不应闭合字符串（深度计数需字符串感知）
        first = {"eventMessage": 'he said "hi }" and left'}
        blob = json.dumps(first).encode("utf-8") + b"\n"
        objects, residual = extract_sim_json_objects(blob)
        self.assertEqual(objects, [first])
        self.assertEqual(residual, b"")


class SimEventEntryTest(unittest.TestCase):
    def _event(self, event_type: str = "logEvent", message_type: str = "Default", message: str = "hello") -> dict:
        return {
            "eventType": event_type,
            "messageType": message_type,
            "processImagePath": "/usr/libexec/lsd",
            "processID": 53962,
            "threadID": 775,
            "timestamp": "2026-11-01 00:07:32.123456+0800",
            "eventMessage": message,
        }

    def test_maps_level_and_fields(self) -> None:
        cases = {"Default": "I", "Info": "I", "Debug": "D", "Error": "E", "Fault": "F"}
        for message_type, level in cases.items():
            entry = sim_event_entry(self._event(message_type=message_type))
            self.assertEqual(entry["level"], level, message_type)
        entry = sim_event_entry(self._event())
        self.assertEqual(entry["tag"], "lsd")
        self.assertEqual(entry["pid"], 53962)
        self.assertEqual(entry["tid"], 775)
        self.assertFalse(entry["continuation"])

    def test_unknown_message_type_maps_to_info(self) -> None:
        entry = sim_event_entry(self._event(message_type="Whatever"))
        self.assertEqual(entry["level"], "I")

    def test_non_log_event_is_filtered(self) -> None:
        self.assertIsNone(sim_event_entry(self._event(event_type="activityCreateEvent")))
        self.assertIsNone(sim_event_entry("not-a-dict"))


# ---------- 测试替身 ----------


class ScriptedSocket:
    """按脚本回放的 socket 替身：sendall 记录数据，recv 按序吐出响应分片。"""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.sent = b""
        self.closed = False

    def settimeout(self, value: float) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, size: int) -> bytes:
        if not self._chunks:
            raise OSError("脚本响应已耗尽")
        return self._chunks.pop(0)

    def close(self) -> None:
        self.closed = True


class ScriptedSocketFactory:
    """按序回放脚本 socket（usbmux 枚举/隧道与 ReadPairRecord 共用一条注入链）。"""

    def __init__(self, sockets: list[ScriptedSocket]) -> None:
        self.sockets = list(sockets)

    def __call__(self) -> ScriptedSocket:
        if not self.sockets:
            raise OSError("脚本 socket 已耗尽")
        return self.sockets.pop(0)


def usbmux_plist_response(payload: dict) -> list[bytes]:
    body = plistlib.dumps(payload, fmt=plistlib.FMT_BINARY)
    return [USBMUX_HEADER.pack(USBMUX_HEADER.size + len(body), USBMUX_VERSION, MESSAGE_PLIST, 1), body]


def lockdown_response(payload: dict) -> list[bytes]:
    body = plistlib.dumps(payload, fmt=plistlib.FMT_BINARY)
    return [struct.pack(">I", len(body)), body]


def list_devices_response(udid: str) -> list[bytes]:
    return usbmux_plist_response({
        "MessageType": "ListDevices",
        "DeviceList": [{"DeviceID": 7, "Properties": {"SerialNumber": udid}}],
    })


def _lockdown_requests(sent: bytes) -> list[dict]:
    requests: list[dict] = []
    offset = 0
    while offset < len(sent):
        (length,) = struct.unpack_from(">I", sent, offset)
        requests.append(plistlib.loads(sent[offset + 4:offset + 4 + length]))
        offset += 4 + length
    return requests


def _connect_request(sent: bytes) -> dict:
    length, _version, message, _tag = USBMUX_HEADER.unpack_from(sent, 0)
    assert message == MESSAGE_PLIST
    return plistlib.loads(sent[USBMUX_HEADER.size:length])


def handshake_sockets(service_response: dict) -> tuple[list[ScriptedSocket], ScriptedSocket]:
    """构造一次完整握手所需的三条 socket：枚举、lockdown 隧道、配对记录。"""
    list_sock = ScriptedSocket(list_devices_response(UDID))
    lockdown_sock = ScriptedSocket(
        usbmux_plist_response({"MessageType": "Result", "Number": 0})
        + lockdown_response({"Request": "QueryType", "Type": "com.apple.mobile.lockdown"})
        + lockdown_response({
            "Request": "StartSession",
            "SessionID": 1,
            "EnableSessionSSL": False,
            "EnableSessionBypass": True,
        })
        + lockdown_response(service_response)
    )
    pair_sock = ScriptedSocket(usbmux_plist_response({
        "MessageType": "Result",
        "Number": 0,
        "PairRecordData": plistlib.dumps(
            {"HostID": UDID, "HostCertificate": b"cert-bytes", "HostPrivateKey": b"key-bytes"},
            fmt=plistlib.FMT_BINARY,
        ),
    }))
    return [list_sock, lockdown_sock, pair_sock], lockdown_sock


def build_lockdown(service_response: dict, *extra: ScriptedSocket) -> tuple[LockdownClient, ScriptedSocket]:
    sockets, lockdown_sock = handshake_sockets(service_response)
    factory = ScriptedSocketFactory([*sockets, *extra])
    usbmux = UsbmuxClient(socket_factory=factory)
    return LockdownClient(usbmux, socket_factory=factory), lockdown_sock


# ---------- lockdown 握手 ----------


class LockdownHandshakeTest(unittest.TestCase):
    def test_start_service_returns_port_and_sends_expected_sequence(self) -> None:
        client, lockdown_sock = build_lockdown({
            "Request": "StartService",
            "Service": "com.apple.syslog_relay",
            "Port": 45678,
            "EnableServiceSSL": False,
        })
        self.assertEqual(client.start_service(UDID, "com.apple.syslog_relay"), 45678)
        # 隧道请求连到 lockdown 端口（usbmux 大端 u16）
        connect_request = _connect_request(lockdown_sock.sent)
        self.assertEqual(connect_request["MessageType"], "Connect")
        self.assertEqual(connect_request["PortNumber"], swap_port(62078))
        # lockdown 请求序列：QueryType → StartSession(HostID) → StartService
        requests = _lockdown_requests(lockdown_sock.sent[USBMUX_HEADER.unpack_from(lockdown_sock.sent, 0)[0]:])
        self.assertEqual([item["Request"] for item in requests], ["QueryType", "StartSession", "StartService"])
        self.assertEqual(requests[1]["HostID"], UDID)
        self.assertEqual(requests[2]["Service"], "com.apple.syslog_relay")

    def test_read_pair_record_sends_expected_request(self) -> None:
        record = plistlib.dumps({"HostID": UDID, "HostCertificate": b"cert-bytes", "HostPrivateKey": b"key-bytes"}, fmt=plistlib.FMT_BINARY)
        pair_sock = ScriptedSocket(usbmux_plist_response({
            "MessageType": "Result",
            "Number": 0,
            "PairRecordData": record,
        }))
        client = LockdownClient(UsbmuxClient(socket_factory=ScriptedSocketFactory([pair_sock])), socket_factory=ScriptedSocketFactory([pair_sock]))
        client.read_pair_record(UDID)
        length, _version, message, _tag = USBMUX_HEADER.unpack_from(pair_sock.sent, 0)
        self.assertEqual(message, MESSAGE_PLIST)
        payload = plistlib.loads(pair_sock.sent[USBMUX_HEADER.size:length])
        self.assertEqual(payload["MessageType"], "ReadPairRecord")
        self.assertEqual(payload["PairRecordID"], UDID)

    def test_start_service_rejection_maps_to_lookin_unavailable(self) -> None:
        client, _ = build_lockdown({"Request": "StartService", "Error": "InvalidService"})
        with self.assertRaises(CoreError) as ctx:
            client.start_service(UDID, "com.apple.syslog_relay")
        self.assertEqual(ctx.exception.code, "LOOKIN_UNAVAILABLE")

    def test_missing_pair_record_mentions_pairing_hint(self) -> None:
        list_sock = ScriptedSocket(list_devices_response(UDID))
        lockdown_sock = ScriptedSocket(
            usbmux_plist_response({"MessageType": "Result", "Number": 0})
            + lockdown_response({"Request": "QueryType", "Type": "com.apple.mobile.lockdown"})
        )
        pair_sock = ScriptedSocket(usbmux_plist_response({"MessageType": "Result", "Number": 4}))
        factory = ScriptedSocketFactory([list_sock, lockdown_sock, pair_sock])
        client = LockdownClient(UsbmuxClient(socket_factory=factory), socket_factory=factory)
        with self.assertRaises(CoreError) as ctx:
            client.start_service(UDID, "com.apple.syslog_relay")
        self.assertEqual(ctx.exception.code, "LOOKIN_UNAVAILABLE")
        self.assertIn("请先用 Xcode/Finder 配对设备", str(ctx.exception))

    def test_query_type_mismatch_is_rejected(self) -> None:
        list_sock = ScriptedSocket(list_devices_response(UDID))
        lockdown_sock = ScriptedSocket(
            usbmux_plist_response({"MessageType": "Result", "Number": 0})
            + lockdown_response({"Request": "QueryType", "Type": "com.apple.mobile.something-else"})
        )
        pair_sock = ScriptedSocket(usbmux_plist_response({"MessageType": "Result", "Number": 4}))
        factory = ScriptedSocketFactory([list_sock, lockdown_sock, pair_sock])
        client = LockdownClient(UsbmuxClient(socket_factory=factory), socket_factory=factory)
        with self.assertRaises(CoreError) as ctx:
            client.start_service(UDID, "com.apple.syslog_relay")
        self.assertEqual(ctx.exception.code, "LOOKIN_UNAVAILABLE")

    def test_open_service_stream_connects_to_returned_port(self) -> None:
        service_sock = ScriptedSocket(usbmux_plist_response({"MessageType": "Result", "Number": 0}))
        client, _ = build_lockdown(
            {"Request": "StartService", "Service": "com.apple.syslog_relay", "Port": 45678, "EnableServiceSSL": False},
            ScriptedSocket(list_devices_response(UDID)),  # 服务隧道的第二次枚举
            service_sock,
        )
        stream = client.open_service_stream(UDID, "com.apple.syslog_relay")
        self.assertIs(stream, service_sock)
        request = _connect_request(service_sock.sent)
        self.assertEqual(request["PortNumber"], swap_port(45678))

    def test_wrap_tls_with_garbage_pair_raises_lookin_unavailable(self) -> None:
        # 垃圾证书/私钥无法加载：映射 LOOKIN_UNAVAILABLE（临时 PEM 文件在 finally 内清理）
        with self.assertRaises(CoreError) as ctx:
            wrap_tls(ScriptedSocket([]), {"HostCertificate": b"not-a-cert", "HostPrivateKey": b"not-a-key"})
        self.assertEqual(ctx.exception.code, "LOOKIN_UNAVAILABLE")


# ---------- SyslogHub 替身 ----------


class StubStream:
    """可脚本化的行流替身：迭代完脚本后阻塞，close() 置位事件令下一次迭代报断流。"""

    def __init__(self, lines: list[str]) -> None:
        self.lines = list(lines)
        self.closed = Event()
        self.close_count = 0

    def __iter__(self) -> StubStream:
        return self

    def __next__(self) -> str:
        if self.lines:
            return self.lines.pop(0)
        self.closed.wait(5)  # 模拟空闲阻塞，等 clear()/测试收尾
        raise CoreError("LOOKIN_UNAVAILABLE", "stub 流已关闭", retryable=True)

    def close(self) -> None:
        self.close_count += 1
        self.closed.set()


class StubRelay:
    """stream(serial) 依次返回脚本化流（超出脚本后复用最后一个）。"""

    def __init__(self, streams: list[Callable[[], StubStream]]) -> None:
        self._streams = list(streams)
        self.calls = 0

    def stream(self, udid: str) -> StubStream:
        self.calls += 1
        index = min(self.calls - 1, len(self._streams) - 1)
        return self._streams[index]()


class FakeStdout:
    def __init__(self, data: bytes, *, block_after_eof: bool = False) -> None:
        self._data = data
        self._position = 0
        self._block_after_eof = block_after_eof
        self._gate = Event()

    @property
    def exhausted(self) -> bool:
        return self._position >= len(self._data)

    def read1(self, size: int = -1) -> bytes:
        if self.exhausted:
            if self._block_after_eof:
                self._gate.wait(5)  # 模拟持续流式输出，等测试收尾
            return b""
        end = len(self._data) if size is None or size < 0 else min(len(self._data), self._position + max(size, 1))
        chunk = self._data[self._position:end]
        self._position = end
        return chunk

    def close(self) -> None:
        pass


class FakePopen:
    """duck-typing Popen：stdout 脚本化，进程控制方法全部安全空转。"""

    def __init__(self, data: bytes, *, block_after_eof: bool = False) -> None:
        self.stdout: FakeStdout = FakeStdout(data, block_after_eof=block_after_eof)
        self.stderr = None
        self.pid = 999999
        self._terminated = False

    def poll(self) -> int | None:
        return 0 if self._terminated or self.stdout.exhausted else None

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def terminate(self) -> None:
        self._terminated = True

    def send_signal(self, sig: int) -> None:
        self._terminated = True

    def kill(self) -> None:
        self._terminated = True


class StubSimctl:
    """spawn 依次消费 payloads（耗尽后复用最后一个）；block_after_eof 模拟持续流式输出。"""

    def __init__(self, udids: list[str], payloads: bytes | list[bytes] = b"", *, block_after_eof: bool = False) -> None:
        self.udids = list(udids)
        self.payloads = [payloads] if isinstance(payloads, bytes) else list(payloads)
        self.block_after_eof = block_after_eof
        self.spawned: list[str] = []

    def booted_udids(self) -> list[str]:
        return list(self.udids)

    def log_stream(self, udid: str) -> FakePopen:
        self.spawned.append(udid)
        index = min(len(self.spawned) - 1, len(self.payloads) - 1)
        return FakePopen(self.payloads[index], block_after_eof=self.block_after_eof)


# ---------- SyslogHub（真机路径） ----------


class SyslogHubRelayTest(unittest.TestCase):
    def test_first_read_returns_existing_lines_then_incremental(self) -> None:
        hub = SyslogHub(StubRelay([lambda: StubStream([relay_line(1), relay_line(2)])]), StubSimctl([]))
        first = _read_until(hub, "ios-x", UDID, lambda p: p["cursor"] == 2)
        self.assertEqual([entry["seq"] for entry in first["lines"]], [1, 2])
        self.assertEqual(first["buffered"], 2)
        self.assertFalse(first["dropped"])
        second = hub.read("ios-x", UDID, after=first["cursor"])
        self.assertEqual(second["lines"], [])
        self.assertEqual(second["cursor"], 2)
        third = hub.read("ios-x", UDID, after=1)
        self.assertEqual([entry["seq"] for entry in third["lines"]], [2])
        stale = hub.read("ios-x", UDID, after=999)
        self.assertTrue(stale["reset"])
        self.assertEqual([entry["seq"] for entry in stale["lines"]], [1, 2])

    def test_limit_caps_selection_and_hard_cap(self) -> None:
        hub = SyslogHub(StubRelay([lambda: StubStream([relay_line(i) for i in range(1, 8)])]), StubSimctl([]))
        payload = _read_until(hub, "ios-x", UDID, lambda p: p["cursor"] == 7)
        trimmed = hub.read("ios-x", UDID, limit=3)
        self.assertEqual([entry["seq"] for entry in trimmed["lines"]], [5, 6, 7])
        over = hub.read("ios-x", UDID, limit=MAX_LIMIT + 500)  # 超上限被收敛，不抛错
        self.assertEqual(len(over["lines"]), 7)

    def test_buffer_rollover_marks_dropped_once(self) -> None:
        hub = SyslogHub(
            StubRelay([lambda: StubStream([relay_line(i) for i in range(1, 6)])]),
            StubSimctl([]),
            max_buffer=3,
        )
        payload = _read_until(hub, "ios-x", UDID, lambda p: p["cursor"] == 5)
        self.assertEqual(payload["buffered"], 3)
        self.assertTrue(payload["dropped"])
        again = hub.read("ios-x", UDID, after=payload["cursor"])
        self.assertFalse(again["dropped"])
        self.assertEqual(again["lines"], [])

    def test_clear_resets_cursor_and_reconnects_stream(self) -> None:
        first = StubStream([relay_line(1), relay_line(2)])
        second = StubStream([relay_line(3)])
        relay = StubRelay([lambda: first, lambda: second])
        hub = SyslogHub(relay, StubSimctl([]))
        payload = _read_until(hub, "ios-x", UDID, lambda p: p["cursor"] == 2)
        self.assertEqual(payload["cursor"], 2)
        result = hub.clear("ios-x", UDID)
        self.assertEqual(result, {"deviceId": "ios-x", "cleared": True, "cursor": 0})
        self.assertGreaterEqual(first.close_count, 1)
        after = _read_until(hub, "ios-x", UDID, lambda p: p["cursor"] == 1 and p["buffered"] == 1)
        self.assertEqual([entry["seq"] for entry in after["lines"]], [1])
        self.assertEqual(after["lines"][0]["message"], "msg3")
        self.assertEqual(relay.calls, 2)


# ---------- SyslogHub（模拟器路径） ----------


def sim_event(event_type: str = "logEvent", message_type: str = "Default", message: str = "hello", pid: int = 53962) -> dict:
    return {
        "eventType": event_type,
        "messageType": message_type,
        "processImagePath": "/usr/libexec/lsd",
        "processID": pid,
        "threadID": 775,
        "timestamp": "2026-11-01 00:07:32.123456+0800",
        "eventMessage": message,
    }


def sim_payload() -> bytes:
    events = [
        sim_event(message="x }, { y { brace } 你好"),
        sim_event(event_type="activityCreateEvent", message="should be filtered"),
        sim_event(message_type="Error", message="boom"),
        sim_event(message_type="Debug", message="dbg"),
        sim_event(message_type="Fault", message="fatal"),
    ]
    return b"".join(json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n" for event in events)


class SyslogHubSimulatorTest(unittest.TestCase):
    def test_simulator_stream_maps_entries_and_filters(self) -> None:
        # block_after_eof：流保持存活，避免「耗尽即自愈重拉」干扰单次映射断言
        simctl = StubSimctl([SIM_UDID], sim_payload(), block_after_eof=True)
        hub = SyslogHub(StubRelay([]), simctl)
        # 5 个事件里 activityCreateEvent 被过滤，落库 4 条
        result = _read_until(hub, "sim-1", "simulator:47199", lambda p: p["cursor"] == 4)
        self.assertEqual(set(simctl.spawned), {SIM_UDID})
        lines = result["lines"]
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0]["tag"], "lsd")
        self.assertEqual(lines[0]["pid"], 53962)
        self.assertEqual(lines[0]["tid"], 775)
        self.assertEqual(lines[0]["level"], "I")
        self.assertEqual(lines[0]["message"], "x }, { y { brace } 你好")
        self.assertEqual([entry["level"] for entry in lines], ["I", "E", "D", "F"])
        self.assertTrue(all(entry["message"] != "should be filtered" for entry in lines))

    def test_multiple_booted_simulators_raise_core_unavailable(self) -> None:
        hub = SyslogHub(StubRelay([]), StubSimctl(["A" * 36, "B" * 36], sim_payload()))
        with self.assertRaises(CoreError) as ctx:
            hub.read("sim-1", "simulator:47199")
        self.assertEqual(ctx.exception.code, "CORE_UNAVAILABLE")

    def test_no_booted_simulator_raises_core_unavailable(self) -> None:
        hub = SyslogHub(StubRelay([]), StubSimctl([], sim_payload()))
        with self.assertRaises(CoreError) as ctx:
            hub.read("sim-1", "simulator:47199")
        self.assertEqual(ctx.exception.code, "CORE_UNAVAILABLE")

    def test_exhausted_stream_self_heals_on_next_read(self) -> None:
        # 两次 spawn 均即时 EOF（模拟器退出场景）：线程退出后下一次 read 重新拉起
        # sim_payload 5 个事件过滤 1 条 activityCreateEvent，每次 spawn 落库 4 条
        simctl = StubSimctl([SIM_UDID], [sim_payload(), sim_payload()])
        hub = SyslogHub(StubRelay([]), simctl)
        _read_until(hub, "sim-1", "simulator:47199", lambda p: p["cursor"] == 4)
        again = _read_until(hub, "sim-1", "simulator:47199", lambda p: p["cursor"] == 8, timeout=8.0)
        self.assertEqual(again["cursor"], 8)


# ---------- SimctlClient.log_stream ----------


class SimctlLogStreamTest(unittest.TestCase):
    def test_invalid_udid_is_rejected_without_spawn(self) -> None:
        client = SimctlClient()
        spawned: list[list[str]] = []

        def fake_popen(argv: list[str], **kwargs: object) -> object:
            spawned.append(argv)
            raise AssertionError("不应启动子进程")

        previous = subprocess.Popen
        subprocess.Popen = fake_popen  # type: ignore[assignment]
        try:
            with self.assertRaises(CoreError) as ctx:
                client.log_stream("bad-udid")
        finally:
            subprocess.Popen = previous  # type: ignore[assignment]
        self.assertEqual(ctx.exception.code, "INVALID_ARGUMENT")
        self.assertEqual(spawned, [])

    def test_log_stream_uses_literal_argv_with_shell_disabled(self) -> None:
        client = SimctlClient()
        captured: dict = {}

        def fake_popen(argv: list[str], **kwargs: object) -> object:
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return object()

        previous = subprocess.Popen
        subprocess.Popen = fake_popen  # type: ignore[assignment]
        try:
            client.log_stream(SIM_UDID)
        finally:
            subprocess.Popen = previous  # type: ignore[assignment]
        self.assertEqual(
            captured["argv"],
            ["/usr/bin/xcrun", "simctl", "spawn", SIM_UDID, "log", "stream", "--style", "json", "--level", "debug"],
        )
        self.assertIs(captured["kwargs"]["shell"], False)
        self.assertIs(captured["kwargs"]["start_new_session"], True)


if __name__ == "__main__":
    unittest.main()
