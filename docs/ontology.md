# Ontology 规范 · Data Model Specification

> 这份文档定义世界状态层的所有数据结构。任何对这些结构的修改都需要在 PR 中明确说明并更新本文档。

## 一、设计原则

1. **结构化优先**：能用枚举就不用自由文本，能用 ID 引用就不用名字字符串。
2. **不可变事实 + 可变状态分离**：每个对象都明确区分"出生时就固定的事实"和"运行时变化的状态"。
3. **每条变化都有审计**：所有 mutation 通过 Action 完成，Action 自带 timestamp 和 caller。
4. **LLM 可读**：所有字段都要能被自然语言化（用于注入 prompt）。

## 二、核心 Object Types

### 2.1 `NPC`

```python
@dataclass
class NPC:
    # ===== 不可变身份 · Immutable Identity =====
    id: str                          # e.g. "npc_sun_popo"
    name: str                        # "孙婆婆"
    age: int
    gender: str
    role: str                        # "回春堂老板娘"

    # ===== 不可变人设 · Immutable Personality =====
    personality: Personality         # OCEAN + 武侠维度
    background: str                  # 自然语言出身故事
    secrets: list[Secret]            # 不会主动说，但可能被挖出
    constraints: list[str]           # "不能透露丈夫的死因"等行为底线
    speech_style: SpeechStyle        # 用词、口头禅、方言痕迹

    # ===== 可变状态 · Mutable State =====
    current_location_id: str
    mood: Mood                       # valence + arousal
    health: float                    # 0.0 ~ 1.0
    wealth: int                      # 铜钱
    energy: float                    # 0.0 ~ 1.0，影响是否愿意聊天

    # ===== 关系网 · Relationships =====
    relationships: dict[str, Relationship]      # other_npc_id -> Relationship
    player_relationship: PlayerRelationship     # 与玩家的专属关系

    # ===== 知识 · Knowledge =====
    knowledge: list[Fact]            # 客观知道的事实
    heard_rumors: list[HeardRumor]   # 听说过的传闻（带来源和扭曲）

    # ===== 目标 · Goals =====
    short_term_goals: list[Goal]     # "今天卖出 20 副药"
    long_term_goals: list[Goal]      # "查明丈夫死因"
```

### 2.2 `Personality`

```python
@dataclass(frozen=True)
class Personality:
    # OCEAN 五维（0.0 ~ 1.0）
    openness: float                  # 开放性
    conscientiousness: float         # 尽责性
    extraversion: float              # 外向性
    agreeableness: float             # 宜人性
    neuroticism: float               # 神经质

    # 武侠向补充维度
    honesty: float                   # 诚实度，影响是否说谎
    courage: float                   # 胆量，影响面对威胁的反应
    greed: float                     # 贪婪度，影响金钱诱惑的抗性
    loyalty: float                   # 忠诚度，影响背叛倾向
    pride: float                     # 傲气，影响受辱后的反应
```

**重要约定**：这些值一旦设定就不再变。NPC 当前的"行为"是由 personality + mood + memories + goals 共同决定的——personality 是常量，其他是变量。

### 2.3 `Memory`

整个项目最关键的一类对象。

```python
@dataclass
class Memory:
    id: str
    timestamp: float                 # 游戏内时间

    # ===== 客观事实层 · Objective Layer =====
    event_type: EventType            # 枚举：见面/对话/帮助/伤害/目击/听说...
    participants: list[str]          # NPC ID 或 player_id
    location_id: str
    raw_facts: dict                  # 结构化事实，所有目击者共享

    # ===== 主观解读层 · Subjective Layer =====
    npc_id: str                      # 这条记忆属于谁
    interpretation: str              # 该 NPC 的主观理解（事发时 LLM 生成并固化）
    emotional_charge: float          # -1.0 ~ +1.0

    # ===== 衰减控制 · Decay Control =====
    importance: float                # 0.0 ~ 1.0，决定被想起的概率
    decay_rate: float                # 每游戏天的衰减速率
    last_recalled_at: float          # 最后一次被提取的时间（影响后续衰减）

    # ===== 检索辅助 · Retrieval Aids =====
    tags: list[str]                  # ["金钱", "砍价", "首次见面"]
    embedding: Optional[list[float]] # 语义向量（v0.2 启用）
```

**Memory 的生命周期**：

1. **生成**：某个 Action 执行时，按 `side_effects` 声明的目标 NPC 列表，为每个目击者生成一条 Memory。`interpretation` 由 LLM 在那一刻生成，固化下来。
2. **检索**：NPC 与某人交互时，按 `importance × recency × tag_relevance` 排序，取 top N（默认 10）作为 prompt context。
3. **衰减**：每个 world tick，所有 Memory 的 `importance` 按 `decay_rate` 衰减。被想起时 `last_recalled_at` 更新（被想起的事衰减更慢——符合心理学）。
4. **遗忘**：`importance < 0.05` 时归档为"模糊印象"，不再进入 prompt，但保留在数据库（供调试和未来分析）。

**为什么 interpretation 要固化**：因为人的记忆就是这样工作的。孙婆婆当时觉得玩家"没规矩"，这个印象就会一直跟着她。如果每次取记忆都重新让 LLM 解读，就会出现"她有时候觉得玩家无礼，有时候又觉得玩家爽快"的精神分裂。

### 2.4 `Relationship` / `PlayerRelationship`

```python
@dataclass
class Relationship:
    other_id: str
    affection: float                 # -1.0 ~ +1.0，整体好感
    trust: float                     # 0.0 ~ 1.0，信任度
    familiarity: float               # 0.0 ~ 1.0，熟悉度

    relationship_type: str           # "亲属" / "朋友" / "雇佣" / "宿敌" / "陌生人"
    relationship_label: str          # "侄子" / "旧识" / "杀夫仇人"（叙事性标签）

    notable_memory_ids: list[str]    # 该关系中最重要的几段记忆
    last_interaction_at: float


@dataclass
class PlayerRelationship(Relationship):
    first_met_at: float
    impression_summary: str          # 每几天由 LLM 压缩 memories 生成的概括印象
    # 例："一个新来的年轻侠客，看着不像坏人但有些莽撞。"
```

### 2.5 `Location`

```python
@dataclass
class Location:
    id: str
    name: str                        # "回春堂"
    type: LocationType               # 药铺/客栈/茶肆/铁铺/...
    description: str                 # 基础环境描述

    # 动态状态
    current_npcs: list[str]          # 此刻在场的 NPC ID
    atmosphere: str                  # 当前氛围（由系统根据事件动态更新）

    # 关联
    owner_npc_id: Optional[str]      # 老板是谁
    connected_to: list[str]          # 相邻 location ID
```

### 2.6 `Item`

```python
@dataclass
class Item:
    id: str
    name: str
    type: ItemType                   # 药/食物/武器/书信/钱袋/...
    description: str

    # v0.1 不做复杂属性
    base_price: int                  # 基础铜钱价

    # 所有权
    owner_id: Optional[str]          # 拥有者（NPC 或 player）
    location_id: Optional[str]       # 如果在地上

    # 元信息
    is_unique: bool                  # 独一无二的物件（如某封信）
    metadata: dict                   # 灵活字段（如信件内容、药效说明）
```

### 2.7 `Rumor`

```python
@dataclass
class Rumor:
    id: str
    created_at: float

    # 原始事实
    source_event_id: Optional[str]   # 如果来自真实事件
    original_content: str            # 最初的版本

    # 当前在 NPC 之间的传播态
    spread_chain: list[RumorSpread]  # 谁传给谁，每次扭曲了什么

    veracity: float                  # 真实度（系统知道，NPC 不知道）
    spice_level: float               # 八卦程度，影响传播速度
```

### 2.8 `Action`（执行历史，不是 Action Type 定义）

```python
@dataclass
class ActionRecord:
    id: str
    timestamp: float
    action_type: str                 # "SpreadRumor", "BuyItem"...
    actor_id: str                    # 执行者（player 或 npc_*）
    parameters: dict

    # 执行结果
    succeeded: bool
    side_effects_applied: list[dict] # 实际写入的副作用清单
    memories_generated: list[str]    # 生成了哪些 Memory

    # 审计
    initiated_by: str                # "player_input" / "world_tick" / "llm_decision"
    llm_reasoning: Optional[str]     # 如果由 LLM 决策，附上推理过程
```

**所有 Action 执行都要落这张表。这是后续做行为分析、bug 排查、训练数据筛选的金矿。**

## 三、Link Types

链接是双向的，但用单向边存储（查询时双向解析）。

| 边 | 方向 | 含义 |
|---|---|---|
| `MEMBER_OF` | NPC → Faction | NPC 属于某派系（包括秘密派系） |
| `OWNS` | NPC → Location/Item | 所有权 |
| `KNOWS` | NPC → Fact | NPC 知道某个事实 |
| `REMEMBERS` | NPC → Memory | NPC 有某段记忆 |
| `RELATES_TO` | NPC → NPC | 关系网中的一条边 |
| `HEARD` | NPC → Rumor | NPC 听说过某传闻 |
| `LOCATED_AT` | NPC/Item → Location | 当前位置 |
| `OCCURRED_AT` | Event → Location | 事件发生地 |

## 四、命名约定

- ID 格式：`{type}_{slug}`，例 `npc_sun_popo`, `loc_huichun_pharmacy`, `item_zhixue_gao`
- 字段命名：snake_case
- 枚举：单独的 Python `Enum` 类，不要在字段里散落字符串字面量
- 时间：浮点秒数（Unix 时间），游戏内时间另存

## 五、数据持久化

v0.1：SQLite，每个 Object Type 一张表，关系网用单独的 `relationships` 表，Memory 单独一张表。

v0.2 起：考虑切到 PostgreSQL + pgvector（为了语义检索 Memory）。

详见 [`schemas/`](../wulin_mud/ontology/schemas/) 目录下的 SQL 文件（待生成）。

## 六、序列化

所有 Object Type 必须实现 `to_dict()` 和 `from_dict()`，且字段命名与 JSON key 一致。

用于：
- 持久化
- LLM prompt 注入（先 `to_dict()` 再 natural-language 化）
- 调试 dump
- 未来的 API 暴露

## 七、Schema 演进策略

这个项目一定会改 schema（v0.1 → v0.2 → v1.0）。我们采用：

1. **加字段总是允许的**，给默认值即可。
2. **改字段语义需要写 migration script**，放在 `scripts/migrations/`。
3. **删字段需要在 PR 描述里证明没人引用**。

不要走"先把字段塞进 metadata dict 再说"这条歪路——它一定会让 Memory 那种关键对象失控。
