from __future__ import annotations

import os
import secrets
import threading
import time
from pathlib import Path

from .adb import AdbClient, find_adb
from .audit import ActionLog
from .contracts import CoreInfo
from .devices import DeviceGate, DeviceRegistry
from .logcat import LogcatHub
from .media import MediaHub
from .mcp_catalog import ToolDispatcher
from .plugins import PluginRegistry
from .server import DEFAULT_PORT_START, CoreContext, bind_server, derive_session_token
from .settings import SettingsStore, default_data_dir
from .snapshots import CaptureCoordinator, SnapshotStore
from .uilogs import UiLogStore

PRODUCT_VERSION = "22.6.1"


def builtin_plugins_dir() -> Path:
    """内置插件源码在 repos/plugins，打包时被 PyInstaller 塞进包内 builtin_plugins。

    因此运行期先看包内目录（打包形态），再回落到工程目录（开发形态）；
    环境变量优先，供打包脚本与测试指向别处。
    """
    override = os.environ.get("LAYOUTSEE_BUILTIN_PLUGINS")
    if override:
        return Path(override)
    packaged = Path(__file__).resolve().parent / "builtin_plugins"
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[3] / "plugins"


def build_core(nonce: str, static_dir: Path | None = None, data_dir: Path | None = None, port_start: int = DEFAULT_PORT_START):
    """创建全部服务并原子绑定回环端口；返回 (context, server)。"""
    data_dir = data_dir or default_data_dir()
    settings = SettingsStore(data_dir)
    # Finder 启动的 GUI 应用看不到终端 PATH：若未显式配置且探测到候选路径，持久化一次。
    if not settings.adb_path():
        discovered = find_adb()
        if discovered:
            try:
                settings.update({"adbPath": discovered})
            except Exception:
                pass
    audit = ActionLog(data_dir / "audit")
    adb = AdbClient(resolver=settings.adb_path)
    gate = DeviceGate()
    registry = DeviceRegistry(adb, settings, audit, gate)
    store = SnapshotStore(secret=secrets.token_bytes(32))
    capture = CaptureCoordinator(adb, registry, store, gate)
    plugins = PluginRegistry(data_dir / "plugins", builtin_dir=builtin_plugins_dir(), product_version=PRODUCT_VERSION)
    dispatcher = ToolDispatcher(adb=adb, registry=registry, store=store, gate=gate, capture=capture, audit=audit, plugins=plugins)
    media = MediaHub(adb)
    ui_log = UiLogStore(data_dir)
    logcat = LogcatHub(adb)

    context = CoreContext(
        info=None,  # 端口绑定后写入
        nonce=nonce,
        session_token=derive_session_token(nonce),
        static_dir=static_dir,
        settings=settings,
        adb=adb,
        audit=audit,
        registry=registry,
        gate=gate,
        store=store,
        capture=capture,
        dispatcher=dispatcher,
        plugins_dir=data_dir / "plugins",
        data_dir=data_dir,
        plugins=plugins,
        media=media,
        ui_log=ui_log,
        logcat=logcat,
    )
    server = bind_server(context, port_start)
    context.info = CoreInfo(
        port=server.server_port,
        pid=os.getpid(),
        nonce=nonce,
        productVersion=PRODUCT_VERSION,
        apiVersion="1.0",
        snapshotSchemaVersion="1.0",
    )

    reaper = threading.Thread(target=_reap_media_loop, args=(media,), name="layoutsee-media-reaper", daemon=True)
    reaper.start()
    return context, server


def _reap_media_loop(media: MediaHub) -> None:
    while True:
        time.sleep(2.0)
        try:
            media.reap_idle()
        except Exception:
            pass
