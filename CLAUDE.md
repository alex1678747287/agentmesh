<!-- agentmesh-managed -->

# Profile

- Role: Full-stack developer
- Languages: Go, Python, some Android
- Response language: Chinese
- Code comments: English
- No emoji
- Keep it simple, no over-engineering

# Servers

- Alibaba Cloud: 8.140.235.152, root, SSH key auth, CentOS 8 x86_64

# Tools

- Python 3.12 at C:/Users/Admin/AppData/Local/Programs/Python/Python312/python.exe
- paramiko installed for SSH operations
- Project root: D:\project

# Models

- Claude Code: Sonnet 4.6 default, Opus for complex tasks, Haiku for simple
- Codex CLI: GPT-5.4 Thinking default
- OpenClaw: codex/gpt-5.2 primary, multi-model routing

# Rules

- Write minimal code, avoid unnecessary abstractions
- Prefer editing existing files over creating new ones
- Use Go for backend services, Python for scripts and AI tooling
- Vue for frontend when needed
- Code comments in English, responses in Chinese
- Security first: validate inputs, no hardcoded secrets
- Test critical paths, skip trivial tests

# AgentMesh Collaboration

You are part of a multi-agent system managed by agentmesh.
When a task is better suited for another agent, dispatch it via MCP tools or CLI.

## MCP Tools (preferred - native integration)

If agentmesh MCP server is available, use these tools directly:
- `agentmesh_dispatch` - dispatch a task to another agent (auto-routes or specify agent)
- `agentmesh_status` - check which agents are online
- `agentmesh_memory` - read shared memory from cross-agent executions

## CLI Commands (fallback)

```bash
agentmesh run --agent claude_code "implement user login"
agentmesh run --agent codex_cli "review auth module"
agentmesh run --agent openclaw "analyze project architecture"
agentmesh run "fix the null pointer bug"  # auto-route
agentmesh pipeline pipeline.yaml          # multi-step DAG
agentmesh status                          # check agents
```

## When to Dispatch

- Code review/audit -> codex_cli
- Implementation/fix -> claude_code
- Analysis/planning -> openclaw
- Agent unavailable -> agentmesh auto-fallbacks to next best agent

## Shared Context

All agents share context via `.ai/` directory:
- `.ai/profile.md` - user preferences
- `.ai/rules.md` - coding rules
- `.ai/projects/{name}.md` - project-specific context
- `.ai/memory.jsonl` - auto-recorded execution memory

<!-- agentmesh-managed -->
