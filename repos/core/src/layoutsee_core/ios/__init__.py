"""iOS 协议包：usbmuxd 隧道 → PeerTalk 帧 → NSKeyedArchiver 载荷 → Lookin 请求 → uiautomator XML。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
模块分工：usbmux（设备枚举/端口隧道）、peertalk（16 字节大端帧）、archiver（归档编解码）、
client（请求编排与分批聚合）、driver（设备驱动 + XML 生成）。
"""
from __future__ import annotations

from .client import LookinClient
from .driver import IOSDeviceDriver
from .usbmux import UsbmuxClient

__all__ = ["IOSDeviceDriver", "LookinClient", "UsbmuxClient"]
