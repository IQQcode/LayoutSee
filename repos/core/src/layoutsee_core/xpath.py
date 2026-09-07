from __future__ import annotations

import re
import threading
import time
import xml.etree.ElementTree as ET

import elementpath
from elementpath.exceptions import ElementPathSyntaxError

from .errors import CoreError

MAX_EXPRESSION_LENGTH = 512
QUERY_TIMEOUT_S = 0.3

# 形如 //android.widget.Button 的点分标签名（Appium 风格）
TAG_TOKEN = re.compile(r"[A-Za-z_]\w*(?:\.[\w$]+)+")
TAG_BOUNDARY = "[/(), \t\r\n]"


def rewrite_class_tags(expression: str) -> str:
    """把点分标签改写为 class 属性谓词，避免被解析成命名空间前缀。引号内不处理。"""
    output: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(expression):
        char = expression[index]
        if quote is not None:
            output.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            output.append(char)
            index += 1
            continue
        if char == "/":
            separator = "//" if expression.startswith("//", index) else "/"
            rest = expression[index + len(separator):]
            match = TAG_TOKEN.match(rest)
            if match:
                tag = match.group(0)
                after = rest[len(tag):]
                if not after or after[0] in TAG_BOUNDARY:
                    output.append(f'{separator}*[@class="{tag}"]')
                    index += len(separator) + len(tag)
                    continue
        output.append(char)
        index += 1
    return "".join(output)


def validate_expression(expression: str) -> None:
    """语法预检：非法表达式返回 INVALID_XPATH，不发真实请求。"""
    if not isinstance(expression, str) or not expression.strip():
        raise CoreError("INVALID_XPATH", "XPath 表达式不能为空。", details={"hint": "示例：//*[@resource-id='com.example:id/btn']"})
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise CoreError("INVALID_XPATH", f"XPath 表达式过长（最多 {MAX_EXPRESSION_LENGTH} 字符）。")
    try:
        elementpath.select(ET.Element("probe"), rewrite_class_tags(expression))
    except (ElementPathSyntaxError, TypeError) as error:
        raise CoreError("INVALID_XPATH", f"XPath 语法错误：{error}", details={"expression": expression}) from error


def _evaluate(expression: str, root: ET.Element, element_to_key: dict[int, str]) -> list[str]:
    results = elementpath.select(root, rewrite_class_tags(expression))
    keys: list[str] = []
    for result in results:
        if not isinstance(result, ET.Element):
            continue
        key = element_to_key.get(id(result))
        if key is not None:
            keys.append(key)
    return keys


def query_record(record: dict[str, object], expression: str) -> dict[str, object]:
    """在快照保存的原始 XML 上执行 XPath；隔离线程硬超时 300ms。"""
    validate_expression(expression)
    elements = record["elements"]
    if not elements:
        return {"expression": expression, "matchCount": 0, "nodeKeys": [], "elapsedMs": 0}
    root: ET.Element = elements[0]
    element_to_key = record["element_to_key"]

    box: list[object] = [None]

    def run() -> None:
        box[0] = _evaluate(expression, root, element_to_key)

    thread = threading.Thread(target=run, name="layoutsee-xpath", daemon=True)
    started = time.monotonic()
    thread.start()
    thread.join(QUERY_TIMEOUT_S)
    if thread.is_alive():
        raise CoreError("OPERATION_TIMEOUT", "XPath 查询超时，请简化表达式。", retryable=True)
    keys = box[0] if box[0] is not None else []
    return {
        "expression": expression,
        "matchCount": len(keys),
        "nodeKeys": keys,
        "elapsedMs": int((time.monotonic() - started) * 1000),
    }
