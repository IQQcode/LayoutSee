# 此文件由 contracts:generate 自动生成，禁止手改。
# schema sha256: ffa3cb3503da450dccc8889d442b5d03aca26a7e9e696cbb5d94bfe9b976f2d4

from __future__ import annotations

from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict

class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Literal["DEVICE_NOT_FOUND", "DEVICE_DISCONNECTED", "DEVICE_OFFLINE", "DEVICE_UNAUTHORIZED", "ADB_NOT_FOUND", "SNAPSHOT_IN_PROGRESS", "SNAPSHOT_STALE", "REF_NOT_FOUND", "AMBIGUOUS_ELEMENT", "INVALID_XPATH", "READ_ONLY_MODE", "DEVICE_BUSY", "INVALID_ARGUMENT", "MEDIA_UNAVAILABLE", "PLUGIN_INVALID", "PLUGIN_NOT_FOUND", "PLUGIN_INCOMPATIBLE", "PLUGIN_PERMISSION_DENIED", "PLUGIN_RATE_LIMITED", "HOST_CAPABILITY_UNAVAILABLE", "PERMISSION_REQUIRED", "VERSION_INCOMPATIBLE", "CORE_UNAVAILABLE", "OPERATION_TIMEOUT"]
    message: str
    retryable: bool
    details: Optional[dict[str, Any]] = None

CoreInfoEnvelope = Union[dict[str, Any], dict[str, Any]]

class CoreInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    port: int
    pid: int
    nonce: str
    productVersion: Literal["0.1.0"]
    apiVersion: Literal["1.0"]
    snapshotSchemaVersion: Literal["1.0"]

class Device(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deviceId: str
    platform: Literal["android"]
    serial: str
    model: Optional[str] = None
    product: Optional[str] = None
    status: Literal["connected", "unauthorized", "offline", "error"]
    capabilities: list[Literal["screenshot", "layout", "input", "apps", "media-screenshot-fallback"]]
    readonly: bool
    lastSeenAt: Optional[int] = None

class McpToolCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"]
    tools: list[dict[str, Any]]

PluginBridgeMessageMethod = Literal["host.getContext", "snapshot.get", "snapshot.query", "device.info", "device.currentApp", "device.logcat", "device.tap", "device.swipe", "device.inputText", "device.logcatClear", "mcp.callTool", "storage.get", "storage.set", "host.saveFile", "host.copyText", "ui.toast", "ui.confirm"]

class PluginBridgeMessageCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    kind: Literal["call"]
    id: int
    method: PluginBridgeMessageMethod
    params: Optional[dict[str, Any]] = None

class PluginBridgeMessageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    kind: Literal["result"]
    id: int
    data: Any

class PluginBridgeMessageFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    kind: Literal["error"]
    id: int
    error: ApiError

class PluginBridgeMessageEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    v: Literal[1]
    kind: Literal["event"]
    name: Literal["context", "snapshot", "device", "theme", "readonly"]
    payload: dict[str, Any]

PluginBridgeMessage = Union[PluginBridgeMessageCall, PluginBridgeMessageResult, PluginBridgeMessageFailure, PluginBridgeMessageEvent]

PluginCoreContributionExpr = str

class PluginCoreContributionTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    kind: Literal["read", "write"]
    description: str
    inputSchema: dict[str, Any]
    steps: list[PluginCoreContributionStep]

class PluginCoreContributionCallStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call: str
    args: Optional[dict[str, Any]] = None
    alias: Optional[str] = None

class PluginCoreContributionAssertStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    require: PluginCoreContributionExpr
    otherwise: dict[str, Any]

PluginCoreContributionStep = Union[PluginCoreContributionCallStep, PluginCoreContributionAssertStep]

class PluginCoreContributionRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    severity: Literal["error", "warning", "info"]
    when: PluginCoreContributionPredicate
    evidence: str
    suggestion: Optional[str] = None

class PluginCoreContributionPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    all: Optional[list[PluginCoreContributionCondition]] = None
    any: Optional[list[PluginCoreContributionCondition]] = None

class PluginCoreContributionCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    op: Literal["eq", "ne", "lt", "lte", "gt", "gte", "contains", "nonempty", "empty"]
    value: Optional[Any] = None

class PluginCoreContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"]
    tools: Optional[list[PluginCoreContributionTool]] = None
    rules: Optional[list[PluginCoreContributionRule]] = None

class PluginIndexEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    hosts: Optional[list[Literal["app", "web"]]] = None
    devicePlatforms: Optional[list[Literal["android", "ios", "harmony"]]] = None
    runtime: Optional[Literal["iframe", "declarative"]] = None
    origin: Literal["builtin", "local", "registry"]
    overrides: Optional[Literal["builtin"]] = None
    legacy: Optional[bool] = None
    status: Literal["ready", "incompatible", "invalid", "host-mismatch", "device-mismatch"]
    activation: Optional[Literal["onOpen", "onSnapshot", "onCommand"]] = None
    permissions: Optional[list[str]] = None
    grantedPermissions: Optional[list[str]] = None
    contributions: Optional[dict[str, Any]] = None
    error: Optional[ApiError] = None

class PluginIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"]
    directory: str
    builtinDirectory: Optional[str] = None
    generatedAt: int
    cacheHit: bool
    items: list[PluginIndexEntry]

class PluginManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"]
    id: str
    name: str
    version: str
    entry: str
    platforms: list[Literal["android", "ios", "harmony", "macos"]]
    permissions: list[Literal["device.read", "device.write", "snapshot.read", "network.none"]]

PluginManifestPermission = Literal["snapshot.read", "device.read", "device.write", "mcp.call", "storage.local", "host.integration"]

PluginManifestRelativeAsset = str

PluginManifestHtmlEntry = str

class PluginManifestContributions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workbenchTabs: Optional[list[PluginManifestTabContribution]] = None
    workbenchCards: Optional[list[PluginManifestCardContribution]] = None
    commands: Optional[list[PluginManifestCommandContribution]] = None
    mcpTools: Optional[PluginManifestSourceRef] = None
    diagnosticRules: Optional[PluginManifestSourceRef] = None

class PluginManifestSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: PluginManifestRelativeAsset

class PluginManifestTabContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str
    icon: Optional[str] = None
    order: Optional[int] = None
    entry: PluginManifestHtmlEntry

class PluginManifestCardContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    slot: Literal["element.sidebar", "intelligence.bottom", "common.bottom"]
    entry: PluginManifestHtmlEntry
    height: Optional[int] = None

class PluginManifestCommandContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: str

class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["2.0"]
    id: str
    name: str
    description: Optional[str] = None
    version: str
    engines: Optional[dict[str, Any]] = None
    hosts: Optional[list[Literal["app", "web"]]] = None
    devicePlatforms: Optional[list[Literal["android", "ios", "harmony"]]] = None
    activation: Optional[Literal["onOpen", "onSnapshot", "onCommand"]] = None
    runtime: Optional[Literal["iframe", "declarative"]] = None
    permissions: Optional[list[PluginManifestPermission]] = None
    contributions: PluginManifestContributions

class LayoutSnapshotSize(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int
    height: int

class LayoutSnapshotBounds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: float
    top: float
    right: float
    bottom: float

class LayoutSnapshotLayoutNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodeKey: str
    parentKey: Union[str, None]
    depth: int
    childIndex: int
    className: str
    resourceId: Optional[str] = None
    text: Optional[str] = None
    contentDescription: Optional[str] = None
    boundsPx: LayoutSnapshotBounds
    boundsNormalized: LayoutSnapshotBounds
    visible: bool
    enabled: bool
    clickable: bool
    scrollable: bool
    drawingOrder: Optional[int] = None
    raw: dict[str, Any]

class LayoutSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    snapshotId: str
    deviceId: str
    createdAt: int
    foreground: dict[str, Any]
    windowSizePx: LayoutSnapshotSize
    density: Optional[float] = None
    hierarchyAccuracy: Literal["exact", "best_effort", "limited"]
    synchronization: Literal["exact", "best_effort", "context_changed"]
    screenshot: Union[None, dict[str, Any]]
    roots: list[str]
    nodes: list[LayoutSnapshotLayoutNode]
    warnings: list[str]

class FakeCoreScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"]
    boot: dict[str, Any]
    devices: list[Device]
    responses: dict[str, Any]
    media: dict[str, Any]
    mcp: dict[str, Any]
    faults: list[str]
    staticAssets: dict[str, Any]

class MediaControlMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal["1.0"]
    type: Literal["hello", "ready", "state", "heartbeat", "error"]
    deviceId: str
    timestamp: int
    payload: Optional[dict[str, Any]] = None
