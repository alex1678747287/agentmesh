"""Data models for agentmesh."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class AgentType(Enum):
    CLAUDE_CODE = "claude_code"
    CODEX_CLI = "codex_cli"
    OPENCLAW = "openclaw"


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class AgentResult:
    agent: AgentType
    task_id: str
    output: str
    exit_code: int
    duration: float
    token_usage: dict | None = None


@dataclass
class Task:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    prompt: str = ""
    agent: AgentType = AgentType.OPENCLAW
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = field(default_factory=list)
    result: AgentResult | None = None
    condition: dict | None = None  # {"on": "task_id", "if_exit": 0}


@dataclass
class Pipeline:
    """A DAG of tasks. Tasks with no depends_on run in parallel."""
    name: str = ""
    tasks: list[Task] = field(default_factory=list)
