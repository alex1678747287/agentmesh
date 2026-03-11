"""Claude Code adapter - calls claude CLI in non-interactive mode."""

from __future__ import annotations

import asyncio
import time

from agentmesh.adapters import BaseAdapter, register_adapter
from agentmesh.models import AgentResult, AgentType


@register_adapter(AgentType.CLAUDE_CODE)
class ClaudeCodeAdapter(BaseAdapter):

    async def execute(self, prompt: str, context: str = "", timeout: int = 300) -> AgentResult:
        full_prompt = self.build_prompt(prompt, context)
        cmd = ["claude", "-p", full_prompt, "--print"]

        max_turns = self.config.get("max_turns", 10)
        cmd.extend(["--max-turns", str(max_turns)])

        if tools := self.config.get("allowed_tools"):
            for t in tools:
                cmd.extend(["--allowedTools", t])

        start = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.config.get("cwd"),
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return AgentResult(
                agent=AgentType.CLAUDE_CODE, task_id="", output="[timeout]",
                exit_code=-1, duration=time.monotonic() - start,
            )

        return AgentResult(
            agent=AgentType.CLAUDE_CODE,
            task_id="",
            output=stdout.decode("utf-8", errors="replace"),
            exit_code=proc.returncode or 0,
            duration=time.monotonic() - start,
        )

    async def health_check(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode == 0
        except Exception:
            return False
