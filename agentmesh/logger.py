"""Execution logger - records agent calls for audit and cost tracking."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agentmesh.models import AgentResult

_DEFAULT_LOG_DIR = Path(".ai/logs")
_log_dir: Path = _DEFAULT_LOG_DIR


def set_ai_dir(ai_dir: str | Path):
    """Override the log directory based on ai_dir config."""
    global _log_dir
    _log_dir = Path(ai_dir) / "logs"


def log_result(result: AgentResult, prompt: str = ""):
    """Append an execution record to the log file."""
    _log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = _log_dir / f"{today}.jsonl"

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
    """Read log entries from the last N days."""
    if not _log_dir.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    entries = []
    for log_file in sorted(_log_dir.glob("*.jsonl"), reverse=True):
        # File name is YYYY-MM-DD.jsonl, skip files older than cutoff
        if log_file.stem < cutoff_str:
            break
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if agent and entry.get("agent") != agent:
                    continue
                entries.append(entry)
    return entries
