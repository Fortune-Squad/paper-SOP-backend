---
name: verification-protocol
type: rule
requires_llm: true
---

# Rule: Verification Protocol

验证修复是否真正解决了 issue（而非删断言绕过）。

## 检查要点
1. 修复是否针对 root cause（而非 symptom）
2. 原始测试是否仍然存在且通过
3. 是否有新增测试覆盖修复的场景
4. 修复是否引入新的 regression
