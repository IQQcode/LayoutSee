import { app, BrowserWindow, clipboard, dialog, ipcMain, Menu, nativeTheme, session, shell } from "electron";
import { access, mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { KernelSupervisor } from "./kernel-supervisor.mjs";
import { DailyFileLogger } from "./logging.mjs";

const currentDirectory = dirname(fileURLToPath(import.meta.url));
const bootstrapPath = join(currentDirectory, "../bootstrap/index.html");
const preloadPath = join(currentDirectory, "../preload/index.cjs");
const bootstrapUrl = pathToFileURL(bootstrapPath).href;

const TRUSTED_EXTERNAL_URLS = Object.freeze({
  "adb-help": "https://developer.android.com/tools/releases/platform-tools",
  "mcp-client-help": "https://modelcontextprotocol.io/docs/develop/build-client",
});

let mainWindow = null;
let supervisor = null;
let logger = null;
let isQuitting = false;
let lastSystemTheme = "light";
const recentLogLines = [];

function rememberLog(channel, message) {
  recentLogLines.push(`[${channel}] ${message}`);
  if (recentLogLines.length > 40) recentLogLines.shift();
}

function logToFile(channel, message, secrets = []) {
  const line = String(message);
  rememberLog(channel, line);
  logger?.write(channel, line, secrets);
}

function isTrustedFrame(frame) {
  if (!frame) return false;
  const url = frame.url;
  if (url === bootstrapUrl) return true;
  return Boolean(supervisor?.origin && url.startsWith(`${supervisor.origin}/`));
}

function assertTrustedFrame(event) {
  if (!isTrustedFrame(event.senderFrame)) throw new Error("IPC_ORIGIN_REJECTED");
}

function assertString(value, name, { max = 512 } = {}) {
  if (typeof value !== "string" || value.length === 0 || value.length > max) throw new Error("IPC_ARGUMENT_INVALID");
  return value;
}

function sendState(state) {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send("kernel:state", state);
}

function sendTheme(theme) {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send("kernel:theme", theme);
}

function readSystemTheme() {
  return nativeTheme.shouldUseDarkColors ? "dark" : "light";
}

function kernelSessionPayload() {
  return { ...supervisor.snapshot(), sessionToken: supervisor.sessionToken() };
}

function buildSanitizedDiagnostics() {
  const kernel = supervisor.diagnostics();
  const lines = [
    `LayoutSee ${app.getVersion()} (${process.platform} ${process.arch})`,
    `Electron ${process.versions.electron} / Chromium ${process.versions.chrome}`,
    `Core 状态: ${kernel.state}${kernel.detail ? ` (${kernel.detail})` : ""}`,
    `重启尝试: ${kernel.restartAttempt}`,
    `Core 进程: ${kernel.hasCoreProcess ? "存在" : "不存在"}`,
    `服务地址: ${kernel.origin ?? "不可用"}`,
  ];
  if (recentLogLines.length > 0) {
    lines.push("", "最近日志（已脱敏）:", ...recentLogLines.slice(-12));
  }
  return lines.join("\n");
}

function installIpc() {
  ipcMain.handle("app:info", (event) => {
    assertTrustedFrame(event);
    return { version: app.getVersion(), platform: process.platform, arch: process.arch };
  });

  ipcMain.handle("kernel:session", (event) => {
    assertTrustedFrame(event);
    return kernelSessionPayload();
  });

  ipcMain.handle("kernel:retry", async (event) => {
    assertTrustedFrame(event);
    await loadBootstrap();
    await startKernel();
  });

  ipcMain.handle("kernel:diagnostics", (event) => {
    assertTrustedFrame(event);
    return buildSanitizedDiagnostics();
  });

  ipcMain.handle("diagnostics:copy", (event) => {
    assertTrustedFrame(event);
    clipboard.writeText(buildSanitizedDiagnostics());
    return { copied: true };
  });

  ipcMain.handle("logs:open", async (event) => {
    assertTrustedFrame(event);
    const logsDirectory = join(app.getPath("appData"), "LayoutSee", "logs");
    await logger?.ensureDirectory();
    return { opened: (await shell.openPath(logsDirectory)) === "" };
  });

  ipcMain.handle("plugins:open", async (event) => {
    assertTrustedFrame(event);
    const pluginsDirectory = join(app.getPath("appData"), "LayoutSee", "plugins");
    await mkdir(pluginsDirectory, { recursive: true });
    return { opened: (await shell.openPath(pluginsDirectory)) === "" };
  });

  ipcMain.handle("adb:choose", async (event) => {
    assertTrustedFrame(event);
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "选择 adb 可执行文件",
      properties: ["openFile", "showHiddenFiles"],
    });
    if (result.canceled || result.filePaths.length === 0) return null;
    const path = result.filePaths[0];
    try {
      await access(path);
    } catch {
      return null;
    }
    return { path };
  });

  ipcMain.handle("layout:export", async (event, payload) => {
    assertTrustedFrame(event);
    if (!payload || typeof payload !== "object") throw new Error("IPC_ARGUMENT_INVALID");
    const name = assertString(payload.name, "name", { max: 160 });
    const content = assertString(payload.content, "content", { max: 16_000_000 });
    const result = await dialog.showSaveDialog(mainWindow, {
      title: "导出布局 XML",
      defaultPath: name.endsWith(".xml") ? name : `${name}.xml`,
      filters: [{ name: "XML", extensions: ["xml"] }],
    });
    if (result.canceled || !result.filePath) return { saved: false };
    await writeFile(result.filePath, content, "utf-8");
    return { saved: true, path: result.filePath };
  });

  ipcMain.handle("external:open", async (event, kind) => {
    assertTrustedFrame(event);
    assertString(kind, "kind", { max: 32 });
    const url = TRUSTED_EXTERNAL_URLS[kind];
    if (!url) throw new Error("IPC_ARGUMENT_INVALID");
    await shell.openExternal(url);
    return { opened: true };
  });

  ipcMain.handle("theme:system", (event) => {
    assertTrustedFrame(event);
    return readSystemTheme();
  });

  ipcMain.handle("theme:set", (event, theme) => {
    assertTrustedFrame(event);
    assertString(theme, "theme", { max: 16 });
    if (!["light", "dark", "system"].includes(theme)) throw new Error("IPC_ARGUMENT_INVALID");
    nativeTheme.themeSource = theme;
    return readSystemTheme();
  });

  ipcMain.handle("app:quit", (event) => {
    assertTrustedFrame(event);
    app.quit();
  });
}

async function loadBootstrap() {
  await mainWindow.loadFile(bootstrapPath);
}

async function startKernel() {
  try {
    const origin = await supervisor.start();
    if (!mainWindow || mainWindow.isDestroyed()) return;
    await mainWindow.loadURL(origin);
  } catch {
    sendState(supervisor.snapshot());
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 720,
    minWidth: 940,
    minHeight: 640,
    show: false,
    title: "LayoutSee",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 18, y: 16 },
    backgroundColor: nativeTheme.shouldUseDarkColors ? "#151517" : "#f7f7f8",
    webPreferences: {
      preload: preloadPath,
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      webviewTag: false,
      devTools: !app.isPackaged,
      spellcheck: false,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  mainWindow.webContents.on("will-attach-webview", (event) => event.preventDefault());
  mainWindow.webContents.on("will-navigate", (event, url) => {
    const allowed = url === bootstrapUrl || Boolean(supervisor?.origin && url.startsWith(`${supervisor.origin}/`));
    if (!allowed) event.preventDefault();
  });
  mainWindow.webContents.session.on("will-download", (event) => event.preventDefault());
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  supervisor.on("state", (state) => {
    sendState(state);
    if (state.state === "ready" && state.origin && mainWindow && !mainWindow.isDestroyed()) {
      const current = mainWindow.webContents.getURL();
      if (!current.startsWith(`${state.origin}/`)) void mainWindow.loadURL(state.origin);
    }
  });
  nativeTheme.on("updated", () => {
    lastSystemTheme = readSystemTheme();
    sendTheme(lastSystemTheme);
  });
}

function installMenu() {
  const template = [
    {
      label: "LayoutSee",
      submenu: [
        { role: "about", label: "关于 LayoutSee" },
        { type: "separator" },
        { role: "hide" },
        { role: "hideOthers" },
        { role: "unhide" },
        { type: "separator" },
        { role: "quit", label: "退出 LayoutSee" },
      ],
    },
    {
      label: "编辑",
      submenu: [
        { role: "undo", label: "撤销" },
        { role: "redo", label: "重做" },
        { type: "separator" },
        { role: "cut", label: "剪切" },
        { role: "copy", label: "复制" },
        { role: "paste", label: "粘贴" },
        { role: "selectAll", label: "全选" },
      ],
    },
    {
      label: "视图",
      submenu: [
        { label: "后退", accelerator: "Cmd+[", click: () => mainWindow?.webContents.navigationHistory.canGoBack() && mainWindow.webContents.goBack() },
        { label: "前进", accelerator: "Cmd+]", click: () => mainWindow?.webContents.navigationHistory.canGoForward() && mainWindow.webContents.goForward() },
        { label: "重新加载", accelerator: "Cmd+R", click: () => mainWindow?.webContents.reload() },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
        ...(app.isPackaged ? [] : [{ role: "toggleDevTools", label: "开发者工具" }]),
      ],
    },
    {
      label: "窗口",
      submenu: [
        { role: "minimize", label: "最小化" },
        { role: "zoom", label: "缩放" },
        { type: "separator" },
        { role: "close", label: "关闭窗口" },
      ],
    },
    {
      label: "帮助",
      submenu: [
        {
          label: "打开日志目录",
          click: () => void shell.openPath(join(app.getPath("appData"), "LayoutSee", "logs")),
        },
        {
          label: "ADB 安装帮助",
          click: () => void shell.openExternal(TRUSTED_EXTERNAL_URLS["adb-help"]),
        },
        {
          label: "MCP 客户端帮助",
          click: () => void shell.openExternal(TRUSTED_EXTERNAL_URLS["mcp-client-help"]),
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    logger = new DailyFileLogger(join(app.getPath("appData"), "LayoutSee", "logs"));
    session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => callback(false));
    session.defaultSession.setPermissionCheckHandler(() => false);

    const resourcesPath = process.env.LAYOUTSEE_RESOURCES_DIR || process.resourcesPath;
    supervisor = new KernelSupervisor({ resourcesPath, log: logToFile });
    lastSystemTheme = readSystemTheme();
    installIpc();
    installMenu();
    createWindow();
    void loadBootstrap();
    void startKernel();
  });

  app.on("activate", () => {
    if (mainWindow) {
      mainWindow.show();
      return;
    }
    createWindow();
    void loadBootstrap().then(startKernel);
  });

  app.on("before-quit", (event) => {
    if (isQuitting) return;
    event.preventDefault();
    isQuitting = true;
    void supervisor?.stop().finally(() => app.exit(0));
  });
}
