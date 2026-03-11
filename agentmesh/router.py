"""Agent router - decides which agent handles a task, with availability awareness."""

from __future__ import annotations

import re

from agentmesh.models import AgentType

# (pattern, agent, weight) - higher weight wins on conflict
ROUTE_RULES: list[tuple[str, AgentType, int]] = [
    # Code review / audit
    (r"review|audit|check|lint|审查|检查|代码审查", AgentType.CODEX_CLI, 10),
    # Testing
    (r"test|spec|测试|单元测试", AgentType.CODEX_CLI, 10),
    # Implementation
    (r"implement|write|create|fix|build|code|实现|编写|修复|创建|开发", AgentType.CLAUDE_CODE, 10),
    # Refactor
    (r"refactor|重构|优化代码", AgentType.CLAUDE_CODE, 8),
    # Analysis / planning
    (r"analyze|plan|design|research|分析|规划|设计|调研", AgentType.OPENCLAW, 10),
    # DevOps
    (r"deploy|devops|docker|k8s|部署|运维|容器", AgentType.OPENCLAW, 8),
    # Documentation
    (r"document|readme|文档|说明", AgentType.OPENCLAW, 5),
]


class Router:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.default = AgentType(self.config.get("default_agent", "claude_code"))
        self.rules = list(ROUTE_RULES)
        for pattern, agent_name in self.config.get("rules", {}).items():
            self.rules.append((pattern, AgentType(agent_name), 10))

    def route(self, prompt: str, explicit_agent: str | None = None,
              available: set[AgentType] | None = None) -> AgentType:
        """Determine which agent should handle the prompt.
        If available is provided, only route to online agents.
        """
        if explicit_agent:
            target = AgentType(explicit_agent)
            # If explicitly requested but unavailable, still return it
            # (scheduler handles fallback)
            return target

        prompt_lower = prompt.lower()
        # Score all agents
        scores: dict[AgentType, int] = {}
        for pattern, agent_type, weight in self.rules:
            matches = re.findall(pattern, prompt_lower)
            if matches:
                scores[agent_type] = scores.get(agent_type, 0) + len(matches) * weight

        if not scores:
            # No pattern matched, use default
            if available and self.default not in available:
                return next(iter(available)) if available else self.default
            return self.default

        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # If availability info provided, prefer available agents
        if available:
            for agent, _score in ranked:
                if agent in available:
                    return agent
            # All matched agents unavailable, pick any available one
            return next(iter(available))

        return ranked[0][0]

    def explain(self, prompt: str) -> str:
        """Explain routing decision for debugging."""
        prompt_lower = prompt.lower()
        scores: dict[str, tuple[list[str], int]] = {}
        for pattern, agent_type, weight in self.rules:
            matches = re.findall(pattern, prompt_lower)
            if matches:
                name = agent_type.value
                prev_matches, prev_score = scores.get(name, ([], 0))
                scores[name] = (prev_matches + matches, prev_score + len(matches) * weight)
        if not scores:
            return f"No pattern matched, using default: {self.default.value}"
        ranked = sorted(scores.items(), key=lambda x: x[1][1], reverse=True)
        lines = [f"  {a}: {m} (score={s})" for a, (m, s) in ranked]
        return f"Routing decision:\n" + "\n".join(lines) + f"\n  -> {ranked[0][0]}"
