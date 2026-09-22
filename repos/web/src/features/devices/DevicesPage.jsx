import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AndroidLogo, ArrowClockwise, Check, Copy, CursorClick, GridFour, Info, X } from "@phosphor-icons/react";
import { api } from "../../api/client.js";
import { MorphGlyph, glyphs } from "../../components/MorphIcons.jsx";
import { Banner, Button, Dialog, EmptyState, IconButton, Spinner, StatusPill, useToast } from "../../components/ui.jsx";
import { PlatformPlaceholder } from "./PlatformPlaceholder.jsx";

const STATUS_TEXT = {
  connected: "已连接",
  unauthorized: "未授权",
  offline: "已离线",
  error: "异常",
};

const STATUS_TONE = {
  connected: "success",
  unauthorized: "warning",
  offline: "neutral",
  error: "danger",
};

// 平台 Tab：Android 已实现；iOS / HarmonyOS 先给占位与预告，不做功能实现
const PLATFORMS = [
  { id: "android", label: "Android" },
  {
    id: "ios",
    label: "iOS",
    glyph: glyphs.platformIos,
    headline: "iOS 支持正在路上",
    note: "设备接入 · 敬请期待",
    detail: "V0.1 先把 Android 真机链路做扎实：发现、投屏、抓取、定位。iOS 的接入会沿用同一套快照与元素模型，正在设计中。",
  },
  {
    id: "harmony",
    label: "HarmonyOS",
    glyph: glyphs.platformHarmony,
    headline: "HarmonyOS 支持正在路上",
    note: "设备接入 · 敬请期待",
    detail: "HarmonyOS NEXT 的调试链路与 Android 差异较大，我们会在 Android 体验稳定后单独评估，当前还没有可交付的版本。",
  },
];

export function DevicesPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(() => new Set(JSON.parse(sessionStorage.getItem("layoutsee.groupSelection") || "[]")));
  const [diagnosticsFor, setDiagnosticsFor] = useState(null);
  const [platform, setPlatform] = useState("android");

  const load = useCallback(async ({ manual = false } = {}) => {
    if (manual) setRefreshing(true);
    try {
      const payload = await api.devices();
      setData(payload);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(() => load(), 5000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    sessionStorage.setItem("layoutsee.groupSelection", JSON.stringify([...selected]));
  }, [selected]);

  const devices = data?.items ?? [];
  const online = devices.filter((item) => item.status === "connected");

  const toggle = (deviceId) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(deviceId)) next.delete(deviceId);
      else next.add(deviceId);
      return next;
    });
  };

  const copySerial = async (serial) => {
    await navigator.clipboard.writeText(serial);
    toast("序列号已复制");
  };

  const adbMissing = data && !data.items.length && data.lastError?.startsWith("ADB_NOT_FOUND");

  return (
    <main className="page-content">
      <div className="page-heading">
        <div>
          <h1>设备管理</h1>
          <p>管理和监控已连接的移动设备</p>
        </div>
        <div className="page-toolbar">
          <Button icon={ArrowClockwise} loading={refreshing} onClick={() => load({ manual: true })}>刷新</Button>
          <Button icon={GridFour} variant="primary" onClick={() => navigate("/group")}>
            群控{selected.size > 0 ? `（${selected.size}）` : ""}
          </Button>
        </div>
      </div>

      <div className="platform-tabs" role="tablist" aria-label="设备平台">
        {PLATFORMS.map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={platform === item.id}
            className={platform === item.id ? "active" : ""}
            onClick={() => setPlatform(item.id)}
          >
            {item.id === "android"
              ? <AndroidLogo size={16} aria-hidden="true" />
              : <MorphGlyph icon={item.glyph} size={16} strokeWidth={1.8} />}
            {item.label}
            {item.id === "android" && devices.length > 0 ? <span>{devices.length}</span> : null}
            {item.id !== "android" ? <em>预告</em> : null}
          </button>
        ))}
      </div>

      {platform !== "android" ? (
        <PlatformPlaceholder
          key={platform}
          platform={PLATFORMS.find((item) => item.id === platform)}
          onBackToAndroid={() => setPlatform("android")}
        />
      ) : (
      <>

      {error ? (
        <Banner tone="danger" icon={Info}>
          <b>设备枚举失败</b>，已保留上一轮结果。<code>{error.message}</code>
        </Banner>
      ) : null}

      {loading ? (
        <div className="table-card" style={{ padding: 24 }}><Spinner label="正在枚举设备" /></div>
      ) : devices.length === 0 ? (
        // scanning：仅在 ADB 可用时开启声呐扫描（找不到 adb 时并没有在扫，不该装作在扫）
        <section className={`table-card device-empty${adbMissing ? "" : " scanning"}`} style={{ padding: 20 }}>
          <EmptyState icon={AndroidLogo} title={adbMissing ? "未找到 ADB 工具链" : "还没有检测到设备"} description={adbMissing ? "请在设置中指定 adb 路径，或安装 Android platform-tools 后重新检测。" : "使用 USB 连接设备并开启开发者模式，LayoutSee 会自动发现可用设备。"}>
            <div className="setup-guide">
              <div className="guide-step">
                <span className="step-no" aria-hidden="true">1</span>
                <div><b>开启开发者选项与 USB 调试</b><p>在设备「设置 → 关于手机」连续点击版本号，然后开启 USB 调试。</p></div>
              </div>
              <div className="guide-step">
                <span className="step-no" aria-hidden="true">2</span>
                <div><b>使用数据线连接 Mac</b><p>确认线缆支持数据传输，而不是仅充电。</p></div>
              </div>
              <div className="guide-step">
                <span className="step-no" aria-hidden="true">3</span>
                <div><b>在设备上确认授权弹窗</b><p>勾选「始终允许这台计算机调试」后点击允许。</p></div>
              </div>
              {adbMissing ? (
                <div style={{ marginTop: 4 }}>
                  <Button variant="primary" onClick={() => navigate("/settings")}>打开设置指定 adb 路径</Button>
                </div>
              ) : null}
            </div>
          </EmptyState>
        </section>
      ) : (
        <section className="table-card">
          <div className="device-table table-head" aria-hidden="true">
            <span>#</span><span>平台</span><span>序列号</span><span>型号</span><span>产品</span><span>状态</span><span className="align-right">操作</span>
          </div>
          {devices.map((device, index) => {
            const statusClass = device.status === "connected" ? "" : device.status;
            return (
              <div className="device-table table-row" key={device.deviceId}>
                <span className="muted">{index + 1}</span>
                <span className="platform-cell"><span className="platform-icon"><AndroidLogo size={15} aria-hidden="true" /></span>Android</span>
                <button className="serial-copy" onClick={() => copySerial(device.serial)} aria-label={`复制序列号 ${device.serial}`}>
                  {device.serial}<Copy size={13} aria-hidden="true" />
                </button>
                <span>{device.model || "—"}</span>
                <span>{device.product || "—"}</span>
                <span className={`status-inline ${statusClass}`}>
                  <i aria-hidden="true" />
                  {device.readonly ? `${STATUS_TEXT[device.status] ?? device.status} · 只读` : STATUS_TEXT[device.status] ?? device.status}
                </span>
                <span className="row-actions">
                  {device.status !== "connected" ? (
                    <Button compact onClick={() => setDiagnosticsFor(device.deviceId)}>诊断</Button>
                  ) : (
                    <Button compact variant="primary" icon={CursorClick} onClick={() => navigate(`/devices/${encodeURIComponent(device.deviceId)}/workbench/common`)}>
                      控制
                    </Button>
                  )}
                </span>
              </div>
            );
          })}
          <div className="table-footer">
            <span>共 {devices.length} 台设备 · {online.length} 台在线</span>
            <span className="muted">{data?.lastError ? `最近错误：${data.lastError}` : data?.refreshedAt ? `最近刷新：${new Date(data.refreshedAt).toLocaleTimeString()}` : ""}</span>
          </div>
        </section>
      )}

      </>
      )}

      <DiagnosticsDialog deviceId={diagnosticsFor} onClose={() => setDiagnosticsFor(null)} />
    </main>
  );
}

function DiagnosticsDialog({ deviceId, onClose }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!deviceId) return;
    let active = true;
    setLoading(true);
    setResult(null);
    setError(null);
    api.deviceDiagnostics(deviceId)
      .then((payload) => active && setResult(payload))
      .catch((err) => active && setError(err))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [deviceId]);

  return (
    <Dialog
      title="接入诊断"
      open={Boolean(deviceId)}
      onClose={onClose}
      footer={<Button variant="primary" onClick={onClose}>完成</Button>}
    >
      {loading ? <Spinner label="正在诊断" /> : error ? (
        <Banner tone="danger" icon={X}><b>诊断失败</b>：{error.message}</Banner>
      ) : result ? (
        <div>
          <StatusPill tone={result.healthy ? "success" : "warning"} dot>{result.healthy ? "全部检查通过" : "存在需要处理的检查项"}</StatusPill>
          <div style={{ marginTop: 12 }}>
            {(result.checks ?? []).map((check) => (
              <div className="diag-row" key={check.name}>
                <span className={`diag-status ${check.status}`} aria-hidden="true">
                  {check.status === "pass" ? <Check size={12} weight="bold" /> : check.status === "fail" ? <X size={12} weight="bold" /> : "?"}
                </span>
                <div>
                  <b>{check.name}</b>
                  <p>{check.message}</p>
                  {check.hint ? <p className="hint">建议：{check.hint}</p> : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </Dialog>
  );
}
