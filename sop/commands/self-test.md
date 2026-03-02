---
name: self-test
description: subtask 完成后自检
argument-hint: wp_id subtask_id
---

# Command: self-test

## Inputs
- `execution/{wp_id}/subtasks/st_{n}_spec.yaml` — 含 acceptance criteria
- subtask 产物文件

## Steps
1. 逐条运行 acceptance criteria
2. 收集测试结果和 metrics
3. 运行 ArtifactBoundaryChecker
4. 输出 PASS/FAIL + evidence

## Output Format
```json
{
  "verdict": "PASS | FAIL",
  "criteria_results": [
    {"id": "C1", "name": "...", "result": "PASS|FAIL", "evidence": "..."}
  ],
  "boundary_check": "PASS | FAIL",
  "boundary_violations": []
}
```

## Constraints
- READ-ONLY：不修改任何产物文件
- 只报告事实，不做修复
