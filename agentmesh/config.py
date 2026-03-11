"""Configuration loader for agentmesh."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = {
    "agents": {
        "claude_code": {
            "enabled": True,
            "command": "claude",
            "args": ["-p", "{prompt}", "--print"],
            "timeout": 300,
            "max_turns": 10,
        },
        "codex_cli": {
            "enabled": True,
            "command": "codex",
            "args": ["exec", "{prompt}"],
            "timeout": 300,
            "approval_mode": "auto-edit",
        },
        "openclaw": {
            "enabled": True,
            "command": "openclaw",
            "args": ["agent", "--message", "{prompt}", "--json"],
            "timeout": 300,
            "gateway_url": "ws://localhost:19888",
        },
    },
    "context": {
        "ai_dir": ".ai",
        "hot_max_tokens": 200,
        "warm_max_tokens": 500,
    },
    "router": {
        "default_agent": "claude_code",
        "rules": {
            "review": "codex_cli",
            "implement": "claude_code",
            "analyze": "openclaw",
        },
    },
}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config from yaml file, falling back to defaults."""
    config = DEFAULT_CONFIG.copy()
    if path:
        p = Path(path)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            config = _deep_merge(config, user_config)
    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
