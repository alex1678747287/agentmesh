"""CLI entry point for agentmesh."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from agentmesh.adapters import get_all_adapters
from agentmesh.config import load_config
from agentmesh.context import ContextBuilder
from agentmesh.models import AgentType
from agentmesh.router import Router
from agentmesh.scheduler import Scheduler

console = Console()


def _find_config() -> Path | None:
    """Search for config.yaml in cwd and parents."""
    for name in ("agentmesh.yaml", "agentmesh.yml", "config.yaml"):
        p = Path.cwd() / name
        if p.exists():
            return p
    return None


@click.group()
@click.option("--config", "-c", type=click.Path(), default=None, help="Config file path")
@click.pass_context
def main(ctx, config):
    """agentmesh - Multi AI agent collaboration hub."""
    ctx.ensure_object(dict)
    config_path = config or _find_config()
    ctx.obj["config"] = load_config(config_path)


@main.command()
@click.argument("prompt")
@click.option("--agent", "-a", type=click.Choice(["claude_code", "codex_cli", "openclaw"]))
@click.option("--project", "-p", default=None, help="Project name for warm context")
@click.pass_context
def run(ctx, prompt, agent, project):
    """Run a task on an agent."""
    config = ctx.obj["config"]
    adapters = get_all_adapters(config)
    context_builder = ContextBuilder(
        ai_dir=config["context"]["ai_dir"],
        project=project,
    )
    router = Router(config.get("router", {}))
    scheduler = Scheduler(adapters, context_builder)

    target = router.route(prompt, explicit_agent=agent)
    console.print(f"[dim]Routing to {target.value}...[/dim]")

    result = asyncio.run(scheduler.run_single(prompt, target))

    if result.exit_code == 0:
        console.print(result.output)
    else:
        console.print(f"[red]Agent failed (exit={result.exit_code})[/red]")
        console.print(result.output)
    console.print(f"[dim]Duration: {result.duration:.1f}s[/dim]")


@main.command()
@click.pass_context
def status(ctx):
    """Check health of all agents."""
    config = ctx.obj["config"]
    adapters = get_all_adapters(config)

    table = Table(title="Agent Status")
    table.add_column("Agent", style="cyan")
    table.add_column("Status")

    async def check_all():
        for agent_type, adapter in adapters.items():
            ok = await adapter.health_check()
            status_str = "[green]OK[/green]" if ok else "[red]DOWN[/red]"
            table.add_row(agent_type.value, status_str)

    asyncio.run(check_all())
    console.print(table)


@main.command()
@click.option("--project", "-p", default=None)
@click.pass_context
def init(ctx, project):
    """Initialize .ai/ directory structure."""
    ai_dir = Path(ctx.obj["config"]["context"]["ai_dir"])
    ai_dir.mkdir(exist_ok=True)
    (ai_dir / "projects").mkdir(exist_ok=True)

    # Create profile.md if not exists
    profile = ai_dir / "profile.md"
    if not profile.exists():
        profile.write_text("# Profile\n\n- Language: zh-CN\n- Stack: Go, Python\n", "utf-8")
        console.print(f"Created {profile}")

    # Create rules.md if not exists
    rules = ai_dir / "rules.md"
    if not rules.exists():
        rules.write_text("# Rules\n\n- Code comments in English\n- Keep it simple\n", "utf-8")
        console.print(f"Created {rules}")

    if project:
        proj_file = ai_dir / "projects" / f"{project}.md"
        if not proj_file.exists():
            proj_file.write_text(f"# {project}\n\n", "utf-8")
            console.print(f"Created {proj_file}")

    console.print("[green]Initialized .ai/ directory[/green]")


@main.command()
@click.option("--dir", "-d", default=".", help="Project directory to sync")
@click.pass_context
def sync(ctx, dir):
    """Sync .ai/ context to CLAUDE.md and AGENTS.md."""
    from agentmesh.sync import sync_all

    ai_dir = ctx.obj["config"]["context"]["ai_dir"]
    project_dir = Path(dir)
    sync_all(ai_dir=project_dir / ai_dir, project_dir=project_dir)
    console.print(f"[green]Synced .ai/ to CLAUDE.md and AGENTS.md in {project_dir}[/green]")


@main.command()
@click.option("--days", "-d", default=7, help="Number of days to show")
@click.option("--agent", "-a", default=None, help="Filter by agent")
@click.pass_context
def log(ctx, days, agent):
    """Show execution logs."""
    from agentmesh.logger import read_logs

    entries = read_logs(days=days, agent=agent)
    if not entries:
        console.print("[dim]No logs found[/dim]")
        return

    table = Table(title=f"Execution Log (last {days} days)")
    table.add_column("Time", style="dim")
    table.add_column("Agent", style="cyan")
    table.add_column("Duration")
    table.add_column("Exit")
    table.add_column("Prompt", max_width=40)

    for e in entries[-20:]:  # show last 20
        exit_style = "green" if e["exit_code"] == 0 else "red"
        table.add_row(
            e["ts"][:19],
            e["agent"],
            f"{e['duration']}s",
            f"[{exit_style}]{e['exit_code']}[/{exit_style}]",
            e.get("prompt_preview", "")[:40],
        )
    console.print(table)


if __name__ == "__main__":
    main()
