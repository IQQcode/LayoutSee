import { useEffect, useMemo, useState } from "react";
import { CaretDown, CaretRight, LockKey, TerminalWindow } from "@phosphor-icons/react";
import { api } from "../../../api/client.js";
import { LogTags, uiLog } from "../../../api/logger.js";
import { Banner, Button, CopyButton, Spinner, StatusPill } from "../../../components/ui.jsx";

const CLIENTS = [".mcp.json", "Claude", "Cursor", "Comate"];

export function McpTab({ device, deviceId, readonly, onToast }) {
  const [tools, setTools] = useState(null);
  const [error, setError] = useState(null);
  const [client, setClient] = useState(".mcp.json");
  const [expanded, setExpanded] = useState(-1);

  useEffect(() => {
    let active = true;
    api.mcpTools()
      .then((payload) => {
        if (!active) return;
        setTools(payload.tools ?? []);
        uiLog(LogTags.mcp, "工具列表已加载", "info", `${payload.tools?.length ?? 0} 个工具`);
      })
      .catch((err) => {
        if (!active) return;
        setError(err);
        uiLog(LogTags.mcp, "工具列表读取失败", "error", `${err?.code ?? ""} ${err?.message ?? err}`);
      });
    return () => {
      active = false;
    };
  }, []);

  const port = window.location.port || "11663";
  const endpoint = `http://127.0.0.1:${port}/mcp/${deviceId}/sse`;

  const snippets = useMemo(() => ({
    ".mcp.json": `{\n  "mcpServers": {\n    "layoutsee-${deviceId}": {\n      "type": "sse",\n      "url": "${endpoint}"\n    }\n  }\n}`,
    Claude: `# ~/Library/Application Support/Claude/claude_desktop_config.json\n{\n  "mcpServers": { "layoutsee": { "url": "${endpoint}" } }\n}`,
    Cursor: `# Cursor MCP settings\n{\n  "layoutsee": { "url": "${endpoint}" } }\n}`,
    Comate: `# Comate MCP 配置\n{\n  "layoutsee": { "url": "${endpoint}" } }\n}`,
  }), [deviceId, endpoint]);

  const writeTools = tools?.filter((tool) => tool.kind === "write") ?? [];

  return (
    <div className="panel-scroll">
      <div className="panel-title">
        <div>
          <h2>MCP Server</h2>
          <p>让 AI Agent 读取并控制当前设备</p>
        </div>
        <StatusPill tone={readonly ? "warning" : "success"} dot>{readonly ? "只读模式" : "写工具可用"}</StatusPill>
      </div>

      {readonly ? (
        <Banner tone="warning" icon={LockKey}>
          <b>只读模式已开启</b>，MCP 写入工具调用将返回 <code>READ_ONLY_MODE</code>，设备不会发生变化。
        </Banner>
      ) : (
        <Banner tone="warning" icon={TerminalWindow}>
          <b>写入工具已启用</b>，Agent 可以向当前设备发送触控、滑动手势和按键指令，所有操作都会进入审计日志。
        </Banner>
      )}

      <section className="content-card">
        <div className="card-heading">
          <div>
            <h3>端点信息</h3>
            <p>每台在线设备拥有独立 MCP 端点；端口变化时配置会随页面自动刷新</p>
          </div>
        </div>
        <div className="field-grid">
          <label className="field">
            <span>设备</span>
            <div className="input-with-action">
              <input value={`${device.model || "设备"}（${deviceId}）`} readOnly aria-label="MCP 设备标识" />
            </div>
          </label>
          <label className="field">
            <span>SSE 端点</span>
            <div className="input-with-action">
              <input value={endpoint} readOnly aria-label="MCP SSE 端点" />
              <CopyButton value={endpoint} label="复制" />
            </div>
          </label>
        </div>
      </section>

      <div className="client-tabs" role="tablist" aria-label="客户端配置">
        {CLIENTS.map((name) => (
          <button key={name} role="tab" aria-selected={client === name} className={client === name ? "active" : ""} onClick={() => setClient(name)}>{name}</button>
        ))}
      </div>
      <section className="content-card code-card">
        <div className="card-heading">
          <div>
            <h3>配置</h3>
            <p>将以下内容添加到 {client} 的 MCP 配置文件</p>
          </div>
          <Button compact icon={TerminalWindow} onClick={() => {
            uiLog(LogTags.mcp, "复制配置", "info", client);
            navigator.clipboard.writeText(snippets[client]).then(() => onToast?.("MCP 配置已复制")).catch(() => onToast?.("复制失败", "danger"));
          }}>复制</Button>
        </div>
        <pre><code>{snippets[client]}</code></pre>
      </section>

      <section className="content-card">
        <div className="card-heading">
          <div>
            <h3>可用工具</h3>
            <p>工具名称、数量与读写分类来自运行时 tools/list，与真实 Core 保持一致</p>
          </div>
          <span className="status-pill neutral">{tools ? `${tools.length} 个` : "…"}</span>
        </div>
        {error ? <Banner tone="danger"><b>工具列表读取失败</b>：{error.message}</Banner> : !tools ? <Spinner label="正在读取工具列表" /> : (
          <div className="tool-list">
            {tools.map((tool, index) => (
              <div className={`tool-item ${expanded === index ? "expanded" : ""}`} key={tool.name}>
                <button aria-expanded={expanded === index} onClick={() => setExpanded(expanded === index ? -1 : index)}>
                  <span className={`tool-kind ${tool.kind}`}>{tool.kind === "write" ? "写入" : "只读"}</span>
                  <code>{tool.name}</code>
                  <span className="tool-desc">{tool.description}</span>
                  {expanded === index ? <CaretDown size={13} /> : <CaretRight size={13} />}
                </button>
                {expanded === index ? (
                  <div className="tool-detail">
                    <span>参数：</span><code>{JSON.stringify(tool.inputSchema)}</code>
                    <span style={{ marginLeft: 10 }}>{tool.kind === "write" && readonly ? "当前被只读模式拦截" : "当前可调用"}</span>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </section>

      <Banner tone="info" style={{ marginTop: 4 }}>
        <b>设备离线时端点保留</b>，重新连接后自动恢复可用；离线调用返回 <code>DEVICE_OFFLINE</code> 而非堆栈。
      </Banner>
    </div>
  );
}
