import { useCallback, useEffect, useRef, useState } from "react";
import { Info, Warning } from "@phosphor-icons/react";
import { api } from "../../api/client.js";
import { ScrcpyViewer } from "../../media/scrcpyStream.js";
import { LogTags, uiLog, uiLogApi } from "../../api/logger.js";

const MAX_STREAM_RETRIES = 3;
const MAX_WIREFRAMES = 1200;

function hitTest(nodes, nx, ny) {
  const candidates = [];
  for (const node of nodes) {
    const b = node.boundsNormalized;
    if (nx < b.left || nx > b.right || ny < b.top || ny > b.bottom) continue;
    if (!node.visible && !node.clickable) continue;
    candidates.push(node);
  }
  candidates.sort((a, b) => {
    if (a.visible !== b.visible) return a.visible ? -1 : 1;
    if (a.depth !== b.depth) return b.depth - a.depth;
    const areaA = (a.boundsNormalized.right - a.boundsNormalized.left) * (a.boundsNormalized.bottom - a.boundsNormalized.top);
    const areaB = (b.boundsNormalized.right - b.boundsNormalized.left) * (b.boundsNormalized.bottom - b.boundsNormalized.top);
    if (areaA !== areaB) return areaA - areaB;
    return (b.drawingOrder ?? 0) - (a.drawingOrder ?? 0);
  });
  return candidates[0] || null;
}

export function DeviceCanvas({ device, snapshot, viewMode = "live", readonly, frozen, inspect, highlights, onSelectNode, onToast, onFitWidth, onPointerInfo }) {
  const wrapRef = useRef(null);
  const frameRef = useRef(null);
  const canvasRef = useRef(null);
  const viewerRef = useRef(null);
  const retriesRef = useRef(0);
  const [frame, setFrame] = useState(null);
  const [dims, setDims] = useState({ width: 0, height: 0 });
  const [deviceSize, setDeviceSize] = useState(null);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [frameError, setFrameError] = useState(null);
  const [hover, setHover] = useState(null);
  const [intervalMs, setIntervalMs] = useState(800);
  const [mediaMode, setMediaMode] = useState("loading");
  const [streamTick, setStreamTick] = useState(0);
  const objectUrl = useRef(null);
  const drag = useRef(null);
  const pointerInfoAt = useRef(0);
  const deviceId = device?.deviceId;
  const snapshotView = viewMode === "snapshot" && snapshot?.data;
  const liveActive = mediaMode === "live" && device?.status === "connected" && !snapshotView;

  // 媒体能力：决定 scrcpy 实时流或截图轮询
  useEffect(() => {
    let active = true;
    retriesRef.current = 0;
    setMediaMode("loading");
    api.settings().then((store) => {
      if (active) setIntervalMs(Math.min(3000, Math.max(400, store.screenshotFallbackIntervalMs ?? 800)));
    }).catch(() => {});
    api.mediaCapabilities(deviceId).then((payload) => {
      if (!active) return;
      const mode = payload?.mode === "scrcpy" && payload?.live ? "live" : "screenshot";
      setMediaMode(mode);
      uiLog(LogTags.media, `媒体模式：${mode === "live" ? "scrcpy 实时投屏" : "截图轮询"}`, "info", deviceId);
    }).catch(() => {
      if (active) setMediaMode("screenshot");
    });
    // 设备物理分辨率：点击坐标换算的基准（流是缩放过的，两者不同）
    api.windowSize(deviceId).then((size) => {
      if (active && size?.width) setDeviceSize(size);
    }).catch(() => {});
    return () => {
      active = false;
    };
  }, [deviceId]);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return undefined;
    const update = () => setViewport({ width: wrap.clientWidth, height: wrap.clientHeight });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(wrap);
    return () => observer.disconnect();
  }, []);

  // scrcpy 实时流生命周期（快照查看模式挂起推流，省 CPU 且避免延迟累积）
  useEffect(() => {
    if (!liveActive) return undefined;
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    uiLog(LogTags.media, "启动 scrcpy 实时流", "info", `第 ${retriesRef.current + 1} 次尝试`);
    const viewer = new ScrcpyViewer({
      canvas,
      deviceId,
      onMeta: (meta) => {
        setDims({ width: meta.width, height: meta.height });
        setFrameError(null);
        uiLog(LogTags.media, "scrcpy 流已建立", "info", `${meta.width}x${meta.height}@${meta.fps}fps`);
      },
      onStats: (stats) => {
        if (stats.frames > 0 && stats.frames % 120 === 0) {
          uiLog(LogTags.media, "投屏进行中", "info", `${stats.fps}fps 已解码 ${stats.frames} 帧 丢弃 ${stats.dropped}`);
        }
      },
      onError: (error) => {
        retriesRef.current += 1;
        uiLog(LogTags.media, "scrcpy 流异常", "warning", `${error?.message ?? error}（第 ${retriesRef.current} 次）`);
        if (retriesRef.current >= MAX_STREAM_RETRIES) {
          setMediaMode("screenshot");
          uiLog(LogTags.media, "多次失败，降级为截图轮询", "warning");
        } else {
          setStreamTick((tick) => tick + 1);
        }
      },
    });
    viewerRef.current = viewer;
    viewer.start();
    return () => {
      viewer.stop();
      viewerRef.current = null;
    };
  }, [liveActive, device?.status, deviceId, streamTick]);

  // 截图轮询降级链路
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
        setFrameError(null);
      } catch (error) {
        if (!active) return;
        setFrameError(error);
      }
    };
    if (!liveActive && !snapshotView && device?.status === "connected" && !frozen) {
      tick();
      timer = setInterval(tick, intervalMs);
    }
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [liveActive, snapshotView, device?.deviceId, device?.status, intervalMs, frozen]);

  useEffect(() => {
    viewerRef.current?.setFrozen(Boolean(frozen));
  }, [frozen]);

  useEffect(() => () => {
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
  }, []);

  // 渲染尺寸：投屏/截图按内容比例；快照查看用快照截图比例
  const contentUrl = snapshotView ? snapshot.data.screenshot?.contentUrl : null;
  const renderAspect = (() => {
    if (snapshotView && snapshot.data.screenshot?.width) {
      return `${snapshot.data.screenshot.width} / ${snapshot.data.screenshot.height}`;
    }
    return dims.width && dims.height ? `${dims.width} / ${dims.height}` : "9 / 19";
  })();

  const frameSize = (() => {
    // live 模式零留白贴合 scrcpy；快照模式留少量呼吸边
    const margin = snapshotView ? 12 : 0;
    const source = snapshotView && snapshot.data.screenshot?.width
      ? { width: snapshot.data.screenshot.width, height: snapshot.data.screenshot.height }
      : dims;
    if (!source.width || !source.height || !viewport.width || !viewport.height) return null;
    const scale = Math.min((viewport.width - margin) / source.width, (viewport.height - margin) / source.height);
    // floor 而非 round：保证画面永不超出容器，避免出现横向滚动条
    return { width: Math.max(80, Math.floor(source.width * scale)), height: Math.max(80, Math.floor(source.height * scale)) };
  })();

  // 流建立后上报画面宽度，工作台可把设备区宽度自适应到画面比例（仅首次）
  useEffect(() => {
    if (snapshotView || !dims.width || !viewport.height || !onFitWidth) return;
    const scale = Math.min(viewport.width / dims.width, viewport.height / dims.height);
    onFitWidth(Math.floor(dims.width * scale));
  }, [dims, viewport.height, snapshotView, onFitWidth]);

  // 点击坐标 → 设备物理像素（投屏流是缩放视图，必须用设备真实分辨率换算）
  const toDevicePx = (clientX, clientY) => {
    const rect = frameRef.current?.getBoundingClientRect();
    const target = deviceSize ?? (snapshotView ? snapshot.data.windowSizePx : dims);
    if (!rect || !target?.width) return null;
    const nx = (clientX - rect.left) / rect.width;
    const ny = (clientY - rect.top) / rect.height;
    if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return null;
    return { x: Math.round(nx * target.width), y: Math.round(ny * target.height), nx, ny };
  };

  const nodeOverlays = useCallback(() => {
    const overlays = [];
    const nodes = snapshot?.data?.nodes ?? [];
    if (snapshotView) {
      // 布局查看模式：全节点线框（对齐 UIAutoDev），供自由浏览与点选
      let drawn = 0;
      for (const node of nodes) {
        if (!node.visible || drawn >= MAX_WIREFRAMES) continue;
        const b = node.boundsNormalized;
        if (b.right - b.left <= 0.0005 || b.bottom - b.top <= 0.0005) continue;
        const selected = highlights?.[node.nodeKey];
        overlays.push(
          <div
            key={`wire-${node.nodeKey}`}
            className={`node-overlay wireframe ${selected ? `selected ${selected === "selected" ? "" : selected}` : ""}`}
            style={{
              left: `${b.left * 100}%`,
              top: `${b.top * 100}%`,
              width: `${(b.right - b.left) * 100}%`,
              height: `${(b.bottom - b.top) * 100}%`,
            }}
          />,
        );
        drawn += 1;
      }
      return overlays;
    }
    for (const [key, kind] of Object.entries(highlights ?? {})) {
      const node = nodes.find((item) => item.nodeKey === key);
      if (node) {
        const b = node.boundsNormalized;
        overlays.push(
          <div
            key={`${kind}-${key}`}
            className={`node-overlay ${kind}`}
            style={{ left: `${b.left * 100}%`, top: `${b.top * 100}%`, width: `${(b.right - b.left) * 100}%`, height: `${(b.bottom - b.top) * 100}%` }}
          />,
        );
      }
    }
    return overlays;
  }, [snapshot, highlights, snapshotView]);

  const sendAction = async (action) => {
    if (readonly) {
      onToast?.("只读模式已开启，写操作被拦截", "warning");
      return;
    }
    if (frozen) {
      onToast?.("画面已冻结，请先解除冻结", "warning");
      return;
    }
    try {
      await uiLogApi(LogTags.media, `注入动作 ${action.type}`, () => api.action(device.deviceId, action));
    } catch (error) {
      onToast?.(error.message, "danger");
    }
  };

  const onPointerMove = (event) => {
    // 底部状态栏要的是设备物理坐标与百分比，两种视图模式都上报；节流 60ms，避免 pointermove 打满父级重渲染
    const now = performance.now();
    if (now - pointerInfoAt.current >= 60) {
      pointerInfoAt.current = now;
      const point = toDevicePx(event.clientX, event.clientY);
      onPointerInfo?.(point ? { x: point.x, y: point.y, nx: point.nx, ny: point.ny } : null);
    }
    if (snapshotView) return;
    const rect = frameRef.current?.getBoundingClientRect();
    if (!rect || !dims.width) return;
    const nx = (event.clientX - rect.left) / rect.width;
    const ny = (event.clientY - rect.top) / rect.height;
    setHover({ x: Math.round(nx * dims.width), y: Math.round(ny * dims.height), nx, ny });
    if (!drag.current) return;
    if (Math.hypot(event.clientX - drag.current.x, event.clientY - drag.current.y) > 6) drag.current.moved = true;
  };

  const onPointerDown = (event) => {
    if (snapshotView) return;
    if (event.button !== 0) return;
    drag.current = { x: event.clientX, y: event.clientY, moved: false };
  };

  const onPointerUp = (event) => {
    const point = toDevicePx(event.clientX, event.clientY);
    if (!point) return;
    if (snapshotView) {
      // 布局查看模式：点击命中节点并联动属性/层级，不注入 tap
      const node = snapshot.data ? hitTest(snapshot.data.nodes, point.nx, point.ny) : null;
      if (node) onSelectNode?.(node.nodeKey);
      else onToast?.("该位置没有可命中的节点", "warning");
      return;
    }
    if (!drag.current || event.button !== 0) return;
    const start = drag.current;
    drag.current = null;
    if (start.moved) {
      const from = toDevicePx(start.x, start.y);
      if (from && (Math.abs(from.x - point.x) > 4 || Math.abs(from.y - point.y) > 4)) {
        void sendAction({ type: "swipe", fromX: from.x, fromY: from.y, toX: point.x, toY: point.y, durationMs: 300 });
      }
      return;
    }
    if (inspect) {
      const node = snapshot?.data ? hitTest(snapshot.data.nodes, point.nx, point.ny) : null;
      if (node) onSelectNode?.(node.nodeKey);
      else onToast?.("该位置没有可命中的节点", "warning");
      return;
    }
    void sendAction({ type: "tap", x: point.x, y: point.y });
  };

  const onContextMenu = (event) => {
    event.preventDefault();
    if (snapshotView) return;
    void sendAction({ type: "press_key", key: "HOME" });
  };

  const onAuxClick = (event) => {
    if (snapshotView) return;
    if (event.button === 1) void sendAction({ type: "press_key", key: "HOME" });
    if (event.button === 2) void sendAction({ type: "press_key", key: "BACK" });
  };

  const onWheel = (event) => {
    event.preventDefault();
    if (snapshotView) return;
    if (Math.abs(event.deltaY) < 8) return;
    const rect = frameRef.current?.getBoundingClientRect();
    if (!rect) return;
    const cx = rect.left + rect.width / 2;
    const from = toDevicePx(cx, rect.top + rect.height * 0.72);
    const to = toDevicePx(cx, rect.top + rect.height * 0.28);
    if (!from || !to) return;
    void sendAction({ type: "swipe", fromX: from.x, fromY: from.y, toX: to.x, toY: to.y, durationMs: 260 });
  };

  const onKeyDown = (event) => {
    if (snapshotView) return;
    if (event.key === "Enter") {
      event.preventDefault();
      void sendAction({ type: "press_key", key: "ENTER" });
      return;
    }
    if (event.key === "Backspace") {
      event.preventDefault();
      void sendAction({ type: "press_key", key: "DEL" });
      return;
    }
    if (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) {
      void sendAction({ type: "input_text", text: event.key });
    }
  };

  const showPollingFrame = !liveActive && !snapshotView;
  const liveLabel = snapshotView
    ? "布局查看"
    : frozen ? "已冻结" : inspect ? "审查模式" : readonly ? "只读模式" : liveActive ? "实时投屏" : "截图模式";
  const labelTone = frozen ? "frozen" : inspect ? "inspect" : readonly ? "readonly" : "";

  return (
    <div className={`device-canvas-wrap ${snapshotView ? "snapshot-view" : "live-view"}`} ref={wrapRef}>
      <div className="device-viewport">
        <div
          ref={frameRef}
          className={`device-frame ${snapshotView ? "snapshot" : ""} ${dims.width > dims.height ? "landscape" : ""}`}
          style={{ width: frameSize?.width ?? undefined, height: frameSize?.height ?? undefined, aspectRatio: frameSize ? undefined : renderAspect, touchAction: "none" }}
          tabIndex={0}
          role="img"
          aria-label={`${device.model || "设备"}画面${snapshotView ? "（布局查看）" : ""}`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerLeave={() => { setHover(null); pointerInfoAt.current = 0; onPointerInfo?.(null); }}
          onPointerUp={onPointerUp}
          onContextMenu={onContextMenu}
          onAuxClick={onAuxClick}
          onWheel={onWheel}
          onKeyDown={onKeyDown}
        >
          <canvas
            ref={canvasRef}
            className="device-pixel"
            style={{ display: liveActive ? "block" : "none", width: "100%", height: "100%", objectFit: "contain" }}
            aria-hidden="true"
          />
          {snapshotView && contentUrl ? <img className="device-pixel" src={contentUrl} alt="快照画面" draggable="false" /> : null}
          {showPollingFrame && frame ? <img className="device-pixel" src={frame} alt="" onLoad={(event) => setDims({ width: event.target.naturalWidth, height: event.target.naturalHeight })} draggable="false" /> : null}
          {showPollingFrame && !frame && !frameError ? <span className="frame-placeholder">正在获取画面…</span> : null}
          {showPollingFrame && frameError ? <span className="frame-placeholder"><Info size={16} />画面获取失败，将自动重试</span> : null}
          {snapshot ? nodeOverlays() : null}
          <span className={`stream-badge ${labelTone}`}>
            <i aria-hidden="true" />{liveLabel}
          </span>
          {hover && !snapshotView ? (
            <span className="hover-readout" aria-hidden="true">
              {hover.x}×{hover.y} · {Math.round(hover.nx * 1000) / 10}%/{Math.round(hover.ny * 1000) / 10}%
            </span>
          ) : null}
        </div>
      </div>
      {snapshot?.meta?.synchronization === "context_changed" ? (
        <div style={{ position: "absolute", left: 16, top: 16 }}>
          <span className="stream-badge error" style={{ position: "static" }}><Warning size={12} />快照与画面不同步</span>
        </div>
      ) : null}
    </div>
  );
}
