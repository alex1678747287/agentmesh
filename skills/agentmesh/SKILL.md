---
name: agentmesh
description: Multi-agent orchestration skill. Dispatch tasks to Claude Code or Codex CLI, share context and memory across agents. Triggers on "dispatch to claude", "codex review", "multi-agent", "agentmesh run".
version: 0.1.0
metadata:
  openclaw:
    requires:
      bins:
        - python3
    emoji: "mesh"
---

# AgentMesh - Multi-Agent Orchestration

Dispatch tasks to Claude Code or Codex CLI from within OpenClaw.

## Setup

```bash
pip install agentmesh
agentmesh init
```

## Tasks

### 1) Run a task on Claude Code

When the user wants Claude Code to handle implementation:

```bash
agentmesh run --agent claude_code "implement user login with JWT"
```

### 2) Run a task on Codex CLI

When the user wants Codex to review or generate code:

```bash
agentmesh run --agent codex_cli "review the auth module for security issues"
```

### 3) Auto-route a task

Let agentmesh decide which agent is best:

```bash
agentmesh run "fix the null pointer bug in user service"
```

### 4) Check agent status

```bash
agentmesh status
```

## Routing Rules

- "review", "audit", "check" -> Codex CLI
- "implement", "write", "create", "fix" -> Claude Code
- "analyze", "plan", "design" -> OpenClaw (self)
- "test", "spec" -> Codex CLI
- "deploy", "devops" -> OpenClaw (self)

## Context

AgentMesh reads `.ai/` directory for shared context:
- `.ai/profile.md` - user preferences (always loaded)
- `.ai/rules.md` - coding rules (always loaded)
- `.ai/projects/{name}.md` - project-specific context (loaded with --project flag)
