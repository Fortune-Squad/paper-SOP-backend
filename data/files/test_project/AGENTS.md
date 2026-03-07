# AGENTS.md — SignalPass Project Rules
## Project Overview
SignalPass 多模型科研 SOP 项目
## Red Lines
1. 不做学术不端/代写代交付
2. 不绕过限额/不轮询多 Key
3. 不把闭源模型输出作为可售训练集
## Role Boundaries
- **executor**: 写代码、跑测试、生成 artifacts（详见 sop/agents/executor.md）
- **reviewer**: 只读审阅，输出 PASS/FAIL + issues（详见 sop/agents/reviewer.md）
- **boundary-checker**: 只读 git diff，输出 violations（详见 sop/agents/boundary-checker.md）
- **snapshot-writer**: 只写 AGENTS.md 动态 section（详见 sop/agents/snapshot-writer.md）
- **assembly-builder**: 读 frozen/，写 delivery/（详见 sop/agents/assembly-builder.md）
- **diagnostician**: Gemini 专用，escalation 诊断（详见 sop/agents/diagnostician.md）
## Available Commands
- `init-wp` → 初始化 WP（sop/commands/init-wp.md）
- `execute-subtask` → 执行子任务（sop/commands/execute-subtask.md）
- `self-test` → subtask 完成后自检（sop/commands/self-test.md）
- `submit-review` → 提交 review（sop/commands/submit-review.md）
- `fix-issues` → 修复 review 问题（sop/commands/fix-issues.md）
- `freeze-wp` → 冻结 WP（sop/commands/freeze-wp.md）
- `assemble-delivery` → 组装交付包（sop/commands/assemble-delivery.md）
## Quality Standards
- Gate = binary PASS/FAIL
- 验证器通过 + 代码能跑 + 维度对 + 趋势对 + 文件齐
- 不允许"作弊修复"：删断言/跳测试/硬编码答案
## Output Format
所有模型输出必须是 SubtaskResult JSON（schema 见 DevSpec §5.3），不是自由文本。
## Frozen Files
以下路径不可修改（hook 自动检查）：
- `artifacts/04_frozen/` 下所有文件
- 任何 `FROZEN_MANIFEST.json` 中列出的文件
## Key Rules
- 详见 `sop/rules/` 目录
- MEMORY.md 中的 [LEARN:tag] 条目必须在相关任务中遵守
<!-- AUTO-GENERATED: Do not edit below this line. Updated by Orchestra snapshot_generator -->
## Current Status
- **Phase**: step_0_2
- **Active WPs**: None
- **Last completed**: None
- **Blockers**: None
- **Next action**: Waiting for task assignment
- **Cross-model need**: None
- **RA pending**: None
<!-- END AUTO-GENERATED -->
