---
name: beware-gemini-citations
type: rule
requires_llm: true
---

# Rule: Beware Gemini Citations

Gemini 引用必须交叉验证（~30% 编造率）。

## 检查要点
1. 每条 Gemini 提供的引用必须验证 DOI 可访问
2. 验证论文标题、作者、年份与 DOI 匹配
3. 验证引用内容与 Gemini 声称的一致
4. 不信任 Gemini 的"这篇论文说了..."类断言
