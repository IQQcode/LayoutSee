import { createHash } from "node:crypto";
import { readdir, readFile, stat } from "node:fs/promises";
import { join, relative } from "node:path";

export async function listFiles(root, suffix = "") {
  const result = [];
  for (const entry of await readdir(root)) {
    const path = join(root, entry);
    if ((await stat(path)).isDirectory()) result.push(...await listFiles(path, suffix));
    else if (!suffix || path.endsWith(suffix)) result.push(path);
  }
  return result.sort();
}

export async function loadSchemas(root) {
  return Promise.all((await listFiles(root, ".json")).map(async (path) => ({
    path,
    relativePath: relative(root, path),
    schema: JSON.parse(await readFile(path, "utf8")),
  })));
}

export async function schemaDigest(root) {
  const hash = createHash("sha256");
  for (const path of await listFiles(root)) {
    hash.update(relative(root, path));
    hash.update(await readFile(path));
  }
  return hash.digest("hex");
}

