"""PeerTalk 帧协议编解码（Lookin 传输层）。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
帧结构（Lookin_PTProtocol.m 用 htonl/ntohl，全部大端）：

    struct PTFrame { u32 version; u32 type; u32 tag; u32 payloadSize; }  // 16 字节

- version 恒为 1；type 为 Lookin 请求类型常量（见 client.py）
- tag 由客户端递增（禁用 0），服务端响应回显请求的 type + tag
- payloadSize 上限 512MB，超出视为协议异常拒绝
"""
from __future__ import annotations

import socket
import struct

from ..errors import CoreError

PT_HEADER = struct.Struct(">IIII")
PT_VERSION = 1
MAX_PAYLOAD_SIZE = 512 * 1024 * 1024


def read_exact(sock: socket.socket, size: int) -> bytes:
    """读满 size 字节；对端提前 EOF（短读）抛 LOOKIN_UNAVAILABLE。"""
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(min(remaining, 65536))
        if not chunk:
            raise CoreError("LOOKIN_UNAVAILABLE", "连接被对端关闭，帧数据不完整。", retryable=True)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(sock: socket.socket) -> tuple[int, int, bytes]:
    """读取一帧，返回 (type, tag, payload)。"""
    version, frame_type, tag, payload_size = PT_HEADER.unpack(read_exact(sock, PT_HEADER.size))
    if version != PT_VERSION:
        raise CoreError("LOOKIN_UNAVAILABLE", f"不支持的 PeerTalk 帧版本：{version}（期望 {PT_VERSION}）")
    if payload_size > MAX_PAYLOAD_SIZE:
        raise CoreError("LOOKIN_UNAVAILABLE", f"帧载荷超出上限：{payload_size} 字节（上限 {MAX_PAYLOAD_SIZE}）")
    payload = read_exact(sock, payload_size) if payload_size else b""
    return frame_type, tag, payload


def write_frame(sock: socket.socket, frame_type: int, tag: int, payload: bytes | bytearray = b"") -> None:
    """写出一帧（16 字节大端头 + 载荷）。"""
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise CoreError("LOOKIN_UNAVAILABLE", f"待发送载荷超出上限：{len(payload)} 字节（上限 {MAX_PAYLOAD_SIZE}）")
    sock.sendall(PT_HEADER.pack(PT_VERSION, frame_type, tag, len(payload)) + bytes(payload))
