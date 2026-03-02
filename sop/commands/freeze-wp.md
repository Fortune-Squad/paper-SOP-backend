---
name: freeze-wp
description: 冻结 Work Package
argument-hint: wp_id
---

# Command: freeze-wp

## Inputs
- WP gate 结果（PASS）
- RA 结果（ADVANCE 或 POLISH）

## Steps
1. 版本标签：git tag {wp_id}-v{version}
2. 产物上传到持久化存储（含 checksum）
3. 生成 FROZEN_MANIFEST.json（含 ra_result 引用）
4. 更新 state.json（via StateStore）: WP status → E6_WP_FROZEN
5. 更新 AGENTS.md 动态 section
6. 写入 session_log summary
7. 如有新教训 → 追加 MEMORY.md
8. 解锁依赖此 WP 的下游 WP

## Output Format
FROZEN_MANIFEST.json

## Constraints
- 冻结后不可直接修改
- 如需修改：创建新版本 → 重新跑 gate + RA → 重新冻结
