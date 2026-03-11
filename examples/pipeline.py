"""Example: run a multi-step pipeline."""

import asyncio

from agentmesh.adapters import get_all_adapters
from agentmesh.config import load_config
from agentmesh.context import ContextBuilder
from agentmesh.models import AgentType, Pipeline, Task
from agentmesh.scheduler import Scheduler


async def main():
    config = load_config("agentmesh.yaml")
    adapters = get_all_adapters(config)
    ctx = ContextBuilder(ai_dir=".ai", project="meeting")
    scheduler = Scheduler(adapters, ctx)

    # Define a pipeline:
    # 1. Claude Code implements the feature
    # 2. Codex CLI reviews the implementation (depends on step 1)
    pipeline = Pipeline(
        name="implement-and-review",
        tasks=[
            Task(
                id="impl",
                prompt="Implement a /api/health endpoint that returns server status",
                agent=AgentType.CLAUDE_CODE,
            ),
            Task(
                id="review",
                prompt="Review the implementation for security and best practices",
                agent=AgentType.CODEX_CLI,
                depends_on=["impl"],
            ),
        ],
    )

    results = await scheduler.run_pipeline(pipeline)
    for r in results:
        print(f"--- {r.agent.value} ({r.task_id}) [{r.duration:.1f}s] ---")
        print(r.output[:500])


if __name__ == "__main__":
    asyncio.run(main())
