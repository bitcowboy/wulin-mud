# 贡献指南 · Contributing

> 在写代码之前，先读 [`docs/architecture.md`](docs/architecture.md)。整个项目的设计哲学都在那里。

## 一、开始之前

### 必读

1. [`docs/architecture.md`](docs/architecture.md) — 项目的"宪法"
2. [`docs/ontology.md`](docs/ontology.md) — 数据模型规范
3. [`docs/action-types.md`](docs/action-types.md) — Action 系统设计

### 强烈建议

4. [`docs/npc-spec.md`](docs/npc-spec.md) — 看一遍孙婆婆种子，理解 NPC 是怎么设计的
5. [`docs/llm-integration.md`](docs/llm-integration.md) — 理解 LLM 的工作边界

## 二、三条工程红线

**违反任何一条的 PR 会被直接打回。**

### 红线 1：LLM 永远不写世界状态

```python
# ❌ 永远不允许这种代码
async def generate_npc_response(npc, player_input):
    response = await llm.chat(...)
    npc.mood = parse_mood_from_response(response)  # 不！
    npc.affection_to_player += 0.1                  # 不！
    return response

# ✅ 必须这样
async def generate_npc_response(npc, player_input):
    response = await llm.chat(...)
    suggested_action = parse_action_suggestion(response)
    if suggested_action:
        action_result = await ACTION_REGISTRY[suggested_action.name].execute(
            params=suggested_action.params,
            world=world,
            actor_id=npc.id,
        )
        # state changes happen inside the action, not here
    return response.dialogue
```

### 红线 2：NPC 记忆是结构化对象

```python
# ❌ 不要把整段对话历史拼进 prompt
prompt = f"""
你是孙婆婆。下面是你过去和这个玩家的所有对话：
{full_conversation_history}  # 不！
"""

# ✅ 检索结构化 Memory，按 importance + recency 排序
memories = memory_store.retrieve(
    npc_id=npc.id,
    about_subject=player.id,
    top_n=10,
    order_by="importance_decayed",
)
prompt = render_memories_for_prompt(memories)
```

### 红线 3：人设不可漂移

NPC 的 `personality`、`background`、`constraints`、`speech_style` 是 **immutable**。

如果需要让某个 NPC "成长"（例如重大创伤后性格改变），必须通过显式的 `PersonalityShift` Action 完成——而且这种 Action 应该极少出现。

任何"为了让这次对话顺利"而临时修改 personality 的尝试都是错的。**让 NPC 显得僵硬地拒绝某话题，比让她"通融一下"更符合架构。**

## 三、代码规范

### Python

- 版本：3.11+
- 格式化：`ruff format`
- 检查：`ruff check`
- 类型：`mypy --strict`
- 测试：`pytest`

提交前：

```bash
ruff format .
ruff check . --fix
mypy wulin_mud
pytest
```

或者用 pre-commit：

```bash
pre-commit install
```

### 命名

- 模块、函数、变量：snake_case
- 类：PascalCase
- 常量：UPPER_SNAKE_CASE
- 私有：单下划线前缀 `_internal`
- Object ID：`{type}_{snake_case_name}`，例 `npc_sun_popo`

### 注释

- 代码注释用英文
- Docstring 用英文（Google 风格）
- 设计文档可以中文（README、docs/）

### 类型注解

- 所有 public 函数必须有完整类型注解
- 用 `pydantic` 或 `dataclass` 表达 schema，不要散落 dict
- 复杂 dict 用 `TypedDict` 而不是 `dict[str, Any]`

## 四、Pull Request 流程

### 提交前

- [ ] 通过 `ruff check` + `mypy` + `pytest`
- [ ] 如果改动 Ontology schema，更新 `docs/ontology.md`
- [ ] 如果新增 Action，更新 `docs/action-types.md` 中的清单
- [ ] 如果新增 NPC，确保通过 `tests/world/test_npc_consistency.py` 校验
- [ ] PR 描述里说明：你在改什么、为什么、对架构有什么影响

### PR 模板

```markdown
## 改了什么
（一两句话）

## 为什么
（动机，最好关联 issue）

## 架构影响
- [ ] 没有改 Ontology schema
- [ ] 没有引入新的 LLM 调用点
- [ ] 没有违反三条红线
- [ ] （如果改了）已更新对应文档

## 测试
- 新增了哪些测试
- 跑过了哪些 eval
```

## 五、关于 LLM 实验

这个项目本质是 LLM 工程项目。鼓励：

- 在 `scripts/experiments/` 下做小型实验
- 在 PR 里附上 LLM 输出的对比样本（prompt 改前 vs 改后）
- 记录失败案例 —— 这些是最值钱的资产

但要避免：

- 提交"我感觉这样 prompt 更好" 的修改（用 eval 数据说话）
- 把 prompt 散落到代码各处（统一在 `wulin_mud/llm/prompts/`）
- 直接复制粘贴 LLM 的代码而不理解（这是个架构项目，不是 vibe coding 项目）

## 六、设计讨论

重大设计决策走 Issue 讨论，不要在 PR 里夹带。

讨论的标题前缀用 `[design]`，例：
- `[design] 是否引入 NPC 之间的间接 Memory 传递？`
- `[design] Memory 衰减曲线参数怎么调`

提案模板：

1. **问题**：当前架构在什么场景下不够用
2. **选项**：列出至少 2 个方案
3. **推荐**：你倾向哪个，为什么
4. **风险**：每个选项的弱点

## 七、不欢迎的事

- 给 NPC 加"自动学习"逻辑而绕过 Action 层
- 把 Memory 改成 vector-only 存储而丢掉结构化字段
- 在没跑 eval 的情况下宣称 prompt 改好了
- 提交大段 AI 生成代码而不经过自己理解
- 给项目加"特性"而不加测试

## 八、欢迎的事

- 揪出违反三条红线的现有代码
- 设计更刁钻的 eval 场景（专门暴露 LLM 漂移）
- 优化 Memory 检索的 ranking 函数
- 设计新的 NPC 种子（参考孙婆婆的格式）
- 改进 LLM prompt 模板（带 A/B 数据）
- 把 docs/ 写得更好
