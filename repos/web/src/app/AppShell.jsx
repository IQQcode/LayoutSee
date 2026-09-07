import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { DeviceMobile, GearSix, GridFour, Wrench } from "@phosphor-icons/react";
import { HostBridge, KERNEL_STATE_TEXT } from "./HostBridge.js";
import { Banner, IconButton } from "../components/ui.jsx";

const NAV_ITEMS = [
  { id: "devices", label: "设备", path: "/devices", icon: DeviceMobile },
  { id: "group", label: "群控", path: "/group", icon: GridFour },
  { id: "settings", label: "设置", path: "/settings", icon: GearSix },
];

function KernelBanner() {
  const [session, setSession] = useState(HostBridge.getSession());
  useEffect(() => HostBridge.subscribe(setSession), []);
  if (!session || session.state === "ready" || session.state === "stopping" || session.state === "stopped") return null;
  const tone = session.state === "failed" || session.state === "no_session" ? "danger" : "warning";
  return (
    <div style={{ padding: "0 16px 10px" }}>
      <Banner tone={tone} icon={Wrench}>
        <b>{KERNEL_STATE_TEXT[session.state] ?? "Core 状态异常"}</b>
        {session.detail ? <span>（{session.detail}）</span> : null}
        <span style={{ marginLeft: 10 }}>
          {session.state === "failed" ? (
            <button className="button compact" onClick={() => HostBridge.retryKernel()}>重试</button>
          ) : session.state === "no_session" ? (
            "请改用 Core 启动时打印的 http://127.0.0.1 地址访问。"
          ) : (
            "已保留最后一帧与已有快照，写操作已暂停。"
          )}
        </span>
      </Banner>
    </div>
  );
}

function useKernelOrigin() {
  const [session, setSession] = useState(HostBridge.getSession());
  useEffect(() => HostBridge.subscribe(setSession), []);
  return session;
}

export function AppShell() {
  const [coreInfo, setCoreInfo] = useState(null);
  const session = useKernelOrigin();
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    fetch("/api/v1/info", { headers: { Accept: "application/json" } })
      .then((response) => response.json())
      .then((payload) => {
        if (active && payload.ok) setCoreInfo(payload.data);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const kernelState = session?.state ?? "ready";
  const kernelDotClass = kernelState === "ready" ? "" : kernelState === "failed" ? "failed" : "offline";

  const titlebar = useMemo(
    () => (
      <header className="window-titlebar">
        <div className="brand-lockup">
          <img className="brand-mark" src="/layoutsee-icon-192.png" alt="" aria-hidden="true" />
          <span>LayoutSee</span>
          <span className="version-chip">V0.1</span>
        </div>
        <div className="top-actions">
          <IconButton
            icon={GearSix}
            label="打开设置"
            tooltip="设置"
            active={window.location.pathname.startsWith("/settings")}
            onClick={() => navigate("/settings")}
          />
        </div>
      </header>
    ),
    [navigate],
  );

  return (
    <div className="app-shell">
      {titlebar}
      <div className="app-body">
        <aside className="sidebar">
          <nav aria-label="主导航">
            {NAV_ITEMS.map(({ id, label, path, icon: Icon }) => (
              <NavLink key={id} to={path} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
                <span className="nav-icon"><Icon size={19} aria-hidden="true" /></span>
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-status">
            <span className={`kernel-dot ${kernelDotClass}`} aria-hidden="true" />
            <div>
              <strong>{kernelState === "ready" ? "本地内核已连接" : "本地内核异常"}</strong>
              <small>{coreInfo ? `127.0.0.1:${coreInfo.port}` : "连接中…"}</small>
            </div>
          </div>
        </aside>
        <main className="page-area" style={{ display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
          <KernelBanner />
          <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
