# 插件接口契约草案（W1 的输入）

本文件是可直接落进 `repos/contracts/` 的草案，评审通过后按 [doc.md](./doc.md) 的 W1 执行。生成物由 `npm run contracts:generate` 产出，禁止手改。

> **落地状态（2026-08-31）**：W1 已执行完毕，实际落地版本以 `repos/contracts/schemas/plugin/*` 为准。落地时相对本草案有三处修正：
> 1. 新增 `schemas/plugin/manifest-v1.json`（title `PluginManifestV1`），承载 v1 清单的兼容读取契约，`platforms` 枚举含存量里出现过的 `macos`；
> 2. 声明式步骤字段避开 Python 保留字：`with` → `args`、`as` → `alias`、`assert` → `require`、`else` → `otherwise`；比较运算符改用 `lt/lte/gt/gte`。否则 `generated_contracts.py` 无法编译；
> 3. `$defs` 中 `Step` 的 union 别名必须排在 `CallStep`/`AssertStep` **之后**，因为生成器按键序输出、union 别名是运行时求值。


## 1. `schemas/plugin/manifest.json`（替换现有 1.0）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://layoutsee.local/schemas/plugin/manifest.json",
  "title": "PluginManifest",
  "type": "object",
  "additionalProperties": false,
  "required": ["schemaVersion", "id", "name", "version", "contributions"],
  "properties": {
    "schemaVersion": { "const": "2.0" },
    "id": { "type": "string", "pattern": "^[a-z0-9]+(?:[.-][a-z0-9]+)*$", "maxLength": 64 },
    "name": { "type": "string", "minLength": 1, "maxLength": 80 },
    "description": { "type": "string", "maxLength": 200 },
    "version": { "type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$" },
    "engines": {
      "type": "object",
      "additionalProperties": false,
      "required": ["layoutsee"],
      "properties": { "layoutsee": { "type": "string", "maxLength": 40 } }
    },
    "hosts": {
      "type": "array", "minItems": 1, "uniqueItems": true,
      "items": { "enum": ["app", "web"] },
      "default": ["app", "web"]
    },
    "devicePlatforms": {
      "type": "array", "minItems": 1, "uniqueItems": true,
      "items": { "enum": ["android", "ios", "harmony"] }
    },
    "activation": { "enum": ["onOpen", "onSnapshot", "onCommand"], "default": "onOpen" },
    "runtime": { "enum": ["iframe", "declarative"], "default": "iframe" },
    "permissions": {
      "type": "array", "uniqueItems": true,
      "items": { "$ref": "#/$defs/Permission" }
    },
    "contributions": { "$ref": "#/$defs/Contributions" }
  },
  "$defs": {
    "Permission": {
      "enum": ["snapshot.read", "device.read", "device.write", "mcp.call", "storage.local", "host.integration"]
    },
    "RelativeAsset": { "type": "string", "pattern": "^(?!/)(?!.*\\.\\.)[A-Za-z0-9._/-]+$", "maxLength": 200 },
    "HtmlEntry": { "type": "string", "pattern": "^(?!/)(?!.*\\.\\.)[A-Za-z0-9._/-]+\\.html$", "maxLength": 200 },
    "Contributions": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "workbenchTabs": { "type": "array", "maxItems": 4, "items": { "$ref": "#/$defs/TabContribution" } },
        "workbenchCards": { "type": "array", "maxItems": 4, "items": { "$ref": "#/$defs/CardContribution" } },
        "commands": { "type": "array", "maxItems": 20, "items": { "$ref": "#/$defs/CommandContribution" } },
        "mcpTools": { "$ref": "#/$defs/SourceRef" },
        "diagnosticRules": { "$ref": "#/$defs/SourceRef" }
      }
    },
    "SourceRef": {
      "type": "object", "additionalProperties": false, "required": ["source"],
      "properties": { "source": { "$ref": "#/$defs/RelativeAsset" } }
    },
    "TabContribution": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "title", "entry"],
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z0-9-]{1,32}$" },
        "title": { "type": "string", "minLength": 1, "maxLength": 12 },
        "icon": { "type": "string", "maxLength": 40 },
        "order": { "type": "integer", "minimum": 100, "maximum": 999, "default": 500 },
        "entry": { "$ref": "#/$defs/HtmlEntry" }
      }
    },
    "CardContribution": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "slot", "entry"],
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z0-9-]{1,32}$" },
        "slot": { "enum": ["element.sidebar", "intelligence.bottom", "common.bottom"] },
        "entry": { "$ref": "#/$defs/HtmlEntry" },
        "height": { "type": "integer", "minimum": 80, "maximum": 480 }
      }
    },
    "CommandContribution": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "title"],
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z0-9.-]{1,48}$" },
        "title": { "type": "string", "minLength": 1, "maxLength": 24 }
      }
    }
  }
}
```

## 2. `schemas/plugin/index.json`（新增）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://layoutsee.local/schemas/plugin/index.json",
  "title": "PluginIndex",
  "type": "object",
  "additionalProperties": false,
  "required": ["schemaVersion", "directory", "generatedAt", "cacheHit", "items"],
  "properties": {
    "schemaVersion": { "const": "1.0" },
    "directory": { "type": "string" },
    "builtinDirectory": { "type": "string" },
    "generatedAt": { "type": "integer", "minimum": 0 },
    "cacheHit": { "type": "boolean" },
    "items": { "type": "array", "items": { "$ref": "#/$defs/Entry" } }
  },
  "$defs": {
    "Entry": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "status", "origin"],
      "properties": {
        "id": { "type": "string" },
        "name": { "type": "string" },
        "version": { "type": "string" },
        "origin": { "enum": ["builtin", "local", "registry"] },
        "overrides": { "enum": ["builtin"] },
        "legacy": { "type": "boolean" },
        "status": { "enum": ["ready", "incompatible", "invalid", "host-mismatch", "device-mismatch"] },
        "activation": { "enum": ["onOpen", "onSnapshot", "onCommand"] },
        "permissions": { "type": "array", "items": { "type": "string" } },
        "grantedPermissions": { "type": "array", "items": { "type": "string" } },
        "contributions": { "type": "object", "additionalProperties": true },
        "error": { "$ref": "https://layoutsee.local/schemas/common/error.json" }
      }
    }
  }
}
```

## 3. `schemas/plugin/bridge.json`（新增）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://layoutsee.local/schemas/plugin/bridge.json",
  "title": "PluginBridgeMessage",
  "oneOf": [
    { "$ref": "#/$defs/Call" },
    { "$ref": "#/$defs/Result" },
    { "$ref": "#/$defs/Failure" },
    { "$ref": "#/$defs/Event" }
  ],
  "$defs": {
    "Method": {
      "enum": ["host.getContext", "snapshot.get", "snapshot.query", "device.info", "device.currentApp",
               "device.tap", "device.swipe", "device.inputText", "mcp.callTool",
               "storage.get", "storage.set", "host.saveFile", "host.copyText", "ui.toast", "ui.confirm"]
    },
    "Call": {
      "type": "object", "additionalProperties": false, "required": ["v", "kind", "id", "method"],
      "properties": {
        "v": { "const": 1 }, "kind": { "const": "call" },
        "id": { "type": "integer", "minimum": 1 },
        "method": { "$ref": "#/$defs/Method" },
        "params": { "type": "object", "additionalProperties": true }
      }
    },
    "Result": {
      "type": "object", "additionalProperties": false, "required": ["v", "kind", "id", "data"],
      "properties": { "v": { "const": 1 }, "kind": { "const": "result" }, "id": { "type": "integer" }, "data": {} }
    },
    "Failure": {
      "type": "object", "additionalProperties": false, "required": ["v", "kind", "id", "error"],
      "properties": { "v": { "const": 1 }, "kind": { "const": "error" }, "id": { "type": "integer" },
                      "error": { "$ref": "https://layoutsee.local/schemas/common/error.json" } }
    },
    "Event": {
      "type": "object", "additionalProperties": false, "required": ["v", "kind", "name", "payload"],
      "properties": { "v": { "const": 1 }, "kind": { "const": "event" },
                      "name": { "enum": ["context", "snapshot", "device", "theme", "readonly"] },
                      "payload": { "type": "object", "additionalProperties": true } }
    }
  }
}
```

## 4. `schemas/plugin/core-contribution.json`（新增，声明式工具与规则）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://layoutsee.local/schemas/plugin/core-contribution.json",
  "title": "PluginCoreContribution",
  "type": "object",
  "additionalProperties": false,
  "required": ["schemaVersion"],
  "properties": {
    "schemaVersion": { "const": "1.0" },
    "tools": { "type": "array", "maxItems": 10, "items": { "$ref": "#/$defs/Tool" } },
    "rules": { "type": "array", "maxItems": 10, "items": { "$ref": "#/$defs/Rule" } }
  },
  "$defs": {
    "Expr": { "type": "string", "pattern": "^\\$\\.[A-Za-z0-9_.]+$", "maxLength": 80 },
    "Tool": {
      "type": "object", "additionalProperties": false,
      "required": ["name", "kind", "description", "inputSchema", "steps"],
      "properties": {
        "name": { "type": "string", "pattern": "^[a-z][a-z0-9_]{2,40}$" },
        "kind": { "enum": ["read", "write"] },
        "description": { "type": "string", "minLength": 4, "maxLength": 200 },
        "inputSchema": { "type": "object", "additionalProperties": true },
        "steps": { "type": "array", "minItems": 1, "maxItems": 6, "items": { "$ref": "#/$defs/Step" } }
      }
    },
    "CallStep": {
      "type": "object", "additionalProperties": false, "required": ["call"],
      "properties": {
        "call": { "type": "string", "maxLength": 40 },
        "args": { "type": "object", "additionalProperties": true },
        "alias": { "type": "string", "pattern": "^[a-z][a-z0-9_]{0,20}$" }
      }
    },
    "AssertStep": {
      "type": "object", "additionalProperties": false, "required": ["require", "otherwise"],
      "properties": {
        "require": { "$ref": "#/$defs/Expr" },
        "otherwise": {
          "type": "object", "additionalProperties": false, "required": ["code", "message"],
          "properties": { "code": { "type": "string", "pattern": "^[A-Z][A-Z0-9_]+$" }, "message": { "type": "string", "maxLength": 200 } }
        }
      }
    },
    "Step": {
      "oneOf": [{ "$ref": "#/$defs/CallStep" }, { "$ref": "#/$defs/AssertStep" }]
    },
    "Rule": {
      "type": "object", "additionalProperties": false,
      "required": ["type", "severity", "when", "evidence"],
      "properties": {
        "type": { "type": "string", "pattern": "^[a-z][a-z0-9_]{2,40}$" },
        "severity": { "enum": ["error", "warning", "info"] },
        "when": { "$ref": "#/$defs/Predicate" },
        "evidence": { "type": "string", "minLength": 4, "maxLength": 200 },
        "suggestion": { "type": "string", "maxLength": 200 }
      }
    },
    "Predicate": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "all": { "type": "array", "maxItems": 6, "items": { "$ref": "#/$defs/Condition" } },
        "any": { "type": "array", "maxItems": 6, "items": { "$ref": "#/$defs/Condition" } }
      }
    },
    "Condition": {
      "type": "object", "additionalProperties": false, "required": ["field", "op"],
      "properties": {
        "field": { "type": "string", "maxLength": 60 },
        "op": { "enum": ["eq", "ne", "lt", "lte", "gt", "gte", "contains", "nonempty", "empty"] },
        "value": {}
      }
    }
  }
}
```

`steps[].call` 的取值域在实现里限定为 `ToolRegistry` 中已注册的内置工具名，插件不能调用其他插件贡献的工具（避免链式依赖与循环）。

## 5. `schemas/common/error.json` 枚举增量

在现有 `code` 枚举后追加，`errors.py` 的 `STATUS_BY_CODE` 同步补齐：

```text
PLUGIN_NOT_FOUND            → 404
PLUGIN_INCOMPATIBLE         → 426
PLUGIN_PERMISSION_DENIED    → 403
PLUGIN_RATE_LIMITED         → 429
HOST_CAPABILITY_UNAVAILABLE → 501
```

`PLUGIN_INVALID`（422）与 `PERMISSION_REQUIRED`（403）已存在，路径逃逸继续复用 `PERMISSION_REQUIRED` 以兼容 `fixtures/invalid/plugin-path-escape.json`。

## 6. `openapi/core-v1.yaml` 增量

```yaml
  /api/v1/plugins/index:
    get:
      operationId: getPluginIndex
      parameters:
        - name: refresh
          in: query
          required: false
          schema: { type: boolean, default: false }
      responses:
        "200": { $ref: "#/components/responses/JsonEnvelope" }
  /api/v1/plugins/{pluginId}/permissions:
    put:
      operationId: updatePluginPermissions
      parameters:
        - name: pluginId
          in: path
          required: true
          schema: { type: string }
      responses:
        "200": { $ref: "#/components/responses/JsonEnvelope" }
        "403": { $ref: "#/components/responses/JsonEnvelope" }
  /plugin-assets/{pluginId}/{assetPath}:
    get:
      operationId: getPluginAsset
      parameters:
        - name: pluginId
          in: path
          required: true
          schema: { type: string }
        - name: assetPath
          in: path
          required: true
          schema: { type: string }
      responses:
        "200": { description: 插件静态资源，独立严格 CSP }
        "403": { $ref: "#/components/responses/JsonEnvelope" }
        "404": { $ref: "#/components/responses/JsonEnvelope" }
```

保留 `/api/v1/plugins`（旧列表）一个版本周期，响应体保持现状，内部改为由索引派生，`PluginsTab` 迁到 `/index` 后再删。

## 7. fixtures 清单

| 文件 | 用途 |
| --- | --- |
| `valid/plugin-manifest.json` | 更新为 v2 完整样例（含 tabs + cards + mcpTools + rules） |
| `valid/plugin-manifest-legacy.json` | v1 清单，走 `plugin/manifest-v1.json`，断言存量 `platforms` 可含 `macos` |
| `valid/plugin-index.json` | 索引响应样例，含 builtin/local 覆盖与一条 invalid |
| `valid/plugin-bridge-call.json` | 桥调用样例（`device.tap`） |
| `valid/plugin-core-contribution.json` | 声明式 composite 工具 + 一条诊断规则 |
| `invalid/plugin-path-escape.json` | v2 结构，`entry: "../outside.html"` → `PERMISSION_REQUIRED` |
| `invalid/plugin-activation-startup.json` | `activation: "onStartup"` → schema 拒绝，锁死"启动即激活" |
| `invalid/plugin-bridge-unknown-method.json` | 桥调用未知 method（`shell.exec`）→ schema 拒绝 |



