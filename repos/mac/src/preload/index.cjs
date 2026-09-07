const { contextBridge, ipcRenderer } = require("electron");

function subscribe(channel, listener) {
  const handler = (_event, payload) => listener(payload);
  ipcRenderer.on(channel, handler);
  return () => ipcRenderer.removeListener(channel, handler);
}

contextBridge.exposeInMainWorld("layoutSeeShell", Object.freeze({
  getAppInfo: () => ipcRenderer.invoke("app:info"),
  getKernelSession: () => ipcRenderer.invoke("kernel:session"),
  retryKernel: () => ipcRenderer.invoke("kernel:retry"),
  getSanitizedDiagnostics: () => ipcRenderer.invoke("kernel:diagnostics"),
  copySanitizedDiagnostics: () => ipcRenderer.invoke("diagnostics:copy"),
  openLogsDir: () => ipcRenderer.invoke("logs:open"),
  openPluginsDir: () => ipcRenderer.invoke("plugins:open"),
  chooseAdbPath: () => ipcRenderer.invoke("adb:choose"),
  exportLayout: (name, content) => ipcRenderer.invoke("layout:export", { name, content }),
  openTrustedExternal: (kind) => ipcRenderer.invoke("external:open", kind),
  getSystemTheme: () => ipcRenderer.invoke("theme:system"),
  setNativeTheme: (theme) => ipcRenderer.invoke("theme:set", theme),
  onKernelStateChange: (listener) => subscribe("kernel:state", listener),
  onSystemThemeChange: (listener) => subscribe("kernel:theme", listener),
  quit: () => ipcRenderer.invoke("app:quit"),
}));
