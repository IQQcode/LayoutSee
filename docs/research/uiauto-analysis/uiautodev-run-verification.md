# UIAutoDev 本地运行验证记录

## 环境

- 工作区：`/Users/jiazihui/Documents/AgentHubs/Workspace/LayoutSee/uiautodev`
- 操作系统：macOS Tahoe，Apple Silicon
- 系统 Python：3.12.4
- 仓库提交：`3da93ec`（2025-11-22）
- 真机条件：当前环境未发现已配置的 Android ADB 或 iOS WDA 设备，因此本次只能验证源码、Mock API 和启动链路，不能验证真实设备截图、层级树和 scrcpy 视频。

## 首次执行结果

### 1. 直接运行

执行：

```bash
python3 -m uiautodev --help
```

结果：失败，系统 Python 缺少 `click`：

```text
ModuleNotFoundError: No module named 'click'
```

执行测试：

```bash
python3 -m pytest -q
```

结果：失败，系统 Python 没有安装 `pytest`。

### 2. 依赖安装尝试

按 `pyproject.toml` 创建了仓库内 `.venv`，并尝试安装项目依赖。网络镜像能够获取大部分包，但项目声明的 `adbutils>=2.8.10,<3` 没有可直接使用的当前 Python 3.12 二进制，源码构建阶段被取消；镜像中的旧版 `adbutils` 又依赖无法获取的 `apkutils2`。因此没有把不完整依赖标记为可运行环境，也没有污染系统 Python。

这不是项目逻辑错误，但会影响在当前机器上“一键启动”的复现。建议使用项目文档支持的 Python 3.8+ 虚拟环境，并使用 Poetry/官方 PyPI，或提前准备匹配 Python 版本的 adbutils wheel。

### 3. 源码级验证

执行：

```bash
python3 -m compileall -q uiautodev tests e2etests examples
```

结果：通过（退出码 0）。说明当前源码在 Python 3.12 下语法层面完整。

仓库内已有可执行的 Mock 路由和测试设计：

- `/api/mock/list`
- `/api/mock/mock-serial/screenshot/0`
- `/api/mock/mock-serial/hierarchy`
- Android XML parser 的 bounds、display-id 测试

但由于 FastAPI、Pydantic、adbutils 等运行依赖没有完整落地，本次没有伪造测试通过结果。

## 二次执行结果

本次用户要求继续执行后，改用 `uv` 在仓库内创建 `.venv-run`，安装了 FastAPI、Pydantic、HTTPX、uvicorn、adbutils、pytest 等依赖。Pillow 在当前镜像下解包 macOS 动态库非常慢，因此为不连接真机的 Mock 验证准备了 `/tmp/uiautodev-stubs/` 临时兼容模块：它只提供导入所需的 `PIL`、`uiautomator2`、`wdapy` 最小接口，不修改项目源码，也不代表真实图像编码或设备连接能力。

### 1. CLI 入口

执行：

```bash
PYTHONPATH=/tmp/uiautodev-stubs:$PWD .venv-run/bin/python -m uiautodev --help
```

结果：成功，输出了 `android`、`ios`、`server`、`shutdown`、`version` 等命令。

### 2. 单元测试

执行：

```bash
PYTHONPATH=/tmp/uiautodev-stubs:$PWD .venv-run/bin/python -m pytest -q
```

结果：`9 passed, 1 warning in 0.34s`。通过项包括 Android XML bounds/display-id 解析、API info、Mock 设备列表、Mock 截图、Mock 层级树、Pydantic 布尔转换和触控控制器。唯一警告来自当前 Starlette 对 `httpx` TestClient 的弃用提示，不影响测试结果。

### 3. Mock 模式真实服务

执行：

```bash
UIAUTODEV_MOCK=1 \
PYTHONPATH=/tmp/uiautodev-stubs:$PWD \
.venv-run/bin/python -m uiautodev server \
  --no-browser --host 127.0.0.1 --port 20243
```

服务成功启动并监听 `http://127.0.0.1:20243`。以下请求均返回 HTTP 200：

```text
GET /api/info                         200
GET /api/android/list                 200
GET /api/android/mock-serial/hierarchy 200
GET /api/android/mock-serial/screenshot/0 200
GET /api/android/features             200
GET /shutdown                         200
```

返回内容核对结果：`/api/info` 报告 Darwin/Python 及 Android、iOS、Harmony 驱动；设备列表返回 `mock-serial`；层级树包含 `root`、`mock1`、`mock2` 及归一化 bounds；截图响应的媒体类型为 `image/jpeg`。截图字节来自临时桩的 `mock-image`，只证明路由、Driver、Response 链路正确，不能替代真实 Pillow JPEG 编码验证。

服务通过 `/shutdown` 正常退出，没有遗留监听进程。

## 建议的可复现命令

在依赖可获取、且不连接真实设备的情况下：

```bash
cd uiautodev
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip poetry
poetry install
UIAUTODEV_MOCK=1 uiauto.dev server --no-browser --host 127.0.0.1 --port 20242
```

然后验证：

```bash
curl http://127.0.0.1:20242/api/info
curl http://127.0.0.1:20242/api/mock/list
curl http://127.0.0.1:20242/api/mock/mock-serial/hierarchy
curl -I http://127.0.0.1:20242/api/mock/mock-serial/screenshot/0
```

真实 Android 设备需开启 USB 调试并可被 `adb devices` 看到；若 uiautomator2 服务不可用，可设置：

```bash
export UIAUTODEV_USE_ADB_DRIVER=1
```

真实 iOS 设备还需 usbmuxd、Developer Disk Image、已签名 WDA，iOS 17+ 需要前台或后台运行 `ios tunnel start --userspace`。这些前置条件满足后，再验证 `/api/ios/list`、`/{serial}/hierarchy` 和截图接口。

## 启动判断

项目的启动入口和默认端口已经实际验证：在临时兼容模块和 Mock 模式下，CLI、单元测试、FastAPI 服务和主要 API 均可运行；真实设备端到端验证仍需要可用的 Pillow、uiautomator2/WDA 运行时及 Android/iOS 设备。研究报告中的架构结论来自本地源码、仓库测试、GitHub 页面和语雀文档的交叉核对。
