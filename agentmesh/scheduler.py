"""Task scheduler with pipeline support, fallback, and availability checks."""

from __future__ import annotations

import asyncio
import time

from agentmesh.adapters import BaseAdapter
from agentmesh.context import ContextBuilder
from agentmesh.logger import log_result
from agentmesh.memory import record_memory
from agentmesh.models import AgentResult, AgentType, Pipeline, Task, TaskStatus
from agentmesh.validator import validate_output


class Scheduler:
    def __init__(
        self,
        adapters: dict[AgentType, BaseAdapter],
        context_builder: ContextBuilder | None = None,
        project: str | None = None,
        config: dict | None = None,
        health_cache_ttl: int = 10,
    ):
        self.adapters = adapters
        self.context_builder = context_builder
        self.project = project
        self._health_cache: dict[AgentType, bool] = {}
        self._health_ts: float = 0
        self._health_ttl = health_cache_ttl
        self._config = config or {}
        # Load fallback order from config, with sensible defaults
        self._fallback_map = self._build_fallback_map(config)

    def _build_fallback_map(self, config: dict | None) -> dict[AgentType, list[AgentType]]:
        default = {
            AgentType.CLAUDE_CODE: [AgentType.OPENCLAW, AgentType.CODEX_CLI],
            AgentType.CODEX_CLI: [AgentType.CLAUDE_CODE, AgentType.OPENCLAW],
            AgentType.OPENCLAW: [AgentType.CLAUDE_CODE, AgentType.CODEX_CLI],
        }
        if not config or "fallback_order" not in config:
            return default
        result = {}
        for key, candidates in config["fallback_order"].items():
            try:
                agent = AgentType(key)
                result[agent] = [AgentType(c) for c in candidates]
            except ValueError:
                continue
        # Fill in any missing agents with defaults
        for agent in AgentType:
            if agent not in result:
                result[agent] = default.get(agent, [])
        return result

    def _get_timeout(self, agent: AgentType) -> int:
        """Get timeout for an agent from config."""
        agents_cfg = self._config.get("agents", {})
        return agents_cfg.get(agent.value, {}).get("timeout", 300)

    async def check_available(self, force: bool = False) -> set[AgentType]:
        """Check which agents are online. Cached for 30s."""
        now = time.monotonic()
        if not force and self._health_cache and (now - self._health_ts) < self._health_ttl:
            return {a for a, ok in self._health_cache.items() if ok}
        checks = await asyncio.gather(
            *[self._check_one(at, ad) for at, ad in self.adapters.items()],
            return_exceptions=True,
        )
        self._health_cache = {}
        for (at, _), ok in zip(self.adapters.items(), checks):
            self._health_cache[at] = bool(ok) if not isinstance(ok, Exception) else False
        self._health_ts = now
        return {a for a, ok in self._health_cache.items() if ok}

    async def _check_one(self, at: AgentType, ad: BaseAdapter) -> bool:
        try:
            return await asyncio.wait_for(ad.health_check(), timeout=5)
        except Exception:
            return False

    def _pick_fallback(self, target: AgentType, available: set[AgentType]) -> AgentType | None:
        for candidate in self._fallback_map.get(target, []):
            if candidate in available:
                return candidate
        return None

    async def run_single(self, prompt: str, agent: AgentType,
                         timeout: int | None = None) -> AgentResult:
        """Run a single task. Falls back to another agent if target is down."""
        if timeout is None:
            timeout = self._get_timeout(agent)
        available = await self.check_available()
        actual, note = self._resolve_agent(agent, available)
        if actual is None:
            return AgentResult(
                agent=agent, task_id="", exit_code=1, duration=0,
                output="[all agents unavailable]",
            )

        adapter = self.adapters[actual]
        context = self.context_builder.build(prompt=prompt) if self.context_builder else ""
        start = time.monotonic()
        result = await adapter.execute(prompt, context, timeout)
        result.agent = actual
        result.duration = time.monotonic() - start
        if note:
            result.output = note + result.output
        log_result(result, prompt)
        record_memory(result, prompt, self.project)
        # Validate AFTER memory recording so warnings don't pollute memory
        vr = validate_output(result, prompt)
        if vr.warnings:
            result.output += "\n\n[validator] " + "; ".join(vr.warnings)
        return result

    async def run_pipeline(self, pipeline: Pipeline) -> list[AgentResult]:
        """Execute pipeline DAG with conditional branches and fallback."""
        available = await self.check_available()
        completed: dict[str, AgentResult] = {}
        skipped: set[str] = set()
        pending = {t.id: t for t in pipeline.tasks}

        while pending:
            ready = [
                t for t in pending.values()
                if all(dep in completed or dep in skipped for dep in t.depends_on)
            ]
            if not ready:
                raise RuntimeError("Deadlock: unresolvable task dependencies")

            # Phase 1: skip tasks whose conditions are not met
            to_skip = []
            for task in ready:
                if task.condition and not self._check_condition(task, completed):
                    task.status = TaskStatus.DONE
                    task.result = AgentResult(
                        agent=task.agent, task_id=task.id,
                        output="[skipped: condition not met]",
                        exit_code=0, duration=0,
                    )
                    completed[task.id] = task.result
                    skipped.add(task.id)
                    to_skip.append(task.id)
            for tid in to_skip:
                del pending[tid]

            # Re-filter after condition checks
            ready = [
                t for t in pending.values()
                if all(dep in completed or dep in skipped for dep in t.depends_on)
            ]
            if not ready:
                if not pending:
                    break
                raise RuntimeError("Deadlock: unresolvable task dependencies")

            results = await asyncio.gather(
                *[self._run_task(t, completed, available) for t in ready],
                return_exceptions=True,
            )
            for task, result in zip(ready, results):
                if isinstance(result, Exception):
                    task.status = TaskStatus.FAILED
                    task.result = AgentResult(
                        agent=task.agent, task_id=task.id,
                        output=str(result), exit_code=1, duration=0,
                    )
                else:
                    task.result = result
                completed[task.id] = task.result
            for task in ready:
                pending.pop(task.id, None)

        return [t.result for t in pipeline.tasks if t.result]

    def _check_condition(self, task: Task, completed: dict[str, AgentResult]) -> bool:
        """Check if task's condition is met based on upstream results."""
        cond = task.condition
        if not cond:
            return True
        # YAML parses 'on' as True (boolean), handle both
        ref_id = cond.get("on") or cond.get(True, "")
        if not ref_id or ref_id not in completed:
            return False
        ref_result = completed[ref_id]
        if "if_exit" in cond:
            return ref_result.exit_code == cond["if_exit"]
        if "if_contains" in cond:
            return cond["if_contains"].lower() in ref_result.output.lower()
        return True

    async def _run_task(self, task: Task, completed: dict[str, AgentResult],
                        available: set[AgentType]) -> AgentResult:
        actual, note = self._resolve_agent(task.agent, available)
        if actual is None:
            task.status = TaskStatus.FAILED
            return AgentResult(
                agent=task.agent, task_id=task.id,
                output=f"[{task.agent.value} unavailable, skipped]",
                exit_code=1, duration=0,
            )

        adapter = self.adapters[actual]
        task.status = TaskStatus.RUNNING

        context = self.context_builder.build(prompt=task.prompt, level="full") if self.context_builder else ""
        if task.depends_on:
            handoff = []
            for dep_id in task.depends_on:
                dep_result = completed[dep_id]
                handoff.append(
                    f"<upstream task={dep_id}>\n"
                    f"{_summarize_upstream(dep_result.output)}\n"
                    f"</upstream>"
                )
            context += "\n\n" + "\n".join(handoff)

        start = time.monotonic()
        result = await adapter.execute(task.prompt, context)
        result.agent = actual
        result.task_id = task.id
        result.duration = time.monotonic() - start
        if note:
            result.output = note + result.output
        task.status = TaskStatus.DONE if result.exit_code == 0 else TaskStatus.FAILED
        log_result(result, task.prompt)
        record_memory(result, task.prompt, self.project)
        vr = validate_output(result, task.prompt)
        if vr.warnings:
            result.output += "\n\n[validator] " + "; ".join(vr.warnings)
        return result

    def _resolve_agent(self, target: AgentType,
                       available: set[AgentType]) -> tuple[AgentType | None, str]:
        """Resolve target agent with fallback. Returns (agent, note)."""
        if target in available:
            return target, ""
        fb = self._pick_fallback(target, available)
        if fb:
            return fb, f"[{target.value} unavailable, fallback -> {fb.value}]\n"
        if available:
            pick = next(iter(available))
            return pick, f"[{target.value} unavailable, using {pick.value}]\n"
        return None, ""


# Max chars for upstream output passed to downstream tasks
_UPSTREAM_MAX_CHARS = 3000


def _summarize_upstream(output: str) -> str:
    """Truncate/summarize upstream output for downstream context injection."""
    # Strip validator warnings before passing downstream
    if "\n\n[validator]" in output:
        output = output[:output.index("\n\n[validator]")]
    if len(output) <= _UPSTREAM_MAX_CHARS:
        return output
    # Keep first chunk (usually the most important) + last chunk (conclusion)
    head_size = _UPSTREAM_MAX_CHARS * 2 // 3
    tail_size = _UPSTREAM_MAX_CHARS // 3
    head = output[:head_size]
    # Prefer cutting at code fence or blank line boundary
    for boundary in ("\n```\n", "\n\n"):
        idx = head.rfind(boundary)
        if idx > head_size // 2:
            head = head[:idx + len(boundary)]
            break
    else:
        nl = head.rfind("\n")
        if nl > head_size // 2:
            head = head[:nl]
    tail = output[-tail_size:]
    # Start tail at a clean boundary
    for boundary in ("\n```", "\n\n"):
        idx = tail.find(boundary)
        if 0 < idx < tail_size // 3:
            tail = tail[idx:]
            break
    else:
        nl = tail.find("\n")
        if nl > 0:
            tail = tail[nl + 1:]
    omitted = len(output) - len(head) - len(tail)
    return f"{head}\n\n[...{omitted} chars omitted...]\n\n{tail}"
