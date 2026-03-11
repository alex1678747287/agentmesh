"""Auto memory - extract and persist key info from agent outputs."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from agentmesh.models import AgentResult

MEMORY_FILE = Path(".ai/memory.jsonl")
MAX_ENTRIES = 200  # rolling window


def record_memory(result: AgentResult, prompt: str = "", project: str | None = None):
    """Extract key info from result and append to shared memory."""
    if result.exit_code != 0 or not result.output:
        return

    entries = _extract_entries(prompt, result.output, result.agent.value, project)
    if not entries:
        return

    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _trim_memory()


def load_recent_memory(n: int = 20) -> list[dict]:
    """Load the most recent n memory entries."""
    if not MEMORY_FILE.exists():
        return []
    entries = []
    with open(MEMORY_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries[-n:]


def build_memory_context(n: int = 10) -> str:
    """Build a context string from recent memory entries."""
    entries = load_recent_memory(n)
    if not entries:
        return ""
    lines = ["# Recent Memory"]
    for e in entries:
        tags = ", ".join(e.get("tags", []))
        lines.append(f"- [{tags}] {e['content']}")
    return "\n".join(lines)


# Patterns to extract key info from agent output
_EXTRACTORS: list[tuple[str, list[str], re.Pattern]] = [
    # File paths created/modified
    ("file", ["file", "change"], re.compile(
        r"(?:created?|modified?|updated?|wrote|deleted?)\s+[`'\"]?([^\s`'\"]+\.\w{1,10})[`'\"]?",
        re.IGNORECASE,
    )),
    # Error fixes
    ("fix", ["bugfix"], re.compile(
        r"(?:fixed?|resolved?|patched?)\s+(.{10,80}?)(?:\.|$)",
        re.IGNORECASE,
    )),
    # API endpoints
    ("api", ["api"], re.compile(
        r"(?:endpoint|route|api)\s*[:=]?\s*[`'\"]?((?:GET|POST|PUT|DELETE|PATCH)\s+/\S+)",
        re.IGNORECASE,
    )),
    # Dependencies added
    ("dep", ["dependency"], re.compile(
        r"(?:installed?|added?)\s+(?:package|dependency|dep)\s+[`'\"]?(\S+)[`'\"]?",
        re.IGNORECASE,
    )),
    # Config changes
    ("config", ["config"], re.compile(
        r"(?:set|configured?|changed?)\s+[`'\"]?(\S+)[`'\"]?\s*(?:to|=)\s*[`'\"]?(\S+)[`'\"]?",
        re.IGNORECASE,
    )),
]


def _extract_entries(prompt: str, output: str, agent: str,
                     project: str | None) -> list[dict]:
    """Extract structured memory entries from agent output."""
    entries = []
    ts = datetime.now(timezone.utc).isoformat()

    for kind, tags, pattern in _EXTRACTORS:
        for match in pattern.finditer(output[:2000]):
            content = match.group(0).strip()
            if len(content) < 5:
                continue
            entry = {
                "ts": ts,
                "agent": agent,
                "kind": kind,
                "tags": tags + ([project] if project else []),
                "content": content[:200],
            }
            entries.append(entry)

    # Always record a summary if output is substantial
    if len(output) > 100 and not entries:
        summary = output[:150].replace("\n", " ").strip()
        entries.append({
            "ts": ts,
            "agent": agent,
            "kind": "summary",
            "tags": ["task"] + ([project] if project else []),
            "content": f"[{prompt[:50]}] {summary}",
        })

    return entries[:5]  # cap per execution


def _trim_memory():
    """Keep memory file within MAX_ENTRIES."""
    if not MEMORY_FILE.exists():
        return
    lines = MEMORY_FILE.read_text("utf-8").strip().splitlines()
    if len(lines) > MAX_ENTRIES:
        trimmed = lines[-MAX_ENTRIES:]
        MEMORY_FILE.write_text("\n".join(trimmed) + "\n", "utf-8")

