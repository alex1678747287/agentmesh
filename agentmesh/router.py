"""Agent router - decides which agent handles a task."""

from __future__ import annotations

import re

from agentmesh.models import AgentType

# Keyword-based routing rules
ROUTE_PATTERNS: dict[str, AgentType] = {
    r"review|audit|check": AgentType.CODEX_CLI,
    r"implement|write|create|fix|build": AgentType.CLAUDE_CODE,
    r"analyze|plan|design|research": AgentType.OPENCLAW,
    r"test|spec": AgentType.CODEX_CLI,
    r"deploy|devops|docker|k8s": AgentType.OPENCLAW,
}


class Router:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.default = AgentType(self.config.get("default_agent", "claude_code"))
        # Merge user-defined rules
        self.rules = ROUTE_PATTERNS.copy()
        for pattern, agent_name in self.config.get("rules", {}).items():
            self.rules[pattern] = AgentType(agent_name)

    def route(self, prompt: str, explicit_agent: str | None = None) -> AgentType:
        """Determine which agent should handle the prompt."""
        if explicit_agent:
            return AgentType(explicit_agent)

        prompt_lower = prompt.lower()
        for pattern, agent_type in self.rules.items():
            if re.search(pattern, prompt_lower):
                return agent_type

        return self.default
