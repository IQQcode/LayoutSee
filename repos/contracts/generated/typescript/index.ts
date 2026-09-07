// 此文件由 contracts:generate 自动生成，禁止手改。
// schema sha256: ffa3cb3503da450dccc8889d442b5d03aca26a7e9e696cbb5d94bfe9b976f2d4

export interface ApiError {
  "code": "DEVICE_NOT_FOUND" | "DEVICE_DISCONNECTED" | "DEVICE_OFFLINE" | "DEVICE_UNAUTHORIZED" | "ADB_NOT_FOUND" | "SNAPSHOT_IN_PROGRESS" | "SNAPSHOT_STALE" | "REF_NOT_FOUND" | "AMBIGUOUS_ELEMENT" | "INVALID_XPATH" | "READ_ONLY_MODE" | "DEVICE_BUSY" | "INVALID_ARGUMENT" | "MEDIA_UNAVAILABLE" | "PLUGIN_INVALID" | "PLUGIN_NOT_FOUND" | "PLUGIN_INCOMPATIBLE" | "PLUGIN_PERMISSION_DENIED" | "PLUGIN_RATE_LIMITED" | "HOST_CAPABILITY_UNAVAILABLE" | "PERMISSION_REQUIRED" | "VERSION_INCOMPATIBLE" | "CORE_UNAVAILABLE" | "OPERATION_TIMEOUT";
  "message": string;
  "retryable": boolean;
  "details"?: Record<string, unknown>;
}

export type CoreInfoEnvelope = { "ok": true; "data": CoreInfo; "requestId": string } | { "ok": false; "error": ApiError; "requestId": string };

export interface CoreInfo {
  "port": number;
  "pid": number;
  "nonce": string;
  "productVersion": "0.1.0";
  "apiVersion": "1.0";
  "snapshotSchemaVersion": "1.0";
}

export interface Device {
  "deviceId": string;
  "platform": "android";
  "serial": string;
  "model"?: string;
  "product"?: string;
  "status": "connected" | "unauthorized" | "offline" | "error";
  "capabilities": Array<"screenshot" | "layout" | "input" | "apps" | "media-screenshot-fallback">;
  "readonly": boolean;
  "lastSeenAt"?: number;
}

export interface McpToolCatalog {
  "schemaVersion": "1.0";
  "tools": Array<{ "name": string; "kind": "read" | "write"; "description": string; "inputSchema": Record<string, unknown> }>;
}

export type PluginBridgeMessageMethod = "host.getContext" | "snapshot.get" | "snapshot.query" | "device.info" | "device.currentApp" | "device.logcat" | "device.tap" | "device.swipe" | "device.inputText" | "device.logcatClear" | "mcp.callTool" | "storage.get" | "storage.set" | "host.saveFile" | "host.copyText" | "ui.toast" | "ui.confirm";

export interface PluginBridgeMessageCall {
  "v": 1;
  "kind": "call";
  "id": number;
  "method": PluginBridgeMessageMethod;
  "params"?: Record<string, unknown>;
}

export interface PluginBridgeMessageResult {
  "v": 1;
  "kind": "result";
  "id": number;
  "data": unknown;
}

export interface PluginBridgeMessageFailure {
  "v": 1;
  "kind": "error";
  "id": number;
  "error": ApiError;
}

export interface PluginBridgeMessageEvent {
  "v": 1;
  "kind": "event";
  "name": "context" | "snapshot" | "device" | "theme" | "readonly";
  "payload": Record<string, unknown>;
}

export type PluginBridgeMessage = PluginBridgeMessageCall | PluginBridgeMessageResult | PluginBridgeMessageFailure | PluginBridgeMessageEvent;

export type PluginCoreContributionExpr = string;

export interface PluginCoreContributionTool {
  "name": string;
  "kind": "read" | "write";
  "description": string;
  "inputSchema": Record<string, unknown>;
  "steps": Array<PluginCoreContributionStep>;
}

export interface PluginCoreContributionCallStep {
  "call": string;
  "args"?: Record<string, unknown>;
  "alias"?: string;
}

export interface PluginCoreContributionAssertStep {
  "require": PluginCoreContributionExpr;
  "otherwise": { "code": string; "message": string };
}

export type PluginCoreContributionStep = PluginCoreContributionCallStep | PluginCoreContributionAssertStep;

export interface PluginCoreContributionRule {
  "type": string;
  "severity": "error" | "warning" | "info";
  "when": PluginCoreContributionPredicate;
  "evidence": string;
  "suggestion"?: string;
}

export interface PluginCoreContributionPredicate {
  "all"?: Array<PluginCoreContributionCondition>;
  "any"?: Array<PluginCoreContributionCondition>;
}

export interface PluginCoreContributionCondition {
  "field": string;
  "op": "eq" | "ne" | "lt" | "lte" | "gt" | "gte" | "contains" | "nonempty" | "empty";
  "value"?: unknown;
}

export interface PluginCoreContribution {
  "schemaVersion": "1.0";
  "tools"?: Array<PluginCoreContributionTool>;
  "rules"?: Array<PluginCoreContributionRule>;
}

export interface PluginIndexEntry {
  "id": string;
  "name"?: string;
  "version"?: string;
  "description"?: string;
  "hosts"?: Array<"app" | "web">;
  "devicePlatforms"?: Array<"android" | "ios" | "harmony">;
  "runtime"?: "iframe" | "declarative";
  "origin": "builtin" | "local" | "registry";
  "overrides"?: "builtin";
  "legacy"?: boolean;
  "status": "ready" | "incompatible" | "invalid" | "host-mismatch" | "device-mismatch";
  "activation"?: "onOpen" | "onSnapshot" | "onCommand";
  "permissions"?: Array<string>;
  "grantedPermissions"?: Array<string>;
  "contributions"?: Record<string, unknown>;
  "error"?: ApiError;
}

export interface PluginIndex {
  "schemaVersion": "1.0";
  "directory": string;
  "builtinDirectory"?: string;
  "generatedAt": number;
  "cacheHit": boolean;
  "items": Array<PluginIndexEntry>;
}

export interface PluginManifestV1 {
  "schemaVersion": "1.0";
  "id": string;
  "name": string;
  "version": string;
  "entry": string;
  "platforms": Array<"android" | "ios" | "harmony" | "macos">;
  "permissions": Array<"device.read" | "device.write" | "snapshot.read" | "network.none">;
}

export type PluginManifestPermission = "snapshot.read" | "device.read" | "device.write" | "mcp.call" | "storage.local" | "host.integration";

export type PluginManifestRelativeAsset = string;

export type PluginManifestHtmlEntry = string;

export interface PluginManifestContributions {
  "workbenchTabs"?: Array<PluginManifestTabContribution>;
  "workbenchCards"?: Array<PluginManifestCardContribution>;
  "commands"?: Array<PluginManifestCommandContribution>;
  "mcpTools"?: PluginManifestSourceRef;
  "diagnosticRules"?: PluginManifestSourceRef;
}

export interface PluginManifestSourceRef {
  "source": PluginManifestRelativeAsset;
}

export interface PluginManifestTabContribution {
  "id": string;
  "title": string;
  "icon"?: string;
  "order"?: number;
  "entry": PluginManifestHtmlEntry;
}

export interface PluginManifestCardContribution {
  "id": string;
  "slot": "element.sidebar" | "intelligence.bottom" | "common.bottom";
  "entry": PluginManifestHtmlEntry;
  "height"?: number;
}

export interface PluginManifestCommandContribution {
  "id": string;
  "title": string;
}

export interface PluginManifest {
  "schemaVersion": "2.0";
  "id": string;
  "name": string;
  "description"?: string;
  "version": string;
  "engines"?: { "layoutsee": string };
  "hosts"?: Array<"app" | "web">;
  "devicePlatforms"?: Array<"android" | "ios" | "harmony">;
  "activation"?: "onOpen" | "onSnapshot" | "onCommand";
  "runtime"?: "iframe" | "declarative";
  "permissions"?: Array<PluginManifestPermission>;
  "contributions": PluginManifestContributions;
}

export interface LayoutSnapshotSize {
  "width": number;
  "height": number;
}

export interface LayoutSnapshotBounds {
  "left": number;
  "top": number;
  "right": number;
  "bottom": number;
}

export interface LayoutSnapshotLayoutNode {
  "nodeKey": string;
  "parentKey": string | null;
  "depth": number;
  "childIndex": number;
  "className": string;
  "resourceId"?: string;
  "text"?: string;
  "contentDescription"?: string;
  "boundsPx": LayoutSnapshotBounds;
  "boundsNormalized": LayoutSnapshotBounds;
  "visible": boolean;
  "enabled": boolean;
  "clickable": boolean;
  "scrollable": boolean;
  "drawingOrder"?: number;
  "raw": Record<string, unknown>;
}

export interface LayoutSnapshot {
  "snapshotId": string;
  "deviceId": string;
  "createdAt": number;
  "foreground": { "packageName": string; "activity"?: string };
  "windowSizePx": LayoutSnapshotSize;
  "density"?: number;
  "hierarchyAccuracy": "exact" | "best_effort" | "limited";
  "synchronization": "exact" | "best_effort" | "context_changed";
  "screenshot": null | { "width": number; "height": number; "contentUrl": string };
  "roots": Array<string>;
  "nodes": Array<LayoutSnapshotLayoutNode>;
  "warnings": Array<string>;
}

export interface FakeCoreScenario {
  "schemaVersion": "1.0";
  "boot": { "readyDelayMs": number; "nonceMode": "echo" | "mismatch" };
  "devices": Array<Device>;
  "responses": Record<string, unknown>;
  "media": { "mode": "frames" | "screenshot" | "unavailable"; "disconnectAfter": number | null };
  "mcp": { "tools": "v0.1" };
  "faults": Array<string>;
  "staticAssets": { "source": "web-dist" | "builtin" };
}

export interface MediaControlMessage {
  "schemaVersion": "1.0";
  "type": "hello" | "ready" | "state" | "heartbeat" | "error";
  "deviceId": string;
  "timestamp": number;
  "payload"?: Record<string, unknown>;
}

export async function getCoreInfo(origin = window.location.origin): Promise<CoreInfoEnvelope> {
  const response = await fetch(new URL("/api/v1/info", origin), { headers: { Accept: "application/json" } });
  return response.json() as Promise<CoreInfoEnvelope>;
}
