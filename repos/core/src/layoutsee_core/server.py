from __future__ import annotations

import hmac
import json
import mimetypes
import os
import queue
import re
import struct
import sys
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .contracts import CoreInfo
from .errors import CoreError
from .mcp_catalog import ToolDispatcher, catalog
from .settings import SettingsStore

SESSION_TOKEN_CONTEXT = "layoutsee-ui-v1"
SESSION_PLACEHOLDER = b"__LAYOUTSEE_SESSION__"
MAX_BODY_BYTES = 1_048_576

# 主文档 CSP：frame-src 'self' 是插件 iframe 的前提，插件页由同源 /plugin-assets/ 提供
MAIN_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self' ws://127.0.0.1:*; frame-src 'self'; object-src 'none'; base-uri 'none'"
)
PLUGIN_ASSET_PATTERN = re.compile(r"^/plugin-assets/([^/]+)/(.+)$")
PLUGIN_ASSET_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}

DEVICE_SUB_PATTERN = re.compile(r"^/api/v1/devices/([^/]+)/([^/]+)$")
DEVICE_SUB2_PATTERN = re.compile(r"^/api/v1/devices/([^/]+)/([^/]+)/([^/]+)$")
SNAPSHOT_SUB_PATTERN = re.compile(r"^/api/v1/snapshots/([^/]+)/([^/]+)$")
MCP_DEVICE_PATTERN = re.compile(r"^/mcp/([^/]+)/(sse|message)$")

# 终端：命令整串交给 adb shell 执行，输出与耗时都设硬上限，避免单次请求拖住设备闸门
SHELL_COMMAND_MAX_CHARS = 2000
SHELL_DEFAULT_TIMEOUT_MS = 15_000
SHELL_MAX_TIMEOUT_MS = 60_000
SHELL_OUTPUT_MAX_BYTES = 256 * 1024


def _clip_output(raw: bytes) -> tuple[str, bool]:
    truncated = len(raw) > SHELL_OUTPUT_MAX_BYTES
    return raw[:SHELL_OUTPUT_MAX_BYTES].decode("utf-8", errors="replace"), truncated


@dataclass
class CoreContext:
    info: CoreInfo
    nonce: str
    session_token: str
    static_dir: Path | None
    settings: SettingsStore
    adb: Any
    audit: Any
    registry: Any
    gate: Any
    store: Any
    capture: Any
    dispatcher: ToolDispatcher
    plugins_dir: Path
    data_dir: Path
    plugins: Any = field(default=None)
    media: Any = field(default=None)
    ui_log: Any = field(default=None)
    logcat: Any = field(default=None)


def derive_session_token(nonce: str) -> str:
    return hmac.new(bytes.fromhex(nonce), SESSION_TOKEN_CONTEXT.encode("ascii"), "sha256").hexdigest()


def struct_pack_keepalive() -> bytes:
    """媒体流心跳记录：pts=0、len=0，客户端读到后跳过。"""
    return struct.pack(">QI", 0, 0)


class LoopbackServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(self, address: tuple[str, int], handler: type[BaseHTTPRequestHandler], *, context: CoreContext):
        super().__init__(address, handler)
        self.context = context


class CoreRequestHandler(BaseHTTPRequestHandler):
    server: LoopbackServer

    @property
    def context(self) -> CoreContext:
        return self.server.context

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def version_string(self) -> str:
        return "LayoutSeeCore/0.1"

    def send_response(self, code, message=None):
        self._last_status = code
        super().send_response(code, message)

    def send_error(self, code, message=None, explain=None):
        # 框架层错误（如未知方法 501）后连接状态不可信，强制关闭避免污染 keep-alive
        self.close_connection = True
        super().send_error(code, message, explain)

    def end_headers(self) -> None:
        # 插件资源用独立策略覆盖，避免与主文档策略叠加成交集
        self.send_header("Content-Security-Policy", getattr(self, "_csp_override", None) or MAIN_CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        super().end_headers()

    # ---------- 响应助手 ----------

    def _request_id(self) -> str:
        value = self.headers.get("X-Request-Id")
        return value if value and len(value) <= 64 else f"req-{uuid.uuid4().hex}"

    def _json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _envelope(self, data: object) -> None:
        self._json(HTTPStatus.OK, {"ok": True, "data": data, "requestId": self._request_id()})

    def _error(self, error: CoreError) -> None:
        self._json(error.status, {"ok": False, "error": error.to_dict(), "requestId": self._request_id()})

    def _png(self, payload: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    # ---------- chunked 流式响应 ----------

    def _chunked_start(self, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

    def _chunk(self, payload: bytes) -> bool:
        try:
            self.wfile.write(f"{len(payload):x}\r\n".encode("ascii") + payload + b"\r\n")
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

    def _chunked_end(self) -> None:
        try:
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _read_body(self) -> dict[str, object]:
        self._drain_request_body()
        raw = self._body_raw if self._body_raw else b"{}"
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except ValueError as error:
            raise CoreError("INVALID_ARGUMENT", "请求体不是合法 JSON。") from error
        if not isinstance(payload, dict):
            raise CoreError("INVALID_ARGUMENT", "请求体必须是 JSON 对象。")
        return payload

    def _drain_request_body(self) -> None:
        """读走 Content-Length 声明的请求体并缓存。

        不排空 body 的话，残留字节会被 keep-alive 上的下一个请求当成方法名解析，
        表现为随机的 501 Unsupported method（真机踩坑：抓取成功后快照详情 501）。
        """
        if self._body_drained:
            return
        self._body_drained = True
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            self._body_raw = b""
            return
        if length > MAX_BODY_BYTES:
            raise CoreError("INVALID_ARGUMENT", "请求体过大。")
        self._body_raw = self.rfile.read(length)

    def _require_session(self) -> None:
        token = self.headers.get("X-LayoutSee-Session")
        if not token or not hmac.compare_digest(str(token), self.context.session_token):
            raise CoreError("PERMISSION_REQUIRED", "会话校验失败，写操作已拒绝。", details={"hint": "请通过 LayoutSee 应用发起操作"})

    def _allowed_origins(self) -> tuple[str, ...]:
        port = self.context.info.port
        return (f"http://127.0.0.1:{port}", f"http://localhost:{port}")

    def _require_local_caller(self) -> None:
        """Host 与 Origin 双校验，读写都做。

        浏览器宿主下 session token 由 index.html 注入，同机任意网页都能对 loopback 发简单请求，
        单靠 token 不足以拦住副作用。Host 校验同时挡住 DNS rebinding（恶意域名解析到 127.0.0.1，
        但 Host 头仍是该域名）。Origin 缺失属正常情况（同源导航、MCP 客户端、curl），放行。
        """
        port = self.context.info.port
        host = (self.headers.get("Host") or "").strip()
        if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            raise CoreError("PERMISSION_REQUIRED", "请求 Host 不是本机回环地址，已拒绝。", details={"hint": "请通过 http://127.0.0.1 访问"})
        origin = (self.headers.get("Origin") or "").strip()
        if origin and origin not in self._allowed_origins():
            raise CoreError("PERMISSION_REQUIRED", "请求来源不在允许列表，已拒绝。", details={"hint": "请在 LayoutSee 界面内操作"})

    def _dispatch_api(self, path: str) -> None:
        if path == "/health/live":
            self._json(HTTPStatus.OK, {"ready": True})
            return
        if path == "/health/ready":
            self._json(HTTPStatus.OK, {"ready": True})
            return
        if path == "/api/v1/info":
            self._envelope(self.context.info.model_dump())
            return
        if path == "/api/v1/devices":
            self._envelope(self.context.registry.snapshot())
            return
        if path == "/api/v1/devices/refresh":
            self.context.registry.refresh()
            self._envelope(self.context.registry.snapshot())
            return
        if path == "/api/v1/settings":
            self._envelope(self.context.settings.get())
            return
        if path == "/api/v1/paths":
            # 浏览器宿主打不开本地目录，只能把路径显示出来让用户自己去
            self._envelope({
                "dataDir": str(self.context.data_dir),
                "logsDir": str(self.context.data_dir / "logs"),
                "pluginsDir": str(self.context.plugins_dir),
            })
            return
        if path == "/api/v1/plugins":
            self._envelope(self._list_plugins())
            return
        if path == "/api/v1/plugins/index":
            refresh = parse_qs(urlparse(self.path).query).get("refresh", ["false"])[0].lower() in ("1", "true", "yes")
            self._envelope(self._plugin_registry().index(refresh=refresh))
            return
        if path == "/api/v1/mcp/tools":
            self._envelope(catalog(self.context.plugins))
            return

        device_sub2 = DEVICE_SUB2_PATTERN.match(path)
        if device_sub2:
            device_id, sub1, sub2 = (unquote(part) for part in device_sub2.groups())
            if sub1 == "snapshots" and sub2 == "latest":
                record = self.context.store.latest_for(device_id)
                self._envelope({"snapshotId": record["snapshot"]["snapshotId"] if record else None, **({"synchronization": record["snapshot"]["synchronization"], "createdAt": record["snapshot"]["createdAt"]} if record else {})})
                return
            if sub1 == "media" and sub2 == "capabilities":
                self._envelope(self._media_capabilities())
                return
            if sub1 == "media" and sub2 == "stream":
                self._media_stream(device_id)
                return

        device_sub = DEVICE_SUB_PATTERN.match(path)
        if device_sub:
            device_id, sub = unquote(device_sub.group(1)), device_sub.group(2)
            if sub == "diagnostics":
                self._envelope(self.context.adb.diagnostics(self.context.registry.serial_for(device_id)))
                return
            if sub == "current-app":
                self._envelope(self.context.adb.current_app(self.context.registry.serial_for(device_id)))
                return
            if sub == "apps":
                params = parse_qs(urlparse(self.path).query)
                query = params.get("q", [""])[0]
                include_system = params.get("includeSystem", ["false"])[0] in ("1", "true", "yes")
                items = self.context.adb.apps(self.context.registry.serial_for(device_id), query, include_system)
                self._envelope({"items": items, "query": query, "includeSystem": include_system})
                return
            if sub == "screenshot":
                self._png(self.context.adb.screenshot(self.context.registry.serial_for(device_id)))
                return
            if sub == "window-size":
                self._envelope(self.context.adb.window_size(self.context.registry.serial_for(device_id)))
                return
            if sub == "logcat":
                params = parse_qs(urlparse(self.path).query)
                after = params.get("after", [""])[0]
                limit = params.get("limit", ["500"])[0]
                self._envelope(self._read_logcat(device_id, after, limit))
                return

        snapshot_sub = SNAPSHOT_SUB_PATTERN.match(path)
        if snapshot_sub:
            snapshot_id, sub = unquote(snapshot_sub.group(1)), snapshot_sub.group(2)
            if sub == "screenshot":
                record = self.context.store.get(snapshot_id)
                png = record.get("png")
                if not png:
                    raise CoreError("MEDIA_UNAVAILABLE", "该快照没有可用截图。")
                self._png(png)
                return
        if path.startswith("/api/v1/snapshots/"):
            snapshot_id = unquote(path.removeprefix("/api/v1/snapshots/"))
            if snapshot_id and "/" not in snapshot_id:
                record = self.context.store.get(snapshot_id)
                self._envelope(record["snapshot"])
                return

        mcp_match = MCP_DEVICE_PATTERN.match(path)
        if mcp_match:
            device_id, mode = unquote(mcp_match.group(1)), mcp_match.group(2)
            if mode == "sse":
                self._mcp_sse(device_id)
                return
            if mode == "message":
                self._mcp_message(device_id)
                return
        raise CoreError("CORE_UNAVAILABLE", f"未实现的接口：{path}")

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_OPTIONS(self) -> None:
        # BaseHTTPRequestHandler 默认对未实现方法返回 501 HTML，前端会显示「请求失败（501）」
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, PUT, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------- 写接口 ----------

    def _dispatch_write(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/v1/devices/refresh":
            self.context.registry.refresh()
            self._envelope(self.context.registry.snapshot())
            return
        if path == "/api/v1/plugins/reload":
            self._require_session()
            self._envelope(self._list_plugins(refresh=True))
            return
        if path == "/api/v1/settings":
            self._require_session()
            self._envelope(self.context.settings.update(self._read_body()))
            return
        if path == "/api/v1/ui-logs":
            self._require_session()
            self._envelope(self._append_ui_logs(self._read_body()))
            return
        device_sub = DEVICE_SUB_PATTERN.match(path)
        if device_sub:
            device_id, sub = unquote(device_sub.group(1)), device_sub.group(2)
            if sub == "actions":
                self._require_session()
                self._envelope(self._execute_action(device_id, self._read_body()))
                return
            if sub == "snapshots":
                self._require_session()
                key = self.headers.get("Idempotency-Key")
                self._envelope(self._capture(device_id, key))
                return
            if sub == "readonly":
                self._require_session()
                body = self._read_body()
                self._envelope(self.context.registry.set_readonly(device_id, bool(body.get("readonly"))))
                return
            if sub == "shell":
                self._require_session()
                self._envelope(self._execute_shell(device_id, self._read_body()))
                return
        device_sub2 = DEVICE_SUB2_PATTERN.match(path)
        if device_sub2:
            device_id, sub1, sub2 = (unquote(part) for part in device_sub2.groups())
            if sub1 == "logcat" and sub2 == "clear":
                self._require_session()
                self._envelope(self._clear_logcat(device_id, self._read_body()))
                return
        snapshot_sub = SNAPSHOT_SUB_PATTERN.match(path)
        if snapshot_sub:
            snapshot_id, sub = unquote(snapshot_sub.group(1)), snapshot_sub.group(2)
            record = self.context.store.get(snapshot_id)
            body = self._read_body()
            if sub == "xpath":
                from .xpath import query_record

                self._envelope(query_record(record, str(body.get("expression", ""))))
                return
            if sub == "selectors":
                from .selectors import generate_selectors

                self._envelope(generate_selectors(record, str(body.get("nodeKey", ""))))
                return
            if sub == "summary":
                from .summary import summarize

                self._envelope(summarize(record, snapshot_id))
                return
            if sub == "diagnostics":
                from .diagnostics import diagnose

                self._envelope(diagnose(record, snapshot_id))
                return
        mcp_match = MCP_DEVICE_PATTERN.match(path)
        if mcp_match:
            device_id, mode = unquote(mcp_match.group(1)), mcp_match.group(2)
            self._mcp_message(device_id)
            return
        raise CoreError("CORE_UNAVAILABLE", f"未实现的接口：{path}")

    def _handle(self) -> None:
        # 每个请求重置 body 缓存；任何带 body 的请求都必须排空，否则污染 keep-alive
        self._body_drained = False
        self._body_raw = b""
        self._csp_override = None  # keep-alive 复用 handler 实例，插件策略不能泄漏到下一个请求
        started = time.monotonic()
        status = HTTPStatus.INTERNAL_SERVER_ERROR
        error_code: str | None = None
        try:
            path = urlparse(self.path).path
            if path.startswith("/api/") or path.startswith("/health/"):
                self._drain_request_body()
                self._require_local_caller()
                if self.command == "GET":
                    self._dispatch_api(path)
                else:
                    self._dispatch_write()
                return
            if path.startswith("/mcp/"):
                self._drain_request_body()
                self._require_local_caller()
                if self.command == "GET":
                    self._dispatch_api(path)
                else:
                    self._dispatch_write()
                return
            if path.startswith("/plugin-assets/"):
                self._drain_request_body()
                self._require_local_caller()
                if self.command != "GET":
                    raise CoreError("CORE_UNAVAILABLE", f"未实现的接口：{path}")
                self._serve_plugin_asset(path)
                return
            if self.command == "GET":
                self._serve_static()
                return
            raise CoreError("CORE_UNAVAILABLE", f"未实现的接口：{path}")
        except CoreError as error:
            status = error.status
            error_code = error.code
            self._error(error)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            status = HTTPStatus.SERVICE_UNAVAILABLE
            error_code = "INTERNAL_ERROR"
            self._error(CoreError("CORE_UNAVAILABLE", "Core 内部错误，请查看日志。", retryable=True))
        finally:
            self._log_request(started, status, error_code)

    def _log_request(self, started: float, status: HTTPStatus, error_code: str | None) -> None:
        """请求级访问日志走 stderr，由壳收集到 logs/<date>-core.log。"""
        duration_ms = int((time.monotonic() - started) * 1000)
        actual = getattr(self, "_last_status", status)
        line = f"[request] {self.command} {self.path} -> {getattr(actual, 'value', actual)} {duration_ms}ms"
        if error_code:
            line += f" {error_code}"
        print(line, file=sys.stderr, flush=True)

    # ---------- 业务处理 ----------

    def _execute_action(self, device_id: str, body: dict[str, object]) -> dict[str, object]:
        action_type = str(body.get("type", ""))
        allowed = {"tap", "swipe", "input_text", "press_key", "start_app", "stop_app", "rotate", "clear_app", "uninstall_app"}
        if action_type not in allowed:
            raise CoreError("INVALID_ARGUMENT", f"不支持的动作：{action_type}")
        source = str(body.get("source", "ui"))
        if source not in ("ui", "mcp", "plugin"):
            raise CoreError("INVALID_ARGUMENT", "动作来源非法。")
        action_id = str(body.get("actionId") or uuid.uuid4().hex[:12])
        request_id = self._request_id()
        # source=plugin 时带上 pluginId，审计才能回溯到具体插件
        plugin_id = str(body.get("pluginId") or "") or None
        payload = dict(body.get("payload") or body)
        payload.pop("type", None)
        payload.pop("source", None)
        payload.pop("actionId", None)
        payload.pop("pluginId", None)

        if self.context.registry.is_readonly(device_id):
            self.context.audit.requested(action_id=action_id, source=source, device_id=device_id, action_type=action_type, payload=payload, request_id=request_id, decision="blocked-readonly", plugin_id=plugin_id)
            raise CoreError("READ_ONLY_MODE", "设备处于只读模式，写操作已被拦截。", details={"hint": "关闭只读模式后重试"})
        serial = self.context.registry.serial_for(device_id)
        self.context.audit.requested(action_id=action_id, source=source, device_id=device_id, action_type=action_type, payload=payload, request_id=request_id, decision="allowed", plugin_id=plugin_id)
        started = time.monotonic()
        try:
            with self.context.gate.acquire(device_id):
                result = self.context.adb.action(serial, action_type, payload)
        except CoreError as error:
            self.context.audit.result(action_id=action_id, result_code=error.code, duration_ms=int((time.monotonic() - started) * 1000), request_id=request_id)
            raise
        self.context.audit.result(action_id=action_id, result_code="ok", duration_ms=int((time.monotonic() - started) * 1000), request_id=request_id)
        return {"actionId": action_id, **result}

    def _execute_shell(self, device_id: str, body: dict[str, object]) -> dict[str, object]:
        command = str(body.get("command", "")).strip()
        if not command:
            raise CoreError("INVALID_ARGUMENT", "命令不能为空。")
        if len(command) > SHELL_COMMAND_MAX_CHARS:
            raise CoreError("INVALID_ARGUMENT", f"命令过长，最多 {SHELL_COMMAND_MAX_CHARS} 个字符。")
        # 超时上限锁在 60s：终端是同步请求，再长会把 ThreadingHTTPServer 的连接和设备闸门一起占住
        try:
            timeout_ms = int(body.get("timeoutMs") or SHELL_DEFAULT_TIMEOUT_MS)
        except (TypeError, ValueError):
            raise CoreError("INVALID_ARGUMENT", "timeoutMs 必须是整数毫秒。") from None
        timeout_ms = min(max(timeout_ms, 1000), SHELL_MAX_TIMEOUT_MS)

        action_id = str(body.get("actionId") or uuid.uuid4().hex[:12])
        request_id = self._request_id()
        source = str(body.get("source", "ui"))
        if source not in ("ui", "mcp", "plugin"):
            raise CoreError("INVALID_ARGUMENT", "动作来源非法。")
        # 命令内容按 device_shell 规则脱敏（只留长度与哈希），stdout 一律不入审计
        payload = {"command": command, "timeoutMs": timeout_ms}
        if self.context.registry.is_readonly(device_id):
            self.context.audit.requested(action_id=action_id, source=source, device_id=device_id, action_type="device_shell", payload=payload, request_id=request_id, decision="blocked-readonly")
            raise CoreError("READ_ONLY_MODE", "设备处于只读模式，终端命令已被拦截。", details={"hint": "关闭只读模式后重试"})
        serial = self.context.registry.serial_for(device_id)
        self.context.audit.requested(action_id=action_id, source=source, device_id=device_id, action_type="device_shell", payload=payload, request_id=request_id, decision="allowed")
        started = time.monotonic()
        try:
            with self.context.gate.acquire(device_id):
                result = self.context.adb.run(["shell", command], serial=serial, timeout=timeout_ms / 1000, check=False)
        except CoreError as error:
            self.context.audit.result(action_id=action_id, result_code=error.code, duration_ms=int((time.monotonic() - started) * 1000), request_id=request_id)
            raise
        duration_ms = int((time.monotonic() - started) * 1000)
        self.context.audit.result(action_id=action_id, result_code="ok" if result.returncode == 0 else "shell-nonzero", duration_ms=duration_ms, request_id=request_id)
        stdout, stdout_truncated = _clip_output(result.stdout)
        stderr, stderr_truncated = _clip_output(result.stderr)
        return {
            "actionId": action_id,
            "command": command,
            "exitCode": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": stdout_truncated or stderr_truncated,
            "durationMs": duration_ms,
            "timeoutMs": timeout_ms,
        }

    def _logcat_hub(self) -> Any:
        hub = self.context.logcat
        if hub is None:
            raise CoreError("CORE_UNAVAILABLE", "日志读取未装配。")
        return hub

    def _read_logcat(self, device_id: str, after: str, limit: str) -> dict[str, object]:
        """读日志是只读操作：不过设备闸门、不入审计，只做参数收敛。"""
        try:
            cursor = int(after) if after not in ("", None) else None
            count = int(limit)
        except (TypeError, ValueError):
            raise CoreError("INVALID_ARGUMENT", "after / limit 必须是整数。") from None
        serial = self.context.registry.serial_for(device_id)
        return self._logcat_hub().read(device_id, serial, after=cursor, limit=count)

    def _clear_logcat(self, device_id: str, body: dict[str, object]) -> dict[str, object]:
        source = str(body.get("source", "ui"))
        if source not in ("ui", "mcp", "plugin"):
            raise CoreError("INVALID_ARGUMENT", "动作来源非法。")
        plugin_id = str(body.get("pluginId") or "") or None
        action_id = str(body.get("actionId") or uuid.uuid4().hex[:12])
        request_id = self._request_id()
        # 清空设备日志会丢掉别人正在看的数据，按写操作对待：只读拦截 + 审计
        if self.context.registry.is_readonly(device_id):
            self.context.audit.requested(action_id=action_id, source=source, device_id=device_id, action_type="logcat_clear", payload={}, request_id=request_id, decision="blocked-readonly", plugin_id=plugin_id)
            raise CoreError("READ_ONLY_MODE", "设备处于只读模式，清空日志已被拦截。", details={"hint": "关闭只读模式后重试"})
        serial = self.context.registry.serial_for(device_id)
        self.context.audit.requested(action_id=action_id, source=source, device_id=device_id, action_type="logcat_clear", payload={}, request_id=request_id, decision="allowed", plugin_id=plugin_id)
        started = time.monotonic()
        try:
            result = self._logcat_hub().clear(device_id, serial)
        except CoreError as error:
            self.context.audit.result(action_id=action_id, result_code=error.code, duration_ms=int((time.monotonic() - started) * 1000), request_id=request_id)
            raise
        self.context.audit.result(action_id=action_id, result_code="ok", duration_ms=int((time.monotonic() - started) * 1000), request_id=request_id)
        return {"actionId": action_id, **result}

    def _capture(self, device_id: str, idempotency_key: str | None) -> dict[str, object]:
        record = self.context.capture.capture(device_id, idempotency_key)
        snapshot = record["snapshot"]
        return {
            "snapshotId": snapshot["snapshotId"],
            "deviceId": snapshot["deviceId"],
            "createdAt": snapshot["createdAt"],
            "synchronization": snapshot["synchronization"],
            "hierarchyAccuracy": snapshot["hierarchyAccuracy"],
            "nodeCount": len(snapshot["nodes"]),
            "warnings": snapshot["warnings"],
            "windowSizePx": snapshot["windowSizePx"],
        }

    def _media_capabilities(self) -> dict[str, object]:
        interval = int(self.context.settings.get().get("screenshotFallbackIntervalMs", 800))
        payload = self.context.media.capabilities() if self.context.media is not None else {"mode": "screenshot", "live": False, "reason": "媒体服务未装配。"}
        payload["screenshotIntervalMs"] = interval
        return payload

    def _media_stream(self, device_id: str) -> None:
        """scrcpy H.264 记录流：头 LSS1(4s) + width/height/fps(u32)，之后每帧 [pts u64][len u32][payload]。"""
        if self.context.media is None:
            raise CoreError("MEDIA_UNAVAILABLE", "媒体服务未装配。")
        serial = self.context.registry.serial_for(device_id)
        fps_cap = int(self.context.settings.get().get("videoFpsCap", 24))
        _, subscriber = self.context.media.stream(serial, fps_cap)
        keepalive = struct_pack_keepalive()
        self.close_connection = True  # 长推流连接不复用，结束即断开
        self._chunked_start("application/octet-stream")
        try:
            while True:
                try:
                    record = subscriber.queue.get(timeout=5.0)
                except queue.Empty:
                    if not self._chunk(keepalive):
                        break
                    continue
                if record is None:
                    break
                if not self._chunk(record):
                    break
        finally:
            self.context.media.release(serial, subscriber)
            self._chunked_end()

    def _append_ui_logs(self, body: dict[str, object]) -> dict[str, object]:
        if self.context.ui_log is None:
            return {"accepted": 0}
        entries = body.get("entries")
        if not isinstance(entries, list):
            raise CoreError("INVALID_ARGUMENT", "entries 必须是数组。")
        if len(entries) > 100:
            raise CoreError("INVALID_ARGUMENT", "单批日志不能超过 100 条。")
        normalized: list[dict[str, object]] = []
        for entry in entries[:100]:
            if not isinstance(entry, dict):
                continue
            normalized.append({
                "tag": str(entry.get("tag", ""))[:120],
                "level": str(entry.get("level", "info"))[:12],
                "message": str(entry.get("message", ""))[:2000],
                "timestampMs": entry.get("timestampMs") if isinstance(entry.get("timestampMs"), int) else int(time.time() * 1000),
            })
        self.context.ui_log.append(normalized)
        return {"accepted": len(normalized)}

    def _plugin_registry(self) -> Any:
        registry = self.context.plugins
        if registry is None:
            raise CoreError("CORE_UNAVAILABLE", "插件索引未装配。")
        return registry

    def _list_plugins(self, *, refresh: bool = False) -> dict[str, object]:
        """v0 兼容视图：由索引派生，只暴露首个工作台 Tab 入口。"""
        index = self._plugin_registry().index(refresh=refresh)
        items: list[dict[str, object]] = []
        for entry in index.get("items", []):
            tabs = (entry.get("contributions") or {}).get("workbenchTabs") or []
            item: dict[str, object] = {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "version": entry.get("version"),
                "entry": tabs[0].get("entry") if tabs else None,
                "permissions": entry.get("permissions") or [],
                "status": "loaded" if entry.get("status") == "ready" else entry.get("status"),
            }
            if entry.get("error"):
                item["error"] = entry["error"].get("message")
            items.append(item)
        return {"items": items, "directory": index.get("directory")}

    # ---------- 静态资源与 SPA 回退 ----------

    def _serve_static(self) -> None:
        static_dir = self.context.static_dir
        if static_dir is None:
            body = b"<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>LayoutSee Core</title><body><main><h1>LayoutSee Core</h1></main></body></html>"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        path = urlparse(self.path).path
        relative = path.lstrip("/") or "index.html"
        candidate = (static_dir / relative).resolve()
        if candidate.is_file() and str(candidate).startswith(str(static_dir.resolve())):
            self._send_file(candidate)
            return
        index = static_dir / "index.html"
        if index.is_file():
            self._send_file(index)
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"code": "CORE_UNAVAILABLE", "message": "页面资源缺失。", "retryable": False}, "requestId": self._request_id()})

    def _send_file(self, path: Path) -> None:
        content = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        is_index = path.name == "index.html"
        if is_index:
            # 浏览器宿主没有 preload，会话令牌只能随首页下发。用 meta 而非内联 script：
            # CSP 是 script-src 'self'，内联脚本会被拦掉。
            content = content.replace(SESSION_PLACEHOLDER, self.context.session_token.encode("ascii"))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        if is_index:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    # ---------- 插件资源托管 ----------

    def _plugin_csp(self) -> str:
        """插件页策略。iframe 用 sandbox="allow-scripts"（无 allow-same-origin），
        文档 origin 是 opaque，CSP 里的 'self' 匹配不到任何来源，所以必须写显式回环 origin。
        connect-src 'none' 让插件无法自行发网络请求，全部能力只能走 postMessage 桥。
        """
        port = self.context.info.port
        origins = f"http://127.0.0.1:{port} http://localhost:{port}"
        return (
            f"default-src 'none'; script-src {origins}; style-src {origins} 'unsafe-inline'; "
            f"img-src {origins} data: blob:; font-src {origins} data:; connect-src 'none'; "
            f"frame-ancestors {origins}; base-uri 'none'; form-action 'none'"
        )

    def _serve_plugin_asset(self, path: str) -> None:
        match = PLUGIN_ASSET_PATTERN.match(path)
        if match is None:
            raise CoreError("PLUGIN_NOT_FOUND", "插件资源路径不完整。")
        plugin_id, asset_path = unquote(match.group(1)), unquote(match.group(2))
        resolved = self._plugin_registry().resolve_asset(plugin_id, asset_path)
        content = resolved.read_bytes()
        self._csp_override = self._plugin_csp()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", PLUGIN_ASSET_TYPES.get(resolved.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    # ---------- MCP over SSE ----------

    def _mcp_sse(self, device_id: str) -> None:
        self.context.registry.device(device_id)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        endpoint = f"/mcp/{device_id}/message"
        self.wfile.write(f"event: endpoint\ndata: {endpoint}\n\n".encode("utf-8"))
        self.wfile.flush()
        try:
            while True:
                time.sleep(15)
                self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return

    def _mcp_message(self, device_id: str) -> None:
        try:
            body = self._read_body()
        except CoreError:
            self._json(HTTPStatus.BAD_REQUEST, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return
        request_id = body.get("id")
        method = str(body.get("method", ""))
        params = body.get("params") if isinstance(body.get("params"), dict) else {}
        response: dict[str, object] = {"jsonrpc": "2.0", "id": request_id}

        try:
            if method == "initialize":
                response["result"] = {
                    "protocolVersion": str(params.get("protocolVersion") or "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "layoutsee", "version": "0.1.0"},
                }
            elif method == "notifications/initialized":
                self._json(HTTPStatus.ACCEPTED, {})
                return
            elif method == "tools/list":
                tools = [{"name": item["name"], "description": item["description"], "inputSchema": item["inputSchema"]} for item in catalog(self.context.plugins)["tools"]]
                response["result"] = {"tools": tools}
            elif method == "tools/call":
                name = str(params.get("name", ""))
                arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
                try:
                    result = self.context.dispatcher.call(device_id, name, arguments, source="mcp", request_id=self._request_id())
                    response["result"] = {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}], "isError": False}
                except CoreError as error:
                    payload = {"ok": False, "error": error.to_dict()}
                    response["result"] = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "isError": True}
            elif method == "ping":
                response["result"] = {}
            else:
                response["error"] = {"code": -32601, "message": f"Method not found: {method}"}
        except CoreError as error:
            response["error"] = {"code": -32603, "message": error.message}
        self._json(HTTPStatus.OK, response)


def bind_server(context: CoreContext, port_start: int = 33299, attempts: int = 10) -> LoopbackServer:
    last_error: OSError | None = None
    for port in range(port_start, port_start + attempts):
        try:
            return LoopbackServer(("127.0.0.1", port), CoreRequestHandler, context=context)
        except OSError as error:
            last_error = error
    raise RuntimeError("CORE_PORT_EXHAUSTED") from last_error


def ready_line(info: CoreInfo) -> str:
    return f"READY {json.dumps(info.model_dump(), ensure_ascii=False, separators=(',', ':'))}"
