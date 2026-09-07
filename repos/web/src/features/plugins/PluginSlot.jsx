import { useCallback, useEffect, useRef, useState } from "react";
import { PuzzlePiece, Warning } from "@phosphor-icons/react";
import { Banner, Button } from "../../components/ui.jsx";
import { LogTags, uiLog } from "../../api/logger.js";
import { attachBridge, grantedPermissions, postBridgeEvent, setGrantedPermissions } from "./bridgeHost.js";

const LOAD_TIMEOUT_MS = 8000;

/**
 * 插件挂载点：只在被激活时创建 iframe，离开即销毁（等价于 LRU=1）。
 * 上下文用 ref 读取，避免每次快照更新都重建 iframe 让插件状态丢失。
 */
export function PluginSlot({ tab, context, onToast, height }) {
  const frameRef = useRef(null);
  const contextRef = useRef(context);
  const [phase, setPhase] = useState("loading");
  const [reloadKey, setReloadKey] = useState(0);

  contextRef.current = context;

  const requestPermission = useCallback((permission) => {
    const approved = window.confirm(`插件「${tab.pluginName}」请求 ${permission} 权限，是否允许？`);
    uiLog(LogTags.workbench, `插件权限请求 ${tab.pluginId}`, approved ? "info" : "warning", `${permission} → ${approved ? "允许" : "拒绝"}`);
    return approved;
  }, [tab.pluginId, tab.pluginName]);

  useEffect(() => {
    const frame = frameRef.current;
    if (!frame) return undefined;
    return attachBridge(frame, {
      tab,
      getContext: () => contextRef.current ?? {},
      onToast,
      requestPermission,
    });
  }, [tab, onToast, requestPermission, reloadKey]);

  useEffect(() => {
    setPhase("loading");
    const timer = window.setTimeout(() => {
      setPhase((current) => {
        if (current !== "loading") return current;
        uiLog(LogTags.workbench, `插件加载超时 ${tab.pluginId}`, "warning", `${LOAD_TIMEOUT_MS}ms`);
        return "timeout";
      });
    }, LOAD_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [tab.url, tab.pluginId, reloadKey]);

  // 快照变化推事件，插件按需自取，不必轮询
  useEffect(() => {
    if (phase !== "ready") return;
    postBridgeEvent(frameRef.current, "snapshot.changed", { snapshotId: context?.snapshotMeta?.snapshotId ?? null });
  }, [phase, context?.snapshotMeta?.snapshotId]);

  useEffect(() => {
    if (phase !== "ready") return;
    postBridgeEvent(frameRef.current, "node.selected", { nodeKey: context?.selectedNode ?? null });
  }, [phase, context?.selectedNode]);

  // 主题、只读、切设备都靠这一条事件下发，插件按能力查询自行适配，不做环境嗅探
  useEffect(() => {
    if (phase !== "ready") return;
    postBridgeEvent(frameRef.current, "context.changed", {
      theme: context?.theme ?? "light",
      readonly: Boolean(context?.readonly),
      deviceId: context?.deviceId ?? null,
    });
  }, [phase, context?.theme, context?.readonly, context?.deviceId]);

  return (
    <div className="plugin-slot">
      {phase === "timeout" ? (
        <Banner tone="warning">
          <b>插件页面加载超时</b>：{tab.pluginName} 未在 {LOAD_TIMEOUT_MS / 1000} 秒内就绪。
          <Button compact icon={Warning} onClick={() => setReloadKey((value) => value + 1)} style={{ marginLeft: 8 }}>重新加载</Button>
        </Banner>
      ) : null}
      <iframe
        key={reloadKey}
        ref={frameRef}
        className="plugin-frame"
        title={`${tab.pluginName} · ${tab.title}`}
        src={tab.url}
        // 关键：不给 allow-same-origin，插件文档保持 opaque origin，拿不到宿主 DOM 与存储
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
        loading="lazy"
        style={height ? { height, minHeight: 0 } : undefined}
        onLoad={() => setPhase("ready")}
      />
      <small className="plugin-slot-foot">
        <PuzzlePiece size={13} aria-hidden="true" />
        {tab.pluginId} · v{tab.version} · 已授权 {grantedPermissions(tab.pluginId).length}/{tab.permissions.length} 项
        {grantedPermissions(tab.pluginId).length > 0 ? (
          <button type="button" className="copy-inline" onClick={() => { setGrantedPermissions(tab.pluginId, []); onToast?.("已撤销该插件的全部授权"); }}>撤销授权</button>
        ) : null}
      </small>
    </div>
  );
}
