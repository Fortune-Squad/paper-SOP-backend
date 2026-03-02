---
name: execute-subtask
description: 执行子任务
argument-hint: wp_id subtask_id
---

# Command: execute-subtask

## Inputs
- `execution/{wp_id}/spec.yaml` — WP 规格
- `execution/{wp_id}/subtasks/st_{n}_spec.yaml` — 子任务规格
- 前置 subtask 的 SubtaskResult（如有）
- MEMORY.md 相关 [LEARN:tag] 条目

## Steps
1. 读取 subtask spec（含 allowed_paths / forbidden_paths）
2. 读取前置 subtask 的 what_changed + metrics + open_issues
3. 执行任务（代码生成/数据处理/图表生成等）
4. 自测（运行 acceptance criteria）
5. 运行 ArtifactBoundaryChecker
6. 写入 SubtaskResult（结构化四件套）
7. 更新 state.json（via StateStore）
8. 更新 AGENTS.md 动态 section
9. 增量写入 session_log

## Output Format
SubtaskResult JSON（§5.3）

## Constraints
- 只允许修改 allowed_paths 中的文件
- 禁止触碰 forbidden_paths
- 越界改动将被 BoundaryChecker 自动拦截并 FAIL
- 完成后增量写入 session log（决策点记录）
