import { access, readFile } from "node:fs/promises";

await access(new URL("../src/main.jsx", import.meta.url));
const html = await readFile(new URL("../index.html", import.meta.url), "utf8");
if (!html.includes('lang="zh-CN"') || !html.includes('name="viewport"')) throw new Error("Web 入口缺少语言或视口声明");
console.log("Web 工程静态检查通过");

