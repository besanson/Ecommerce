"""MCP-style message types.

This module models the *shape* of MCP (Model Context Protocol) messages -
JSON-RPC-flavoured request/response between agents - without claiming to be a
conformant MCP implementation. The transport in `gacct.mcp.transport` is
in-process. The point of using MCP-style framing is so that an audience can
see agent-to-agent communication as structured messages rather than as
opaque Python calls.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class MCPMessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    NOTIFICATION = "notification"


class MCPMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    correlation_id: Optional[str] = Field(
        default=None,
        description="Set on responses and errors to the message_id of the originating request.",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sender: str
    receiver: str
    message_type: MCPMessageType
    method: Optional[str] = Field(
        default=None,
        description="Tool / method name. None for non-RPC notifications.",
    )
    params: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[str] = None

    def short(self) -> str:
        """One-line description for the dialogue view."""

        if self.message_type == MCPMessageType.REQUEST:
            return f"{self.sender} → {self.receiver}: {self.method}(...)"
        if self.message_type == MCPMessageType.RESPONSE:
            return f"{self.sender} → {self.receiver}: {self.method}() OK"
        if self.message_type == MCPMessageType.ERROR:
            return f"{self.sender} → {self.receiver}: {self.method}() ERROR: {self.error}"
        return f"{self.sender} → {self.receiver}: notify {self.method}"
