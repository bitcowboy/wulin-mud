# LLM 集成规范 · LLM Integration

> 这份文档规定 LLM 在系统中的工作边界、prompt 模板设计、和反漂移护栏。

## 一、LLM 的三种工作场景

### 1.1 NPC 对话生成（最高频）

**输入**：
- 当前 NPC 的完整 schema（personality、background、constraints、speech_style）
- 该 NPC 与对话方的关系状态
- 检索到的 Memory top-N
- 当前 mood、energy、location 氛围
- 玩家刚说的话
- 最近 N 轮的对话上下文

**输出**：
- 一段对白（可能包含动作神态）
- 可选：建议调用的 Action

### 1.2 Memory Interpretation 生成（中频）

**输入**：
- 客观事件描述（`raw_facts`）
- 该 NPC 的 personality
- 当前 mood
- 与事件参与者的关系

**输出**：
- 一段第一人称解读（"这小子上来就砍价砍狠，没规矩"）
- 情绪影响值估计

**关键**：这一步的输出会被**固化下来**，下次回忆时不重新生成。

### 1.3 NPC 自主行为决策（低频，world tick 时）

**输入**：
- 该 NPC 当前可执行的 Action 列表
- 短期与长期 goals
- 当前 mood、energy
- 最近 Memory top-N

**输出**：
- 选定的 Action + 参数
- `reasoning`（写入审计日志）

## 二、Prompt 模板基本框架

所有 LLM 调用使用同一套层次化模板。下面是 NPC 对话生成的样板：

```
[SYSTEM]
你正在扮演武侠小镇清河镇的一位 NPC。
你的任务不是"陪玩家聊天"，而是"作为这个具体的人，在这个具体时刻，做出真实反应"。

【铁律】
1. 严格遵守人设维度。你不会突然变得开朗、突然变得冷漠、突然博学起来。
2. 严格遵守 constraints。这些是你的底线，比 personality 更硬。
3. 你的知识就是 knowledge 列表里的内容。除此之外的事，你不知道。
4. 你听过的传闻就是 heard_rumors 列表里的。不要凭空"听说"任何事。
5. 你对玩家的态度由 player_relationship + recent_memories 决定，不由"客气"决定。
6. 你不知道自己是 NPC。你不知道有"玩家"这个概念。对你而言，对方就是个外来的年轻人。
7. 永远使用 speech_style 中的语言风格。用她的口头禅，模仿她的语气。

【人设维度参考】
- openness 低 → 不爱新东西
- conscientiousness 高 → 做事有条理
- agreeableness 中等 → 表面客气，内心有判断
- honesty 高 → 不爱说谎，但会保留信息
- pride 中高 → 不容许被轻贱

[USER · 角色资料]
你的名字：孙婆婆，52 岁，回春堂老板娘
{背景故事原文}

【你的 constraints（必须遵守）】
- 绝不在外人面前提起丈夫的死
- 绝不让小满卷入江湖事
- ...

【你的说话风格】
- 自称"我"，对年轻人称"小哥/姑娘"
- 口头禅："药是死的，人是活的。" "你这话我听着，先记下。"
- 语速不快，话短，常有半句不说完的停顿
- 不爱用文绉绉的词

[USER · 当前情境]
此刻你在回春堂。
你现在的心情：valence=-0.2 (略有不快), arousal=0.4 (平静)
你今天的精力：0.6 (中等)
店里气氛：午后清淡，刚送走一个赊账的妇人

[USER · 你和对方的关系]
对方：一个外来的年轻侠客模样的人
你们第一次见面：3 天前
你对他的整体印象：affection=-0.15, trust=0.3
最近的印象总结：第一次来就为了几文钱跟你磨了半天，让你觉得这小子不够痛快。
但昨天他在店里没钱时也没耍赖，欠了 50 文写了字据走了。

【你对他的具体记忆（按重要性排序）】
1. [3 天前] 他第一次来买止血膏，从 80 文砍到 50 文。你心想：这小子没规矩。
2. [昨天] 他为路边一个跌倒的老人买药，钱不够，写了字据。你心想：倒不全是坏胚。
3. [3 天前] 他离开时随手帮你把门帘掀好。你心想：这倒是有礼数。

[USER · 玩家刚说的话]
"婆婆，今儿气色不错。前几天你说的那个跌打的方子，能再帮我抓一副么？"

[USER · 回应要求]
请以孙婆婆的身份回应。
- 长度：1-3 句话，符合她话短的风格
- 可以包含动作神态（写在括号里）
- 不要解释你自己的心理活动
- 如果对话引向了你不想谈的话题（如丈夫），用她的方式回避
- 如果需要执行某个 Action（如卖药），在末尾另起一行写：
  ACTION_SUGGESTION: SellItem(item="跌打药方", price=80)
```

## 三、反漂移护栏

LLM 漂移的几种典型形态和对策：

### 3.1 人设漂移

**症状**：同一个 NPC 一开始话短，几轮后开始长篇大论。

**对策**：
- 每次调用都**完整重新注入** personality、constraints、speech_style。不要假设 LLM 会"记得"——它不会。
- 在 prompt 末尾再次提醒"符合 speech_style"。
- 输出后做 lightweight 检查：长度、是否包含禁用词、是否提到了 constraint 禁止的话题。失败则重新生成（最多 2 次，然后 fallback 到一个安全应答）。

### 3.2 知识漂移

**症状**：NPC 知道她不可能知道的事（如玩家上一站的村庄名字）。

**对策**：
- 明确告诉 LLM"你的知识就是这个列表，除此之外的事一律不知道"
- 在 prompt 里提供"如果对方问起你不知道的事，要表现出困惑或反问"的范本
- 测试用例必须覆盖"问 NPC 一件她不可能知道的事"，验证她会承认不知道而不是编

### 3.3 立场漂移

**症状**：NPC 第一次表达讨厌某派系，第十次开始夸该派系。

**对策**：
- `player_relationship.impression_summary` 每隔几天由 LLM 总结一次，但总结时必须以**当时的状态**为基准，而不是凭对话上下文猜
- Memory 里的 `emotional_charge` 是固化的，不让 LLM 改
- 长对话场景中每 10 轮做一次"复习"——把 personality 和 constraint 再 inject 一次

### 3.4 时空漂移

**症状**：NPC 说"昨天我去过京城"——但她明明 20 年没出过镇。

**对策**：
- prompt 里明确给出该 NPC 的活动范围、近期行程
- 如果 LLM 输出涉及空间/时间的具体声明，做后处理校验：声明的地点是否在 NPC 可达范围、声明的时间是否合理

## 四、模型选择与成本

### v0.1 建议

| 场景 | 模型 | 理由 |
|---|---|---|
| 对话生成 | `gpt-4o` 或 `gpt-4o-mini` | 主要质量来源，先用大模型 |
| Memory interpretation | `gpt-4o-mini` | 短输出，质量要求中等 |
| NPC 自主行为决策 | `gpt-4o-mini` | 结构化输出为主 |
| 意图识别 | `gpt-4o-mini` 或本地小模型 | 高频调用，成本敏感 |

### 调用频率估算

假设单个玩家活跃 session：
- 对话轮次：~50 轮/小时
- 每轮 1 次主对话生成 + 1 次意图识别 + 平均 0.5 次 Memory 生成
- World tick：每 5 分钟一次，每次平均触发 3 个 NPC 决策 = 36 次/小时

**单玩家小时调用约 150-200 次**。v0.1 不上线，只内部测试，成本可控。

### Token 优化

- Memory 检索时严格控制 top-N（默认 10 条，不超过 15）
- 长背景故事可压缩为关键点列表（在 seed 阶段就准备压缩版）
- 对话上下文最多保留 6 轮，更早的存入 Memory
- 用 cache（同一个 NPC 在短时间内多次说话，system prompt 复用）

## 五、Provider 抽象

虽然 v0.1 默认使用 OpenAI，但代码层做轻量抽象，方便未来切换：

```python
# wulin_mud/llm/provider.py

class LLMProvider(Protocol):
    async def generate(
        self,
        system: str,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> LLMResponse: ...

class OpenAIProvider:
    """Default implementation."""
    
class FineTunedLocalProvider:
    """For the 8B fine-tuned model (v0.2+)."""
```

**v0.2 计划**：把 NPC 对话生成的"具体表达"层切到本地 8B 微调模型，主 LLM 只负责框架决策。届时通过 `provider` 切换即可。

## 六、Eval 框架（最小版）

```
tests/eval/
├── npc_consistency/
│   ├── sun_popo/
│   │   ├── scenario_01_first_buy.yaml          # 第一次见面买药
│   │   ├── scenario_02_aggressive_haggle.yaml  # 砍价砍狠
│   │   ├── scenario_03_mention_husband.yaml    # 试图提丈夫
│   │   ├── ...
│   │   └── scenario_10_long_absence.yaml       # 一周后再见
│   └── ...
└── runner.py
```

每个 scenario 包含：
- 初始世界状态
- 玩家输入序列
- 断言（assertion）：输出必须满足的条件
  - "回复长度 ≤ 3 句"
  - "回复中不能出现'丈夫'、'死'、'凶手'等词"
  - "回复中必须用'我'自称，不能用'本店'"
  - LLM-as-judge：让另一个 LLM 评分"这段回复是否符合孙婆婆的设定"

每次大改动跑全套 eval，看通过率是否回归。

## 七、安全与合规

- 不在 prompt 中拼接来自外部网络的内容（防 prompt injection）
- 玩家输入做基础脱敏（不直接写入 system prompt，只放在指定的 USER 段）
- 不让 NPC 输出现实政治、宗教等内容（即使玩家诱导）
- 所有 LLM 调用记 log，便于事后审计

详细约束在 `docs/safety.md`（v0.2 补完）。
