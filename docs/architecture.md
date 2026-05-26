# 架构设计 · Architecture

> 这是整个项目最重要的一份文档。读完它才能理解后面所有具体设计为什么是这样。

## 一、设计哲学

### 1.1 我们在反对什么

绝大多数"AI NPC" demo 的失败模式是同一种：

- 第一次见面，NPC 说自己是铁匠
- 第三次见面，NPC 开始谈人生哲学
- 第五次见面，NPC 忘了自己说过讨厌某派系，热情为对方站台
- 第十次见面，玩家已经不再相信屏幕另一端是个"人"

根本原因不是 LLM 不够聪明，而是**架构错了**。这些 demo 把 LLM 当成了 NPC 的"大脑+记忆+身份+行为决策器"的全部。LLM 没有持久状态，每次调用都是从零开始拼接 prompt——人格、记忆、关系全都活在易碎的 context 窗口里。

这就像让一个失忆症患者每天扮演同一个角色，靠的全是别人塞给他的便条。早晚要出戏。

### 1.2 我们的主张

> **世界状态必须存活在 LLM 之外的一个结构化、可治理、可演化的运行时里。LLM 只是这个运行时的实时解释器和代言人。**

具体到游戏里：

- **谁是这个 NPC** → 由 Ontology 中的 `NPC` 对象定义，固化，LLM 不能改
- **这个 NPC 记得什么** → 由结构化的 `Memory` 表存储，按重要性和时间衰减，LLM 只能读
- **这个 NPC 现在想做什么** → 由系统在 world tick 时决策，LLM 提供选项但不直接执行
- **这个 NPC 此刻怎么说话** → LLM 的工作，但说话内容必须在该 NPC 的人设、记忆、知识范围内

这套主张的工程范本，是 Palantir 在企业数据领域的 Ontology 架构。我们把它移植过来。

## 二、三层结构

```
┌─────────────────────────────────────────────────────────┐
│  消费层 · Consumption Layer                              │
│  玩家 CLI / 未来的 Web 前端 / 调试工具                    │
└────────────────────────┬────────────────────────────────┘
                         │ reads + Action calls
┌────────────────────────▼────────────────────────────────┐
│  生成表达层 · Expression Layer                            │
│  LLM as real-time interpreter:                          │
│  - NPC 对话生成                                          │
│  - 环境描述生成                                          │
│  - 传闻演变与扭曲                                        │
│  - 只读 Ontology，只能通过 Action 写入                    │
└────────────────────────┬────────────────────────────────┘
                         │ query / Action invocation
┌────────────────────────▼────────────────────────────────┐
│  世界状态层 · World State Layer (the Ontology)           │
│  - Object Types: NPC, Location, Item, Faction, Rumor... │
│  - Link Types: relationships, ownership, knowledge...   │
│  - Action Types: validated, audited, side-effect-aware  │
│  - Memory store + decay rules                           │
│  - World tick scheduler                                 │
└─────────────────────────────────────────────────────────┘
```

### 2.1 世界状态层（State Layer）

**这是世界真正发生了什么的地方。**

所有"事实"都活在这里。NPC 的身份、性格、当前位置、心情、健康、财富、记忆、知识、关系，全都是结构化数据。没有"由 LLM 想象"的余地。

详见 [`ontology.md`](ontology.md)。

### 2.2 生成表达层（Expression Layer）

**这是 LLM 干活的地方，但工作边界严格。**

LLM 的输入永远是从 Ontology 查询得到的结构化 context（"你正在扮演孙婆婆，今年 52 岁，开回春堂药铺。你对面这个玩家上次来打过砍价，你对他的好感是 -0.2。你最近听说镖局生意不好。现在他刚走进店里。"）。

LLM 的输出有两种合法形态：
- **纯表达性输出**：对白、神态描写、环境氛围描述——这些不改变世界状态
- **Action 调用建议**：LLM 可以"建议"调用某个 Action（如 `RefuseService` 或 `AskAboutGoods`），但 Action 是否真的被执行、参数是否合法，由 Action 层校验

LLM **永远不能**直接修改任何 Ontology 字段。

详见 [`llm-integration.md`](llm-integration.md)。

### 2.3 消费层（Consumption Layer）

v0.1 只有 CLI。玩家输入自然语言，系统解析后路由到对应的 Action 或对话流程。

未来可以加 Web 终端、调试面板、世界状态可视化、玩家行为审计日志查看器。

## 三、工程红线

**这三条是不可商量的。违反任何一条都会让整个架构垮塌。**

### 红线 1：LLM 永远不写世界状态

所有对 Ontology 的写入必须通过 Action Type。Action 携带：

- **前置条件**：能不能执行（NPC 在场吗？有这个物品吗？关系够吗？）
- **副作用声明**：会改哪些 property、会写哪些 Memory、会触发哪些下游传导
- **审计记录**：谁因为什么在什么时候调用的

LLM 可以提议 Action，但 Action 的执行由 Action Layer 校验和执行。LLM 输出的任何"事实陈述"如果改变世界状态，必须能落到一个合法 Action 上，否则只是该 NPC 的主观感受/谎言/幻想（这本身也是合法的——但不会改变世界）。

### 红线 2：NPC 的记忆是结构化的

**反模式**：把 NPC 过去所有对话原文塞进 prompt。

**正确做法**：

```python
Memory(
    timestamp=...,
    event_type="haggled_aggressively",
    participants=[player_id, npc_id],
    raw_facts={"item": "止血膏", "asked_discount": 0.5},
    npc_interpretation="这小子第一次来就砍价砍狠了，没规矩",
    emotional_charge=-0.3,
    importance=0.4,
    decay_rate=0.05,  # 每天衰减
)
```

`raw_facts` 是客观的（所有目击者共享）。`npc_interpretation` 在事件发生时由 LLM 基于该 NPC 的 personality 生成并**固化下来**——下次回忆时不再重新生成。这是为什么不同 NPC 目击同一事件会有不同记忆的根本机制。

### 红线 3：人设不可漂移

NPC 的核心维度（personality 五维 + 武侠向补充维度、background、constraints）一旦在世界初始化时定下，**运行期内不再修改**。

LLM 可以让 NPC 在对话中"表演"出复杂、矛盾、伪装——但底层维度不变。性格的演化只能通过显式的 `PersonalityShift` Action 完成，且这种 Action 应该极少发生（重大创伤、长期关系变化才会触发）。

## 四、世界 tick 模型

世界不只是在玩家行动时才动。它有自己的节奏。

**Tick 频率**：v0.1 使用 5 分钟一次的真实时间 tick。游戏内时间和真实时间的映射比例可配置（默认 1 分钟真实时间 = 10 分钟游戏内时间）。

**每个 tick 做什么**：

1. **NPC 心情漂移**：基于性格的基线和最近事件，每个 NPC 的 mood 向其稳态回归或被新事件扰动
2. **Memory 衰减**：每条 Memory 的 `importance` 按 `decay_rate` 衰减
3. **Rumor 扩散**：根据 NPC 之间的关系网，传闻在听话人之间扩散（同时可能被扭曲）
4. **NPC 自主行为**：处于"空闲"状态的 NPC 根据当前目标和约束选择下一步行动（吃饭、巡店、串门、记账），由系统调用 LLM 做决策，输出必须是合法 Action
5. **延迟事件触发**：登记过 `delayed_until` 的事件到时执行

详见 [`docs/world-tick.md`](world-tick.md)（待写）。

## 五、与 Palantir Ontology 模型的对照

| Palantir 概念 | wulin-mud 对应 |
|---|---|
| Ontology | World State Ontology |
| Object Type | `NPC`, `Location`, `Item`, `Faction`, `Rumor`, `Event` |
| Link Type | `NPC.member_of(Faction)`, `NPC.knows(Fact)`, `NPC.remembers(Memory)` |
| Action Type | `SpreadRumor`, `BuyItem`, `OffendNPC`, `SwearBrotherhood` ... |
| Function | NPC 决策函数、Memory 检索函数、Rumor 扭曲函数 |
| AIP Logic | LLM 驱动的对话生成与 NPC 自主决策 |
| AIP Evals | NPC 一致性回归测试（见 `tests/eval/`） |
| Branching | （v1.0+）赛季分叉、PTR、what-if 沙箱 |
| Audit log | 所有 Action 执行日志，作为后续分析的训练信号 |

详见 [`docs/palantir-mapping.md`](palantir-mapping.md)（待写）。

## 六、不做什么

为了保证 v0.1 能在 2-3 周内跑出来，明确不做的事：

- ❌ 战斗系统（v0.2 再说，先不打架）
- ❌ 物品的复杂属性（武器只有名字，没有 DPS）
- ❌ 玩家自定义角色（玩家就是一个外来年轻侠客）
- ❌ 任何形式的图形化界面
- ❌ 玩家之间的多人交互
- ❌ 自动剧情生成（玩家自己探索就是剧情）
- ❌ NPC 之间的自主"剧情对话"在玩家不在场时发生（太烧 token 且 v0.1 用不上）

## 七、成功标准（v0.1）

如果下面这条标准能被验证，整个架构方向就是对的：

> **一个独立测试者（没参与开发）与孙婆婆这个 NPC 自由交互 30 分钟以上，结束后被问"你觉得她是个什么样的人"，能给出连贯、具体、与种子设定相符的描述；并且能说出至少 3 件他和她之间"发生过的事"。**

这比任何技术指标都重要。
