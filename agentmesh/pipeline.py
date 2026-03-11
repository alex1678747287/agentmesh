"""Pipeline loader - parse YAML pipeline definitions."""

from __future__ import annotations

from pathlib import Path

import yaml

from agentmesh.models import AgentType, Pipeline, Task


def load_pipeline(path: str | Path) -> Pipeline:
    """Load a pipeline from a YAML file.

    Format:
        name: my-pipeline
        tasks:
          - id: analyze
            prompt: "Analyze the codebase structure"
            agent: openclaw
          - id: implement
            prompt: "Implement the feature based on analysis"
            agent: claude_code
            depends_on: [analyze]
          - id: review
            prompt: "Review the implementation"
            agent: codex_cli
            depends_on: [implement]
    """
    p = Path(path)
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    tasks = []
    for t in data.get("tasks", []):
        tasks.append(Task(
            id=t.get("id", ""),
            prompt=t.get("prompt", ""),
            agent=AgentType(t.get("agent", "claude_code")),
            depends_on=t.get("depends_on", []),
        ))

    return Pipeline(name=data.get("name", p.stem), tasks=tasks)
