"""Adapter base class and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod

from agentmesh.models import AgentResult, AgentType


class BaseAdapter(ABC):
    """Base class for all agent adapters."""

    agent_type: AgentType

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def execute(self, prompt: str, context: str = "", timeout: int = 300) -> AgentResult:
        """Execute a task on the agent."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the agent is available."""
        ...

    def build_prompt(self, task_prompt: str, context: str) -> str:
        """Combine context + task into final prompt."""
        parts = []
        if context:
            parts.append(f"<context>\n{context}\n</context>\n")
        parts.append(task_prompt)
        return "\n".join(parts)


# Adapter registry
_ADAPTERS: dict[AgentType, type[BaseAdapter]] = {}


def register_adapter(agent_type: AgentType):
    """Decorator to register an adapter class."""
    def decorator(cls: type[BaseAdapter]):
        cls.agent_type = agent_type
        _ADAPTERS[agent_type] = cls
        return cls
    return decorator


def get_adapter(agent_type: AgentType, config: dict) -> BaseAdapter:
    """Get an adapter instance by agent type."""
    cls = _ADAPTERS.get(agent_type)
    if not cls:
        raise ValueError(f"No adapter registered for {agent_type}")
    return cls(config)


def get_all_adapters(config: dict) -> dict[AgentType, BaseAdapter]:
    """Get all registered adapters."""
    agents_config = config.get("agents", {})
    result = {}
    for agent_type, cls in _ADAPTERS.items():
        agent_key = agent_type.value
        if agents_config.get(agent_key, {}).get("enabled", True):
            result[agent_type] = cls(agents_config.get(agent_key, {}))
    return result
