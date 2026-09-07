import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import YAML from "yaml";
import { loadSchemas } from "./lib.mjs";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const schemas = await loadSchemas(resolve(packageRoot, "schemas"));
for (const { relativePath, schema } of schemas) {
  if (schema.$schema !== "https://json-schema.org/draft/2020-12/schema") throw new Error(`${relativePath} 未声明 Draft 2020-12`);
  if (!schema.$id || !schema.title) throw new Error(`${relativePath} 缺少 $id 或 title`);
}
const openapi = YAML.parse(await readFile(resolve(packageRoot, "openapi/core-v1.yaml"), "utf8"));
if (openapi.openapi !== "3.1.0") throw new Error("OpenAPI 必须使用 3.1.0");
if (!openapi.paths?.["/api/v1/info"] || !openapi.paths?.["/health/ready"]) throw new Error("OpenAPI 缺少启动握手接口");
console.log(`契约静态检查通过：${schemas.length} 份 schema`);
