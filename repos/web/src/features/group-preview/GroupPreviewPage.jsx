import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AndroidLogo, ArrowLeft, Snowflake } from "@phosphor-icons/react";
import { api } from "../../api/client.js";
import { Banner, Button, EmptyState, StatusPill } from "../../components/ui.jsx";

const STATUS_TONE = { connected: "success", unauthorized: "warning", offline: "neutral", error: "danger" };
const STATUS_TEXT = { connected: "在线", unauthorized: "未授权", offline: "已离线", error: "异常" };

function DeviceCell({ device, intervalMs }) {
  const [frame, setFrame] = useState(null);
  const [frozen, setFrozen] = useState(false);
  const objectUrl = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    let timer = 0;
    const tick = async () => {
      try {
        const response = await fetch(`/api/v1/devices/${encodeURIComponent(device.deviceId)}/screenshot`, { headers: { Accept: "image/png" } });
        if (!active) return;
        if (!response.ok) throw new Error(`HTTP_${response.status}`);
        const blob = await response.blob();
        if (!active) return;
        if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
        objectUrl.current = URL.createObjectURL(blob);
        setFrame(objectUrl.current);
      } catch {
        // 保留上一帧，仅冻结该格
      }
    };
    if (device.status === "connected" && !frozen) {
      tick();
      timer = setInterval(tick, intervalMs || 1000);
    }
    return () => {
      active = false;
      clearInterval(timer);
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = null;
    };
  }, [device.deviceId, device.status, intervalMs, frozen]);

  const offline = device.status !== "connected";
  return (
    <article className={`group-card ${offline ? "offline" : ""}`}>
      <div className="group-meta">
        <strong>{device.model || "Android 设备"}</strong>
        <StatusPill tone={STATUS_TONE[device.status] ?? "neutral"} dot>{STATUS_TEXT[device.status] ?? device.status}</StatusPill>
        <small>{device.serial}</small>
      </div>
      <div
        className="group-frame"
        onDoubleClick={() => !offline && navigate(`/devices/${encodeURIComponent(device.deviceId)}/workbench/common`)}
        title={offline ? "设备已离线" : "双击进入工作台"}
      >
        {frame ? <img src={frame} alt={`${device.model || "设备"} 实时画面`} decoding="async" draggable="false" /> : (
          <span style={{ color: "var(--ls-color-text-tertiary)" }}>{offline ? "设备已离线" : "连接中…"}</span>
        )}
        {frozen ? <span className="stream-badge frozen" style={{ position: "absolute", top: 8, left: 8 }}><Snowflake size={12} />已冻结</span> : null}
      </div>
      {!offline ? (
        <div style={{ display: "flex", justifyContent: "flex-end", padding: 8 }}>
          <button className="button compact" onClick={() => setFrozen((value) => !value)}>{frozen ? "恢复画面" : "冻结该格"}</button>
        </div>
      ) : null}
    </article>
  );
}

export function GroupPreviewPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [settings, setSettings] = useState(null);
  const [selection] = useState(() => JSON.parse(sessionStorage.getItem("layoutsee.groupSelection") || "[]"));

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [devices, store] = await Promise.all([api.devices(), api.settings()]);
        if (!active) return;
        setData(devices);
        setSettings(store);
      } catch {
        // 保留上一轮结果
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  const intervalMs = Math.min(2000, Math.max(500, (settings?.screenshotFallbackIntervalMs ?? 1000) * 2));
  const devices = data?.items ?? [];
  const byId = new Map(devices.map((item) => [item.deviceId, item]));
  const selectedDevices = selection.map((id) => byId.get(id)).filter(Boolean);

  if (selection.length === 0 || selectedDevices.length === 0) {
    return (
      <main className="page-content">
        <div className="page-heading">
          <div>
            <h1>群控预览</h1>
            <p>同时观察多台设备的运行画面</p>
          </div>
        </div>
        <section className="table-card">
          <EmptyState icon={AndroidLogo} title={devices.length === 0 ? "请先连接设备" : "还没有选择设备"} description="先从设备列表勾选一台或多台设备，再进入群控预览。双击某个预览格可进入该设备工作台。">
            <button className="button primary" onClick={() => navigate("/devices")}>前往设备页选择</button>
          </EmptyState>
        </section>
      </main>
    );
  }

  return (
    <main className="page-content" style={{ display: "flex", flexDirection: "column" }}>
      <div className="page-heading">
        <div>
          <h1>群控预览</h1>
          <p>按数量自适应排列并保持真实宽高比；双击某个预览格进入该设备工作台</p>
        </div>
        <div className="page-toolbar">
          <Button icon={ArrowLeft} onClick={() => navigate("/devices")}>返回设备页</Button>
        </div>
      </div>
      {selectedDevices.length > 4 ? (
        <Banner tone="info"><b>已选择 {selectedDevices.length} 台设备</b>，超出性能阈值，已自动降低各格刷新频率。</Banner>
      ) : null}
      <div className="group-grid">
        {selectedDevices.map((device) => (
          <DeviceCell key={device.deviceId} device={device} intervalMs={intervalMs} />
        ))}
      </div>
    </main>
  );
}
