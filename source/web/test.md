# web 测试

```bash
npm --workspace @layoutsee/web run lint    # 入口、语言、视口等快速检查
npm --workspace @layoutsee/web run test    # 纯函数单测（node --test tests/*.test.mjs）
npm --workspace @layoutsee/web run build   # 生产构建
```

`npm run test:web` 是同一套测试的根目录别名，已并入 `npm run test:unit`。

现有单测：

- `tests/scrcpy-stream.test.mjs` — 解码器纯函数（AnnexB 分割、avcc 转换、avcC 精确长度）
- `tests/workbench-interactions.test.mjs` — 终端历史环形缓冲与高危命令识别、XPath 命中序号收敛

组件是 JSX，node --test 不解析，因此这两个文件都用「读源码 + 截取纯函数片段 + `new Function` 执行」的方式取被测函数。往 JSX 文件里加纯函数时保持它在顶层且不引用组件状态，测试才能切出来。

行为验证使用真实 Core 同源托管 `dist`（打包后应用即此形态）或 `npm run dev:web`（浏览器宿主形态），不以独立 Vite 页面代替握手验证。页面级自动化（路由恢复、Tab 切换状态保留、分隔条键盘与 ARIA）属后续测试基建 Story。
