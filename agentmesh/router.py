"""Agent router - decides which agent handles a task, with context-aware routing."""

from __future__ import annotations

import re

from agentmesh.models import AgentType

# Compound rules: (pattern_combo, agent, weight)
# These match when ALL patterns in the combo are found, giving higher weight
_COMPOUND_RULES: list[tuple[list[str], AgentType, int]] = [
    # "optimize SQL" / "SQL performance" -> analysis, not implementation
    (["sql", "optim|perf|slow|慢|性能"], AgentType.OPENCLAW, 20),
    # "design API" / "API architecture" -> analysis
    (["api|接口", "design|architect|设计|架构"], AgentType.OPENCLAW, 20),
    # "fix test" / "test failing" -> implementation (fix the code, not write tests)
    (["fix|修复|repair", "test|测试"], AgentType.CLAUDE_CODE, 20),
    # "write test" / "add test" -> testing
    (["write|add|create|编写|添加", "test|测试|spec"], AgentType.CODEX_CLI, 20),
    # "review security" / "security audit" -> review
    (["security|安全|auth|认证", "review|audit|check|审查"], AgentType.CODEX_CLI, 20),
    # "deploy to production" / "production release" -> devops analysis
    (["deploy|发布|上线", "prod|生产|release"], AgentType.OPENCLAW, 18),
    # "refactor for performance" -> analysis first
    (["refactor|重构", "perf|性能|optim"], AgentType.OPENCLAW, 18),
    # "debug crash" / "investigate error" -> implementation
    (["debug|investigate|调试|排查", "crash|error|bug|panic|异常"], AgentType.CLAUDE_CODE, 18),
]

# Simple keyword rules: (pattern, agent, weight) - lower priority than compound
ROUTE_RULES: list[tuple[str, AgentType, int]] = [
    (r"review|audit|check|lint|审查|检查|代码审查", AgentType.CODEX_CLI, 10),
    (r"test|spec|测试|单元测试", AgentType.CODEX_CLI, 10),
    (r"implement|write|create|fix|build|code|实现|编写|修复|创建|开发", AgentType.CLAUDE_CODE, 10),
    (r"refactor|重构|优化代码", AgentType.CLAUDE_CODE, 8),
    (r"analyze|plan|design|research|分析|规划|设计|调研", AgentType.OPENCLAW, 10),
    (r"deploy|devops|docker|k8s|部署|运维|容器", AgentType.OPENCLAW, 8),
    (r"document|readme|文档|说明", AgentType.OPENCLAW, 5),
    (r"sql|query|database|数据库|查询|索引|migration", AgentType.OPENCLAW, 6),
    (r"performance|benchmark|profil|性能|基准", AgentType.OPENCLAW, 6),
]


class Router:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.default = AgentType(self.config.get("default_agent", "claude_code"))
        self.simple_rules = list(ROUTE_RULES)
        self.compound_rules = list(_COMPOUND_RULES)
        for pattern, agent_name in self.config.get("rules", {}).items():
            self.simple_rules.append((pattern, AgentType(agent_name), 10))

    def route(self, prompt: str, explicit_agent: str | None = None,
              available: set[AgentType] | None = None) -> AgentType:
        """Determine which agent should handle the prompt."""
        if explicit_agent:
            return AgentType(explicit_agent)

        prompt_lower = prompt.lower()
        scores: dict[AgentType, int] = {}

        # Phase 1: compound rules (higher priority)
        for patterns, agent_type, weight in self.compound_rules:
            if all(re.search(p, prompt_lower) for p in patterns):
                scores[agent_type] = scores.get(agent_type, 0) + weight

        # Phase 2: simple keyword rules
        for pattern, agent_type, weight in self.simple_rules:
            matches = re.findall(pattern, prompt_lower)
            if matches:
                scores[agent_type] = scores.get(agent_type, 0) + len(matches) * weight

        if not scores:
            if available and self.default not in available:
                return next(iter(available)) if available else self.default
            return self.default

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        if available:
            for agent, _score in ranked:
                if agent in available:
                    return agent
            return next(iter(available))

        return ranked[0][0]

    def explain(self, prompt: str) -> str:
        """Explain routing decision for debugging."""
        prompt_lower = prompt.lower()
        details: list[str] = []

        for patterns, agent_type, weight in self.compound_rules:
            if all(re.search(p, prompt_lower) for p in patterns):
                details.append(f"  [compound] {agent_type.value}: {patterns} (+{weight})")

        scores: dict[str, tuple[list[str], int]] = {}
        for pattern, agent_type, weight in self.simple_rules:
            matches = re.findall(pattern, prompt_lower)
            if matches:
                name = agent_type.value
                prev_matches, prev_score = scores.get(name, ([], 0))
                scores[name] = (prev_matches + matches, prev_score + len(matches) * weight)

        for name, (matches, score) in sorted(scores.items(), key=lambda x: x[1][1], reverse=True):
            details.append(f"  [simple] {name}: {matches} (score={score})")

        if not details:
            return f"No pattern matched, using default: {self.default.value}"

        result = self.route(prompt)
        return "Routing decision:\n" + "\n".join(details) + f"\n  -> {result.value}"
