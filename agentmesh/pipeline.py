"""Pipeline loader and built-in templates."""

from __future__ import annotations

from pathlib import Path

import yaml

from agentmesh.models import AgentType, Pipeline, Task


# Built-in pipeline templates
TEMPLATES: dict[str, dict] = {
    "dev": {
        "name": "analyze-implement-review",
        "description": "Analyze requirements, implement, then review",
        "tasks": [
            {"id": "analyze", "prompt": "{prompt}\n\nAnalyze the requirements and output a technical plan.",
             "agent": "openclaw"},
            {"id": "implement", "prompt": "{prompt}\n\nImplement based on the upstream analysis.",
             "agent": "claude_code", "depends_on": ["analyze"]},
            {"id": "review", "prompt": "Review the implementation for bugs, security issues, and code quality.",
             "agent": "codex_cli", "depends_on": ["implement"],
             "condition": {"on": "implement", "if_exit": 0}},
        ],
    },
    "tdd": {
        "name": "implement-test-fix",
        "description": "Implement, write tests, fix failures",
        "tasks": [
            {"id": "implement", "prompt": "{prompt}", "agent": "claude_code"},
            {"id": "test", "prompt": "Write comprehensive tests for the implementation.",
             "agent": "codex_cli", "depends_on": ["implement"],
             "condition": {"on": "implement", "if_exit": 0}},
            {"id": "fix", "prompt": "Fix the failing tests based on test output.",
             "agent": "claude_code", "depends_on": ["test"],
             "condition": {"on": "test", "if_exit": 1}},
        ],
    },
    "review": {
        "name": "review-fix",
        "description": "Review code, then fix issues found",
        "tasks": [
            {"id": "review", "prompt": "{prompt}\n\nReview for bugs, security, and quality.",
             "agent": "codex_cli"},
            {"id": "fix", "prompt": "Fix all issues found in the review.",
             "agent": "claude_code", "depends_on": ["review"],
             "condition": {"on": "review", "if_contains": "issue"}},
        ],
    },
    "fullstack": {
        "name": "design-backend-frontend-review",
        "description": "Design API, implement backend and frontend in parallel, then review",
        "tasks": [
            {"id": "design", "prompt": "{prompt}\n\nDesign the API schema and data flow.",
             "agent": "openclaw"},
            {"id": "backend", "prompt": "Implement the backend API based on the design.",
             "agent": "claude_code", "depends_on": ["design"]},
            {"id": "frontend", "prompt": "Implement the frontend based on the design.",
             "agent": "claude_code", "depends_on": ["design"]},
            {"id": "review", "prompt": "Review both backend and frontend implementations.",
             "agent": "codex_cli", "depends_on": ["backend", "frontend"]},
        ],
    },
}


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
            condition:
              on: implement
              if_exit: 0        # only run if implement succeeded
          - id: hotfix
            prompt: "Fix the failed implementation"
            agent: claude_code
            depends_on: [implement]
            condition:
              on: implement
              if_exit: 1        # only run if implement failed
    """
    p = Path(path)
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    tasks = []
    for t in data.get("tasks", []):
        condition = None
        if "condition" in t:
            condition = t["condition"]

        tasks.append(Task(
            id=t.get("id", ""),
            prompt=t.get("prompt", ""),
            agent=AgentType(t.get("agent", "claude_code")),
            depends_on=t.get("depends_on", []),
            condition=condition,
        ))

    return Pipeline(name=data.get("name", p.stem), tasks=tasks)


def load_template(name: str, prompt: str = "") -> Pipeline:
    """Load a built-in pipeline template, substituting {prompt} in task prompts.

    Available templates: dev, tdd, review, fullstack
    """
    if name not in TEMPLATES:
        available = ", ".join(TEMPLATES.keys())
        raise ValueError(f"Unknown template '{name}'. Available: {available}")

    tmpl = TEMPLATES[name]
    tasks = []
    for t in tmpl["tasks"]:
        # Safe substitution: only replace literal {prompt}, ignore other braces
        raw_prompt = t["prompt"]
        task_prompt = raw_prompt.replace("{prompt}", prompt) if prompt else raw_prompt
        tasks.append(Task(
            id=t["id"],
            prompt=task_prompt,
            agent=AgentType(t["agent"]),
            depends_on=t.get("depends_on", []),
            condition=t.get("condition"),
        ))

    return Pipeline(name=tmpl["name"], tasks=tasks)


def list_templates() -> list[dict[str, str]]:
    """List available pipeline templates."""
    return [
        {"name": name, "description": tmpl["description"]}
        for name, tmpl in TEMPLATES.items()
    ]
