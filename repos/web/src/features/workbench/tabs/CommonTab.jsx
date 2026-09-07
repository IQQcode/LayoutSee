import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, Broom, MagnifyingGlass, Play, Stop, Trash } from "@phosphor-icons/react";
import { api } from "../../../api/client.js";
import { LogTags, uiLog, uiLogApi } from "../../../api/logger.js";
import { Banner, Button, Dialog, Spinner, StatusPill } from "../../../components/ui.jsx";
import { CopyButton } from "../../../components/ui.jsx";

// 包管理的高风险动作：文案与动作类型集中在一处，二次确认对话框按 type 取文案
const RISKY_ACTIONS = Object.freeze({
  stop: { type: "stop_app", title: "停止应用", verb: "强制结束该应用的所有进程，未保存的数据可能丢失", confirm: "确认停止", success: "已停止" },
  clear: { type: "clear_app", title: "清除应用数据", verb: "清空该应用的全部数据与缓存，等同于恢复到刚安装的状态，不可撤销", confirm: "确认清除", success: "数据已清除" },
  uninstall: { type: "uninstall_app", title: "卸载应用", verb: "从设备上卸载该应用及其数据，不可撤销；系统应用通常会被设备拒绝", confirm: "确认卸载", success: "已卸载" },
});

export function CommonTab({ device, deviceId, readonly, onToast }) {
  const [app, setApp] = useState(null);
  const [appLoading, setAppLoading] = useState(true);
  const [appError, setAppError] = useState(null);
  const [launchPackage, setLaunchPackage] = useState("");
  const [launchActivity, setLaunchActivity] = useState("");
  const [apps, setApps] = useState([]);
  const [appsLoading, setAppsLoading] = useState(false);
  const [appsQuery, setAppsQuery] = useState("");
  const [includeSystem, setIncludeSystem] = useState(false);
  const [appsError, setAppsError] = useState(null);
  const [pendingAction, setPendingAction] = useState(null);
  const [busy, setBusy] = useState(false);

  const loadApp = useCallback(async () => {
    setAppLoading(true);
    try {
      const payload = await uiLogApi(LogTags.common, "读取前台应用", () => api.currentApp(deviceId));
      setApp(payload);
      setAppError(null);
      uiLog(LogTags.common, "前台应用", "info", payload?.packageName ?? "unknown");
      // 「启动应用」表单默认预填当前前台应用（用户已输入时不覆盖）
      if (payload?.packageName && payload.packageName !== "unknown") {
        setLaunchPackage((current) => current || payload.packageName);
        setLaunchActivity((current) => current || payload.activity || "");
      }
    } catch (error) {
      setAppError(error);
    } finally {
      setAppLoading(false);
    }
  }, [deviceId]);

  useEffect(() => {
    loadApp();
  }, [loadApp, deviceId]);

  const loadApps = useCallback(async (query = appsQuery, withSystem = includeSystem) => {
    setAppsLoading(true);
    try {
      const payload = await uiLogApi(LogTags.common, `查询已安装应用 q=${query || "（全部）"}${withSystem ? " +系统" : ""}`, () => api.apps(deviceId, query, withSystem));
      setApps(payload.items ?? []);
      setAppsError(null);
      uiLog(LogTags.common, "应用列表", "info", `${payload.items?.length ?? 0} 个包`);
    } catch (error) {
      setAppsError(error);
    } finally {
      setAppsLoading(false);
    }
  }, [appsQuery, deviceId, includeSystem]);

  const run = async (fn, success) => {
    setBusy(true);
    try {
      await fn();
      uiLog(LogTags.common, success, "info");
      onToast?.(success);
    } catch (error) {
      uiLog(LogTags.common, "应用操作失败", "error", error.message);
      onToast?.(error.message, "danger");
    } finally {
      setBusy(false);
    }
  };

  const launch = () => {
    if (!launchPackage.trim()) {
      onToast?.("请输入包名", "warning");
      return;
    }
    uiLog(LogTags.common, "启动应用", "info", `${launchPackage.trim()}/${launchActivity.trim() || "(默认)"}`);
    void run(() => api.action(deviceId, { type: "start_app", packageName: launchPackage.trim(), activity: launchActivity.trim() }), "启动指令已发送");
  };

  const runRisky = async () => {
    if (!pendingAction) return;
    const { kind, packageName } = pendingAction;
    const spec = RISKY_ACTIONS[kind];
    setPendingAction(null);
    uiLog(LogTags.common, spec.title, "info", packageName);
    await run(() => api.action(deviceId, { type: spec.type, packageName }), `${packageName} ${spec.success}`);
    // 卸载会改变已安装列表，停止/清除会影响前台应用，两类都刷新一次
    if (kind === "uninstall") void loadApps();
    void loadApp();
  };

  return (
    <div className="panel-scroll">
      <div className="panel-title">
        <div>
          <h2>当前应用</h2>
          <p>查看和控制设备前台进程</p>
        </div>
        <div className="panel-actions">
          <Button compact icon={ArrowClockwise} loading={appLoading} onClick={loadApp}>刷新</Button>
        </div>
      </div>

      <section className="content-card">
        {appLoading ? <Spinner label="正在读取前台应用" /> : appError ? (
          <Banner tone="danger">
            <b>读取前台应用失败</b>：{appError.message}
            <div style={{ marginTop: 6 }}><Button compact onClick={loadApp}>重试</Button></div>
          </Banner>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
              <StatusPill tone="success" dot>运行中</StatusPill>
              <strong style={{ fontSize: 13 }}>{app.packageName === "unknown" ? "未知应用" : app.packageName}</strong>
            </div>
            <div className="field-grid">
              <label className="field">
                <span>包名</span>
                <div className="input-with-action">
                  <input value={app.packageName} readOnly aria-label="前台应用包名" />
                  <CopyButton value={app.packageName} label="复制" />
                </div>
              </label>
              <label className="field">
                <span>Activity</span>
                <div className="input-with-action">
                  <input value={app.activity || "—"} readOnly aria-label="前台 Activity" />
                  <CopyButton value={app.activity || ""} label="复制" />
                </div>
              </label>
            </div>
            <div className="button-row">
              <Button variant="danger" icon={Stop} disabled={readonly || busy || app.packageName === "unknown"} onClick={() => setPendingAction({ kind: "stop", packageName: app.packageName })}>停止应用</Button>
              <Button icon={Broom} disabled={readonly || busy || app.packageName === "unknown"} onClick={() => setPendingAction({ kind: "clear", packageName: app.packageName })}>清除数据</Button>
              {readonly ? <span style={{ alignSelf: "center", color: "var(--ls-color-text-tertiary)", fontSize: 12 }}>只读模式下启动与停止不可用</span> : null}
            </div>
          </>
        )}
      </section>

      <section className="content-card">
        <div className="card-heading">
          <div>
            <h3>启动应用</h3>
            <p>输入包名与 Activity 切换调试目标；只读模式下不可用</p>
          </div>
        </div>
        <div className="field-grid">
          <label className="field">
            <span>包名</span>
            <input
              className="input-with-action" style={{ height: 32, padding: "0 10px", borderRadius: 8, border: "1px solid var(--ls-color-border-default)", background: "var(--ls-color-bg-subtle)" }}
              value={launchPackage} onChange={(event) => setLaunchPackage(event.target.value)} placeholder="默认填入当前前台应用" aria-label="启动应用包名"
            />
          </label>
          <label className="field">
            <span>Activity（可选）</span>
            <input
              style={{ height: 32, padding: "0 10px", borderRadius: 8, border: "1px solid var(--ls-color-border-default)", background: "var(--ls-color-bg-subtle)" }}
              value={launchActivity} onChange={(event) => setLaunchActivity(event.target.value)} placeholder=".MainActivity" aria-label="启动应用 Activity"
            />
          </label>
        </div>
        <div className="button-row">
          <Button variant="primary" icon={Play} disabled={readonly || busy} loading={busy} onClick={launch}>启动</Button>
        </div>
      </section>

      <section className="content-card">
        <div className="card-heading">
          <div>
            <h3>包管理</h3>
            <p>搜索设备上的应用，点击包名填入启动表单，行内可直接停止、清除数据或卸载</p>
          </div>
          <Button compact icon={MagnifyingGlass} loading={appsLoading} onClick={() => loadApps()}>查询</Button>
        </div>
        <div className="tree-filter" style={{ padding: 0, marginBottom: 8, display: "flex", gap: 10, alignItems: "center" }}>
          <input
            value={appsQuery}
            onChange={(event) => setAppsQuery(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && loadApps()}
            placeholder="搜索包名，例如 com.baidu"
            aria-label="搜索已安装应用"
            style={{ flex: 1 }}
          />
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--ls-color-text-secondary)", whiteSpace: "nowrap" }}>
            <input
              type="checkbox"
              checked={includeSystem}
              onChange={(event) => { setIncludeSystem(event.target.checked); void loadApps(appsQuery, event.target.checked); }}
            />
            包含系统应用
          </label>
        </div>
        {appsError ? <Banner tone="danger"><b>应用列表读取失败</b>：{appsError.message}</Banner> : appsLoading ? <Spinner label="正在读取应用列表" /> : (
          <div className="app-list" aria-label="设备应用列表">
            {apps.map((item) => (
              <div key={item.packageName} className={`app-row ${item.packageName === app?.packageName ? "current" : ""}`}>
                <button className="app-row-name" onClick={() => setLaunchPackage(item.packageName)} title="填入启动表单">
                  {item.packageName === app?.packageName ? <StatusPill tone="success">前台</StatusPill> : null}
                  {item.system ? <StatusPill>系统</StatusPill> : null}
                  <span className="mono">{item.packageName}</span>
                </button>
                <div className="app-row-actions">
                  <Button compact icon={Play} disabled={readonly || busy} onClick={() => run(() => api.action(deviceId, { type: "start_app", packageName: item.packageName }), "启动指令已发送")} aria-label={`启动 ${item.packageName}`}>启动</Button>
                  <Button compact icon={Stop} disabled={readonly || busy} onClick={() => setPendingAction({ kind: "stop", packageName: item.packageName })} aria-label={`停止 ${item.packageName}`}>停止</Button>
                  <Button compact icon={Broom} disabled={readonly || busy} onClick={() => setPendingAction({ kind: "clear", packageName: item.packageName })} aria-label={`清除 ${item.packageName} 数据`}>清数据</Button>
                  <Button compact variant="danger" icon={Trash} disabled={readonly || busy || item.system} title={item.system ? "系统应用不支持卸载，设备会拒绝该请求" : undefined} onClick={() => setPendingAction({ kind: "uninstall", packageName: item.packageName })} aria-label={`卸载 ${item.packageName}`}>卸载</Button>
                </div>
              </div>
            ))}
            {apps.length === 0 ? <div className="tree-empty">没有匹配的应用</div> : null}
          </div>
        )}
        {readonly ? <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--ls-color-text-tertiary)" }}>只读模式下包管理写操作全部禁用。</p> : null}
      </section>

      <Dialog
        title={pendingAction ? RISKY_ACTIONS[pendingAction.kind].title : ""}
        open={Boolean(pendingAction)}
        onClose={() => setPendingAction(null)}
        footer={
          <>
            <Button onClick={() => setPendingAction(null)}>取消</Button>
            <Button variant="danger" onClick={runRisky}>{pendingAction ? RISKY_ACTIONS[pendingAction.kind].confirm : "确认"}</Button>
          </>
        }
      >
        <p style={{ margin: 0, lineHeight: 1.7 }}>
          即将对 <code>{pendingAction?.packageName}</code> 执行{pendingAction ? RISKY_ACTIONS[pendingAction.kind].title : ""}。这会{pendingAction ? RISKY_ACTIONS[pendingAction.kind].verb : ""}。确定要继续吗？
        </p>
      </Dialog>
    </div>
  );
}
