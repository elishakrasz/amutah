"""Shared result shapes. Reasons are stable codes plus parameters; the UI
turns them into Hebrew (or other) text from messages/*.json."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Reason:
    code: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Suggestion:
    """A score shown to the committee, never applied automatically."""

    low: int
    high: int
    reason: Reason
