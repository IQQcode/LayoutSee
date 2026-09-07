import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import YAML from "yaml";
import { listFiles, loadSchemas } from "../scripts/lib.mjs";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const schemaRoot = resolve(packageRoot, "schemas");
const schemas = await loadSchemas(schemaRoot);
const ajv = new Ajv2020({ allErrors: true, strict: true });
for (const { schema } of schemas) ajv.addSchema(schema);

test("全部有效夹具通过对应 schema", async () => {
  for (const path of await listFiles(resolve(packageRoot, "fixtures/valid"), ".json")) {
    const fixture = JSON.parse(await readFile(path, "utf8"));
    const schema = schemas.find((item) => item.relativePath === fixture.$schemaRef)?.schema;
    assert.ok(schema, `找不到 schema：${fixture.$schemaRef}`);
    assert.equal(ajv.validate(schema.$id, fixture.value), true, `${path}: ${ajv.errorsText()}`);
  }
});

test("全部无效夹具被拒绝且声明稳定错误码", async () => {
  for (const path of await listFiles(resolve(packageRoot, "fixtures/invalid"), ".json")) {
    const fixture = JSON.parse(await readFile(path, "utf8"));
    const schema = schemas.find((item) => item.relativePath === fixture.$schemaRef)?.schema;
    assert.ok(schema, `找不到 schema：${fixture.$schemaRef}`);
    assert.equal(ajv.validate(schema.$id, fixture.value), false, `${path} 应被拒绝`);
    assert.match(fixture.$expectedError, /^[A-Z][A-Z0-9_]+$/);
  }
});

test("随包内置插件的清单与声明式工具符合契约", async () => {
  const builtinRoot = resolve(packageRoot, "../plugins");
  const manifestSchema = schemas.find((item) => item.relativePath === "plugin/manifest.json").schema;
  const contributionSchema = schemas.find((item) => item.relativePath === "plugin/core-contribution.json").schema;
  const manifests = await listFiles(builtinRoot, ".json");
  assert.ok(manifests.some((path) => path.endsWith("manifest.json")), "内置插件目录里至少要有一个 manifest.json");
  for (const path of manifests) {
    const value = JSON.parse(await readFile(path, "utf8"));
    const schema = path.endsWith("manifest.json") ? manifestSchema : contributionSchema;
    assert.equal(ajv.validate(schema.$id, value), true, `${path}: ${ajv.errorsText()}`);
  }
});

test("OpenAPI 握手接口只绑定 loopback 示例", async () => {
  const api = YAML.parse(await readFile(resolve(packageRoot, "openapi/core-v1.yaml"), "utf8"));
  assert.equal(api.openapi, "3.1.0");
  assert.match(api.servers[0].url, /^http:\/\/127\.0\.0\.1:/);
  assert.ok(api.paths["/api/v1/info"].get);
  assert.ok(api.paths["/health/ready"].get);
  for (const path of [
    "/api/v1/devices",
    "/api/v1/devices/{deviceId}/screenshot",
    "/api/v1/devices/{deviceId}/snapshots",
    "/api/v1/snapshots/{snapshotId}/summary",
    "/api/v1/snapshots/{snapshotId}/diagnostics",
    "/api/v1/settings",
    "/api/v1/plugins",
    "/api/v1/plugins/index",
    "/api/v1/plugins/{pluginId}/permissions",
    "/plugin-assets/{pluginId}/{assetPath}",
    "/api/v1/mcp/tools",
    "/mcp/{deviceId}/tools/call",
  ]) assert.ok(api.paths[path], `OpenAPI 缺少 ${path}`);
});

test("插件清单锁定激活时机与能力白名单", async () => {
  const manifest = schemas.find((item) => item.relativePath === "plugin/manifest.json").schema;
  assert.deepEqual(manifest.properties.activation.enum, ["onOpen", "onSnapshot", "onCommand"]);
  assert.deepEqual(manifest.properties.hosts.items.enum, ["app", "web"]);
  assert.deepEqual(manifest.properties.devicePlatforms.items.enum, ["android", "ios", "harmony"]);
  assert.ok(!("platforms" in manifest.properties), "platforms 已拆成 hosts + devicePlatforms");
  const bridge = schemas.find((item) => item.relativePath === "plugin/bridge.json").schema;
  const methods = bridge.$defs.Method.enum;
  assert.ok(methods.includes("device.tap") && methods.includes("snapshot.get"));
  for (const forbidden of ["shell.exec", "host.fetch", "device.shell"]) {
    assert.ok(!methods.includes(forbidden), `桥不得暴露 ${forbidden}`);
  }
});

test("兼容矩阵精确接受 0.1.0 契约组合", async () => {
  const matrix = JSON.parse(await readFile(resolve(packageRoot, "compatibility/versions.json"), "utf8"));
  assert.equal(matrix.productVersion, "0.1.0");
  assert.deepEqual(matrix.accepted, [{ apiVersion: "1.0", snapshotSchemaVersion: "1.0" }]);
});

test("MCP V0.1 工具目录固定为 12 项", async () => {
  const fixture = JSON.parse(await readFile(resolve(packageRoot, "fixtures/valid/mcp-tool-catalog.json"), "utf8"));
  assert.equal(fixture.value.tools.length, 12);
  assert.equal(new Set(fixture.value.tools.map((tool) => tool.name)).size, 12);
  assert.deepEqual(fixture.value.tools.map((tool) => tool.name), [
    "get_window_size", "get_device_info", "screenshot", "dump_xml",
    "find_elements_by_xpath", "tap", "swipe", "input_text", "press_key",
    "get_layout_summary", "diagnose_layout", "find_element",
  ]);
});
