---
name: no-cheat-fix
type: rule
requires_llm: true
---

# Rule: No Cheat Fix

禁止"作弊修复"模式。

## 禁止模式
1. 删除失败的断言/测试
2. 跳过失败的测试（@skip, @pytest.mark.skip）
3. 硬编码预期答案
4. 注释掉失败的代码
5. 降低精度阈值以通过测试
6. 修改测试数据以匹配错误输出
