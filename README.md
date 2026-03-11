# agentmesh

[English](#english) | [中文](#中文)

---

<a id="english"></a>

## English

Multi AI agent collaboration hub. Unified context, memory and orchestration for Claude Code, Codex CLI and OpenClaw.

### Problem

Using multiple AI coding agents means:
- Rules duplicated across CLAUDE.md, AGENTS.md, and OpenClaw config
- Memory isolated in each agent's private store
- Manual copy-paste to coordinate between agents
- No automated handoff of work products

### Solution

agentmesh provides:
- **Shared context layer** (`.ai/` directory) - single source of truth
- **Agent adapters** - unified interface to call any agent
- **Pipeline orchestration** - chain agents with automatic handoff
- **Smart routing** - auto-select the best agent for each task
- **Three-tier memory** - hot (always loaded), warm (per-project), cold (on-demand)

### Quick Start

```bash
pip install agentmesh
```

Initialize shared context:

```bash
cd your-project
agentmesh init --project myproject
```

This creates:

```
.ai/
├── profile.md          # Your preferences (always loaded)
├── rules.md            # Coding rules (always loaded)
└── projects/
    └── myproject.md    # Project-specific context
```

### Usage

```bash
# Auto-route task to best agent
agentmesh run "implement user login with JWT"

# Specify agent
agentmesh run --agent codex_cli "review auth module"

# Sync .ai/ to CLAUDE.md and AGENTS.md
agentmesh sync

# Check agent health
agentmesh status

# View execution logs
agentmesh log
```

### Architecture

```
┌──────────────────────────────────────────┐
│              agentmesh CLI               │
├──────────┬───────────┬───────────────────┤
│  Router  │ Scheduler │ Context Builder   │
├──────────┴───────────┴───────────────────┤
│            Adapter Layer                 │
├────────────┬────────────┬────────────────┤
│ Claude Code│ Codex CLI  │   OpenClaw     │
└────────────┴────────────┴────────────────┘
                  │
          .ai/ shared context
```

### Pipeline

```python
from agentmesh.models import AgentType, Pipeline, Task

pipeline = Pipeline(
    name="implement-and-review",
    tasks=[
        Task(id="impl", prompt="Implement /api/health endpoint",
             agent=AgentType.CLAUDE_CODE),
        Task(id="review", prompt="Review for security issues",
             agent=AgentType.CODEX_CLI, depends_on=["impl"]),
    ],
)
```

Tasks with `depends_on` wait for upstream completion. Upstream output is automatically injected as context.

### Three-Tier Memory

| Tier | Content | When Loaded | Token Cost |
|------|---------|-------------|------------|
| Hot | profile.md + rules.md | Every call | ~200 |
| Warm | projects/{name}.md | With --project | ~500 |
| Cold | MCP memory search | On demand | Variable |

### OpenClaw Integration

```bash
cp -r skills/agentmesh ~/.openclaw/skills/
```

### Configuration

Copy `config.example.yaml` to `agentmesh.yaml`. See the file for all options.

---

<a id="中文"></a>

## 中文

多 AI Agent 协作中枢。为 Claude Code、Codex CLI 和 OpenClaw 提供统一的上下文、记忆和任务编排。

### 痛点

同时使用多个 AI 编程助手意味着：
- 规则分散在 CLAUDE.md、AGENTS.md、OpenClaw 配置中，维护成本高
- 记忆各自隔离，无法互通
- Agent 之间协作靠手动复制粘贴
- 没有自动化的工作交接机制

### 方案

agentmesh 提供：
- **共享上下文层**（`.ai/` 目录）- 唯一的规则和记忆来源
- **Agent 适配器** - 统一接口调用任意 Agent
- **Pipeline 编排** - 串联 Agent，自动传递上下文
- **智能路由** - 根据任务类型自动选择最佳 Agent
- **三层记忆** - 热（每次加载）、温（按项目加载）、冷（按需搜索）

### 快速开始

```bash
pip install agentmesh
```

初始化共享上下文：

```bash
cd your-project
agentmesh init --project myproject
```

生成目录结构：

```
.ai/
├── profile.md          # 用户偏好（每次加载）
├── rules.md            # 编码规范（每次加载）
└── projects/
    └── myproject.md    # 项目上下文（按需加载）
```

### 使用

```bash
# 自动路由到最佳 Agent
agentmesh run "实现用户登录功能"

# 指定 Agent
agentmesh run --agent codex_cli "审查认证模块"

# 同步 .ai/ 到 CLAUDE.md 和 AGENTS.md
agentmesh sync

# 检查 Agent 状态
agentmesh status

# 查看执行日志
agentmesh log
```

### 三层记忆

| 层级 | 内容 | 加载时机 | Token 消耗 |
|------|------|----------|-----------|
| 热 | profile.md + rules.md | 每次调用 | ~200 |
| 温 | projects/{name}.md | 指定 --project 时 | ~500 |
| 冷 | MCP memory 语义搜索 | 按需 | 不定 |

### OpenClaw 集成

```bash
cp -r skills/agentmesh ~/.openclaw/skills/
```

安装后可在 OpenClaw 中直接调度其他 Agent。

### 配置

复制 `config.example.yaml` 为 `agentmesh.yaml`，按需修改。

---

## License

MIT
