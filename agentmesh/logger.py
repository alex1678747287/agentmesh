"""Execution logger - records agent calls for audit and cost tracking."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agentmesh.models import AgentResult

LOG_DIR = Path(".ai/logs")


def log_result(result: AgentResult, prompt: str = ""):
    """Append an execution record to the log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"{today}.jsonl"

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": result.agent.value,
        "task_id": result.task_id,
        "prompt_preview": prompt[:200] if prompt else "",
        "output_preview": result.output[:200] if result.output else "",
        "exit_code": result.exit_code,
        "duration": round(result.duration, 2),
        "token_usage": result.token_usage,
    }

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_logs(days: int = 7, agent: str | None = None) -> list[dict]:
    """Read recent log entries."""
    if not LOG_DIR.exists():
        return []

    entries = []
    for log_file in sorted(LOG_DIR.glob("*.jsonl"), reverse=True)[:days]:
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line.strip())
                if agent and entry.get("agent") != agent:
                    continue
                entries.append(entry)
    return entries
