#!/bin/bash
# 护栏示例：禁止修改第三方只读内核 source/uiautodev
# 用法：作为 Claude Code PostToolUse hook（Edit|Write），从 stdin 读取 hook JSON
# 命中规则时输出 block 决策并 exit 2，阻止该写入

INPUT=$(cat)
FILE_PATH=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('file_path', ''))
except Exception:
    print('')
" 2>/dev/null)

case "$FILE_PATH" in
  */source/uiautodev/*)
    echo "{\"decision\": \"block\", \"reason\": \"source/uiautodev 为第三方只读内核，禁止直接修改。二开产物请落在 layoutsee-prototype 或独立目录。\"}"
    exit 2
    ;;
  *)
    exit 0
    ;;
esac
