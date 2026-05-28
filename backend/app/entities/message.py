"""Message entity (T066) — Layer 1. Pure dataclass, no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class MessageRole(StrEnum):
    VISITOR = "visitor"
    AGENT = "agent"
    TOOL = "tool"
    SYSTEM = "system"


@dataclass(slots=True)
class Message:
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    role: MessageRole
    content: str  # PII-redacted before write
    router_label: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime | None = None
