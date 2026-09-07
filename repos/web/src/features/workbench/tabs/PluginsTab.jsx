import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, CaretRight, FolderOpen, PuzzlePiece, Terminal, Warning } from "@phosphor-icons/react";
import { api } from "../../../api/client.js";
import { HostBridge } from "../../../app/HostBridge.js";
import { Banner, Button, CopyButton, EmptyState, Spinner, StatusPill } from "../../../components/ui.jsx";
import { pluginTabKey } from "../../plugins/registry.js";

const STATUS_TEXT = Object.freeze({
  ready: "可用",
  incompatible: "版本不兼容",
  invalid: "清单无效",
});

/** 插件入口以卡片流承载：一个插件一张圆角卡片，点卡片进二级页。 */
function PluginCard({ plugin, blocked, onOpen }) {
  const tab = plugin.contributions?.workbenchTabs?.[0] ?? null;
  const openable = plugin.status === "ready" && !blocked && tab;
  const problem = plugin.error?.message || blocked?.message || null;
  return (
    <article
      className={`plugin-tile ${openable ? "is-openable" : "is-disabled"}`}
      role={openable ? "button" : undefined}
      tabIndex={openable ? 0 : undefined}
      onClick={openable ? () => onOpen(pluginTabKey(plugin.id, tab.id)) : undefined}
      onKeyDown={openable ? (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(pluginTabKey(plugin.id, tab.id));
        }
      } : undefined}
    >
      <header>
        <span className="plugin-tile-logo" aria-hidden="true">
          {problem ? <Warning size={19} /> : <PuzzlePiece size={19} />}
        </span>
        <div className="plugin-tile-heading">
          <strong>{plugin.name}</strong>
          <small>v{plugin.version} · {plugin.origin === "builtin" ? "内置" : "本地"}{plugin.overrides === "builtin" ? "（覆盖内置）" : ""}</small>
        </div>
        <StatusPill tone={openable ? "success" : "warning"}>
          {blocked ? "当前环境不可用" : STATUS_TEXT[plugin.status] ?? plugin.status}
        </StatusPill>
      </header>
      <p className="plugin-tile-desc">{plugin.description || problem || "该插件未提供说明"}</p>
      <footer>
        <span className="plugin-tile-meta">{plugin.permissions?.length ?? 0} 项权限 · 激活 {plugin.activation}</span>
        {openable ? <span className="plugin-tile-open">打开<CaretRight size={12} aria-hidden="true" /></span> : null}
      </footer>
    </article>
  );
}

/** 终端是内置工具不是插件，但入口形态与插件卡片一致：固定在卡片流首位，点开进二级页。 */
function TerminalCard({ onOpen }) {
  return (
    <article
      className="plugin-tile is-openable"
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
    >
      <header>
        <span className="plugin-tile-logo" aria-hidden="true"><Terminal size={19} /></span>
        <div className="plugin-tile-heading">
          <strong>终端</strong>
          <small>内置工具</small>
        </div>
        <StatusPill tone="success">可用</StatusPill>
      </header>
      <p className="plugin-tile-desc">命令整串交给 adb shell 执行；上下键翻历史，Ctrl/Cmd+L 清屏，高危命令二次确认。</p>
      <footer>
        <span className="plugin-tile-meta">内置工具 · 打开即用</span>
        <span className="plugin-tile-open">打开<CaretRight size={12} aria-hidden="true" /></span>
      </footer>
    </article>
  );
}

export function PluginsTab({ extensions, onOpenPluginTab, onToast }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloading, setReloading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.pluginIndex());
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const reload = async () => {
    setReloading(true);
    try {
      setData(await api.pluginIndex(true));
      onToast?.("插件目录已重新扫描");
    } catch (err) {
      onToast?.(err.message, "danger");
    } finally {
      setReloading(false);
    }
  };

  const items = data?.items ?? [];
  const unavailableOf = (pluginId) => (extensions?.unavailable ?? []).find((item) => item.pluginId === pluginId) ?? null;

  return (
    <div className="panel-scroll">
      <div className="panel-title">
        <div>
          <h2>设备插件</h2>
          <p>内置插件随包提供，本地插件来自插件目录；同名时本地覆盖内置</p>
        </div>
        <div className="panel-actions">
          <Button compact icon={ArrowClockwise} loading={reloading} disabled={loading} onClick={reload}>重新扫描</Button>
          {HostBridge.can.openDirectory ? (
            <Button compact icon={FolderOpen} onClick={async () => {
              const result = await HostBridge.openPluginsDir();
              if (result?.opened === false) onToast?.("无法打开插件目录", "danger");
            }}>打开插件目录</Button>
          ) : (
            // 浏览器打不开本地目录，退化成把路径给出来让用户自己去
            <CopyButton value={data?.directory ?? ""} label="复制插件目录" />
          )}
        </div>
      </div>

      {error ? <Banner tone="danger"><b>插件索引读取失败</b>：{error.message}</Banner> : null}
      {loading ? <Spinner label="正在扫描插件目录" /> : (
        <>
          <div className="plugin-grid">
            <TerminalCard onOpen={() => onOpenPluginTab("terminal")} />
            {items.map((plugin) => (
              <PluginCard
                key={plugin.id}
                plugin={plugin}
                blocked={plugin.status === "ready" ? unavailableOf(plugin.id) : null}
                onOpen={onOpenPluginTab}
              />
            ))}
          </div>
          {items.length === 0 ? (
            <EmptyState icon={PuzzlePiece} title="还没有安装设备插件" description={`将插件文件夹放入 ${data?.directory ?? "插件目录"}，清单通过校验后即可在此加载。`}>
              {HostBridge.can.openDirectory ? (
                <Button variant="primary" icon={FolderOpen} onClick={() => HostBridge.openPluginsDir()}>在 Finder 中打开插件目录</Button>
              ) : (
                <CopyButton value={data?.directory ?? ""} label="复制插件目录路径" />
              )}
            </EmptyState>
          ) : null}
        </>
      )}
      <Banner tone="info" style={{ marginTop: 14 }}>
        <b>插件运行在受限 iframe 中。</b>能力只能通过 <code>$u</code> 桥调用，页面自身无法发起网络请求；写设备类权限首次使用时会向你确认。
      </Banner>
    </div>
  );
}
