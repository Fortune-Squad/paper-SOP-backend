---
name: init-wp
description: 初始化 Work Package
argument-hint: wp_id
---

# Command: init-wp

## Inputs
- `execution/wp_registry.yaml` — WP DAG 定义
- `artifacts/04_frozen/04_Research_Plan_FROZEN.md` — 冻结研究计划

## Steps
1. 解析 WP spec（owner, reviewer, gate_criteria, depends_on）
2. 生成 subtask 分解（如 subtask_decomposition=auto）
3. 创建 WP 目录结构（code/, data/, figures/, review_log/, gate_results/, subtasks/）
4. 写入 spec.yaml 和 st_{n}_spec.yaml（含 allowed_paths / forbidden_paths）
5. 更新 state.json（via StateStore）: WP status → E1_WP_READY
6. 更新 AGENTS.md 动态 section
7. 创建 session_log

## Output Format
SubtaskResult JSON（§5.3）

## Constraints
- 不修改 PlanFrozen 文件
- subtask 分解需人类在 Exec-Loop1 确认
