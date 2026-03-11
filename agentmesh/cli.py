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
@click.option("--explain", "-e", is_flag=True, help="Show routing decision")
@click.pass_context
def run(ctx, prompt, agent, project, explain):
    """Run a task on an agent."""
    config = ctx.obj["config"]
    adapters = get_all_adapters(config)
    context_builder = ContextBuilder(
        ai_dir=config["context"]["ai_dir"],
        project=project,
    )
    router = Router(config.get("router", {}))
    scheduler = Scheduler(adapters, context_builder, project=project)

    target = router.route(prompt, explicit_agent=agent)
    if explain:
        console.print(f"[dim]{router.explain(prompt)}[/dim]")
    console.print(f"[dim]Routing to {target.value}...[/dim]")

    result = asyncio.run(scheduler.run_single(prompt, target))

    if result.exit_code == 0:
        console.print(result.output)
    else:
        console.print(f"[red]Agent failed (exit={result.exit_code})[/red]")
        console.print(result.output)
    console.print(f"[dim]Duration: {result.duration:.1f}s[/dim]")


@main.command()
@click.argument("pipeline_file", type=click.Path(exists=True))
@click.option("--project", "-p", default=None, help="Project name for warm context")
@click.pass_context
def pipeline(ctx, pipeline_file, project):
    """Execute a pipeline from a YAML file."""
    from agentmesh.pipeline import load_pipeline

    config = ctx.obj["config"]
    adapters = get_all_adapters(config)
    context_builder = ContextBuilder(
        ai_dir=config["context"]["ai_dir"],
        project=project,
    )
    scheduler = Scheduler(adapters, context_builder, project=project)
    pipe = load_pipeline(pipeline_file)

    console.print(f"[bold]Pipeline: {pipe.name}[/bold]")
    console.print(f"[dim]Tasks: {len(pipe.tasks)}[/dim]")

    results = asyncio.run(scheduler.run_pipeline(pipe))

    table = Table(title="Pipeline Results")
    table.add_column("Task", style="cyan")
    table.add_column("Agent")
    table.add_column("Exit")
    table.add_column("Duration")
    table.add_column("Output", max_width=60)

    for task, result in zip(pipe.tasks, results):
        exit_style = "green" if result.exit_code == 0 else "red"
        table.add_row(
            task.id,
            result.agent.value,
            f"[{exit_style}]{result.exit_code}[/{exit_style}]",
            f"{result.duration:.1f}s",
            result.output[:60].replace("\n", " "),
        )
    console.print(table)


@main.command()
@click.option("--agent", "-a", default=None, help="Lock to a specific agent")
@click.option("--project", "-p", default=None, help="Project name for warm context")
@click.pass_context
def chat(ctx, agent, project):
    """Interactive chat mode (REPL).

    Commands inside chat:
      /agent <name>   - switch agent (claude_code, codex_cli, openclaw)
      /auto            - switch back to auto-routing
      /status          - show agent health
      /history         - show session history
      /pipeline <file> - run a pipeline file
      /exit            - quit
    """
    config = ctx.obj["config"]
    adapters = get_all_adapters(config)
    context_builder = ContextBuilder(
        ai_dir=config["context"]["ai_dir"],
        project=project,
    )
    router = Router(config.get("router", {}))
    scheduler = Scheduler(adapters, context_builder, project=project)

    locked_agent = agent
    history: list[tuple[str, str, str]] = []  # (agent, prompt, output_preview)

    console.print("[bold]agentmesh chat[/bold] - type /exit to quit")
    if locked_agent:
        console.print(f"[dim]Locked to: {locked_agent}[/dim]")
    else:
        console.print("[dim]Auto-routing enabled[/dim]")

    while True:
        try:
            prompt = console.input("[bold cyan]> [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not prompt:
            continue

        # Handle slash commands
        if prompt.startswith("/"):
            if _handle_chat_cmd(prompt, adapters, history, console, locked_agent) == "exit":
                break
            if prompt.startswith("/agent "):
                locked_agent = prompt.split(None, 1)[1].strip()
                console.print(f"[dim]Switched to: {locked_agent}[/dim]")
            elif prompt == "/auto":
                locked_agent = None
                console.print("[dim]Auto-routing enabled[/dim]")
            continue

        target = router.route(prompt, explicit_agent=locked_agent)
        console.print(f"[dim]-> {target.value}[/dim]")

        try:
            result = asyncio.run(scheduler.run_single(prompt, target))
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            continue

        if result.exit_code == 0:
            console.print(result.output)
        else:
            console.print(f"[red]Failed (exit={result.exit_code})[/red]")
            console.print(result.output)
        console.print(f"[dim]{result.duration:.1f}s[/dim]")

        history.append((target.value, prompt, result.output[:100]))

    console.print("[dim]Bye[/dim]")


def _handle_chat_cmd(cmd, adapters, history, con, locked_agent) -> str | None:
    """Handle chat slash commands. Returns 'exit' to quit."""
    if cmd in ("/exit", "/quit", "/q"):
        return "exit"

    if cmd == "/status":
        async def _check():
            for at, ad in adapters.items():
                ok = await ad.health_check()
                s = "[green]OK[/green]" if ok else "[red]DOWN[/red]"
                con.print(f"  {at.value}: {s}")
        asyncio.run(_check())
        return None

    if cmd == "/history":
        if not history:
            con.print("[dim]No history yet[/dim]")
        else:
            for i, (ag, pr, out) in enumerate(history, 1):
                con.print(f"  {i}. [{ag}] {pr[:50]} -> {out[:40]}")
        return None

    if cmd.startswith("/pipeline "):
        filepath = cmd.split(None, 1)[1].strip()
        con.print(f"[dim]Use: agentmesh pipeline {filepath}[/dim]")
        return None

    if not cmd.startswith("/agent ") and cmd != "/auto":
        con.print(f"[dim]Unknown command: {cmd}[/dim]")

    return None


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

    profile = ai_dir / "profile.md"
    if not profile.exists():
        profile.write_text("# Profile\n\n- Language: zh-CN\n- Stack: Go, Python\n", "utf-8")
        console.print(f"Created {profile}")

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

    for e in entries[-20:]:
        exit_style = "green" if e["exit_code"] == 0 else "red"
        table.add_row(
            e["ts"][:19],
            e["agent"],
            f"{e['duration']}s",
            f"[{exit_style}]{e['exit_code']}[/{exit_style}]",
            e.get("prompt_preview", "")[:40],
        )
    console.print(table)


@main.command()
@click.option("--count", "-n", default=20, help="Number of entries to show")
@click.pass_context
def memory(ctx, count):
    """Show auto-recorded memory entries."""
    from agentmesh.memory import load_recent_memory

    entries = load_recent_memory(count)
    if not entries:
        console.print("[dim]No memory entries yet[/dim]")
        return

    table = Table(title=f"Memory (last {len(entries)} entries)")
    table.add_column("Time", style="dim")
    table.add_column("Agent", style="cyan")
    table.add_column("Kind")
    table.add_column("Tags")
    table.add_column("Content", max_width=50)

    for e in entries:
        table.add_row(
            e.get("ts", "")[:19],
            e.get("agent", ""),
            e.get("kind", ""),
            ", ".join(e.get("tags", [])),
            e.get("content", "")[:50],
        )
    console.print(table)


if __name__ == "__main__":
    main()