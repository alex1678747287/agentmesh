# agentmesh

Multi AI agent collaboration hub. Unified context, memory and orchestration for Claude Code, Codex CLI and OpenClaw.

## Problem

Using multiple AI coding agents (Claude Code, Codex CLI, OpenClaw) means:
- Rules duplicated across CLAUDE.md, AGENTS.md, and OpenClaw config
- Memory isolated in each agent's private store
- Manual copy-paste to coordinate between agents
- No automated handoff of work products

## Solution

agentmesh provides:
- **Shared context layer** (`.ai/` directory) - single source of truth for rules, profile, and project context
- **Agent adapters** - unified interface to call any agent
- **Pipeline orchestration** - chain agents with automatic handoff
- **Smart routing** - auto-select the best agent for each task
- **Three-tier memory** - hot (always loaded), warm (per-project), cold (on-demand search)

## Quick Start

```bash
pip install agentmesh
```

Initialize shared context in your project:

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

Run a task (auto-routed to best agent):

```bash
agentmesh run "implement user login with JWT"
```

Run on a specific agent:

```bash
agentmesh run --agent codex_cli "review auth module"
```

Check agent health:

```bash
agentmesh status
```

## Architecture

```
┌──────────────────────────────────────────┐
│              agentmesh CLI               │
├──────────┬───────────┬───────────────────┤
│  Router  │ Scheduler │ Context Builder   │
├──────────┴───────────┴───────────────────┤
│            Adapter Layer                 │
├────────────┬────────────┬────────────────┤
│ Claude Code│ Codex CLI  │   OpenClaw     │
│  (claude)  │  (codex)   │  (openclaw)    │
└────────────┴────────────┴────────────────┘
                  │
          .ai/ shared context
```

## Pipeline Example

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

Tasks with `depends_on` wait for upstream tasks. Upstream output is automatically injected as context.

## OpenClaw Integration

Copy the skill to your OpenClaw skills directory:

```bash
cp -r skills/agentmesh ~/.openclaw/workspace/skills/
```

Then from OpenClaw you can say: "dispatch to claude code: fix the login bug"

## Configuration

Copy `config.example.yaml` to `agentmesh.yaml` in your project root. See the file for all options.

## Three-Tier Memory

| Tier | What | When loaded | Token cost |
|------|------|-------------|------------|
| Hot | profile.md + rules.md | Every call | ~200 |
| Warm | projects/{name}.md | With --project flag | ~500 |
| Cold | MCP memory search | On demand | Variable |

## License

MIT
