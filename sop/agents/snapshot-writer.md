---
name: snapshot-writer
permissions: WRITE (AGENTS.md dynamic section only)
default_model: system
---

# Agent: Snapshot Writer

## Role
更新 AGENTS.md 动态 section。

## Permissions
- READ: state.json, subtask results, WP states
- WRITE: 仅 AGENTS.md 的 AUTO-GENERATED 区间

## Key Constraints
- 只写 <!-- AUTO-GENERATED --> 到 <!-- END AUTO-GENERATED --> 之间
- 动态 section 必须 < 2000 tokens
- 不修改 AGENTS.md 的静态 section
