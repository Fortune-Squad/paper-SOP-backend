---
name: fix-issues
description: 修复 review 问题
argument-hint: wp_id iteration_number
---

# Command: fix-issues

## Inputs
- `execution/{wp_id}/review_log/review_{n}.json` — review 发现的问题
- MEMORY.md 相关 [LEARN:tag] 条目

## Steps
1. 读取 critical_issues 列表
2. 逐条修复（仅修复列出的问题）
3. 运行 ArtifactBoundaryChecker
4. 重新运行失败的 acceptance criteria
5. 输出修复后的文件 + 更新后的 gate 结果

## Output Format
SubtaskResult JSON（§5.3）

## Constraints
- 仅修复列出的问题，不做其他改动
- 不要重构
- 不要修复未列出的问题（scope creep）
- 只允许修改 allowed_paths
- 最多 2 轮迭代，超过则 escalate
