from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from gacct.mcp.messages import MCPMessage, MCPMessageType


@dataclass
class MCPTool:
    name: str
    handler: Callable[..., Any]
    description: str = ""


class MCPServer:
    """A named endpoint that exposes a set of tools."""

    def __init__(self, name: str):
        self.name = name
        self._tools: Dict[str, MCPTool] = {}

    def register_tool(self, name: str, handler: Callable[..., Any], description: str = "") -> None:
        if name in self._tools:
            raise ValueError(f"tool {name!r} already registered on server {self.name!r}")
        self._tools[name] = MCPTool(name=name, handler=handler, description=description)

    def list_tools(self) -> List[Dict[str, str]]:
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def invoke(self, method: str, params: Dict[str, Any]) -> Any:
        if method not in self._tools:
            raise KeyError(f"unknown tool {method!r} on server {self.name!r}")
        return self._tools[method].handler(**params)


@dataclass
class MCPTransport:
    """In-process bus that routes calls between agents and logs every message.

    All traffic between the consumer agent and the retailer agent goes through
    this transport. Each request/response pair becomes a logged
    `MCPMessage`. A caller can subscribe `on_message` to receive every event
    (the trace store typically does).
    """

    on_message: Callable[[MCPMessage], None] = field(default=lambda _m: None)
    log: List[MCPMessage] = field(default_factory=list)
    servers: Dict[str, MCPServer] = field(default_factory=dict)

    def register(self, server: MCPServer) -> None:
        if server.name in self.servers:
            raise ValueError(f"server {server.name!r} already registered")
        self.servers[server.name] = server

    def call(
        self,
        *,
        sender: str,
        receiver: str,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        params = params or {}
        request = MCPMessage(
            sender=sender,
            receiver=receiver,
            message_type=MCPMessageType.REQUEST,
            method=method,
            params=params,
        )
        self._emit(request)

        if receiver not in self.servers:
            err = MCPMessage(
                sender=receiver,
                receiver=sender,
                message_type=MCPMessageType.ERROR,
                method=method,
                error=f"unknown server {receiver!r}",
                correlation_id=request.message_id,
            )
            self._emit(err)
            raise KeyError(f"unknown server {receiver!r}")

        try:
            result = self.servers[receiver].invoke(method, params)
        except Exception as exc:  # noqa: BLE001 — surface as MCP error
            err = MCPMessage(
                sender=receiver,
                receiver=sender,
                message_type=MCPMessageType.ERROR,
                method=method,
                error=f"{type(exc).__name__}: {exc}",
                correlation_id=request.message_id,
            )
            self._emit(err)
            raise

        response = MCPMessage(
            sender=receiver,
            receiver=sender,
            message_type=MCPMessageType.RESPONSE,
            method=method,
            result=self._jsonable(result),
            correlation_id=request.message_id,
        )
        self._emit(response)
        return result

    def notify(self, *, sender: str, receiver: str, method: str, params: Dict[str, Any]) -> None:
        msg = MCPMessage(
            sender=sender,
            receiver=receiver,
            message_type=MCPMessageType.NOTIFICATION,
            method=method,
            params=params,
        )
        self._emit(msg)

    def _emit(self, msg: MCPMessage) -> None:
        self.log.append(msg)
        self.on_message(msg)

    @staticmethod
    def _jsonable(value: Any) -> Any:
        """Convert pydantic models and lists thereof for the wire log."""

        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, list):
            return [MCPTransport._jsonable(v) for v in value]
        if isinstance(value, dict):
            return {k: MCPTransport._jsonable(v) for k, v in value.items()}
        return value
