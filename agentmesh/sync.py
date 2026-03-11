"""Sync shared .ai/ context to each agent's native config format."""

from __future__ import annotations

from pathlib import Path

MARKER = "<!-- agentmesh-managed -->"

COLLAB_INSTRUCTIONS = """
# AgentMesh Collaboration

You are part of a multi-agent system managed by agentmesh.
When a task is better suited for another agent, use agentmesh to dispatch it.

## Available Commands

```bash
# Run a task on a specific agent
agentmesh run --agent claude_code "implement user login"
agentmesh run --agent codex_cli "review auth module"
agentmesh run --agent openclaw "analyze project architecture"

# Auto-route (agentmesh picks the best agent)
agentmesh run "fix the null pointer bug"

# Run a multi-step pipeline
agentmesh pipeline pipeline.yaml

# Check which agents are online
agentmesh status
```

## When to Dispatch

- You need code review -> dispatch to codex_cli
- You need implementation -> dispatch to claude_code
- You need analysis/planning -> dispatch to openclaw
- Complex task needs multiple agents -> use pipeline

## Shared Context

All agents share context via `.ai/` directory:
- `.ai/profile.md` - user preferences
- `.ai/rules.md` - coding rules
- `.ai/projects/{name}.md` - project-specific context
""".strip()


def sync_all(ai_dir: str | Path = ".ai", project_dir: str | Path = "."):
    """Sync .ai/ content to CLAUDE.md and AGENTS.md."""
    ai_dir = Path(ai_dir)
    project_dir = Path(project_dir)
    if not ai_dir.exists():
        return

    sync_claude_md(ai_dir, project_dir)
    sync_agents_md(ai_dir, project_dir)


def sync_claude_md(ai_dir: Path, project_dir: Path):
    """Ensure CLAUDE.md includes .ai/ references."""
    claude_md = project_dir / "CLAUDE.md"
    block = _build_include_block(ai_dir)

    if claude_md.exists():
        content = claude_md.read_text("utf-8")
        if MARKER in content:
            # Replace existing managed block
            content = _replace_managed_block(content, block)
        else:
            content = block + "\n\n" + content
        claude_md.write_text(content, "utf-8")
    else:
        claude_md.write_text(block + "\n", "utf-8")


def sync_agents_md(ai_dir: Path, project_dir: Path):
    """Ensure AGENTS.md includes .ai/ references."""
    agents_md = project_dir / "AGENTS.md"
    block = _build_include_block(ai_dir)

    if agents_md.exists():
        content = agents_md.read_text("utf-8")
        if MARKER in content:
            content = _replace_managed_block(content, block)
        else:
            content = block + "\n\n" + content
        agents_md.write_text(content, "utf-8")
    else:
        agents_md.write_text(block + "\n", "utf-8")


def _build_include_block(ai_dir: Path) -> str:
    """Build the managed block content from .ai/ files."""
    parts = [MARKER]

    # Read and inline profile
    profile = ai_dir / "profile.md"
    if profile.exists():
        parts.append(profile.read_text("utf-8").strip())

    # Read and inline rules
    rules = ai_dir / "rules.md"
    if rules.exists():
        parts.append(rules.read_text("utf-8").strip())

    # Add collaboration instructions
    parts.append(COLLAB_INSTRUCTIONS)

    parts.append(MARKER)
    return "\n\n".join(parts)


def _replace_managed_block(content: str, new_block: str) -> str:
    """Replace the managed block in existing content."""
    start = content.find(MARKER)
    end = content.find(MARKER, start + len(MARKER))
    if start == -1 or end == -1:
        return content
    end += len(MARKER)
    return content[:start] + new_block + content[end:]
