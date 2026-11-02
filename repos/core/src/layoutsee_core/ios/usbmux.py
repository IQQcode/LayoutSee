"""usbmuxd 客户端：iOS 设备枚举与端口隧道（macOS 私有协议，纯 socket）。

协议事实源：QMUI/LookinServer @develop (MIT) 配套的 usbmux 使用方式；不包含 hughkli/Lookin (GPL-3.0) 代码。
- unix socket：/var/run/usbmuxd；消息 = 16 字节头 + 载荷，头为 host 字节序（macOS 小端）：

    struct usbmux_header { u32 length(含头); u32 version(=1); u32 message; u32 tag; }

- message：8=plist（载荷为 binary plist）、1=Result（载荷为 4 字节 result code，host 序）
- plist 公共键：MessageType / ProtocolVersion("1") / ClientVersionString / ProgName
- ListDevices：请求 {"MessageType":"ListDevices"} → 响应 {"MessageType":"ListDevices",
  "DeviceList":[{"DeviceID":int,"Properties":{"SerialNumber":"udid",...}}]}
- Listen：请求后 usbmuxd 会推送 DeviceAttached / DeviceDetached（本模块暂不消费推送）
- Connect 必须新开 socket：{"MessageType":"Connect","DeviceID":int,
  "PortNumber":((port&0xFF)<<8)|(port>>8),"ProgName":"layoutsee"}（PortNumber 为大端 u16）
- 响应 Result code==0 成功，之后该 socket 变为裸流（PeerTalk 帧在此之上）
- Result 解析兼容两种形态：message==8 的 plist {"MessageType":"Result","Number":code}
  与 message==1 的 4 字节 result code
"""
from __future__ import annotations

import plistlib
import socket
import struct
from collections.abc import Callable

from ..errors import CoreError

USBMUXD_SOCKET_PATH = "/var/run/usbmuxd"
USBMUX_HEADER = struct.Struct("<IIII")  # host 字节序（macOS 小端）
USBMUX_VERSION = 1
MESSAGE_RESULT = 1
MESSAGE_PLIST = 8
MAX_MESSAGE_SIZE = 16 * 1024 * 1024
PROG_NAME = "layoutsee"
CLIENT_VERSION_STRING = "layoutsee-1"
DEFAULT_TIMEOUT = 3.0


def swap_port(port: int) -> int:
    """端口值转为 usbmuxd 期望的大端 u16。"""
    if not 0 <= port <= 0xFFFF:
        raise ValueError(f"端口超出 u16 范围：{port}")
    return ((port & 0xFF) << 8) | ((port >> 8) & 0xFF)


def encode_plist_message(payload: dict[str, object], tag: int = 0) -> bytes:
    """编码一条 plist 消息（16 字节头 + binary plist 载荷）。"""
    body = plistlib.dumps(payload, fmt=plistlib.FMT_BINARY)
    return USBMUX_HEADER.pack(USBMUX_HEADER.size + len(body), USBMUX_VERSION, MESSAGE_PLIST, tag) + body


def read_message(sock: socket.socket, timeout: float = DEFAULT_TIMEOUT) -> tuple[int, int, bytes]:
    """读取一条 usbmux 消息，返回 (message, tag, payload)；EOF/长度异常抛 LOOKIN_UNAVAILABLE。"""
    sock.settimeout(timeout)
    header = _read_exact(sock, USBMUX_HEADER.size)
    length, _version, message, tag = USBMUX_HEADER.unpack(header)
    if length < USBMUX_HEADER.size or length > MAX_MESSAGE_SIZE:
        raise CoreError("LOOKIN_UNAVAILABLE", f"usbmuxd 消息长度异常：{length}")
    payload = _read_exact(sock, length - USBMUX_HEADER.size) if length > USBMUX_HEADER.size else b""
    return message, tag, payload


def parse_result(message: int, payload: bytes) -> int:
    """解析 Result，兼容 plist（message==8）与 4 字节（message==1）两种形态。"""
    if message == MESSAGE_PLIST:
        obj = plistlib.loads(payload)
        if isinstance(obj, dict):
            number = obj.get("Number")
            if isinstance(number, int) and not isinstance(number, bool):
                return number
        raise CoreError("LOOKIN_UNAVAILABLE", "usbmuxd 返回了无法识别的 Result plist。")
    if message == MESSAGE_RESULT and len(payload) == 4:
        return struct.unpack("=I", payload)[0]
    raise CoreError("LOOKIN_UNAVAILABLE", f"usbmuxd 返回了无法识别的 Result 消息：type={message}")


class UsbmuxClient:
    """usbmuxd 客户端：list_devices() 枚举、connect() 打开设备端口隧道。"""

    def __init__(
        self,
        socket_path: str = USBMUXD_SOCKET_PATH,
        *,
        socket_factory: Callable[[], socket.socket] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.socket_path = socket_path
        self._socket_factory = socket_factory
        self.timeout = timeout

    def _open(self) -> socket.socket:
        if self._socket_factory is not None:
            return self._socket_factory()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)  # 连接与后续读写均受超时保护，防止悬空 socket 文件挂死
        try:
            sock.connect(self.socket_path)
        except OSError as error:
            sock.close()
            raise CoreError(
                "LOOKIN_UNAVAILABLE",
                "无法连接 usbmuxd，请确认运行在 macOS 且 iOS 设备已通过 USB 连接。",
                details={"socket": self.socket_path, "reason": str(error)},
            ) from error
        return sock

    def available(self) -> bool:
        """usbmuxd socket 是否可连。"""
        try:
            sock = self._open()
        except CoreError:
            return False
        try:
            sock.close()
        except OSError:
            pass
        return True

    def list_devices(self) -> list[dict[str, object]]:
        """枚举设备，返回 [{udid, deviceId, properties}]；usbmuxd 不可达/无设备返回空列表。"""
        try:
            return self._list_devices()
        except Exception:  # noqa: BLE001 —— 验收要求：枚举失败一律视为空列表，不外抛
            return []

    def connect(self, udid: str, port: int) -> socket.socket:
        """为设备端口新开一条隧道（Connect 必须新开 socket）；成功后 socket 变为裸流。

        调用方负责关闭返回的 socket。Result 非 0 抛 IOS_DEVICE_NOT_FOUND（设备不可用）
        或 LOOKIN_APP_NOT_FOUND（端口拒绝）。
        """
        device_id = self._device_id_for(udid)
        stream = self._open()
        try:
            request: dict[str, object] = {
                "MessageType": "Connect",
                "DeviceID": device_id,
                "PortNumber": swap_port(port),
                "ProgName": PROG_NAME,
            }
            try:
                stream.sendall(encode_plist_message(request))
                message, _tag, payload = read_message(stream, self.timeout)
                code = parse_result(message, payload)
            except (OSError, ValueError, plistlib.InvalidFileException) as error:
                raise CoreError(
                    "LOOKIN_UNAVAILABLE",
                    f"usbmuxd 隧道握手失败：{error}",
                    details={"udid": udid, "port": port},
                ) from error
            if code == 2:  # USBMUXD_RESULT_BADDEV：设备不可用
                raise CoreError(
                    "IOS_DEVICE_NOT_FOUND",
                    f"usbmuxd 拒绝连接：设备不可用（{udid}）。",
                    details={"udid": udid, "port": port, "result": code},
                )
            if code != 0:
                raise CoreError(
                    "LOOKIN_APP_NOT_FOUND",
                    f"设备拒绝端口连接：端口 {port} 无 Lookin 服务或不可达。",
                    retryable=True,
                    details={"udid": udid, "port": port, "result": code},
                )
            return stream
        except CoreError:
            stream.close()  # socket.close() 幂等
            raise

    def _list_devices(self) -> list[dict[str, object]]:
        sock = self._open()
        try:
            request: dict[str, object] = {
                "MessageType": "ListDevices",
                "ProtocolVersion": "1",
                "ClientVersionString": CLIENT_VERSION_STRING,
                "ProgName": PROG_NAME,
            }
            sock.sendall(encode_plist_message(request))
            # usbmuxd 可能夹杂推送消息，最多读 8 条寻找 ListDevices 响应
            for _ in range(8):
                message, _tag, payload = read_message(sock, self.timeout)
                if message != MESSAGE_PLIST:
                    continue
                obj = plistlib.loads(payload)
                if isinstance(obj, dict) and (obj.get("MessageType") == "ListDevices" or "DeviceList" in obj):
                    return self._normalize_device_list(obj.get("DeviceList"))
            return []
        finally:
            sock.close()

    def _device_id_for(self, udid: str) -> int:
        for entry in self._list_devices():
            if entry["udid"] == udid and isinstance(entry["deviceId"], int):
                return int(entry["deviceId"])  # type: ignore[arg-type]
        raise CoreError("IOS_DEVICE_NOT_FOUND", f"usbmuxd 中未找到设备：{udid}", details={"udid": udid})

    @staticmethod
    def _normalize_device_list(device_list: object) -> list[dict[str, object]]:
        devices: list[dict[str, object]] = []
        if not isinstance(device_list, list):
            return devices
        for entry in device_list:
            if not isinstance(entry, dict):
                continue
            device_id = entry.get("DeviceID")
            properties = entry.get("Properties") if isinstance(entry.get("Properties"), dict) else {}
            udid = properties.get("SerialNumber") if isinstance(properties, dict) else None
            if not isinstance(device_id, int) or isinstance(device_id, bool):
                continue
            if not isinstance(udid, str) or not udid:
                continue
            devices.append({"udid": udid, "deviceId": device_id, "properties": properties})
        return devices


def _read_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(min(remaining, 65536))
        if not chunk:
            raise CoreError("LOOKIN_UNAVAILABLE", "usbmuxd 连接中断。", retryable=True)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
