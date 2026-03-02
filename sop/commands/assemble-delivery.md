---
name: assemble-delivery
description: 组装交付包
argument-hint: delivery_profile
---

# Command: assemble-delivery

## Inputs
- 所有 E6_WP_FROZEN artifacts
- `delivery/manifest.yaml`
- `evidence/refs/refs.bib`

## Steps
1. D0_COLLECT: 扫描所有冻结 artifacts → 构建 delivery manifest
2. D1_FIGURE_POLISH: 适配 journal format → 人类审批
3. D2_ASSEMBLY: 按 delivery_profile 生成交付物
   - internal_draft: 生成 draft.tex/md
   - external_assembly_kit: 生成 outline + figure_slots + claim_map + refs + instructions
4. D3_CITATION_QA: 验证所有 citation keys 存在于 refs.bib
5. D4_REPRO_CHECK: 运行可复现性验证
6. D5_PACKAGE: 按 delivery_profile 打包

## Output Format
Delivery package（按 profile 不同）

## Constraints
- 不产生新的研究结论
- 不引入 refs.bib 中不存在的新引用
- 不添加 Step 0-3 中没有产出的新数据/图表/实验
