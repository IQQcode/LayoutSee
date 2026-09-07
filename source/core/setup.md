# core 构建与启动

Python 依赖由 `pyproject.toml` 声明（pydantic、elementpath），由 uv 维护锁文件。开发环境可执行：

```bash
uv sync --project repos/core
uv run --project repos/core python -m layoutsee_core --nonce <64位小写十六进制随机数>
```

默认从 `33299` 开始尝试 10 个 loopback 端口，成功后只向标准输出写一行 READY。常用参数：

- `--static-dir <path>`：托管正式 Web 构建产物（打包时为 `resources/web`）。
- `--data-dir <path>`：覆盖数据目录（默认 `~/Library/Application Support/LayoutSee`）。
- `--port-start <n>`：端口起点。

单文件制品：

```bash
uv sync --project repos/core --extra packaging
uv run --project repos/core --extra packaging pyinstaller --name layoutsee-core --onedir --clean --noconfirm --paths repos/core/src --distpath repos/core/dist/arm64 --workpath repos/core/build/pyinstaller-arm64 --specpath repos/core/build/pyinstaller-spec repos/core/packaging/entrypoint.py
```

> 采用 onedir（非 onefile）：本机实测 onefile 每次启动需 7-8 秒自解压，首启动 19.9 秒超过 15 秒硬超时；onedir 首启动 8.1 秒、热启动 0.27 秒。决策见 `specs/[Story-0827]-mac-app/technical-design.md` §23.2。
