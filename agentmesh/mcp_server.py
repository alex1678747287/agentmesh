"""AgentMesh MCP Server - exposes agentmesh as MCP tools.

Allows Claude Code, OpenClaw, and other MCP-compatible agents
to natively call agentmesh for cross-agent dispatch.

Uses FastMCP for Windows-compatible stdio transport.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from agentmesh.adapters import get_all_adapters
from agentmesh.config import load_config
from agentmesh.context import ContextBuilder
from agentmesh.memory import load_recent_memory
from agentmesh.models import AgentType
from agentmesh.router import Router
from agentmesh.scheduler import Scheduler


def _find_config() -> Path | None:
    for name in ("agentmesh.yaml", "agentmesh.yml", "config.yaml"):
        p = Path.cwd() / name
        if p.exists():
            return p
    return None


# Init core components (default, no project scope)
_config = load_config(_find_config())
_adapters = get_all_adapters(_config)
_router = Router(_config.get("router", {}))
_default_ctx = ContextBuilder(ai_dir=_config["context"]["ai_dir"])
_scheduler = Scheduler(_adapters, _default_ctx, config=_config)

mcp = FastMCP("agentmesh")


@mcp.tool()
async def agentmesh_dispatch(
    prompt: str,
    agent: str = "auto",
    project: str | None = None,
) -> str:
    """Dispatch a task to another AI agent.

    Use this when the current task is better suited for a different agent.
    Agents: claude_code (implementation), codex_cli (review/testing),
    openclaw (analysis/planning). Set agent to 'auto' for automatic routing.
    """
    if project:
        proj_config = load_config(_find_config(), project=project)
        ctx = ContextBuilder(ai_dir=proj_config["context"]["ai_dir"], project=project)
        scheduler = Scheduler(_adapters, ctx, project=project, config=proj_config)
    else:
        scheduler = _scheduler

    target = _router.route(prompt) if agent == "auto" else AgentType(agent)

    result = await scheduler.run_single(prompt, target)
    if result.exit_code != 0:
        return f"Error (exit {result.exit_code}): {result.output}"
    return result.output


@mcp.tool()
async def agentmesh_status() -> str:
    """Check which AI agents are currently available/online."""
    lines = []
    for agent_type, adapter in _adapters.items():
        ok = await adapter.health_check()
        s = "OK" if ok else "DOWN"
        lines.append(f"{agent_type.value}: {s}")
    return "\n".join(lines)


@mcp.tool()
def agentmesh_memory(count: int = 10) -> str:
    """Read recent shared memory entries from cross-agent executions."""
    entries = load_recent_memory(count)
    if not entries:
        return "No memory entries yet."
    lines = []
    for e in entries:
        tags = ", ".join(e.get("tags", []))
        lines.append(f"[{e.get('ts', '')[:19]}] [{tags}] {e.get('content', '')}")
    return "\n".join(lines)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
