---
name: freeze-hygiene
type: rule
requires_llm: true
---

# Rule: Freeze Hygiene

冻结流程完整检查清单。

## 检查要点
1. 版本标签已创建
2. 所有产物已上传到持久化存储
3. FROZEN_MANIFEST.json 完整（含 checksums）
4. state.json 已更新（via StateStore）
5. AGENTS.md 动态 section 已更新
6. reproduce.sh 可运行
7. 无未提交的更改
