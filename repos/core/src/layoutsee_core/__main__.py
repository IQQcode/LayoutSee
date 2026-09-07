from __future__ import annotations

import argparse
import os
import re
import signal
import threading
from pathlib import Path

from .bootstrap import build_core
from .server import ready_line


def main() -> None:
    parser = argparse.ArgumentParser(description="LayoutSee Core")
    parser.add_argument("--nonce")
    parser.add_argument("--static-dir", type=Path)
    parser.add_argument("--port-start", type=int, default=33299)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--open", action="store_true", help="启动后自动用默认浏览器打开首页（需要 --static-dir）")
    args = parser.parse_args()
    nonce = args.nonce or os.environ.get("LAYOUTSEE_BOOT_NONCE", "")
    if not re.fullmatch(r"[a-f0-9]{64}", nonce):
        raise SystemExit("nonce 必须是 256 位十六进制随机数")

    context, server = build_core(nonce, args.static_dir, args.data_dir, args.port_start)
    context.registry.start()
    print(ready_line(context.info), flush=True)

    # 只有 Core 自己托管首页时才有可打开的页面；令牌由首页 meta 注入，URL 里不带任何密钥
    if args.open and args.static_dir:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{context.info.port}")

    def shutdown(_signum, _frame) -> None:
        context.media.stop_all()
        context.registry.stop()
        threading.Thread(target=server.shutdown, name="layoutsee-shutdown", daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    server.serve_forever(poll_interval=0.1)
    context.registry.stop()


if __name__ == "__main__":
    main()
