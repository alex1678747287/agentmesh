"""Adapter base class and registry."""

from __future__ import annotations

import asyncio
import logging
import re
from abc import ABC, abstractmethod

from agentmesh.models import AgentResult, AgentType

logger = logging.getLogger(__name__)

# Retryable exit codes (transient failures)
_RETRYABLE_CODES = {-1, 1, 137, 143}


class BaseAdapter(ABC):
    """Base class for all agent adapters."""

    agent_type: AgentType

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def _execute(self, prompt: str, context: str = "", timeout: int = 300) -> AgentResult:
        """Execute a task on the agent (implement in subclass)."""
        ...

    async def execute(self, prompt: str, context: str = "", timeout: int = 300) -> AgentResult:
        """Execute with retry. Retries on transient failures."""
        max_retries = self.config.get("max_retries", 2)
        retry_delay = self.config.get("retry_delay", 3)

        last_result = None
        for attempt in range(max_retries + 1):
            result = await self._execute(prompt, context, timeout)
            if result.exit_code == 0:
                return result
            last_result = result
            # Don't retry on timeout (already waited long enough)
            if result.output == "[timeout]":
                return result
            # Don't retry on non-retryable codes
            if result.exit_code not in _RETRYABLE_CODES:
                return result
            if attempt < max_retries:
                logger.info(
                    "Retry %d/%d for %s (exit=%d)",
                    attempt + 1, max_retries, self.agent_type.value, result.exit_code,
                )
                await asyncio.sleep(retry_delay * (attempt + 1))
        return last_result

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the agent is available."""
        ...

    def build_prompt(self, task_prompt: str, context: str) -> str:
        """Combine context + task into final prompt, with injection sanitization."""
        parts = []
        if context:
            parts.append(f"<context>\n{context}\n</context>\n")
        parts.append(_sanitize_prompt(task_prompt))
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
    _ensure_registered()
    agents_config = config.get("agents", {})
    result = {}
    for agent_type, cls in _ADAPTERS.items():
        agent_key = agent_type.value
        if agents_config.get(agent_key, {}).get("enabled", True):
            result[agent_type] = cls(agents_config.get(agent_key, {}))
    return result


def _ensure_registered():
    """Import adapter modules to trigger @register_adapter decorators."""
    if _ADAPTERS:
        return
    from agentmesh.adapters import claude_code, codex_cli, openclaw  # noqa: F401


# Patterns that indicate prompt injection attempts
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*(?:system|admin|root)\s*>", re.IGNORECASE),
    re.compile(r"(?:forget|disregard)\s+(?:everything|all)", re.IGNORECASE),
]

# Sensitive data patterns to redact
_SENSITIVE_PATTERNS = [
    (re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*\S+", re.IGNORECASE), "[REDACTED_PASSWORD]"),
    (re.compile(r"(?:token|api[_-]?key|secret[_-]?key)\s*[:=]\s*\S+", re.IGNORECASE), "[REDACTED_TOKEN]"),
    (re.compile(r"(?:sk|pk|ak)-[a-zA-Z0-9]{20,}"), "[REDACTED_KEY]"),
]


def _sanitize_prompt(prompt: str) -> str:
    """Sanitize prompt to prevent injection and redact sensitive data."""
    # Flag injection attempts (wrap in warning, don't block)
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(prompt):
            prompt = f"[WARNING: potential prompt injection detected]\n{prompt}"
            break
    # Redact sensitive data
    for pattern, replacement in _SENSITIVE_PATTERNS:
        prompt = pattern.sub(replacement, prompt)
    return prompt
