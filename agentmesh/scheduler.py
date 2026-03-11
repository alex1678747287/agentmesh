"""Task scheduler with pipeline support."""

from __future__ import annotations

import asyncio
import time

from agentmesh.adapters import BaseAdapter
from agentmesh.context import ContextBuilder
from agentmesh.logger import log_result
from agentmesh.models import AgentResult, AgentType, Pipeline, Task, TaskStatus


class Scheduler:
    def __init__(
        self,
        adapters: dict[AgentType, BaseAdapter],
        context_builder: ContextBuilder | None = None,
    ):
        self.adapters = adapters
        self.context_builder = context_builder

    async def run_single(self, prompt: str, agent: AgentType,
                         timeout: int = 300) -> AgentResult:
        """Run a single task on a specific agent."""
        adapter = self.adapters.get(agent)
        if not adapter:
            raise ValueError(f"Agent {agent} not available")

        context = self.context_builder.build() if self.context_builder else ""
        start = time.monotonic()
        result = await adapter.execute(prompt, context, timeout)
        result.duration = time.monotonic() - start
        log_result(result, prompt)
        return result

    async def run_pipeline(self, pipeline: Pipeline) -> list[AgentResult]:
        """Execute pipeline respecting task dependencies (DAG)."""
        completed: dict[str, AgentResult] = {}
        pending = {t.id: t for t in pipeline.tasks}

        while pending:
            # Find tasks whose deps are all satisfied
            ready = [
                t for t in pending.values()
                if all(dep in completed for dep in t.depends_on)
            ]
            if not ready:
                raise RuntimeError("Deadlock: unresolvable task dependencies")

            results = await asyncio.gather(
                *[self._run_task(t, completed) for t in ready],
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
                del pending[task.id]

        return [t.result for t in pipeline.tasks if t.result]

    async def _run_task(self, task: Task,
                        completed: dict[str, AgentResult]) -> AgentResult:
        adapter = self.adapters.get(task.agent)
        if not adapter:
            raise ValueError(f"Agent {task.agent} not available")

        task.status = TaskStatus.RUNNING

        # Build context with handoff from upstream tasks
        context = self.context_builder.build() if self.context_builder else ""
        if task.depends_on:
            handoff = []
            for dep_id in task.depends_on:
                dep_result = completed[dep_id]
                handoff.append(f"<upstream task={dep_id}>\n{dep_result.output}\n</upstream>")
            context += "\n\n" + "\n".join(handoff)

        start = time.monotonic()
        result = await adapter.execute(task.prompt, context)
        result.task_id = task.id
        result.duration = time.monotonic() - start
        task.status = TaskStatus.DONE
        log_result(result, task.prompt)
        return result
