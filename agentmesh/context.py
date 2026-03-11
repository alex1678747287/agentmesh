"""Three-tier context builder: hot / warm / cold."""

from __future__ import annotations

from pathlib import Path


class ContextBuilder:
    """
    Hot:  .ai/profile.md + .ai/rules.md  (~200 tokens, always loaded)
    Warm: .ai/projects/{name}.md          (~500 tokens, per project)
    Cold: MCP memory search               (on demand)
    """

    def __init__(self, ai_dir: str | Path = ".ai", project: str | None = None):
        self.ai_dir = Path(ai_dir)
        self.project = project
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
            self._hot = "\n\n".join(parts)
        return self._hot

    @property
    def warm(self) -> str:
        """Load warm memory: project-specific context."""
        if self._warm is None and self.project:
            p = self.ai_dir / "projects" / f"{self.project}.md"
            self._warm = p.read_text("utf-8").strip() if p.exists() else ""
        return self._warm or ""

    def build(self) -> str:
        """Assemble full context string."""
        parts = []
        if self.hot:
            parts.append(self.hot)
        if self.warm:
            parts.append(f"# Project: {self.project}\n{self.warm}")
        return "\n\n---\n\n".join(parts)

    def invalidate(self):
        """Clear cached context."""
        self._hot = None
        self._warm = None
