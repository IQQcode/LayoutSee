import { mkdir, rm, writeFile } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { loadSchemas, schemaDigest } from "./lib.mjs";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const schemaRoot = resolve(packageRoot, "schemas");
const outputFlag = process.argv.indexOf("--output");
const outputRoot = outputFlag >= 0 ? resolve(process.argv[outputFlag + 1]) : resolve(packageRoot, "generated");
const coreGeneratedPath = resolve(packageRoot, "../core/src/layoutsee_core/generated_contracts.py");
const schemas = await loadSchemas(schemaRoot);
const digest = await schemaDigest(schemaRoot);
const titleByFile = new Map(schemas.map(({ path, schema }) => [basename(path), schema.title]));

function refName(ref, ownerTitle) {
  if (ref.startsWith("#/$defs/")) return `${ownerTitle}${ref.split("/").at(-1)}`;
  return titleByFile.get(basename(ref)) ?? "unknown";
}

function tsType(node, ownerTitle) {
  if (!node) return "unknown";
  if (node.$ref) return refName(node.$ref, ownerTitle);
  if (node.const !== undefined) return JSON.stringify(node.const);
  if (node.enum) return node.enum.map((value) => JSON.stringify(value)).join(" | ");
  if (node.oneOf) return node.oneOf.map((item) => tsType(item, ownerTitle)).join(" | ");
  if (Array.isArray(node.type)) return node.type.map((item) => tsType({ ...node, type: item }, ownerTitle)).join(" | ");
  if (node.type === "string") return "string";
  if (node.type === "integer" || node.type === "number") return "number";
  if (node.type === "boolean") return "boolean";
  if (node.type === "null") return "null";
  if (node.type === "array") return `Array<${tsType(node.items, ownerTitle)}>`;
  if (node.type === "object") {
    const entries = Object.entries(node.properties ?? {});
    if (!entries.length) return node.additionalProperties ? "Record<string, unknown>" : "Record<string, never>";
    const required = new Set(node.required ?? []);
    return `{ ${entries.map(([key, value]) => `${JSON.stringify(key)}${required.has(key) ? "" : "?"}: ${tsType(value, ownerTitle)}`).join("; ")} }`;
  }
  return "unknown";
}

function pyType(node, ownerTitle) {
  if (!node) return "Any";
  if (node.$ref) return refName(node.$ref, ownerTitle);
  if (node.const !== undefined) return `Literal[${JSON.stringify(node.const)}]`;
  if (node.enum) return `Literal[${node.enum.map((value) => JSON.stringify(value)).join(", ")}]`;
  if (node.oneOf) return `Union[${node.oneOf.map((item) => pyType(item, ownerTitle)).join(", ")}]`;
  if (Array.isArray(node.type)) return `Union[${node.type.map((item) => pyType({ ...node, type: item }, ownerTitle)).join(", ")}]`;
  if (node.type === "string") return "str";
  if (node.type === "integer") return "int";
  if (node.type === "number") return "float";
  if (node.type === "boolean") return "bool";
  if (node.type === "null") return "None";
  if (node.type === "array") return `list[${pyType(node.items, ownerTitle)}]`;
  if (node.type === "object") return "dict[str, Any]";
  return "Any";
}

function tsDeclaration(title, node, ownerTitle = title) {
  if (node.type === "object" && !node.oneOf) {
    const required = new Set(node.required ?? []);
    const lines = Object.entries(node.properties ?? {}).map(([key, value]) => `  ${JSON.stringify(key)}${required.has(key) ? "" : "?"}: ${tsType(value, ownerTitle)};`);
    return `export interface ${title} {\n${lines.join("\n")}\n}`;
  }
  return `export type ${title} = ${tsType(node, ownerTitle)};`;
}

function pyDeclaration(title, node, ownerTitle = title) {
  if (node.type !== "object" || node.oneOf) return `${title} = ${pyType(node, ownerTitle)}`;
  const required = new Set(node.required ?? []);
  const fields = Object.entries(node.properties ?? {}).map(([key, value]) => {
    const type = pyType(value, ownerTitle);
    return `    ${key}: ${required.has(key) ? type : `Optional[${type}] = None`}`;
  });
  return `class ${title}(BaseModel):\n    model_config = ConfigDict(extra="forbid")\n${fields.length ? fields.join("\n") : "    pass"}`;
}

const tsParts = [];
const pyParts = [];
for (const { schema } of schemas) {
  if (!schema.title) continue;
  for (const [name, definition] of Object.entries(schema.$defs ?? {})) {
    tsParts.push(tsDeclaration(`${schema.title}${name}`, definition, schema.title));
    pyParts.push(pyDeclaration(`${schema.title}${name}`, definition, schema.title));
  }
  tsParts.push(tsDeclaration(schema.title, schema));
  pyParts.push(pyDeclaration(schema.title, schema));
}

const tsHeader = `// 此文件由 contracts:generate 自动生成，禁止手改。\n// schema sha256: ${digest}\n\n`;
const pyHeader = `# 此文件由 contracts:generate 自动生成，禁止手改。\n# schema sha256: ${digest}\n\nfrom __future__ import annotations\n\nfrom typing import Any, Literal, Optional, Union\nfrom pydantic import BaseModel, ConfigDict\n\n`;
const client = `\n\nexport async function getCoreInfo(origin = window.location.origin): Promise<CoreInfoEnvelope> {\n  const response = await fetch(new URL("/api/v1/info", origin), { headers: { Accept: "application/json" } });\n  return response.json() as Promise<CoreInfoEnvelope>;\n}\n`;

await rm(outputRoot, { recursive: true, force: true });
await mkdir(resolve(outputRoot, "typescript"), { recursive: true });
await mkdir(resolve(outputRoot, "python/layoutsee_contracts"), { recursive: true });
const tsOutput = `${tsHeader}${tsParts.join("\n\n")}${client}`;
const pyOutput = `${pyHeader}${pyParts.join("\n\n")}\n`;
await writeFile(resolve(outputRoot, "typescript/index.ts"), tsOutput);
await writeFile(resolve(outputRoot, "python/layoutsee_contracts/models.py"), pyOutput);
await writeFile(resolve(outputRoot, "python/layoutsee_contracts/__init__.py"), "from .models import *  # noqa: F401,F403\n");
if (outputFlag < 0) {
  await mkdir(dirname(coreGeneratedPath), { recursive: true });
  await writeFile(coreGeneratedPath, pyOutput);
}
console.log(`已生成 ${schemas.length} 份契约模型，摘要 ${digest.slice(0, 12)}`);
