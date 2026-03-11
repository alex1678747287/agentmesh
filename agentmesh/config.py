"""Configuration loader for agentmesh.

Supports per-project overrides: if a project-level config exists,
it is deep-merged on top of the base config.
"""

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
            "max_retries": 2,
            "retry_delay": 3,
            "deep_health_check": False,
        },
        "codex_cli": {
            "enabled": True,
            "command": "codex",
            "args": ["exec", "{prompt}"],
            "timeout": 300,
            "approval_mode": "auto-edit",
            "max_retries": 2,
            "retry_delay": 3,
            "deep_health_check": False,
        },
        "openclaw": {
            "enabled": True,
            "command": "openclaw",
            "args": ["agent", "--message", "{prompt}", "--json"],
            "timeout": 300,
            "gateway_url": "ws://localhost:19888",
            "max_retries": 2,
            "retry_delay": 3,
            "deep_health_check": False,
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
    "fallback_order": {
        "claude_code": ["openclaw", "codex_cli"],
        "codex_cli": ["claude_code", "openclaw"],
        "openclaw": ["claude_code", "codex_cli"],
    },
}


def load_config(path: str | Path | None = None, project: str | None = None) -> dict[str, Any]:
    """Load config from yaml file, falling back to defaults.

    If project is given, also look for a project-specific override file
    at <ai_dir>/projects/<project>/agentmesh.yaml.
    """
    config = _deep_copy(DEFAULT_CONFIG)
    if path:
        p = Path(path)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
            config = _deep_merge(config, user_config)

    # Per-project override
    if project:
        ai_dir = config.get("context", {}).get("ai_dir", ".ai")
        project_config_path = Path(ai_dir) / "projects" / project / "agentmesh.yaml"
        if project_config_path.exists():
            with open(project_config_path, encoding="utf-8") as f:
                proj_config = yaml.safe_load(f) or {}
            config = _deep_merge(config, proj_config)

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


def _deep_copy(d: dict) -> dict:
    """Simple deep copy for nested dicts/lists."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _deep_copy(v)
        elif isinstance(v, list):
            result[k] = v[:]
        else:
            result[k] = v
    return result
