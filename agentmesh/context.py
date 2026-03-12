"""Three-tier context builder: hot / warm / cold, with token limits."""

from __future__ import annotations

from pathlib import Path

from agentmesh.memory import build_memory_context


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to approximate token limit."""
    max_chars = max_tokens * 3
    if len(text) <= max_chars:
        return text
    # Truncate at last newline before limit
    truncated = text[:max_chars]
    last_nl = truncated.rfind("\n")
    if last_nl > max_chars // 2:
        truncated = truncated[:last_nl]
    return truncated + "\n[...truncated]"


class ContextBuilder:
    """
    Hot:  .ai/profile.md + .ai/rules.md  (~200 tokens, always loaded)
    Warm: .ai/projects/{name}.md          (~500 tokens, per project)
    Auto: .ai/memory.jsonl recent entries (~200 tokens, auto-recorded)
    Cold: MCP memory search               (on demand)
    """

    def __init__(self, ai_dir: str | Path = ".ai", project: str | None = None,
                 max_hot_tokens: int = 300, max_warm_tokens: int = 500,
                 max_memory_tokens: int = 200, max_total_tokens: int = 1500):
        self.ai_dir = Path(ai_dir)
        self.project = project
        self.max_hot = max_hot_tokens
        self.max_warm = max_warm_tokens
        self.max_memory = max_memory_tokens
        self.max_total = max_total_tokens
        self._hot: str | None = None
        self._warm: str | None = None

    @property
    def hot(self) -> str:
        """Load hot memory: profile + rules."""
        if self._hot is None:
            parts = []
            for name in ("profile.md", "rules.md"):
                p = self.ai_dir / name
                if p.exists():
                    parts.append(p.read_text("utf-8").strip())
            raw = "\n\n".join(parts)
            self._hot = _truncate_to_tokens(raw, self.max_hot)
        return self._hot

    @property
    def warm(self) -> str:
        """Load warm memory: project-specific context."""
        if self._warm is None and self.project:
            p = self.ai_dir / "projects" / f"{self.project}.md"
            raw = p.read_text("utf-8").strip() if p.exists() else ""
            self._warm = _truncate_to_tokens(raw, self.max_warm)
        return self._warm or ""

    def build(self, prompt: str = "", level: str = "auto") -> str:
        """Assemble context string with token budget.

        Levels:
          - "hot":  profile + rules only (~200 tokens). For small tasks.
          - "warm": hot + project context + relevant memory. For normal tasks.
          - "full": hot + warm + more memory entries. For pipeline tasks.
          - "auto": pick level based on prompt length heuristic.
        """
        if level == "auto":
            level = self._auto_level(prompt)

        parts = []
        if self.hot:
            parts.append(self.hot)

        if level in ("warm", "full") and self.warm:
            parts.append(f"# Project: {self.project}\n{self.warm}")

        if level in ("warm", "full"):
            mem_count = 15 if level == "full" else 8
            mem = build_memory_context(mem_count, prompt=prompt)
            if mem:
                parts.append(_truncate_to_tokens(mem, self.max_memory))

        full = "\n\n---\n\n".join(parts)
        return _truncate_to_tokens(full, self.max_total)

    def _auto_level(self, prompt: str) -> str:
        """Pick context level based on prompt characteristics."""
        if not prompt:
            return "warm"
        # Short prompts (< 50 chars) = likely simple task
        if len(prompt) < 50:
            return "hot"
        # Pipeline-related keywords
        if any(kw in prompt.lower() for kw in ("pipeline", "multi", "batch", "all")):
            return "full"
        return "warm"

    def invalidate(self):
        """Clear cached context."""
        self._hot = None
        self._warm = None
