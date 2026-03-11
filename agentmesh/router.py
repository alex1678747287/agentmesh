"""Agent router - decides which agent handles a task."""

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
        # Merge user-defined rules from config
        for pattern, agent_name in self.config.get("rules", {}).items():
            self.rules.append((pattern, AgentType(agent_name), 10))

    def route(self, prompt: str, explicit_agent: str | None = None) -> AgentType:
        """Determine which agent should handle the prompt."""
        if explicit_agent:
            return AgentType(explicit_agent)

        prompt_lower = prompt.lower()
        best_agent = self.default
        best_score = 0

        for pattern, agent_type, weight in self.rules:
            matches = re.findall(pattern, prompt_lower)
            if matches:
                score = len(matches) * weight
                if score > best_score:
                    best_score = score
                    best_agent = agent_type

        return best_agent

    def explain(self, prompt: str) -> str:
        """Explain routing decision for debugging."""
        prompt_lower = prompt.lower()
        # Aggregate scores per agent
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
