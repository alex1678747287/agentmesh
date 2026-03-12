"""Auto memory - extract and persist key info from agent outputs.

Features:
- Regex-based extraction of files, fixes, APIs, deps, configs, DB ops, errors
- TTL-based expiry (default 7 days) with kind-specific TTLs
- Deduplication against recent entries
- Efficient tail-read for recent queries
"""

from __future__ import annotations

import json
import re
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

from agentmesh.models import AgentResult

_DEFAULT__memory_file = Path(".ai/memory.jsonl")
MAX_ENTRIES = 200

# Active memory file path (can be overridden via set_ai_dir)
_memory_file: Path = _DEFAULT__memory_file

# TTL per kind (days). Entries older than this are expired during cleanup.
_TTL_DAYS: dict[str, int] = {
    "error": 3,      # errors become stale fast
    "summary": 5,
    "file": 7,
    "fix": 14,        # bugfix knowledge is valuable longer
    "api": 14,
    "dep": 14,
    "config": 14,
    "db": 30,         # schema changes are long-lived
}
_DEFAULT_TTL_DAYS = 7

# In-memory cache for recent entries (avoids full file scan)
_cache: deque[dict] | None = None
_cache_mtime: float = 0


def set_ai_dir(ai_dir: str | Path):
    """Override the memory file path based on ai_dir config."""
    global _memory_file, _cache, _cache_mtime
    _memory_file = Path(ai_dir) / "memory.jsonl"
    _cache = None
    _cache_mtime = 0

# Patterns to extract key info from agent output
_EXTRACTORS: list[tuple[str, list[str], re.Pattern]] = [
    ("file", ["file", "change"], re.compile(
        r"(?:created?|modified?|updated?|wrote|deleted?|added?)\s+(?:file\s+)?[`'\"]?([^\s`'\"]{3,}\.[\w]{1,10})[`'\"]?",
        re.IGNORECASE,
    )),
    ("fix", ["bugfix"], re.compile(
        r"(?:fixed?|resolved?|patched?|solved?)\s+(.{10,120}?)(?:\.|$|\n)",
        re.IGNORECASE,
    )),
    ("api", ["api"], re.compile(
        r"(?:endpoint|route|api|handler)\s*[:=]?\s*[`'\"]?((?:GET|POST|PUT|DELETE|PATCH)\s+/\S+)",
        re.IGNORECASE,
    )),
    ("dep", ["dependency"], re.compile(
        r"(?:installed?|added?)\s+(?:package|dependency|dep|module)\s+[`'\"]?(\S+)[`'\"]?",
        re.IGNORECASE,
    )),
    ("config", ["config"], re.compile(
        r"(?:set|configured?|changed?|updated?)\s+(?:config\s+)?[`'\"]?(\S+)[`'\"]?\s*(?:to|=)\s*[`'\"]?(.{1,50}?)[`'\"]?(?:\s|$|\.|,)",
        re.IGNORECASE,
    )),
    ("db", ["database"], re.compile(
        r"(?:CREATE\s+TABLE|ALTER\s+TABLE|CREATE\s+INDEX|migration)\s+[`'\"]?(\S+)[`'\"]?",
        re.IGNORECASE,
    )),
    ("error", ["error"], re.compile(
        r"(?:error|exception|panic|traceback)[:]\s*(.{10,100}?)(?:\n|$)",
        re.IGNORECASE,
    )),
]


def _get_cache() -> deque[dict]:
    """Load entries into cache, refreshing if file changed."""
    global _cache, _cache_mtime
    if not _memory_file.exists():
        _cache = deque(maxlen=MAX_ENTRIES)
        return _cache
    mtime = _memory_file.stat().st_mtime
    if _cache is not None and mtime == _cache_mtime:
        return _cache
    _cache = deque(maxlen=MAX_ENTRIES)
    with open(_memory_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    _cache.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    _cache_mtime = mtime
    return _cache


def record_memory(result: AgentResult, prompt: str = "", project: str | None = None):
    """Extract key info from result and append to shared memory."""
    if result.exit_code != 0 or not result.output:
        return

    entries = _extract_entries(prompt, result.output, result.agent.value, project)
    if not entries:
        return

    _memory_file.parent.mkdir(parents=True, exist_ok=True)

    # Deduplicate against recent entries
    cache = _get_cache()
    existing = {e.get("content", "") for e in list(cache)[-20:]}
    new_entries = [e for e in entries if e["content"] not in existing]
    if not new_entries:
        return

    with open(_memory_file, "a", encoding="utf-8") as f:
        for entry in new_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            cache.append(entry)

    global _cache_mtime
    _cache_mtime = _memory_file.stat().st_mtime
    _cleanup_expired()


def load_recent_memory(n: int = 20) -> list[dict]:
    """Load the most recent n memory entries (from cache)."""
    cache = _get_cache()
    return list(cache)[-n:]


def build_memory_context(n: int = 10, prompt: str = "") -> str:
    """Build a context string from memory entries relevant to the prompt.

    If prompt is given, score entries by keyword overlap and pick top N.
    Otherwise fall back to most recent N entries.
    """
    cache = _get_cache()
    if not cache:
        return ""

    if prompt:
        entries = _rank_by_relevance(list(cache), prompt, n)
    else:
        entries = list(cache)[-n:]

    if not entries:
        return ""
    lines = ["# Recent Memory"]
    for e in entries:
        tags = ", ".join(e.get("tags", []))
        lines.append(f"- [{tags}] {e['content']}")
    return "\n".join(lines)


def _rank_by_relevance(entries: list[dict], prompt: str, n: int) -> list[dict]:
    """Score entries by keyword overlap with prompt, return top N."""
    # Tokenize prompt into keywords (3+ chars, lowered)
    keywords = set(
        w for w in re.split(r"[\s/\\.,;:!?(){}[\]\"'`]+", prompt.lower())
        if len(w) >= 3
    )
    if not keywords:
        return entries[-n:]

    scored: list[tuple[float, int, dict]] = []
    for idx, entry in enumerate(entries):
        searchable = (
            entry.get("content", "") + " " +
            " ".join(entry.get("tags", []))
        ).lower()
        # Count keyword hits
        hits = sum(1 for kw in keywords if kw in searchable)
        if hits == 0:
            continue
        # Boost recent entries slightly (recency bonus: 0~0.5)
        recency = idx / max(len(entries), 1) * 0.5
        score = hits + recency
        scored.append((score, idx, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    result = [e for _, _, e in scored[:n]]

    # If not enough relevant entries, pad with most recent
    if len(result) < n:
        existing = {id(e) for e in result}
        for entry in reversed(entries):
            if id(entry) not in existing:
                result.append(entry)
                if len(result) >= n:
                    break

    return result


def _is_expired(entry: dict) -> bool:
    """Check if an entry has exceeded its TTL."""
    ts_str = entry.get("ts", "")
    if not ts_str:
        return False
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False
    kind = entry.get("kind", "")
    ttl = timedelta(days=_TTL_DAYS.get(kind, _DEFAULT_TTL_DAYS))
    return datetime.now(timezone.utc) - ts > ttl


def _cleanup_expired():
    """Remove expired entries and enforce MAX_ENTRIES."""
    global _cache, _cache_mtime
    if not _memory_file.exists():
        return
    cache = _get_cache()
    kept = [e for e in cache if not _is_expired(e)]
    if len(kept) > MAX_ENTRIES:
        kept = kept[-MAX_ENTRIES:]
    # Only rewrite if something was removed
    if len(kept) < len(cache):
        _memory_file.write_text(
            "\n".join(json.dumps(e, ensure_ascii=False) for e in kept) + "\n",
            encoding="utf-8",
        )
        _cache = deque(kept, maxlen=MAX_ENTRIES)
        _cache_mtime = _memory_file.stat().st_mtime


def _extract_entries(prompt: str, output: str, agent: str,
                     project: str | None) -> list[dict]:
    """Extract structured memory entries from agent output."""
    entries = []
    ts = datetime.now(timezone.utc).isoformat()
    scan_text = output[:3000]

    for kind, tags, pattern in _EXTRACTORS:
        for match in pattern.finditer(scan_text):
            content = match.group(0).strip()
            if len(content) < 5:
                continue
            entry = {
                "ts": ts,
                "agent": agent,
                "kind": kind,
                "tags": tags + ([project] if project else []),
                "content": _redact_sensitive(content[:200]),
            }
            entries.append(entry)

    if len(output) > 100 and not entries:
        summary = _smart_summary(output)
        entries.append({
            "ts": ts,
            "agent": agent,
            "kind": "summary",
            "tags": ["task"] + ([project] if project else []),
            "content": _redact_sensitive(f"[{prompt[:50]}] {summary}"),
        })

    return entries[:5]


# Sensitive patterns to redact before storing to memory
_SENSITIVE_RE = [
    re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"(?:token|api[_-]?key|secret[_-]?key)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"(?:sk|pk|ak)-[a-zA-Z0-9]{20,}"),
]


def _redact_sensitive(text: str) -> str:
    """Redact sensitive data from text before storing."""
    for pattern in _SENSITIVE_RE:
        text = pattern.sub("[REDACTED]", text)
    return text


def _smart_summary(output: str) -> str:
    """Extract a meaningful summary from output, skipping noise."""
    lines = output.strip().splitlines()
    noise = {"", "$", ">", "---", "```", "ok", "done", "success"}
    for line in lines[:20]:
        cleaned = line.strip().lower()
        if cleaned not in noise and len(cleaned) > 10:
            return line.strip()[:150]
    return output[:150].replace("\n", " ").strip()
