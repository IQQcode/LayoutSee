# VERSION

## 2026-07-16

- 新增触发条件表格、核心能力、使用方法三个标准章节，优化描述表达
- 新增 README.md 面向用户的使用文档
- 新增 VERSION.md

## 2026-07-15

- 升级 `parse_layout.py`：支持完整 V2 协议解析（Java 序列化外层 + 字符串表 + 嵌套 View Map），精确恢复层级
- 保留固定 key 兜底扫描器，标注 `legacy-key-scan` 和近似层级
- 新增 `--json-only` 参数
- 同步更新 `liv2-format.md`、`runtime-view-workflow.md`、`viewnode-schema.md`、`diagnosis-playbook.md`
