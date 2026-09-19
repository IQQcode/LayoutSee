import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CaretLeft, Copy } from "@phosphor-icons/react";
import { api } from "../../api/client.js";
import { LogTags, uiLog, uiLogApi } from "../../api/logger.js";
import { MorphGlyph, glyphs } from "../../components/MorphIcons.jsx";
import { ResizeHandle, clamp } from "../../components/ResizeHandle.jsx";
import { useToast } from "../../components/ui.jsx";
import { PluginSlot } from "../plugins/PluginSlot.jsx";
import { EMPTY_EXTENSIONS, buildExtensionModel, findPluginTab, isPluginTab } from "../plugins/registry.js";
import { DeviceCanvas } from "./DeviceCanvas.jsx";
import { CommonTab } from "./tabs/CommonTab.jsx";
import { ElementTab } from "./tabs/ElementTab.jsx";
import { IntelligenceTab } from "./tabs/IntelligenceTab.jsx";
import { McpTab } from "./tabs/McpTab.jsx";
import { PluginsTab } from "./tabs/PluginsTab.jsx";
import { TerminalTab } from "./tabs/TerminalTab.jsx";

const DEVICE_MIN = 330;
const DEVICE_MAX = 720;
const DEFAULT_SHARE = 0.44;
// 终端不再是独立 Tab：入口收拢到插件页卡片，路由 /workbench/terminal 保留并复用插件二级页外壳
const TAB_IDS = ["common", "element", "mcp", "plugins", "intelligence"];
const TAB_LABELS = { common: "常用", plugins: "插件", element: "元素查看", mcp: "MCP", intelligence: "布局智能" };

// 图标用 morphicons：icon 变化即弹性变形；pulseIcon 用于一次性动作（按一下变形再变回）
function RailButton({ icon, pulseIcon, pulseMs = 900, label, active, danger, disabled, spinning = false, onClick }) {
  const [hover, setHover] = useState(false);
  const [pulsing, setPulsing] = useState(false);
  const timer = useRef(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const handleClick = (event) => {
    if (pulseIcon && !disabled) {
      setPulsing(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setPulsing(false), pulseMs);
    }
    onClick?.(event);
  };
  return (
    <button
      type="button"
      className={`rail-icon-button ${active ? (danger ? "is-danger" : "is-active") : ""}`}
      aria-label={label}
      disabled={disabled}
      onClick={handleClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <MorphGlyph icon={pulsing && pulseIcon ? pulseIcon : icon} size={19} spinning={spinning} />
      {hover ? <span className="rail-tooltip" role="tooltip">{label}</span> : null}
    </button>
  );
}

export function ControlRail({ device, onBack, onAction, readonly, frozen, inspect, tab, onTab, snapshotView, capturing, captureDone }) {
  const press = (key) => onAction({ type: "press_key", key });
  const writeDisabled = Boolean(readonly || frozen || device?.status !== "connected");
  const snapshotLocked = Boolean(snapshotView);
  // 抓取按钮三段式：待命相机 → 抓取中旋转加载 → 完成对勾
  const captureIcon = capturing ? glyphs.captureBusy : captureDone ? glyphs.captureDone : glyphs.capture;
  // 旋转按钮交替方向：与设备下次旋转方向对应
  const [rotateCcw, setRotateCcw] = useState(false);
  return (
    <aside className="control-rail" aria-label="设备控制轨">
      <RailButton icon={glyphs.back} label="返回设备列表" onClick={onBack} />
      <RailButton icon={glyphs.home} label="Home" disabled={writeDisabled || snapshotLocked} onClick={() => press("HOME")} />
      <RailButton icon={glyphs.recents} label="最近任务" disabled={writeDisabled || snapshotLocked} onClick={() => press("RECENTS")} />
      <div className="rail-divider" />
      <RailButton icon={glyphs.power} label="电源键" disabled={writeDisabled || snapshotLocked} onClick={() => press("POWER")} />
      {/* 音量：图标随档位变形，直观表达音量增减 */}
      <RailButton icon={glyphs.volumeLow} pulseIcon={glyphs.volumeUp} label="音量增大" disabled={writeDisabled || snapshotLocked} onClick={() => press("VOLUME_UP")} />
      <RailButton icon={glyphs.volumeUp} pulseIcon={glyphs.volumeDown} label="音量减小" disabled={writeDisabled || snapshotLocked} onClick={() => press("VOLUME_DOWN")} />
      <RailButton
        icon={rotateCcw ? glyphs.rotateCcw : glyphs.rotateCw}
        pulseIcon={rotateCcw ? glyphs.rotateCw : glyphs.rotateCcw}
        label="旋转屏幕"
        disabled={writeDisabled || snapshotLocked}
        onClick={() => { setRotateCcw((v) => !v); onAction({ type: "rotate" }); }}
      />
      <div className="rail-divider" />
      <RailButton icon={captureIcon} label="抓取布局快照" disabled={device?.status !== "connected"} active={snapshotView} spinning={capturing} onClick={() => onAction({ type: "capture" })} />
      <RailButton icon={frozen ? glyphs.thaw : glyphs.freeze} label={frozen ? "解除冻结" : "冻结画面"} active={frozen} disabled={snapshotLocked} onClick={() => onAction({ type: frozen ? "unfreeze" : "freeze" })} />
      <RailButton icon={readonly ? glyphs.unlocked : glyphs.locked} label={readonly ? "关闭只读模式" : "开启只读模式"} active={readonly} danger={readonly} disabled={snapshotLocked} onClick={() => onAction({ type: readonly ? "readonly-off" : "readonly-on" })} />
      <RailButton icon={inspect ? glyphs.browse : glyphs.inspect} label={inspect ? "退出审查模式" : "进入审查模式"} active={inspect} disabled={snapshotLocked} onClick={() => onAction({ type: inspect ? "inspect-off" : "inspect-on" })} />
      <div className="rail-divider" />
      {TAB_IDS.map((id) => (
        <RailButton key={id} icon={TabIcon(id, tab === id)} label={TAB_LABELS[id]} active={tab === id || (id === "plugins" && (isPluginTab(tab) || tab === "terminal"))} onClick={() => onTab(id)} />
      ))}
      <div className="rail-spacer" />
      <span className={`kernel-dot ${device?.status === "connected" ? "" : "offline"}`} title="设备状态" aria-label={device?.status === "connected" ? "设备在线" : "设备离线"} />
    </aside>
  );
}

// Tab 图标在选中时变形为「展开态」，让切换有形状反馈
function TabIcon(id, active) {
  switch (id) {
    case "common": return active ? glyphs.tabCommonActive : glyphs.tabCommon;
    case "plugins": return active ? glyphs.tabPluginsActive : glyphs.tabPlugins;
    case "element": return active ? glyphs.tabElementActive : glyphs.tabElement;
    case "mcp": return active ? glyphs.tabMcpActive : glyphs.tabMcp;
    case "intelligence": return active ? glyphs.tabIntelligenceActive : glyphs.tabIntelligence;
    default: return glyphs.tabCommon;
  }
}

export function WorkbenchPage() {
  const { deviceId, tab = "common" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [devices, setDevices] = useState([]);
  const [readonly, setReadonly] = useState(false);
  const [frozen, setFrozen] = useState(false);
  const [inspect, setInspect] = useState(false);
  const [snapshotMeta, setSnapshotMeta] = useState(null);
  const [snapshotData, setSnapshotData] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [capturing, setCapturing] = useState(false);
  const [captureDone, setCaptureDone] = useState(false);
  const [highlights, setHighlights] = useState({});
  const [viewMode, setViewMode] = useState("live");
  const [workspaceWidth, setWorkspaceWidth] = useState(() => window.innerWidth);
  const [deviceWidth, setDeviceWidth] = useState(null);
  const [extensions, setExtensions] = useState(EMPTY_EXTENSIONS);
  const [extensionsReady, setExtensionsReady] = useState(false);
  const [pointer, setPointer] = useState(null);
  const [deviceSize, setDeviceSize] = useState(null);
  const [coreInfo, setCoreInfo] = useState(null);
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "light");

  // 插件在 iframe 里读不到宿主的 data-theme，只能由宿主观察后经桥事件下发
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(document.documentElement.dataset.theme || "light"));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  // 状态栏用：设备物理分辨率与 Core 版本在工作台生命周期内不变，各取一次
  useEffect(() => {
    let active = true;
    api.windowSize(deviceId).then((size) => active && size?.width && setDeviceSize(size)).catch(() => {});
    api.info().then((info) => active && setCoreInfo(info)).catch(() => {});
    return () => {
      active = false;
    };
  }, [deviceId]);

  // 插件索引在空闲时才拉：首屏与工作台首次绘制路径上不发插件请求
  useEffect(() => {
    let active = true;
    const load = () => {
      api.pluginIndex()
        .then((index) => {
          if (active) setExtensions(buildExtensionModel(index, { devicePlatform: "android" }));
        })
        .catch(() => {})
        .finally(() => {
          if (active) setExtensionsReady(true);
        });
    };
    const idle = window.requestIdleCallback ? window.requestIdleCallback(load, { timeout: 2000 }) : window.setTimeout(load, 300);
    return () => {
      active = false;
      if (window.cancelIdleCallback) window.cancelIdleCallback(idle);
      else window.clearTimeout(idle);
    };
  }, []);

  useEffect(() => {
    const update = () => setWorkspaceWidth(window.innerWidth);
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const device = useMemo(() => devices.find((item) => item.deviceId === deviceId) ?? null, [devices, deviceId]);

  const deviceMax = useMemo(() => Math.max(DEVICE_MIN, Math.min(DEVICE_MAX, workspaceWidth - 68 - 8 - 520)), [workspaceWidth]);
  const defaultDeviceWidth = useMemo(() => Math.min(deviceMax, Math.max(DEVICE_MIN, Math.round(workspaceWidth * DEFAULT_SHARE))), [deviceMax, workspaceWidth]);

  useEffect(() => {
    setDeviceWidth((current) => {
      const stored = Number(localStorage.getItem(`layoutsee.deviceWidth.${deviceId}`));
      const base = current ?? (Number.isFinite(stored) && stored > 0 ? stored : defaultDeviceWidth);
      return clamp(base, DEVICE_MIN, deviceMax);
    });
  }, [deviceId, defaultDeviceWidth, deviceMax]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const payload = await api.devices();
        if (!active) return;
        setDevices(payload.items ?? []);
      } catch {
        // 保留上一轮设备列表
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    setReadonly(Boolean(device?.readonly));
  }, [device?.readonly]);

  useEffect(() => {
    if (device?.status !== "connected") setViewMode("live");
  }, [device?.status]);

  useEffect(() => {
    setViewMode("live");
  }, [deviceId]);

  useEffect(() => {
    let active = true;
    api.latestSnapshot(deviceId)
      .then((meta) => {
        if (!active || !meta.snapshotId) return;
        setSnapshotMeta(meta);
        return api.snapshot(meta.snapshotId);
      })
      .then((data) => {
        if (active && data) setSnapshotData(data);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [deviceId]);

  const capture = useCallback(async () => {
    if (capturing || device?.status !== "connected") {
      uiLog(LogTags.workbench, "抓取请求被忽略", "warning", capturing ? "已有抓取进行中" : "设备不在线");
      return;
    }
    setCapturing(true);
    const started = performance.now();
    try {
      const meta = await uiLogApi(LogTags.workbench, "抓取 UI 快照", () => api.capture(deviceId));
      const data = await uiLogApi(LogTags.workbench, `读取快照详情 ${meta.snapshotId}`, () => api.snapshot(meta.snapshotId));
      setSnapshotMeta(meta);
      setSnapshotData(data);
      setSelectedNode(null);
      setHighlights({});
      setViewMode("snapshot");
      // 控制轨相机图标短暂变为对勾，给抓取一个完成反馈
      setCaptureDone(true);
      window.setTimeout(() => setCaptureDone(false), 1800);
      uiLog(LogTags.workbench, "快照就绪", "info", `${meta.snapshotId} · ${meta.nodeCount} 节点 · ${Math.round(performance.now() - started)}ms${meta.warnings?.length ? ` · 警告 ${meta.warnings[0]}` : ""}`);
      if (meta.warnings?.length) toast(`快照完成：${meta.warnings[0]}`, "warning");
      else toast(`快照完成，共 ${meta.nodeCount} 个节点`);
    } catch (error) {
      uiLog(LogTags.workbench, "抓取失败", "error", `${error?.code ?? ""} ${error?.message ?? error}`);
      toast(error.message, "danger");
    } finally {
      setCapturing(false);
    }
  }, [capturing, device?.status, deviceId, toast]);

  const resetToLive = useCallback(() => {
    setViewMode("live");
    setHighlights({});
    setSelectedNode(null);
    uiLog(LogTags.workbench, "重置为实时投屏", "info");
  }, []);

  const handleAction = useCallback(async (action) => {
    switch (action.type) {
      case "capture":
        await capture();
        return;
      case "freeze":
        setFrozen(true);
        toast("画面已冻结，抓取期间避免界面变化", "warning");
        return;
      case "unfreeze":
        setFrozen(false);
        toast("画面已恢复刷新");
        return;
      case "readonly-on": {
        try {
          await uiLogApi(LogTags.workbench, "开启只读模式", () => api.setReadonly(deviceId, true));
          setReadonly(true);
          toast("只读模式已开启，所有写入口已拦截", "warning");
        } catch (error) {
          toast(error.message, "danger");
        }
        return;
      }
      case "readonly-off": {
        try {
          await uiLogApi(LogTags.workbench, "关闭只读模式", () => api.setReadonly(deviceId, false));
          setReadonly(false);
          toast("只读模式已关闭");
        } catch (error) {
          toast(error.message, "danger");
        }
        return;
      }
      case "inspect-on":
        setInspect(true);
        toast("审查模式：点击画面将选择节点而不是注入 tap");
        return;
      case "inspect-off":
        setInspect(false);
        return;
      default: {
        try {
          await api.action(deviceId, action);
        } catch (error) {
          toast(error.message, "danger");
        }
      }
    }
  }, [capture, deviceId, toast]);

  const selectNode = useCallback((nodeKey) => {
    setSelectedNode(nodeKey);
    // 替换式红色高亮：仅保留当前选中；XPath/诊断高亮不受影响
    setHighlights((current) => {
      const next = Object.fromEntries(Object.entries(current).filter(([, kind]) => kind !== "selected"));
      next[nodeKey] = "selected";
      return next;
    });
  }, []);

  const showDiagnostic = useCallback((finding) => {
    const next = {};
    for (const key of finding.nodeKeys) next[key] = `diagnostic-${finding.severity}`;
    setHighlights(next);
    if (finding.nodeKeys[0]) setSelectedNode(finding.nodeKeys[0]);
  }, []);

  const setDeviceWidthPersisted = useCallback((width) => {
    // 用户手动调整后不再自动适配画面宽度
    localStorage.setItem(`layoutsee.stageFitted.${deviceId}`, "1");
    setDeviceWidth(width);
    localStorage.setItem(`layoutsee.deviceWidth.${deviceId}`, String(width));
  }, [deviceId]);

  // 流建立后把设备区宽度自适应到画面比例（每台设备仅首次，手动拖过分隔条后跳过）
  const handleFitWidth = useCallback((width) => {
    if (localStorage.getItem(`layoutsee.stageFitted.${deviceId}`)) return;
    localStorage.setItem(`layoutsee.stageFitted.${deviceId}`, "1");
    setDeviceWidthPersisted(clamp(width + 8, DEVICE_MIN, Math.max(DEVICE_MIN, deviceMax)));
  }, [deviceId, deviceMax, setDeviceWidthPersisted]);

  if (!device) {
    return (
      <main style={{ height: "100vh", display: "grid", placeItems: "center" }}>
        <section style={{ display: "grid", gap: 10, justifyItems: "center", textAlign: "center" }}>
          <h1 style={{ margin: 0, fontSize: 17 }}>设备不可用</h1>
          <p style={{ margin: 0, color: "var(--ls-color-text-secondary)" }}>设备可能已断开或不存在，已保留最后画面与快照。</p>
          <button className="button primary" onClick={() => navigate("/devices")}>返回设备列表</button>
        </section>
      </main>
    );
  }

  const setTab = (next) => navigate(`/devices/${encodeURIComponent(deviceId)}/workbench/${next}`);

  const tabProps = { device, deviceId, snapshotMeta, snapshotData, readonly, frozen, onSelectNode: selectNode, onHighlight: showDiagnostic, onCapture: capture, capturing, onToast: toast, onViewReset: resetToLive, snapshotView: viewMode === "snapshot" };
  const activePluginTab = isPluginTab(tab) ? findPluginTab(extensions, tab) : null;
  const pluginContext = { deviceId, snapshotMeta, snapshotData, readonly, selectedNode, theme };

  return (
    <div className="workspace-page" style={{ height: "100vh" }}>
      <header className="window-titlebar workbench-titlebar" aria-label="窗口标题">
        <div className="brand-lockup">
          <img className="brand-mark" src="/layoutsee-icon-192.png" alt="" aria-hidden="true" />
          <span>LayoutSee</span>
          <span className="version-chip">V22.6.1</span>
        </div>
      </header>
      <div className="workspace-body">
      <ControlRail
        device={device}
        onBack={() => navigate("/devices")}
        onAction={handleAction}
        readonly={readonly}
        frozen={frozen}
        inspect={inspect}
        tab={tab}
        onTab={setTab}
        snapshotView={viewMode === "snapshot"}
        capturing={capturing}
        captureDone={captureDone}
      />
      <div className="device-stage" style={{ flex: `0 0 ${deviceWidth ?? defaultDeviceWidth}px`, maxWidth: DEVICE_MAX }}>
        <div className="device-info-bar">
          <div className="info-group"><span>平台</span><strong>Android</strong></div>
          <div className="info-group"><span>设备</span><strong>{device.model || "未知型号"}</strong></div>
          <div className="info-group"><span>序列号</span><strong className="mono">{device.serial}</strong></div>
          <button className="copy-inline" onClick={async () => { await navigator.clipboard.writeText(device.serial); toast("序列号已复制"); }} aria-label="复制序列号"><Copy size={14} /></button>
          <div className="device-switcher">
            <select aria-label="切换设备" value={deviceId} onChange={(event) => navigate(`/devices/${encodeURIComponent(event.target.value)}/workbench/${tab}`)}>
              {devices.filter((item) => item.status === "connected").map((item) => (
                <option key={item.deviceId} value={item.deviceId}>{item.model || item.serial}</option>
              ))}
            </select>
          </div>
        </div>
        <DeviceCanvas
          device={device}
          snapshot={snapshotData ? { data: snapshotData, meta: snapshotMeta } : null}
          viewMode={viewMode}
          readonly={readonly}
          frozen={frozen}
          inspect={inspect}
          highlights={highlights}
          onSelectNode={selectNode}
          onToast={toast}
          onFitWidth={handleFitWidth}
          onPointerInfo={setPointer}
        />
      </div>
      <ResizeHandle
        label="调整设备画面区宽度"
        value={deviceWidth ?? defaultDeviceWidth}
        min={DEVICE_MIN}
        max={deviceMax}
        onChange={setDeviceWidthPersisted}
        onReset={() => setDeviceWidthPersisted(defaultDeviceWidth)}
      />
      <section className="task-panel" style={{ flex: 1, minWidth: 520 }}>
        {isPluginTab(tab) ? (
          // 插件二级页：整块盖住任务 Tab 栏，只留一条返回栏，避免和插件自身的工具栏抢注意力
          <div className="plugin-detail">
            <header className="plugin-detail-bar">
              <button type="button" className="plugin-back" onClick={() => setTab("plugins")}>
                <CaretLeft size={14} aria-hidden="true" />插件
              </button>
              <div className="plugin-detail-title">
                <strong>{activePluginTab?.pluginName ?? (extensionsReady ? "插件不可用" : "插件")}</strong>
                <small>{activePluginTab ? `${activePluginTab.pluginId} · v${activePluginTab.version}` : "正在解析插件入口"}</small>
              </div>
            </header>
            {activePluginTab ? (
              <PluginSlot tab={activePluginTab} context={pluginContext} onToast={toast} />
            ) : !extensionsReady ? (
              <div className="panel-scroll"><p style={{ color: "var(--ls-color-text-tertiary)" }}>正在加载插件入口…</p></div>
            ) : (
              <div className="panel-scroll">
                <p style={{ color: "var(--ls-color-text-secondary)" }}>该插件页面已不可用（插件被移除、清单变更或不支持当前宿主）。</p>
                <button className="button" onClick={() => setTab("plugins")}>返回插件列表</button>
              </div>
            )}
          </div>
        ) : tab === "terminal" ? (
          // 终端二级页：与插件二级页同一外壳，从插件页的终端卡片进入
          <div className="plugin-detail">
            <header className="plugin-detail-bar">
              <button type="button" className="plugin-back" onClick={() => setTab("plugins")}>
                <CaretLeft size={14} aria-hidden="true" />插件
              </button>
              <div className="plugin-detail-title">
                <strong>终端</strong>
                <small>adb shell · 内置工具</small>
              </div>
            </header>
            <TerminalTab {...tabProps} />
          </div>
        ) : (
          <>
            <div className="task-tabs" role="tablist" aria-label="工作台任务">
              {TAB_IDS.map((id) => (
                <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
                  {TAB_LABELS[id]}
                </button>
              ))}
            </div>
            {tab === "common" ? <CommonTab {...tabProps} /> : null}
            {tab === "plugins" ? <PluginsTab {...tabProps} extensions={extensions} onOpenPluginTab={setTab} /> : null}
            {tab === "element" ? <ElementTab {...tabProps} selectedNode={selectedNode} onSelectNode={selectNode} setHighlights={setHighlights} /> : null}
            {tab === "mcp" ? <McpTab {...tabProps} /> : null}
            {tab === "intelligence" ? <IntelligenceTab {...tabProps} onShowFinding={showDiagnostic} /> : null}
          </>
        )}
      </section>
      </div>
      <div className="workbench-statusbar" role="status" aria-live="off">
        <span>分辨率 <b className="mono">{deviceSize ? `${deviceSize.width}×${deviceSize.height}` : "--"}</b></span>
        <span>坐标 <b className="mono">{pointer ? `${pointer.x}, ${pointer.y}` : "--, --"}</b></span>
        <span>百分比 <b className="mono">{pointer ? `${(pointer.nx * 100).toFixed(1)}%, ${(pointer.ny * 100).toFixed(1)}%` : "--, --"}</b></span>
        <span className="statusbar-spacer" />
        <span>节点 <b className="mono">{snapshotMeta?.nodeCount ?? "--"}</b></span>
        <span>Core <b className="mono">{coreInfo?.productVersion ?? "--"}</b></span>
      </div>
    </div>
  );
}
