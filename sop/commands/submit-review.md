---
name: submit-review
description: 提交 review
argument-hint: wp_id
---

# Command: submit-review

## Inputs
- `execution/{wp_id}/gate_results/` — gate 自动检查结果
- 失败项的相关代码片段（不传全文，遵循 T3 规则）
- WP gate 标准

## Steps
1. 打包 artifacts（gate 结果 + 失败项代码片段）
2. 渲染 REVIEW_ACCEPTANCE prompt
3. 提交给 reviewer（ChatGPT/Claude/Human）
4. 解析 reviewer 输出（verdict + critical_issues）
5. 更新 state.json

## Output Format
Review JSON: {verdict, criteria, critical_issues}

## Constraints
- Reviewer 是 READ-ONLY，不能修改文件
- PASS/FAIL 是唯一的 verdict，没有"部分通过"
- 最多列 3 个 critical issues
