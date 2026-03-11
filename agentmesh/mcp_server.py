"""AgentMesh MCP Server - exposes agentmesh as MCP tools.

Allows Claude Code, OpenClaw, and other MCP-compatible agents
to natively call agentmesh for cross-agent dispatch.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from agentmesh.adapters import get_all_adapters
from agentmesh.config import load_config
from agentmesh.context import ContextBuilder
from agentmesh.memory import build_memory_context, load_recent_memory
from agentmesh.models import AgentType
from agentmesh.router import Router
from agentmesh.scheduler import Scheduler

# MCP protocol constants
JSONRPC = "2.0"


class MCPServer:
    """Minimal MCP server over stdio (JSON-RPC 2.0)."""

    def __init__(self):
        config = load_config(_find_config())
        self.config = config
        self.adapters = get_all_adapters(config)
        self.router = Router(config.get("router", {}))
        self.context_builder = ContextBuilder(ai_dir=config["context"]["ai_dir"])
        self.scheduler = Scheduler(self.adapters, self.context_builder)

    async def run(self):
        """Read JSON-RPC messages from stdin, write responses to stdout."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)

        writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout.buffer
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

        buf = b""
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                resp = await self._handle(msg)
                if resp:
                    out = json.dumps(resp, ensure_ascii=False) + "\n"
                    writer.write(out.encode("utf-8"))
                    await writer.drain()

    async def _handle(self, msg: dict) -> dict | None:
        method = msg.get("method", "")
        req_id = msg.get("id")

        if method == "initialize":
            return self._resp(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "agentmesh", "version": "0.2.0"},
            })

        if method == "notifications/initialized":
            return None  # no response needed

        if method == "tools/list":
            return self._resp(req_id, {"tools": self._tool_defs()})

        if method == "tools/call":
            params = msg.get("params", {})
            name = params.get("name", "")
            args = params.get("arguments", {})
            result = await self._call_tool(name, args)
            return self._resp(req_id, result)

        # Unknown method
        return {"jsonrpc": JSONRPC, "id": req_id, "error": {
            "code": -32601, "message": f"Unknown method: {method}"
        }}

    def _resp(self, req_id, result):
        return {"jsonrpc": JSONRPC, "id": req_id, "result": result}

    def _tool_defs(self) -> list[dict]:
        return [
            {
                "name": "agentmesh_dispatch",
                "description": (
                    "Dispatch a task to another AI agent. Use this when the current task "
                    "is better suited for a different agent. Agents: claude_code (implementation), "
                    "codex_cli (review/testing), openclaw (analysis/planning). "
                    "Set agent to 'auto' for automatic routing."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Task description"},
                        "agent": {
                            "type": "string",
                            "enum": ["auto", "claude_code", "codex_cli", "openclaw"],
                            "description": "Target agent or 'auto' for smart routing",
                            "default": "auto",
                        },
                        "project": {
                            "type": "string",
                            "description": "Project name for context loading (optional)",
                        },
                    },
                    "required": ["prompt"],
                },
            },
            {
                "name": "agentmesh_status",
                "description": "Check which AI agents are currently available/online.",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "agentmesh_memory",
                "description": "Read recent shared memory entries from cross-agent executions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer", "default": 10, "description": "Number of entries"},
                    },
                },
            },
        ]

    async def _call_tool(self, name: str, args: dict) -> dict:
        try:
            if name == "agentmesh_dispatch":
                return await self._dispatch(args)
            elif name == "agentmesh_status":
                return await self._status()
            elif name == "agentmesh_memory":
                return self._memory(args)
            else:
                return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}

    async def _dispatch(self, args: dict) -> dict:
        prompt = args["prompt"]
        agent_str = args.get("agent", "auto")
        project = args.get("project")

        if project:
            self.context_builder = ContextBuilder(
                ai_dir=self.config["context"]["ai_dir"], project=project
            )
            self.scheduler = Scheduler(self.adapters, self.context_builder, project=project)

        if agent_str == "auto":
            target = self.router.route(prompt)
        else:
            target = AgentType(agent_str)

        # Check availability, fallback if needed
        available = await self._get_available()
        if target not in available:
            # Try fallback
            fallback = self._pick_fallback(target, available)
            if fallback:
                note = f"[{target.value} unavailable, falling back to {fallback.value}]\n"
                target = fallback
            else:
                return {"content": [{"type": "text",
                    "text": f"Agent {target.value} is unavailable and no fallback found."}],
                    "isError": True}
        else:
            note = ""

        result = await self.scheduler.run_single(prompt, target)
        text = note + result.output
        is_err = result.exit_code != 0
        return {"content": [{"type": "text", "text": text}], "isError": is_err}

    async def _status(self) -> dict:
        lines = []
        for agent_type, adapter in self.adapters.items():
            ok = await adapter.health_check()
            s = "OK" if ok else "DOWN"
            lines.append(f"{agent_type.value}: {s}")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    def _memory(self, args: dict) -> dict:
        n = args.get("count", 10)
        entries = load_recent_memory(n)
        if not entries:
            return {"content": [{"type": "text", "text": "No memory entries yet."}]}
        lines = []
        for e in entries:
            tags = ", ".join(e.get("tags", []))
            lines.append(f"[{e.get('ts', '')[:19]}] [{tags}] {e.get('content', '')}")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    async def _get_available(self) -> set[AgentType]:
        available = set()
        for agent_type, adapter in self.adapters.items():
            try:
                if await asyncio.wait_for(adapter.health_check(), timeout=5):
                    available.add(agent_type)
            except Exception:
                pass
        return available

    def _pick_fallback(self, failed: AgentType, available: set[AgentType]) -> AgentType | None:
        """Pick a fallback agent based on capability overlap."""
        fallback_map = {
            AgentType.CLAUDE_CODE: [AgentType.OPENCLAW, AgentType.CODEX_CLI],
            AgentType.CODEX_CLI: [AgentType.CLAUDE_CODE, AgentType.OPENCLAW],
            AgentType.OPENCLAW: [AgentType.CLAUDE_CODE, AgentType.CODEX_CLI],
        }
        for candidate in fallback_map.get(failed, []):
            if candidate in available:
                return candidate
        return None


def _find_config() -> Path | None:
    for name in ("agentmesh.yaml", "agentmesh.yml", "config.yaml"):
        p = Path.cwd() / name
        if p.exists():
            return p
    return None


def main():
    server = MCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()