---
name: agentmesh
description: Multi-agent orchestration skill. Dispatch tasks to Claude Code or Codex CLI, share context and memory across agents. Triggers on "dispatch to claude", "codex review", "multi-agent", "agentmesh run", "pipeline".
version: 0.2.0
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

### 4) Run a pipeline

Execute a multi-step workflow defined in YAML:

```bash
agentmesh pipeline pipeline.yaml
```

Pipeline YAML format:
```yaml
name: feature-pipeline
tasks:
  - id: analyze
    prompt: "Analyze the codebase"
    agent: openclaw
  - id: implement
    prompt: "Implement the feature"
    agent: claude_code
    depends_on: [analyze]
  - id: review
    prompt: "Review the code"
    agent: codex_cli
    depends_on: [implement]
```

### 5) Interactive chat mode

Start a REPL session with agent switching:

```bash
agentmesh chat
agentmesh chat --agent claude_code  # lock to specific agent
```

Chat commands: `/agent <name>`, `/auto`, `/status`, `/history`, `/exit`

### 6) Check agent status

```bash
agentmesh status
```

## Routing Rules

- "review", "audit", "check", "审查" -> Codex CLI
- "implement", "write", "fix", "实现", "修复" -> Claude Code
- "analyze", "plan", "design", "分析", "设计" -> OpenClaw (self)
- "test", "spec", "测试" -> Codex CLI
- "deploy", "devops", "部署" -> OpenClaw (self)

## When to Dispatch

If the current task is better handled by another agent, dispatch it:
- Need code implementation? -> `agentmesh run --agent claude_code "..."`
- Need code review? -> `agentmesh run --agent codex_cli "..."`
- Multi-step workflow? -> create a pipeline YAML and run it

## Context

AgentMesh reads `.ai/` directory for shared context:
- `.ai/profile.md` - user preferences (always loaded)
- `.ai/rules.md` - coding rules (always loaded)
- `.ai/projects/{name}.md` - project-specific context (loaded with --project flag)
