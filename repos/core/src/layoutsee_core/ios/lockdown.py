"""lockdown 客户端：StartService 握手与配对记录读取（纯 socket，零第三方依赖）。

协议事实源：libimobiledevice lockdown.c / usbmuxd.c（MIT）、pymobiledevice3 lockdown.py（MIT）、
Apple lockdown 惯例；不包含 hughkli/Lookin (GPL-3.0) 代码。
- 与 usbmux 层的 16 字节头不同，lockdown 通道是「4 字节大端长度 + binary plist」成帧，
  长度只计载荷、不含头自身：

    struct { u32 length(仅载荷); binary plist }

- 握手序列（syslog_relay 等系统服务通用）：
  1. UsbmuxClient.connect(udid, 62078) 打开 lockdown 通道（usbmux 隧道，16 字节头）；
  2. QueryType → 响应 Type=="com.apple.mobile.lockdown"；
  3. ReadPairRecord（注意：这是 usbmuxd 消息，走 /var/run/usbmuxd 而非 lockdown 通道）
     → 配对记录 dict，含 HostID / HostCertificate / HostPrivateKey（DER 编码）；
  4. StartSession(HostID) → 响应 EnableSessionBypass=true 则明文，否则 lockdown 通道升级 TLS；
  5. StartService(service) → 响应 Port（host 序，可直接交给 UsbmuxClient.connect）
     与 EnableServiceSSL（true 则服务通道用配对证书做 TLS）；
  6. usbmux connect 新隧道到服务端口 → 裸流（syslog_relay 为按 \\n\\x00 分行的文本流）。
- 标准库 ssl 的 load_cert_chain 只收磁盘文件：DER 转 PEM 写入 0600 临时文件加载，用完即删。
"""
from __future__ import annotations

import base64
import os
import plistlib
import socket
import ssl
import struct
from collections.abc import Callable
from tempfile import mkstemp

from ..errors import CoreError
from .usbmux import (
    CLIENT_VERSION_STRING,
    MESSAGE_PLIST,
    PROG_NAME,
    USBMUXD_SOCKET_PATH,
    UsbmuxClient,
    encode_plist_message,
    read_message,
)

LOCKDOWN_PORT = 62078
LOCKDOWN_TYPE = "com.apple.mobile.lockdown"
LOCKDOWN_LENGTH = struct.Struct(">I")  # 4 字节大端长度，只计载荷
MAX_MESSAGE_SIZE = 16 * 1024 * 1024
PAIR_RETRIES = 8  # usbmuxd 可能夹杂推送消息，最多读 8 条寻找 Result（对齐 usbmux.list_devices 容错）
KEY_PEM_LABELS = ("PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY")  # 配对私钥格式随生成器而异


class LockdownClient:
    """lockdown 客户端：start_service 完成 QueryType→ReadPairRecord→StartSession→StartService。

    ReadPairRecord 的 socket 可经 socket_factory 注入替身（与 UsbmuxClient 同思路）；
    缺省直连 /var/run/usbmuxd。
    """

    def __init__(
        self,
        usbmux: UsbmuxClient,
        *,
        port: int = LOCKDOWN_PORT,
        socket_factory: Callable[[], socket.socket] | None = None,
        timeout: float | None = None,
    ) -> None:
        self.usbmux = usbmux
        self.port = port
        self._socket_factory = socket_factory
        self.timeout = usbmux.timeout if timeout is None else timeout

    def start_service(self, udid: str, service_name: str) -> int:
        """完成握手并返回服务端口（host 序，可直接传 UsbmuxClient.connect）。"""
        service_port, _enable_ssl, _pair = self._handshake(udid, service_name)
        return service_port

    def open_service_stream(self, udid: str, service_name: str) -> socket.socket:
        """握手后新开一条服务隧道；EnableServiceSSL 时对服务通道做 TLS，返回裸流 socket。

        调用方负责关闭返回的 socket；握手失败抛 LOOKIN_UNAVAILABLE / IOS_DEVICE_NOT_FOUND。
        """
        service_port, enable_ssl, pair = self._handshake(udid, service_name)
        stream = self.usbmux.connect(udid, service_port)
        if enable_ssl:
            try:
                stream = wrap_tls(stream, pair)
            except CoreError:
                stream.close()
                raise
        return stream

    # ---------- 握手 ----------

    def _handshake(self, udid: str, service_name: str) -> tuple[int, bool, dict[str, object]]:
        stream = self.usbmux.connect(udid, self.port)
        try:
            query = self._request(stream, {"Request": "QueryType"})
            if query.get("Type") != LOCKDOWN_TYPE:
                raise CoreError(
                    "LOOKIN_UNAVAILABLE",
                    f"lockdown 类型异常：{query.get('Type')!r}",
                    details={"udid": udid},
                )
            pair = self.read_pair_record(udid)
            session = self._request(stream, {"Request": "StartSession", "HostID": pair.get("HostID") or udid})
            if "Error" in session:
                raise CoreError(
                    "LOOKIN_UNAVAILABLE",
                    f"lockdown 拒绝会话：{session['Error']}。请先用 Xcode/Finder 配对设备。",
                    details={"udid": udid, "error": str(session["Error"])},
                )
            if not bool(session.get("EnableSessionBypass")):
                # EnableSessionBypass 缺省/false 均按 Apple 惯例升级 TLS（真机常态）
                stream = wrap_tls(stream, pair)
            service = self._request(stream, {"Request": "StartService", "Service": service_name})
            if "Error" in service:
                raise CoreError(
                    "LOOKIN_UNAVAILABLE",
                    f"lockdown 拒绝启动服务 {service_name}：{service['Error']}。"
                    "请确认设备已解锁并信任本机，或先用 Xcode/Finder 配对设备。",
                    details={"udid": udid, "error": str(service["Error"])},
                )
            port = service.get("Port")
            if not isinstance(port, int) or isinstance(port, bool) or not 0 < port <= 0xFFFF:
                raise CoreError(
                    "LOOKIN_UNAVAILABLE",
                    "lockdown StartService 响应缺少有效端口。",
                    details={"udid": udid},
                )
            return int(port), bool(service.get("EnableServiceSSL")), pair
        finally:
            stream.close()  # SSLSocket.close 会连带关闭底层 socket；close 幂等

    def _request(self, stream: socket.socket, payload: dict[str, object]) -> dict[str, object]:
        body = plistlib.dumps(payload, fmt=plistlib.FMT_BINARY)
        try:
            stream.sendall(LOCKDOWN_LENGTH.pack(len(body)) + body)
        except OSError as error:
            raise CoreError(
                "LOOKIN_UNAVAILABLE",
                f"lockdown 发送失败：{error}",
                retryable=True,
                details={"request": payload.get("Request")},
            ) from error
        return _recv_plist(stream, self.timeout)

    def read_pair_record(self, udid: str) -> dict[str, object]:
        """通过 usbmuxd ReadPairRecord 消息读取配对记录（这是 usbmuxd 消息，非 lockdown 请求）。

        响应 PairRecordData 是内嵌 binary plist 的 data；缺失/拒绝按未配对处理。
        """
        sock = self._open_mux()
        try:
            request: dict[str, object] = {
                "MessageType": "ReadPairRecord",
                "PairRecordID": udid,
                "ProtocolVersion": "1",
                "ClientVersionString": CLIENT_VERSION_STRING,
                "ProgName": PROG_NAME,
            }
            sock.sendall(encode_plist_message(request))
            for _ in range(PAIR_RETRIES):
                message, _tag, payload = read_message(sock, self.timeout)
                if message != MESSAGE_PLIST:
                    continue
                try:
                    obj = plistlib.loads(payload)
                except plistlib.InvalidFileException as error:
                    raise CoreError(
                        "LOOKIN_UNAVAILABLE",
                        "usbmuxd 返回了无法解析的配对记录响应。",
                        details={"udid": udid},
                    ) from error
                if not isinstance(obj, dict) or obj.get("MessageType") != "Result":
                    continue
                if obj.get("Number") != 0 or "PairRecordData" not in obj:
                    raise CoreError(
                        "LOOKIN_UNAVAILABLE",
                        "未找到设备配对记录，请先用 Xcode/Finder 配对设备。",
                        details={"udid": udid, "result": obj.get("Number")},
                    )
                record = obj["PairRecordData"]
                if isinstance(record, (bytes, bytearray)):
                    try:
                        record = plistlib.loads(bytes(record))
                    except plistlib.InvalidFileException as error:
                        raise CoreError(
                            "LOOKIN_UNAVAILABLE",
                            "配对记录 plist 解析失败，请重新配对设备。",
                            details={"udid": udid},
                        ) from error
                if not isinstance(record, dict) or not record.get("HostCertificate"):
                    raise CoreError(
                        "LOOKIN_UNAVAILABLE",
                        "配对记录缺少 Host 证书，请先用 Xcode/Finder 重新配对设备。",
                        details={"udid": udid},
                    )
                return record
            raise CoreError("LOOKIN_UNAVAILABLE", "usbmuxd 未返回 ReadPairRecord 响应。", details={"udid": udid})
        except OSError as error:
            raise CoreError(
                "LOOKIN_UNAVAILABLE",
                f"读取配对记录失败：{error}",
                retryable=True,
                details={"udid": udid},
            ) from error
        finally:
            sock.close()

    def _open_mux(self) -> socket.socket:
        """为 ReadPairRecord 打开一条 usbmuxd socket（ReadPairRecord 不走 lockdown 隧道）。"""
        if self._socket_factory is not None:
            return self._socket_factory()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(USBMUXD_SOCKET_PATH)
        except OSError as error:
            sock.close()
            raise CoreError(
                "LOOKIN_UNAVAILABLE",
                "无法连接 usbmuxd，请确认运行在 macOS 且 iOS 设备已通过 USB 连接。",
                details={"socket": USBMUXD_SOCKET_PATH, "reason": str(error)},
            ) from error
        return sock


def wrap_tls(sock: socket.socket, pair: dict[str, object]) -> ssl.SSLSocket:
    """把通道 socket 升级为 TLS（客户端用配对记录 Host 证书/私钥）；失败时关闭原 socket。"""
    context = _ssl_context(pair)
    try:
        return context.wrap_socket(sock)
    except (OSError, ssl.SSLError) as error:
        try:
            sock.close()
        except OSError:
            pass
        raise CoreError("LOOKIN_UNAVAILABLE", f"TLS 握手失败：{error}", retryable=True) from error


def _ssl_context(pair: dict[str, object]) -> ssl.SSLContext:
    """用配对记录的 Host 证书/私钥构造客户端 TLS 上下文（不校验设备证书公链）。"""
    cert = pair.get("HostCertificate")
    key = pair.get("HostPrivateKey")
    if not isinstance(cert, (bytes, bytearray)) or not isinstance(key, (bytes, bytearray)):
        raise CoreError("LOOKIN_UNAVAILABLE", "配对记录缺少 Host 证书/私钥，请先用 Xcode/Finder 重新配对设备。")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    cert_path: str | None = None
    try:
        cert_path = _write_temp_pem(bytes(cert), "CERTIFICATE")
        for label in KEY_PEM_LABELS:
            key_path = _write_temp_pem(bytes(key), label)
            try:
                context.load_cert_chain(cert_path, key_path)
                return context
            except ssl.SSLError:
                continue
            finally:
                _unlink(key_path)
        raise CoreError("LOOKIN_UNAVAILABLE", "配对记录私钥无法加载，请先用 Xcode/Finder 重新配对设备。")
    finally:
        if cert_path is not None:
            _unlink(cert_path)


def _write_temp_pem(der: bytes, label: str) -> str:
    """DER 转 PEM 写入 0600 临时文件，返回路径（调用方负责删除）。"""
    body = base64.encodebytes(der)
    fd, path = mkstemp(prefix="layoutsee-pair-")  # mkstemp 自带 0600 权限
    try:
        with os.fdopen(fd, "wb") as handle:
            fd = -1  # 所有权移交文件对象
            handle.write(b"-----BEGIN " + label.encode("ascii") + b"-----\n")
            handle.write(body)
            handle.write(b"-----END " + label.encode("ascii") + b"-----\n")
    except BaseException:
        if fd >= 0:
            os.close(fd)
        _unlink(path)
        raise
    return path


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _recv_plist(sock: socket.socket, timeout: float) -> dict[str, object]:
    """读取一条 lockdown plist 消息（4 字节大端长度 + binary plist，长度不含头）。"""
    sock.settimeout(timeout)
    header = _recv_exact(sock, LOCKDOWN_LENGTH.size)
    (length,) = LOCKDOWN_LENGTH.unpack(header)
    if length <= 0 or length > MAX_MESSAGE_SIZE:
        raise CoreError("LOOKIN_UNAVAILABLE", f"lockdown 消息长度异常：{length}")
    body = _recv_exact(sock, length)
    try:
        payload = plistlib.loads(body)
    except plistlib.InvalidFileException as error:
        raise CoreError("LOOKIN_UNAVAILABLE", "lockdown 返回了无法解析的 plist。") from error
    if not isinstance(payload, dict):
        raise CoreError("LOOKIN_UNAVAILABLE", "lockdown 返回了非对象 plist。")
    return payload


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        try:
            chunk = sock.recv(min(remaining, 65536))
        except OSError as error:
            raise CoreError("LOOKIN_UNAVAILABLE", f"lockdown 连接中断：{error}", retryable=True) from error
        if not chunk:
            raise CoreError("LOOKIN_UNAVAILABLE", "lockdown 连接中断。", retryable=True)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
