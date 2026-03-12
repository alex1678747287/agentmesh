"""AgentMesh MCP Server - exposes agentmesh as MCP tools.

Allows Claude Code, OpenClaw, and other MCP-compatible agents
to natively call agentmesh for cross-agent dispatch.

Uses FastMCP for Windows-compatible stdio transport.
"""

from __future__ import annotations

import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from agentmesh.config import load_config
from agentmesh.models import AgentType

logger = logging.getLogger(__name__)

mcp = FastMCP("agentmesh")

# Lazy-initialized globals
_initialized = False
_config: dict = {}
_adapters: dict = {}
_router = None
_scheduler = None


def _find_config() -> Path | None:
    for name in ("agentmesh.yaml", "agentmesh.yml", "config.yaml"):
        p = Path.cwd() / name
        if p.exists():
            return p
    return None


def _ensure_init():
    """Lazy init core components on first use."""
    global _initialized, _config, _adapters, _router, _scheduler
    if _initialized:
        return
    try:
        from agentmesh.adapters import get_all_adapters
        from agentmesh.context import ContextBuilder
        from agentmesh.logger import set_ai_dir as set_log_dir
        from agentmesh.memory import set_ai_dir as set_mem_dir
        from agentmesh.router import Router
        from agentmesh.scheduler import Scheduler

        _config = load_config(_find_config())
        ai_dir = _config["context"]["ai_dir"]
        set_mem_dir(ai_dir)
        set_log_dir(ai_dir)
        _adapters = get_all_adapters(_config)
        _router = Router(_config.get("router", {}))
        ctx = ContextBuilder(ai_dir=ai_dir)
        _scheduler = Scheduler(_adapters, ctx, config=_config)
        _initialized = True
    except Exception:
        logger.exception("Failed to initialize agentmesh MCP server")


def _build_for_project(project: str):
    """Build project-scoped adapters, router, scheduler."""
    from agentmesh.adapters import get_all_adapters
    from agentmesh.context import ContextBuilder
    from agentmesh.router import Router
    from agentmesh.scheduler import Scheduler

    proj_config = load_config(_find_config(), project=project)
    proj_adapters = get_all_adapters(proj_config)
    proj_router = Router(proj_config.get("router", {}))
    ctx = ContextBuilder(ai_dir=proj_config["context"]["ai_dir"], project=project)
    scheduler = Scheduler(proj_adapters, ctx, project=project, config=proj_config)
    return proj_router, scheduler


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
    _ensure_init()
    if not _initialized:
        return "Error: agentmesh failed to initialize. Check logs."

    if project:
        router, scheduler = _build_for_project(project)
    else:
        router, scheduler = _router, _scheduler

    target = router.route(prompt) if agent == "auto" else AgentType(agent)

    result = await scheduler.run_single(prompt, target)
    if result.exit_code != 0:
        return f"Error (exit {result.exit_code}): {result.output}"
    return result.output


@mcp.tool()
async def agentmesh_status() -> str:
    """Check which AI agents are currently available/online."""
    _ensure_init()
    if not _initialized:
        return "Error: agentmesh failed to initialize."
    lines = []
    for agent_type, adapter in _adapters.items():
        ok = await adapter.health_check()
        s = "OK" if ok else "DOWN"
        lines.append(f"{agent_type.value}: {s}")
    return "\n".join(lines)


@mcp.tool()
def agentmesh_memory(count: int = 10) -> str:
    """Read recent shared memory entries from cross-agent executions."""
    _ensure_init()
    from agentmesh.memory import load_recent_memory

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
