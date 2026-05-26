# 武林 MUD · wulin-mud

> 一个验证 AI Native 游戏世界设计哲学的最小可玩原型。
> A minimal playable prototype validating the AI-Native game world design philosophy.

---

## 🇨🇳 中文

### 这是什么

**武林 MUD** 是一个纯文字 MUD 风格的武侠小镇模拟器。它不是一个普通的 LLM 聊天 demo，而是一个用来验证一个具体论点的工程实验：

> **游戏世界的"鲜活感"不来自 LLM 的生成能力，而来自一个结构化、可治理、可演化的世界状态层。LLM 的正确位置是世界状态与玩家体验之间的实时解释器，而不是世界状态本身的来源。**

这个论点的工程对应物，是把企业级数据治理架构（具体参考 Palantir 的 Ontology 模型）移植到游戏世界设计中。详见 [`docs/architecture.md`](docs/architecture.md)。

### 场景设定

清河镇 —— 一个架空唐风的水陆码头小镇。地处官道分支，是去往京畿和西域商道的中转点。表面是个普通的商旅落脚地，水面下是三股暗中博弈的江湖势力。镇上 15 名有名有姓的常驻 NPC，每人有完整的人设、记忆、关系网和秘密。

详见 [`docs/world-setting.md`](docs/world-setting.md)。

### 当前阶段目标（v0.1）

**只验证一件事**：让玩家在与同一个 NPC 反复交互 10 次以上后，依然能感受到这是一个有连贯记忆、稳定人设、合理情绪演化的"真实存在的人"。

**不验证的事**（留给后续版本）：
- 派系联动与因果传导（v0.2）
- 玩家行为对世界历史的沉淀（v0.3）
- 多人协同（v1.0+）

### 快速开始

```bash
# 1. 克隆并进入
git clone https://github.com/bitcowboy/wulin-mud.git && cd wulin-mud

# 2. 安装依赖（需要 Python 3.11+）
pip install -e ".[dev]"

# 3. 配置 LLM API
cp .env.example .env
# 编辑 .env，填入你的 OPENAI_API_KEY

# 4. 初始化世界数据
python -m wulin_mud.scripts.seed_world

# 5. 启动 CLI
python -m wulin_mud
```

进入游戏后，你会被空降到清河镇的码头。试着走进回春堂，跟孙婆婆聊聊。

### 项目结构

```
wulin-mud/
├── docs/                    # 设计文档
│   ├── architecture.md      # 整体架构与设计哲学
│   ├── ontology.md          # 数据模型规范
│   ├── action-types.md      # Action 系统设计
│   ├── npc-spec.md          # NPC 规范 + 孙婆婆种子
│   ├── llm-integration.md   # LLM 调用与 prompt 约束
│   ├── world-setting.md     # 清河镇世界观
│   └── roadmap.md           # 分阶段路线图
├── wulin_mud/
│   ├── ontology/            # Object Types, Link Types 定义
│   ├── actions/             # Action Type 注册表与执行器
│   ├── llm/                 # LLM 调用层与 prompt 模板
│   ├── world/               # 世界 tick 与状态管理
│   ├── core/                # 核心数据结构
│   └── cli/                 # 命令行交互
├── tests/
└── scripts/
    └── seed_world.py        # 世界初始数据种子
```

### 设计原则（必读）

如果你打算给这个项目贡献代码，先读这三件事：

1. **LLM 永远不写世界状态**。所有写入必须经过 Action Type，否则世界会漂移。
2. **NPC 的记忆是结构化的，不是 prompt 拼接出来的**。Memory 是一等公民对象。
3. **先做对，再做快**。这个项目的价值是验证架构，不是炫技。

详见 [`docs/architecture.md`](docs/architecture.md) 第三节"工程红线"。

### License

MIT

---

## 🇬🇧 English

### What this is

**wulin-mud** is a text-based MUD-style simulation of a wuxia (Chinese martial-arts) town. It is not a typical LLM chatbot demo — it is an engineering experiment designed to validate a specific thesis:

> **The "liveness" of a game world does not come from the LLM's generative capability, but from a structured, governable, evolvable world-state layer. The LLM's correct role is as a real-time interpreter between world state and player experience, not as the source of world state itself.**

The engineering analog of this thesis is porting enterprise-grade data governance architecture (specifically, Palantir's Ontology model) into game world design. See [`docs/architecture.md`](docs/architecture.md).

### Setting

**Qinghe Town** — a fictional Tang-style river-port town located at the fork of an imperial road, serving as a transit hub between the capital and the Western trade routes. On the surface, an ordinary town for merchants and travelers; beneath the surface, three covert factions probe each other through proxies. Fifteen named residents, each with a complete personality, memory store, relationship network, and a secret.

See [`docs/world-setting.md`](docs/world-setting.md).

### v0.1 goal

**Validate one thing**: after 10+ interactions with the same NPC, the player should still perceive a coherent person — consistent personality, continuous memory, plausibly evolving emotional state.

**Out of scope for v0.1**:
- Faction propagation & causal chains (v0.2)
- Player-action sedimentation into world history (v0.3)
- Multiplayer (v1.0+)

### Quick start

```bash
git clone https://github.com/bitcowboy/wulin-mud.git && cd wulin-mud
pip install -e ".[dev]"
cp .env.example .env  # set OPENAI_API_KEY
python -m wulin_mud.scripts.seed_world
python -m wulin_mud
```

You will start at Qinghe Town's pier. Try walking into Huichun Pharmacy and talking to Granny Sun.

### Design principles (required reading before contributing)

1. **The LLM never writes world state.** All mutations go through Action Types, or the world will drift.
2. **NPC memory is structured, not a prompt-concat trick.** `Memory` is a first-class object.
3. **Correctness first, speed second.** This project's value is architectural validation, not feature breadth.

See [`docs/architecture.md`](docs/architecture.md) section 3, "Engineering Red Lines".

### License

MIT
