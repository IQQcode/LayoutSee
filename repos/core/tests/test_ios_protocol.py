"""iOS 协议层单测：PeerTalk 帧 / usbmux plist / NSKeyedArchiver / LookinClient / IOSDeviceDriver。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
全部使用本地替身（socketpair 假 usbmuxd、FakeStream 预录帧序列、手写 bplist 金样 fixture），
不依赖真机与真实 usbmuxd。金样 fixture 由一次性脚本手工构造 keyed-archiver 图后
用 plistlib 落盘（生成与复跑方式见 tests/fixtures/lookin/make_fixture.py）。
"""
from __future__ import annotations

import socket
import struct
import threading
import unittest
import plistlib
from pathlib import Path

from layoutsee_core.errors import CoreError
from layoutsee_core.ios import archiver, client, driver, peertalk, usbmux
from layoutsee_core.snapshots import normalize_nodes

UDID = "00008101-000A2C3E1F29002E"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "lookin" / "response_attachment_hierarchy.plist"
FIXTURE_APPLE = Path(__file__).resolve().parent / "fixtures" / "lookin" / "apple_generated_attachment.bin"


def frame_bytes(frame_type: int, tag: int, payload: bytes) -> bytes:
    return peertalk.PT_HEADER.pack(peertalk.PT_VERSION, frame_type, tag, len(payload)) + bytes(payload)


def response_attachment(
    data: object = None,
    *,
    server_version: int = 7,
    error: object = None,
    total: int | None = None,
    current: int | None = None,
    background: object = None,
) -> bytes:
    """测试用：编码 LookinConnectionResponseAttachment（走通用 keyed-archiver 底座）。"""
    fields: dict[str, object] = {"0": data, "1": 0, "lookinServerVersion": server_version}
    if error is not None:
        fields["error"] = error
    if total is not None:
        fields["dataTotalCount"] = total
    if current is not None:
        fields["currentDataCount"] = current
    # 真实 LookinServer 的 encodeWithCoder 无条件写 appIsInBackground（init 默认 NO），这里对齐
    fields["appIsInBackground"] = bool(background) if background is not None else False
    return archiver.encode_keyed_object(
        fields,
        class_name="LookinConnectionResponseAttachment",
        class_chain=["LookinConnectionResponseAttachment", "NSObject"],
    )


class FakeStream:
    """socket 替身：sendall 收集发送字节，recv 按序回放预录字节；耗尽即 EOF。"""

    def __init__(self, chunks: bytes = b"") -> None:
        self._buffer = bytes(chunks)
        self.sent = bytearray()
        self.timeout: float | None = None

    def settimeout(self, value: float | None) -> None:
        self.timeout = value

    def sendall(self, data: bytes | bytearray) -> None:
        self.sent.extend(data)

    def recv(self, size: int) -> bytes:
        if not self._buffer:
            return b""  # EOF
        chunk = self._buffer[: max(1, size)]
        self._buffer = self._buffer[len(chunk):]
        return chunk

    def close(self) -> None:
        pass


class ByteByByteStream(FakeStream):
    """每次 recv 只回 1 字节，模拟分片到达（短读）。"""

    def recv(self, size: int) -> bytes:
        return super().recv(1)


class PeerTalkTest(unittest.TestCase):
    def test_frame_roundtrip(self) -> None:
        a, b = socket.socketpair()
        try:
            payload = b"\x00\x01" * 1000
            peertalk.write_frame(a, 202, 9, payload)
            self.assertEqual(peertalk.read_frame(b), (202, 9, payload))
        finally:
            a.close()
            b.close()

    def test_read_frame_eof_raises_unavailable(self) -> None:
        with self.assertRaises(CoreError) as context:
            peertalk.read_frame(FakeStream(b""))
        self.assertEqual(context.exception.code, "LOOKIN_UNAVAILABLE")

    def test_read_frame_truncated_payload_raises_unavailable(self) -> None:
        header = peertalk.PT_HEADER.pack(peertalk.PT_VERSION, 200, 1, 100)
        with self.assertRaises(CoreError) as context:
            peertalk.read_frame(FakeStream(header + b"short"))
        self.assertEqual(context.exception.code, "LOOKIN_UNAVAILABLE")

    def test_read_frame_oversize_declared_payload_rejected(self) -> None:
        header = peertalk.PT_HEADER.pack(peertalk.PT_VERSION, 200, 1, peertalk.MAX_PAYLOAD_SIZE + 1)
        with self.assertRaises(CoreError) as context:
            peertalk.read_frame(FakeStream(header))
        self.assertEqual(context.exception.code, "LOOKIN_UNAVAILABLE")

    def test_write_frame_oversize_payload_rejected(self) -> None:
        class HugePayload:
            def __len__(self) -> int:
                return peertalk.MAX_PAYLOAD_SIZE + 1

        stream = FakeStream(b"")
        with self.assertRaises(CoreError) as context:
            peertalk.write_frame(stream, 200, 1, HugePayload())  # type: ignore[arg-type]
        self.assertEqual(context.exception.code, "LOOKIN_UNAVAILABLE")
        self.assertEqual(bytes(stream.sent), b"")

    def test_read_frame_tolerates_short_reads(self) -> None:
        payload = b"abc" * 10
        stream = ByteByByteStream(frame_bytes(200, 3, payload))
        self.assertEqual(peertalk.read_frame(stream), (200, 3, payload))


# ---------------------------------------------------------------------------
# usbmux：socketpair 上的假 usbmuxd（每条连接一个线程按脚本回放）
# ---------------------------------------------------------------------------

def serve_list_devices(server: socket.socket) -> None:
    server.settimeout(3)
    _message, tag, _payload = usbmux.read_message(server)
    response = {
        "MessageType": "ListDevices",
        "DeviceList": [{"DeviceID": 7, "Properties": {"SerialNumber": UDID, "ProductType": "iPhone16,1"}}],
    }
    server.sendall(usbmux.encode_plist_message(response, tag))


def serve_list_devices_empty(server: socket.socket) -> None:
    server.settimeout(3)
    _message, tag, _payload = usbmux.read_message(server)
    server.sendall(usbmux.encode_plist_message({"MessageType": "ListDevices", "DeviceList": []}, tag))


def serve_connect_ok_and_echo(server: socket.socket) -> None:
    """Result 0（plist 形态）后 socket 变裸流：回读一帧 PeerTalk 并原样回显。"""
    server.settimeout(3)
    _message, _tag, _payload = usbmux.read_message(server)
    server.sendall(usbmux.encode_plist_message({"MessageType": "Result", "Number": 0}))
    frame_type, tag, payload = peertalk.read_frame(server)
    peertalk.write_frame(server, frame_type, tag, payload)


def serve_connect_refused(server: socket.socket) -> None:
    """Result 3（4 字节裸形态）。"""
    server.settimeout(3)
    usbmux.read_message(server)
    server.sendall(
        struct.pack("<IIII", 20, usbmux.USBMUX_VERSION, usbmux.MESSAGE_RESULT, 0) + struct.pack("=I", 3)
    )


class FakeUsbmuxd:
    """socketpair 假 usbmuxd：add() 注册一条连接的处理脚本，factory() 按序交付客户端侧。"""

    def __init__(self) -> None:
        self._clients: list[socket.socket] = []

    def add(self, behavior) -> None:
        client_side, server_side = socket.socketpair()
        thread = threading.Thread(target=self._serve, args=(server_side, behavior), daemon=True)
        thread.start()
        self._clients.append(client_side)

    def factory(self) -> socket.socket:
        return self._clients.pop(0)

    @staticmethod
    def _serve(server: socket.socket, behavior) -> None:
        try:
            behavior(server)
        except (OSError, CoreError):
            pass
        finally:
            try:
                server.close()
            except OSError:
                pass


class UsbmuxTest(unittest.TestCase):
    def test_list_devices_parses_udid(self) -> None:
        fake = FakeUsbmuxd()
        fake.add(serve_list_devices)
        devices = usbmux.UsbmuxClient(socket_factory=fake.factory).list_devices()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["udid"], UDID)
        self.assertEqual(devices[0]["deviceId"], 7)
        self.assertEqual(devices[0]["properties"]["ProductType"], "iPhone16,1")

    def test_list_devices_without_usbmuxd_returns_empty(self) -> None:
        client = usbmux.UsbmuxClient(socket_path="/tmp/layoutsee-no-such-usbmuxd.sock")
        self.assertEqual(client.list_devices(), [])
        self.assertFalse(client.available())

    def test_connect_result_zero_returns_raw_stream(self) -> None:
        fake = FakeUsbmuxd()
        fake.add(serve_list_devices)  # DeviceID 解析
        fake.add(serve_connect_ok_and_echo)  # Connect + Result 0 + 裸流回显
        stream = usbmux.UsbmuxClient(socket_factory=fake.factory).connect(UDID, 47175)
        try:
            peertalk.write_frame(stream, 200, 5, b"ping-payload")
            self.assertEqual(peertalk.read_frame(stream), (200, 5, b"ping-payload"))
        finally:
            stream.close()

    def test_connect_refused_raises_app_not_found(self) -> None:
        fake = FakeUsbmuxd()
        fake.add(serve_list_devices)
        fake.add(serve_connect_refused)
        with self.assertRaises(CoreError) as context:
            usbmux.UsbmuxClient(socket_factory=fake.factory).connect(UDID, 47175)
        self.assertEqual(context.exception.code, "LOOKIN_APP_NOT_FOUND")
        self.assertEqual(context.exception.details["result"], 3)

    def test_connect_unknown_device_raises_device_not_found(self) -> None:
        fake = FakeUsbmuxd()
        fake.add(serve_list_devices_empty)
        with self.assertRaises(CoreError) as context:
            usbmux.UsbmuxClient(socket_factory=fake.factory).connect("OTHER-UDID", 47175)
        self.assertEqual(context.exception.code, "IOS_DEVICE_NOT_FOUND")

    def test_parse_result_supports_both_forms(self) -> None:
        plist_message = usbmux.encode_plist_message({"MessageType": "Result", "Number": 0})
        plist_payload = plist_message[usbmux.USBMUX_HEADER.size:]
        self.assertEqual(usbmux.parse_result(usbmux.MESSAGE_PLIST, plist_payload), 0)
        self.assertEqual(usbmux.parse_result(usbmux.MESSAGE_RESULT, struct.pack("=I", 3)), 3)

    def test_swap_port_is_big_endian_u16(self) -> None:
        # 47175=0xB847；((port & 0xFF) << 8) | (port >> 8) 字节交换后为 0x47B8（大端 u16 形态）
        self.assertEqual(usbmux.swap_port(47175), 0x47B8)
        self.assertEqual(usbmux.swap_port(0x00FF), 0xFF00)
        with self.assertRaises(ValueError):
            usbmux.swap_port(70000)


class ArchiverTest(unittest.TestCase):
    def test_encode_scalar_fields_are_inline_like_apple(self) -> None:
        """Apple 的 encodeInteger/encodeBool 把标量内联进实例 dict；UID 引用形态会被 Foundation
        的 decodeIntegerForKey: 拒绝（2026-10-25 真机 LookinServer 崩溃根因），必须防回归。"""
        payload = archiver.encode_attachment(None, 0)
        container = plistlib.loads(payload)
        instance = container["$objects"][container["$top"]["root"].data]
        self.assertIsInstance(instance["1"], int)  # 内联整数，而非 UID 引用
        self.assertEqual(instance["1"], 0)
        self.assertIsInstance(instance["0"], plistlib.UID)  # data=None 仍是 $null 引用

    def test_decode_apple_generated_fixture(self) -> None:
        """自研解码器必须能解 Apple NSKeyedArchiver 生成的样本（Swift 生成，结构同请求附件）。"""
        root, warnings = archiver.unarchive(FIXTURE_APPLE.read_bytes())
        self.assertEqual(warnings, [])
        self.assertEqual(root["1"], 0)
        self.assertIsNone(root["0"])
        self.assertEqual(root["_classes"], ["gen_lookin.Att", "NSObject"])

    def test_encode_decode_roundtrip_nested(self) -> None:
        data = {"a": "中文文本", "b": 7, "c": b"\x00\x01\xfe", "d": None, "e": [1, "x", True], "f": {"g": 1.5}}
        root, warnings = archiver.unarchive(archiver.encode_attachment(data, data_type=0))
        self.assertEqual(warnings, [])
        self.assertEqual(root["_classes"], ["LookinConnectionAttachment", "NSObject"])
        self.assertEqual(root["1"], 0)
        inner = root["0"]
        self.assertEqual(inner["a"], "中文文本")
        self.assertEqual(inner["b"], 7)
        self.assertEqual(inner["c"], b"\x00\x01\xfe")
        self.assertIsNone(inner["d"])
        self.assertEqual(inner["e"], [1, "x", True])
        self.assertEqual(inner["f"], {"g": 1.5})

    def test_decode_golden_fixture(self) -> None:
        root, warnings = archiver.unarchive(FIXTURE.read_bytes())
        self.assertEqual(warnings, [])
        self.assertEqual(root["lookinServerVersion"], 7)
        self.assertIsNone(root["error"])
        self.assertIs(root["appIsInBackground"], False)
        self.assertEqual(root["dataTotalCount"], 1)
        self.assertEqual(root["currentDataCount"], 1)
        self.assertEqual(root["_classes"][0], "LookinConnectionResponseAttachment")
        data = root["0"]
        self.assertEqual(data["_classes"][0], "LookinHierarchyInfo")
        self.assertIsNone(data["2"])  # appInfo（数字键，真实编码形态）
        items = data["1"]
        self.assertEqual(len(items), 1)
        window = items[0]
        self.assertEqual(window["_classes"][0], "LookinDisplayItem")
        self.assertEqual(window["frame"], {"X": 0.0, "Y": 0.0, "Width": 390.0, "Height": 844.0})
        self.assertIs(window["representedAsKeyWindow"], True)
        self.assertEqual(window["viewObject"]["oid"], 1)
        self.assertEqual(window["viewObject"]["classChainList"][0], "UIWindow")
        label = window["subitems"][0]
        self.assertEqual(label["frame"]["Width"], 200.0)
        attr = label["attributesGroupList"][0]["attrSections"][0]["attributes"][0]
        self.assertEqual(attr["identifier"], "lb_t_t")
        self.assertEqual(attr["value"], "你好，世界")

    def test_decode_keeps_unknown_class_chain(self) -> None:
        payload = archiver.encode_keyed_object(
            {"oid": 5, "classChainList": ["MyCustomView", "UIView"]},
            class_name="LookinObject",
        )
        root, _warnings = archiver.unarchive(payload)
        self.assertEqual(root["_classes"], ["LookinObject", "NSObject"])
        self.assertEqual(root["oid"], 5)
        self.assertEqual(root["classChainList"], ["MyCustomView", "UIView"])

    def test_decode_error_object(self) -> None:
        payload = archiver.encode_keyed_object(
            {"NSDomain": "LookinError", "NSCode": -404, "NSUserInfo": {"NSLocalizedDescription": "请求超时"}},
            class_name="NSError",
            class_chain=["NSError", "NSObject"],
        )
        root, _warnings = archiver.unarchive(payload)
        self.assertEqual(root["__type"], "NSError")
        self.assertEqual(root["domain"], "LookinError")
        self.assertEqual(root["code"], -404)
        self.assertEqual(root["userInfo"]["NSLocalizedDescription"], "请求超时")
        self.assertEqual(root["description"], "请求超时")

    def test_decode_rect_variants(self) -> None:
        expected = {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}
        self.assertEqual(archiver.decode_rect({"X": 1.0, "Y": 2.0, "Width": 3.0, "Height": 4.0}), expected)
        self.assertEqual(archiver.decode_rect({"NS.x": 1, "NS.y": 2, "NS.width": 3, "NS.height": 4}), expected)
        self.assertEqual(archiver.decode_rect({"origin": {"x": 1, "y": 2}, "size": {"width": 3, "height": 4}}), expected)
        self.assertEqual(archiver.decode_rect([1, 2, 3, 4]), expected)
        self.assertIsNone(archiver.decode_rect("nope"))
        self.assertIsNone(archiver.decode_rect({"X": 1.0}))


class ClientTest(unittest.TestCase):
    def test_ping_accepts_version_7(self) -> None:
        stream = FakeStream(frame_bytes(200, 1, response_attachment(server_version=7)))
        self.assertEqual(client.LookinClient(stream).ping(), 7)

    def test_ping_rejects_version_8(self) -> None:
        stream = FakeStream(frame_bytes(200, 1, response_attachment(server_version=8)))
        with self.assertRaises(CoreError) as context:
            client.LookinClient(stream).ping()
        self.assertEqual(context.exception.code, "LOOKIN_VERSION_MISMATCH")

    def test_request_timeout_raises_operation_timeout(self) -> None:
        class TimeoutStream(FakeStream):
            def recv(self, size: int) -> bytes:
                raise socket.timeout()

        with self.assertRaises(CoreError) as context:
            client.LookinClient(TimeoutStream()).ping()
        self.assertEqual(context.exception.code, "OPERATION_TIMEOUT")

    def test_response_frame_type_mismatch_raises_unavailable(self) -> None:
        # 期望 200（Ping），服务端回 201（App）
        stream = FakeStream(frame_bytes(201, 1, response_attachment(server_version=7)))
        with self.assertRaises(CoreError) as context:
            client.LookinClient(stream).ping()
        self.assertEqual(context.exception.code, "LOOKIN_UNAVAILABLE")
        self.assertEqual(context.exception.details["expectedType"], 200)
        self.assertEqual(context.exception.details["actualType"], 201)

    def test_response_frame_tag_mismatch_raises_unavailable(self) -> None:
        # 服务端未回显请求 tag（回 9 而非 1）
        stream = FakeStream(frame_bytes(200, 9, response_attachment(server_version=7)))
        with self.assertRaises(CoreError) as context:
            client.LookinClient(stream).ping()
        self.assertEqual(context.exception.code, "LOOKIN_UNAVAILABLE")
        self.assertEqual(context.exception.details["actualTag"], 9)

    def test_app_info_parses_screen_scale(self) -> None:
        payload = response_attachment(data=app_info_payload(), background=False)
        info = client.LookinClient(FakeStream(frame_bytes(201, 1, payload))).app_info()
        self.assertEqual(info["screenScale"], 3.0)
        self.assertEqual(info["appBundleIdentifier"], "com.qmui.lookindemo")
        self.assertEqual(info["appName"], "LookinDemo")
        self.assertEqual(info["screenWidth"], 390.0)
        self.assertIs(info["appIsInBackground"], False)

    def test_hierarchy_details_merges_batches(self) -> None:
        batch1 = {1: [{"identifier": "g1", "attrSections": []}]}
        batch2 = [{"oid": 2, "attributesGroups": [{"identifier": "g2", "attrSections": []}]}]
        batch3 = {"oid": 3, "attributesGroups": [], "image": b"\xff\xd8\xff"}  # 图片字段应被丢弃
        chunks = b"".join(
            frame_bytes(203, 1, response_attachment(data=data, total=3, current=index + 1))
            for index, data in enumerate((batch1, batch2, batch3))
        )
        merged = client.LookinClient(FakeStream(chunks)).hierarchy_details()
        self.assertEqual(len(merged["batches"]), 3)
        self.assertEqual(sorted(merged["attrGroupsByOid"]), [1, 2, 3])
        self.assertEqual(merged["attrGroupsByOid"][1][0]["identifier"], "g1")
        self.assertEqual(merged["attrGroupsByOid"][2][0]["identifier"], "g2")
        self.assertEqual(merged["droppedImageFieldCount"], 1)
        self.assertTrue(any("图片" in warning for warning in merged["warnings"]))


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def app_info_payload(name: str = "LookinDemo") -> dict[str, object]:
    """真实 LookinAppInfo 编码键形态（LookinAppInfo.m：数字键为主、部分属性名，2026-10-25 真机校准）。"""
    return {
        "1": None,  # screenshot（needImages=False 时为 null）
        "2": None,  # appIcon
        "3": "iPhone 18 Pro",  # deviceDescription
        "4": "27.0",  # osDescription
        "5": name,  # appName
        "6": 390.0,  # screenWidth
        "7": 844.0,  # screenHeight
        "8": 0,  # deviceType（0=Simulator）
        "appBundleIdentifier": "com.qmui.lookindemo",
        "screenScale": 3.0,
        "serverVersion": 0,
    }


def hierarchy_payload(items: list[object], name: str = "LookinDemo") -> dict[str, object]:
    """真实 LookinHierarchyInfo 编码键形态（1=displayItems 2=appInfo）。"""
    return {"1": items, "2": app_info_payload(name)}


def make_window() -> dict[str, object]:
    """构造 decode 后形态的 Lookin 树（键形态按 2026-10-26 实弹校准：hidden/attributes/短码）。"""
    return {
        "_classes": ["LookinDisplayItem", "NSObject"],
        "frame": {"X": 0.0, "Y": 0.0, "Width": 390.0, "Height": 844.0},
        "alpha": 1.0,
        "hidden": False,
        "viewObject": {"oid": 1, "classChainList": ["UIWindow", "UIView"], "_classes": ["LookinObject", "NSObject"]},
        "subitems": [
            {
                "_classes": ["LookinDisplayItem", "NSObject"],
                "frame": {"X": 20.0, "Y": 100.0, "Width": 200.0, "Height": 44.0},
                "viewObject": {"oid": 2, "classChainList": ["UILabel", "UIView"], "_classes": ["LookinObject", "NSObject"]},
                "attributesGroupList": [{
                    "identifier": "la",
                    "attrSections": [{
                        "identifier": "lb_t",
                        "attributes": [
                            {"identifier": "lb_t_t", "attrType": 24, "value": "你好"},
                        ],
                    }],
                }],
                "subitems": [],
            }
        ],
    }


def groups_by_oid() -> dict[int, list[object]]:
    """AllAttrGroups(210) 聚合结果：oid=2 补充 userInteractionEnabled。"""
    return {
        2: [{
            "identifier": "vl",
            "attrSections": [{
                "identifier": "v_i",
                "attributes": [{"identifier": "vl_i_i", "attrType": 14, "value": True}],
            }],
        }]
    }


class StubUsbmux:
    """usbmux 替身：connect 按序弹出预置流；up=False 模拟 usbmuxd 不可用。"""

    def __init__(self, streams: list[FakeStream] | None = None, devices: list[dict[str, object]] | None = None, up: bool = True) -> None:
        self.streams = list(streams or [])
        self.devices = devices or []
        self.up = up

    def available(self) -> bool:
        return self.up

    def list_devices(self) -> list[dict[str, object]]:
        return self.devices

    def connect(self, udid: str, port: int) -> FakeStream:
        if not self.streams:
            raise CoreError("LOOKIN_UNAVAILABLE", "无预置流。")
        return self.streams.pop(0)


class ReplayServer:
    """模拟器替身：本地 TCP listener，accept 后按序推送预置帧；client 关闭连接后线程退出。"""

    def __init__(self, frames: bytes) -> None:
        self.listener = socket.socket()
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.listener.settimeout(5)
        self.port = self.listener.getsockname()[1]
        self.frames = frames
        threading.Thread(target=self._serve, name="replay-lookin-sim", daemon=True).start()

    def _serve(self) -> None:
        try:
            conn, _ = self.listener.accept()
            conn.sendall(self.frames)
            try:
                # 持续丢弃 client 的请求帧，直到 client 关闭（连接保持，模拟 LookinServer 行为）
                while conn.recv(65536):
                    pass
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass
        except OSError:
            pass

    def close(self) -> None:
        self.listener.close()


class DriverTest(unittest.TestCase):
    def test_devices_descriptor(self) -> None:
        stub = StubUsbmux(devices=[{"udid": UDID, "deviceId": 7, "properties": {"ProductType": "iPhone16,1"}}])
        devices = driver.IOSDeviceDriver(stub, sim_ports=()).devices()
        self.assertEqual(len(devices), 1)
        item = devices[0]
        self.assertEqual(item["deviceId"], f"ios-{UDID}")
        self.assertEqual(item["platform"], "ios")
        self.assertEqual(item["capabilities"], ["layout"])
        self.assertIs(item["readonly"], True)
        self.assertEqual(item["status"], "connected")

    def test_build_xml_fields_and_bounds(self) -> None:
        warnings: list[str] = []
        xml = driver.build_xml([make_window()], 3.0, groups_by_oid(), warnings)
        self.assertEqual(warnings, [])
        self.assertIn('<hierarchy rotation="0">', xml)
        # 直接走生产解析链路 normalize_nodes 断言，同时验证生成的 XML 可被快照管线消费
        nodes, _, _ = normalize_nodes(xml, {"width": 1170, "height": 2532})
        self.assertEqual([node["className"] for node in nodes], ["UIWindow", "UILabel"])
        self.assertEqual(nodes[0]["boundsPx"], {"left": 0, "top": 0, "right": 1170, "bottom": 2532})
        label = nodes[1]
        self.assertEqual(label["boundsPx"], {"left": 60, "top": 300, "right": 660, "bottom": 432})
        self.assertEqual(label["text"], "你好")
        self.assertTrue(label["enabled"])  # groups_by_oid 补充的 vl_i_i=True
        self.assertFalse(label["clickable"])
        self.assertFalse(label["scrollable"])

    def test_build_xml_unparsable_frame_records_warning(self) -> None:
        item: dict[str, object] = {
            "frame": "bad-frame",
            "viewObject": {"oid": 1, "classChainList": ["UIView"]},
            "subitems": [],
        }
        warnings: list[str] = []
        xml = driver.build_xml([item], 1.0, {}, warnings)
        nodes, _, _ = normalize_nodes(xml, {"width": 100, "height": 100})
        self.assertEqual(nodes[0]["boundsPx"], {"left": 0, "top": 0, "right": 0, "bottom": 0})
        self.assertEqual(len(warnings), 1)
        self.assertIn("frame", warnings[0])

    def test_capture_background_only_raises_app_not_found(self) -> None:
        probe = (
            frame_bytes(200, 1, response_attachment(server_version=7))
            + frame_bytes(201, 2, response_attachment(data={"appName": "Background"}, background=True))
        )
        streams = [FakeStream(probe) for _ in driver.IOSDeviceDriver.USB_PORTS]
        ios_driver = driver.IOSDeviceDriver(StubUsbmux(streams))
        with self.assertRaises(CoreError) as context:
            ios_driver.capture(UDID)
        self.assertEqual(context.exception.code, "LOOKIN_APP_NOT_FOUND")
        self.assertEqual(len(context.exception.details["attempts"]), len(driver.IOSDeviceDriver.USB_PORTS))

    def test_capture_happy_path(self) -> None:
        frames = (
            frame_bytes(200, 1, response_attachment(server_version=7))
            + frame_bytes(201, 2, response_attachment(data=app_info_payload(), background=False))
            + frame_bytes(202, 3, response_attachment(data=hierarchy_payload([make_window()])))
            + frame_bytes(210, 4, response_attachment(data=[]))  # window oid=1 无属性组
            + frame_bytes(210, 5, response_attachment(data=groups_by_oid()[2]))  # label oid=2
        )
        ios_driver = driver.IOSDeviceDriver(StubUsbmux([FakeStream(frames)]))
        result = ios_driver.capture(UDID)
        self.assertEqual(result["window_size"], {"width": 1170, "height": 2532})
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["app"]["appName"], "LookinDemo")
        self.assertEqual(result["app"]["screenScale"], 3.0)
        self.assertEqual(result["app"]["port"], 47175)
        nodes, _, _ = normalize_nodes(result["xml"], {"width": 1170, "height": 2532})
        self.assertGreaterEqual(len(nodes), 2)
        self.assertEqual(nodes[1]["text"], "你好")
        self.assertTrue(nodes[1]["enabled"])


def sim_app_info() -> dict[str, object]:
    """模拟器 app_info 响应的 data 字段（真实数字键形态，前台 PackSmart）。"""
    return app_info_payload("PackSmart")


class SimulatorDriverTest(unittest.TestCase):
    """模拟器路径：loopback 直连枚举与抓取（ReplayServer 替身，不依赖真实模拟器）。"""

    def test_simulator_enumerated(self) -> None:
        frames = frame_bytes(200, 1, response_attachment(server_version=7)) + frame_bytes(
            201, 2, response_attachment(data=sim_app_info())
        )
        server = ReplayServer(frames)
        try:
            devices = driver.IOSDeviceDriver(StubUsbmux(), sim_ports=(server.port,)).devices()
        finally:
            server.close()
        self.assertEqual(len(devices), 1)
        item = devices[0]
        self.assertEqual(item["deviceId"], f"ios-sim-{server.port}")
        self.assertEqual(item["serial"], f"simulator:{server.port}")
        self.assertEqual(item["model"], "PackSmart")
        self.assertEqual(item["product"], "iPhone 18 Pro")
        self.assertEqual(item["platform"], "ios")
        self.assertIs(item["readonly"], True)

    def test_simulator_enumerated_without_usbmux(self) -> None:
        frames = frame_bytes(200, 1, response_attachment(server_version=7)) + frame_bytes(
            201, 2, response_attachment(data=sim_app_info())
        )
        server = ReplayServer(frames)
        try:
            devices = driver.IOSDeviceDriver(StubUsbmux(up=False), sim_ports=(server.port,)).devices()
        finally:
            server.close()
        self.assertEqual([item["serial"] for item in devices], [f"simulator:{server.port}"])

    def test_simulator_background_app_filtered(self) -> None:
        frames = frame_bytes(200, 1, response_attachment(server_version=7)) + frame_bytes(
            201, 2, response_attachment(data=sim_app_info(), background=True)
        )
        server = ReplayServer(frames)
        try:
            devices = driver.IOSDeviceDriver(StubUsbmux(), sim_ports=(server.port,)).devices()
        finally:
            server.close()
        self.assertEqual(devices, [])

    def test_simulator_capture_pipeline(self) -> None:
        frames = (
            frame_bytes(200, 1, response_attachment(server_version=7))
            + frame_bytes(201, 2, response_attachment(data=sim_app_info()))
            + frame_bytes(202, 3, response_attachment(data=hierarchy_payload([make_window()], name="PackSmart")))
            + frame_bytes(210, 4, response_attachment(data=[]))  # window oid=1 无属性组
            + frame_bytes(210, 5, response_attachment(data=groups_by_oid()[2]))  # label oid=2
        )
        server = ReplayServer(frames)
        try:
            result = driver.IOSDeviceDriver(StubUsbmux(), sim_ports=(server.port,)).capture(f"simulator:{server.port}")
        finally:
            server.close()
        self.assertEqual(result["window_size"], {"width": 1170, "height": 2532})
        self.assertEqual(result["app"]["appName"], "PackSmart")
        nodes, _, _ = normalize_nodes(result["xml"], {"width": 1170, "height": 2532})
        self.assertEqual([node["className"] for node in nodes], ["UIWindow", "UILabel"])
        self.assertEqual(nodes[1]["text"], "你好")

    def test_simulator_capture_error_mentions_simulator(self) -> None:
        # 端口 1 无监听：连接拒绝 → 模拟器专属文案（提示 Lookin 客户端独占），而非 usbmuxd 文案
        ios_driver = driver.IOSDeviceDriver(StubUsbmux(), sim_ports=())
        with self.assertRaises(CoreError) as ctx:
            ios_driver.capture("simulator:1")
        self.assertEqual(ctx.exception.code, "LOOKIN_APP_NOT_FOUND")
        self.assertIn("模拟器", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
