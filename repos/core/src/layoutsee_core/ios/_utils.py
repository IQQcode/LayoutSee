"""iOS 协议包内部小工具（client/driver 共享，避免重复实现）。

协议事实源：QMUI/LookinServer @develop (MIT)；不包含 hughkli/Lookin (GPL-3.0) 代码。
"""
from __future__ import annotations


def as_int(value: object) -> int | None:
    """宽松转 int：bool 视为非数值；int 原样、整值 float、纯数字字符串可转，其余 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("+-").isdigit():
            return int(text)
    return None
