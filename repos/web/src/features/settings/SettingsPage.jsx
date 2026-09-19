import { useCallback, useEffect, useState } from "react";
import { ClipboardText, FolderOpen, Info } from "@phosphor-icons/react";
import { api } from "../../api/client.js";
import { HostBridge } from "../../app/HostBridge.js";
import { loadThemePreference } from "../../app/theme.js";
import { Banner, Button, CopyButton, StatusPill, useToast } from "../../components/ui.jsx";

const SECTIONS = [
  { id: "appearance", label: "外观" },
  { id: "device", label: "设备与驱动" },
  { id: "casting", label: "投屏" },
  { id: "security", label: "安全" },
  { id: "about", label: "关于" },
];

export function SettingsPage({ onThemeChange }) {
  const toast = useToast();
  const [settings, setSettings] = useState(null);
  const [section, setSection] = useState("appearance");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [appInfo, setAppInfo] = useState(null);
  const [coreInfo, setCoreInfo] = useState(null);
  const [paths, setPaths] = useState(null);
  const [adbPathDraft, setAdbPathDraft] = useState("");
  const [themePreference, setThemePreference] = useState(loadThemePreference);

  useEffect(() => {
    let active = true;
    api.settings().then((payload) => {
      if (!active) return;
      setSettings(payload);
      setAdbPathDraft(payload.adbPath ?? "");
    }).catch((err) => active && setError(err));
    api.info().then((payload) => active && setCoreInfo(payload)).catch(() => {});
    // 浏览器宿主打不开目录，需要拿到路径文本展示
    if (!HostBridge.can.openDirectory) api.paths().then((payload) => active && setPaths(payload)).catch(() => {});
    HostBridge.getAppInfo().then((info) => active && setAppInfo(info));
    return () => {
      active = false;
    };
  }, []);

  const save = useCallback(async (patch, message) => {
    setSaving(true);
    try {
      // 只提交变更字段；schemaVersion 等系统字段由 Core 维护，不随补丁回传
      const merged = await api.saveSettings(patch);
      setSettings(merged);
      toast(message || "设置已保存");
    } catch (err) {
      toast(err.message, "danger");
    } finally {
      setSaving(false);
    }
  }, [toast]);

  const setTheme = (theme) => {
    setThemePreference(theme);
    onThemeChange?.(theme);
    if (settings) void save({ theme }, "主题设置已保存");
  };

  if (!settings) {
    return (
      <main className="page-content">
        {error ? <Banner tone="danger"><b>设置读取失败</b>：{error.message}</Banner> : null}
      </main>
    );
  }

  return (
    <main className="page-content">
      <div className="page-heading">
        <div>
          <h1>设置</h1>
          <p>外观、设备驱动、投屏、安全与应用信息</p>
        </div>
      </div>
      <div className="settings-layout">
        <nav className="settings-nav" aria-label="设置分组">
          {SECTIONS.map(({ id, label }) => (
            <button key={id} className={section === id ? "active" : ""} onClick={() => setSection(id)}>{label}</button>
          ))}
        </nav>
        <div className="settings-section">
          {section === "appearance" ? (
            <section className="content-card">
              <div className="card-heading"><div><h3>主题</h3><p>系统主题变化无需重启即可同步</p></div></div>
              <div className="setting-row">
                <span><b>主题模式</b><small>浅色、深色或跟随系统外观</small></span>
                <div className="segmented" role="tablist" aria-label="主题模式">
                  {["light", "dark", "system"].map((mode) => (
                    <button key={mode} role="tab" aria-selected={themePreference === mode} className={themePreference === mode ? "active" : ""} onClick={() => setTheme(mode)}>
                      {mode === "light" ? "浅色" : mode === "dark" ? "深色" : "跟随系统"}
                    </button>
                  ))}
                </div>
              </div>
            </section>
          ) : null}

          {section === "device" ? (
            <section className="content-card">
              <div className="card-heading"><div><h3>设备与驱动</h3><p>适配本机 Android 工具链环境</p></div></div>
              <div className="setting-row">
                <span><b>ADB 路径</b><small>留空时使用 PATH 中的 adb；改动后立即生效</small></span>
                {HostBridge.can.pickAdbPath ? (
                  <Button compact icon={FolderOpen} onClick={async () => {
                    const chosen = await HostBridge.chooseAdbPath();
                    if (chosen?.path) await save({ adbPath: chosen.path }, "ADB 路径已保存");
                  }}>{settings.adbPath ? "重新选择" : "选择 adb"}</Button>
                ) : (
                  // 浏览器没有文件选择器，改成手输，存在性与可执行位由 Core 校验
                  <input
                    type="text"
                    value={adbPathDraft}
                    placeholder="/opt/homebrew/bin/adb"
                    aria-label="ADB 可执行文件路径"
                    style={{ minWidth: 240 }}
                    onChange={(event) => setAdbPathDraft(event.target.value)}
                    onBlur={() => adbPathDraft !== (settings.adbPath ?? "") && save({ adbPath: adbPathDraft.trim() }, "ADB 路径已保存")}
                  />
                )}
              </div>
              {settings.adbPath ? <div className="setting-row"><code style={{ fontSize: 12 }}>{settings.adbPath}</code></div> : null}
              <div className="setting-row">
                <span><b>设备轮询间隔</b><small>设备列表增量刷新频率（1000–60000 毫秒）</small></span>
                <input type="number" min={1000} max={60000} step={500} value={settings.pollIntervalMs}
                  onChange={(event) => setSettings((current) => ({ ...current, pollIntervalMs: Number(event.target.value) }))}
                  onBlur={() => save({ pollIntervalMs: settings.pollIntervalMs }, "轮询间隔已保存")} />
              </div>
            </section>
          ) : null}

          {section === "casting" ? (
            <section className="content-card">
              <div className="card-heading"><div><h3>投屏</h3><p>实时投屏由 scrcpy 驱动；失败时自动降级为截图轮询</p></div></div>
              <div className="setting-row">
                <span><b>截图刷新间隔</b><small>截图模式下的画面刷新频率（400–5000 毫秒）</small></span>
                <input type="number" min={400} max={5000} step={100} value={settings.screenshotFallbackIntervalMs}
                  onChange={(event) => setSettings((current) => ({ ...current, screenshotFallbackIntervalMs: Number(event.target.value) }))}
                  onBlur={() => save({ screenshotFallbackIntervalMs: settings.screenshotFallbackIntervalMs }, "刷新间隔已保存")} />
              </div>
              <div className="setting-row">
                <span><b>帧率上限</b><small>实时媒体启用后生效的上限（5–60）</small></span>
                <input type="number" min={5} max={60} value={settings.videoFpsCap}
                  onChange={(event) => setSettings((current) => ({ ...current, videoFpsCap: Number(event.target.value) }))}
                  onBlur={() => save({ videoFpsCap: settings.videoFpsCap }, "帧率上限已保存")} />
              </div>
              <div className="setting-row">
                <span><b>断流重连次数</b><small>媒体断流后的重试预算（1–10）</small></span>
                <input type="number" min={1} max={10} value={settings.mediaReconnectAttempts}
                  onChange={(event) => setSettings((current) => ({ ...current, mediaReconnectAttempts: Number(event.target.value) }))}
                  onBlur={() => save({ mediaReconnectAttempts: settings.mediaReconnectAttempts }, "重连次数已保存")} />
              </div>
            </section>
          ) : null}

          {section === "security" ? (
            <section className="content-card">
              <div className="card-heading"><div><h3>安全</h3><p>只读策略在服务端强制，不只是按钮禁用</p></div></div>
              <div className="setting-row">
                <span><b>新设备默认只读</b><small>开启后，每次启动接入的设备默认拦截全部写操作</small></span>
                <button className={`switch ${settings.defaultReadonly ? "on" : ""}`} role="switch" aria-checked={settings.defaultReadonly} disabled={saving}
                  onClick={() => save({ defaultReadonly: !settings.defaultReadonly }, settings.defaultReadonly ? "默认只读已关闭" : "默认只读已开启")}>
                  <span />
                </button>
              </div>
              <div className="setting-row">
                <span><b>复制脱敏诊断</b><small>诊断不包含启动随机数、凭据与完整节点文本</small></span>
                <Button compact icon={ClipboardText} onClick={async () => {
                  await HostBridge.copySanitizedDiagnostics();
                  toast("脱敏诊断已复制");
                }}>复制</Button>
              </div>
              <div className="setting-row">
                <span><b>日志目录</b><small>壳与 Core 日志按天切分保存</small></span>
                {HostBridge.can.openDirectory ? (
                  <Button compact icon={FolderOpen} onClick={() => HostBridge.openLogsDir()}>打开</Button>
                ) : (
                  <CopyButton value={paths?.logsDir ?? ""} label="复制路径" />
                )}
              </div>
              {!HostBridge.can.openDirectory && paths?.logsDir ? (
                <div className="setting-row"><code style={{ fontSize: 12 }}>{paths.logsDir}</code></div>
              ) : null}
            </section>
          ) : null}

          {section === "about" ? (
            <section className="content-card">
              <div className="card-heading"><div><h3>关于 LayoutSee</h3><p>安装完整性与版本兼容状态</p></div></div>
              <div className="about-grid">
                <span>{HostBridge.kind === "shell" ? "壳版本" : "宿主"}</span>
                <code>{HostBridge.kind === "shell" ? (appInfo?.version ?? "读取中…") : "浏览器"}</code>
                <span>运行环境</span><code>{appInfo ? `${appInfo.platform} / ${appInfo.arch}` : "—"}</code>
                <span>Core 版本</span><code>{coreInfo?.productVersion ?? "读取中…"}</code>
                <span>API 版本</span><code>{coreInfo?.apiVersion ?? "—"}</code>
                <span>快照 Schema</span><code>{coreInfo?.snapshotSchemaVersion ?? "—"}</code>
                <span>兼容状态</span>
                <span className="compat-badge">
                  {coreInfo && coreInfo.productVersion === "22.6.1" && coreInfo.apiVersion === "1.0" && coreInfo.snapshotSchemaVersion === "1.0"
                    ? <><StatusPill tone="success" dot>版本兼容</StatusPill></>
                    : <><StatusPill tone="danger" dot>版本不兼容</StatusPill></>}
                </span>
              </div>
              <Banner tone="info" icon={Info} style={{ marginTop: 12 }}>
                <b>离线运行</b>：本应用不需要登录、License 或联网校验；所有数据仅保存在本机。
              </Banner>
            </section>
          ) : null}
        </div>
      </div>
    </main>
  );
}
