"""Output validator - lightweight quality checks on agent results."""

from __future__ import annotations

import logging
import re

from agentmesh.models import AgentResult

logger = logging.getLogger(__name__)

# Minimum output length by task type (detected from prompt keywords)
_MIN_LENGTH: dict[str, int] = {
    "review": 50,      # a real review should have substance
    "implement": 20,
    "analyze": 50,
    "test": 20,
    "default": 10,
}

# Suspicious patterns that indicate the agent didn't really do the work
_LAZY_PATTERNS = [
    re.compile(r"^(looks?\s+good|lgtm|no\s+issues?\s+found|everything\s+is\s+fine)\.?$", re.IGNORECASE),
    re.compile(r"^(ok|done|success|completed?)\.?$", re.IGNORECASE),
    re.compile(r"^I\s+(don'?t|cannot|can'?t)\s+(see|find|access)", re.IGNORECASE),
]

# Expected content markers by task type
_EXPECTED_MARKERS: dict[str, list[str]] = {
    "review": ["bug", "issue", "suggest", "improve", "fix", "good", "concern", "approve"],
    "test": ["test", "assert", "expect", "pass", "fail", "coverage"],
    "implement": ["def ", "func ", "class ", "function", "import", "package"],
    "analyze": ["structure", "pattern", "recommend", "architecture", "component"],
}


class ValidationResult:
    __slots__ = ("passed", "warnings")

    def __init__(self):
        self.passed = True
        self.warnings: list[str] = []

    def warn(self, msg: str):
        self.warnings.append(msg)

    def fail(self, msg: str):
        self.passed = False
        self.warnings.append(msg)


def validate_output(result: AgentResult, prompt: str = "") -> ValidationResult:
    """Run quality checks on agent output. Returns validation result."""
    v = ValidationResult()

    if result.exit_code != 0:
        return v  # already failed, no point validating content

    output = result.output.strip()
    task_type = _detect_task_type(prompt)

    # Check 1: empty or too short
    min_len = _MIN_LENGTH.get(task_type, _MIN_LENGTH["default"])
    if len(output) < min_len:
        v.fail(f"Output too short ({len(output)} chars, expected >={min_len} for {task_type})")
        return v

    # Check 2: lazy/generic response
    first_line = output.split("\n", 1)[0].strip()
    for pattern in _LAZY_PATTERNS:
        if pattern.match(first_line) and len(output) < 100:
            v.warn(f"Suspicious generic response: '{first_line[:60]}'")
            break

    # Check 3: expected content markers
    markers = _EXPECTED_MARKERS.get(task_type, [])
    if markers:
        output_lower = output.lower()
        hits = sum(1 for m in markers if m in output_lower)
        if hits == 0 and len(output) > 50:
            v.warn(f"No expected keywords found for {task_type} task")

    return v


def _detect_task_type(prompt: str) -> str:
    """Detect task type from prompt keywords."""
    p = prompt.lower()
    if any(kw in p for kw in ("review", "audit", "check", "lint", "审查")):
        return "review"
    if any(kw in p for kw in ("test", "spec", "测试")):
        return "test"
    if any(kw in p for kw in ("implement", "write", "create", "fix", "build", "实现", "编写")):
        return "implement"
    if any(kw in p for kw in ("analyze", "plan", "design", "分析", "规划")):
        return "analyze"
    return "default"
