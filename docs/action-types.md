# Action Types · 世界的动词

> Action 是世界中所有可执行变化的统一入口。无论是玩家行为、NPC 自主行为、还是 world tick 触发的变化，都必须经过 Action。

## 一、为什么 Action 必须是统一入口

如果允许"直接改字段"，半年后没人能搞清楚某个状态变化是因为什么发生的。Bug 会变得不可追溯，行为数据会丢失，调优会变成玄学。

**Action 给我们：**
- 完整审计日志（谁因为什么改了什么）
- 副作用的统一传导机制
- 玩家行为的训练数据
- 回滚能力（理论上）
- 对 LLM 行为的护栏（LLM 只能调 Action，不能直接写）

## 二、Action 的标准结构

```python
class ActionType(ABC):
    """Base class for all action types."""

    name: str                        # "BuyItem"
    description: str                 # 给 LLM 看的自然语言说明

    # ===== 参数声明 =====
    parameter_schema: dict           # JSON Schema 风格

    # ===== 权限 =====
    callable_by: set[str]            # {"player", "npc", "system"}

    # ===== 校验 =====
    @abstractmethod
    def validate(self, params: dict, world: WorldState) -> ValidationResult:
        """Pre-condition checks. Returns reason if invalid."""

    # ===== 执行 =====
    @abstractmethod
    def execute(
        self,
        params: dict,
        world: WorldState,
        actor_id: str,
    ) -> ActionResult:
        """Apply side effects, generate memories, return result."""

    # ===== 副作用声明 =====
    @abstractmethod
    def declare_side_effects(self, params: dict) -> SideEffectManifest:
        """
        Static declaration of what this action *could* affect.
        Used for:
        - Generating witness lists (who gets a Memory)
        - Triggering propagation rules
        - Conflict detection
        """
```

`SideEffectManifest` 是关键：

```python
@dataclass
class SideEffectManifest:
    # 哪些字段可能被改
    mutates_fields: list[str]        # ["NPC.wealth", "NPC.mood", "Item.owner_id"]

    # 谁会作为目击者获得 Memory
    witnesses_rule: WitnessesRule    # 同地点所有人 / 指定 NPC 列表 / 派系成员 / ...

    # 是否触发 Rumor
    generates_rumor: bool
    rumor_spice: float

    # 延迟触发的后续 Action
    triggers_delayed: list[DelayedAction]
```

## 三、Action 分类与首批清单

### 3.1 交互类 · Interaction

| Action | 谁能调 | 简述 |
|---|---|---|
| `Greet` | player, npc | 打招呼，建立 familiarity |
| `Talk` | player, npc | 自由对话，由 LLM 生成具体内容，但每轮对话本身是一个 Action |
| `AskAbout` | player, npc | 询问某个话题（人/事/物） |
| `Eavesdrop` | player | 偷听同房间其他人对话 |
| `Observe` | player | 观察某 NPC 或场景细节 |

### 3.2 信息类 · Information

| Action | 谁能调 | 简述 |
|---|---|---|
| `SpreadRumor` | npc, player | 主动传播某传闻 |
| `Lie` | npc, player | 说谎，可能被识破 |
| `RevealSecret` | npc, player | 透露自己的秘密 |
| `SendLetter` | npc, player | 寄信，到达有延迟 |

### 3.3 物资类 · Material

| Action | 谁能调 | 简述 |
|---|---|---|
| `BuyItem` | player, npc | 购买，需要协商价格 |
| `SellItem` | player, npc | 出售 |
| `GiftItem` | player, npc | 赠送，强烈影响 affection |
| `StealItem` | player, npc | 偷窃，有目击者机制 |
| `DamageProperty` | player, npc | 砸东西 |

### 3.4 关系类 · Relational

| Action | 谁能调 | 简述 |
|---|---|---|
| `HelpNPC` | player | 帮助某 NPC（具体形式多样） |
| `OffendNPC` | player | 冒犯（言语或行为） |
| `SaveLife` | player, npc | 救命，重要级 Memory |
| `BetrayTrust` | player, npc | 背叛信任 |
| `SwearBrotherhood` | player, npc | 结拜 / 立誓 |

### 3.5 武力类 · Combat（v0.1 简化）

| Action | 谁能调 | 简述 |
|---|---|---|
| `Challenge` | player, npc | 挑战/约架，开启战斗流程 |
| `Threaten` | player, npc | 威胁（不一定动手） |
| `Ambush` | player, npc | 偷袭 |
| `Mediate` | player, npc | 居中调解冲突 |

### 3.6 移动类 · Movement

| Action | 谁能调 | 简述 |
|---|---|---|
| `MoveTo` | player, npc | 移动到相邻位置 |
| `Wait` | player, npc | 等待，让时间推进 |
| `Leave` | npc | NPC 离开某地（影响目击者集合） |

### 3.7 系统类 · System-Initiated

不由 player 或 npc 直接调用，由 world tick 触发：

| Action | 简述 |
|---|---|
| `DecayMemories` | 衰减所有 Memory 的 importance |
| `DriftMood` | 让 NPC mood 向稳态回归 |
| `PropagateRumor` | 让 rumor 在 NPC 网络中传播 |
| `TriggerDelayed` | 执行到期的延迟 Action |
| `RegenerateImpression` | 重新压缩某 NPC 对玩家的印象总结 |

## 四、Action 执行流程

```
┌─────────────────────────────────────────────┐
│  1. 调用入口                                  │
│     player input | npc decision | scheduler  │
└────────────────────┬─────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│  2. 参数解析                                  │
│     自然语言 → 结构化参数（LLM 辅助）          │
└────────────────────┬─────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│  3. validate()                               │
│     权限 / 前置条件 / 物理合理性                │
└────────────────────┬─────────────────────────┘
                     ▼ (passed)
┌─────────────────────────────────────────────┐
│  4. declare_side_effects()                   │
│     得到目击者集合、潜在传播链                  │
└────────────────────┬─────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│  5. execute()                                │
│     原子写入：状态变更 + 生成 Memory + 写日志  │
└────────────────────┬─────────────────────────┘
                     ▼
┌─────────────────────────────────────────────┐
│  6. 表达层渲染                                │
│     LLM 把结果叙述给玩家（旁白 + NPC 反应）    │
└──────────────────────────────────────────────┘
```

## 五、关键设计决策

### 5.1 LLM 怎么"调用"Action

不是让 LLM 直接返回 `BuyItem({"item": "止血膏"})` 这种 JSON——这容易出错。

采用两阶段：

1. **意图识别**：玩家输入"我想买一副止血膏"，由一个小 LLM（或规则匹配）识别意图为 `BuyItem`
2. **参数补全**：把意图、玩家输入、世界状态丢给主 LLM，输出结构化参数和该 Action 的执行参数

对于 NPC 自主行为，由 world tick 调度时：
1. 查询该 NPC 当前可执行的 Action 列表（基于位置、关系、资源）
2. 让 LLM 在这个列表里选一个，并填参数
3. LLM 必须给出 `reasoning`，记入 `ActionRecord.llm_reasoning`

### 5.2 谁是"目击者"

每个 Action 在 `declare_side_effects` 里返回 `WitnessesRule`，常见几种：

- `SAME_LOCATION`：当前位置所有 NPC
- `EXPLICIT`：指定 ID 列表
- `FACTION_MEMBERS`：某派系所有成员（远程感知，如"听说"）
- `RELATED_TO_PARTICIPANT`：与参与者有关系链的 NPC（间接感知）

每个目击者都生成一条 Memory，但每个人的 `interpretation` 是基于自己的 personality 单独生成的。

### 5.3 失败的 Action 也要记录

`Lie` 被识破、`StealItem` 被发现、`BuyItem` 因为钱不够失败——这些都是有价值的事件，必须留下 Memory（且通常比成功更重要）。

`ActionResult.succeeded = False` 时仍然要执行副作用：失败的偷窃会生成"目击者发现盗窃企图"的 Memory。

### 5.4 原子性

`execute()` 必须在一个数据库事务内完成。任何中间失败要全部回滚。

## 六、扩展指南

加一个新 Action 的步骤：

1. 在 `wulin_mud/actions/` 下新建文件，继承 `ActionType`
2. 实现 `validate` / `execute` / `declare_side_effects`
3. 在 `wulin_mud/actions/__init__.py` 的 `ACTION_REGISTRY` 中注册
4. 在 `tests/actions/test_<name>.py` 写测试，至少覆盖：
   - 正常执行
   - 各种 validation 失败
   - 副作用是否正确写入
   - 目击者 Memory 是否正确生成
5. 如果引入新 EventType，更新 `ontology.py` 的枚举

## 七、未来扩展

v0.2+：
- **Compound Action**：把多个 Action 打包为事务序列（"袭击商队"=移动+威胁+战斗+抢劫+逃跑）
- **Reactive Action**：某 NPC 在被某 Action 影响时自动触发的反应（"被冒犯"→"还嘴"）
- **Delayed Action with conditions**：不只是时间触发，还能是条件触发（"如果三天内没人来还钱"）

v1.0+：
- **跨 shard Action**：多服务器世界的事件传播
- **Action versioning**：支持热重载和 A/B 测试
