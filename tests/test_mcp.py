from __future__ import annotations

import pytest

from gacct.agents.retailer_agent import RetailerAgent
from gacct.domain.product import ProductOffer, RetailerTerms
from gacct.mcp.messages import MCPMessageType
from gacct.mcp.transport import MCPServer, MCPTransport


def _offer(sku: str, price: float, materials=("mesh",)) -> ProductOffer:
    return ProductOffer(
        offer_id=f"o:{sku}",
        retailer_id="retailer:test",
        sku=sku,
        title=sku,
        price_eur=price,
        shipping_eur=5.0,
        shipping_days=2,
        materials=list(materials),
        in_stock=True,
        terms=RetailerTerms(return_window_days=30, free_returns=True),
    )


def _server() -> RetailerAgent:
    return RetailerAgent(
        retailer_id="retailer:test",
        display_name="Test Retailer",
        catalogue=[_offer("A", 100), _offer("B", 110)],
    )


def test_transport_logs_request_and_response():
    log = []
    t = MCPTransport(on_message=log.append)
    t.register(_server())
    result = t.call(sender="agent:c", receiver="retailer:test", method="list_products", params={"max_results": 5})
    assert isinstance(result, list)
    assert len(log) == 2
    assert log[0].message_type == MCPMessageType.REQUEST
    assert log[1].message_type == MCPMessageType.RESPONSE
    assert log[1].correlation_id == log[0].message_id


def test_transport_logs_error_on_unknown_tool():
    log = []
    t = MCPTransport(on_message=log.append)
    t.register(_server())
    with pytest.raises(KeyError):
        t.call(sender="agent:c", receiver="retailer:test", method="not_a_tool", params={})
    assert log[-1].message_type == MCPMessageType.ERROR
    assert "unknown tool" in log[-1].error


def test_transport_rejects_unknown_receiver():
    log = []
    t = MCPTransport(on_message=log.append)
    with pytest.raises(KeyError):
        t.call(sender="agent:c", receiver="retailer:nope", method="list_products", params={})
    assert log[-1].message_type == MCPMessageType.ERROR


def test_propose_substitute_returns_substitute_for():
    t = MCPTransport()
    server = _server()
    t.register(server)
    sub = t.call(sender="agent:c", receiver="retailer:test", method="propose_substitute",
                 params={"original_sku": "A"})
    assert sub is not None
    assert sub.sku == "B"
    assert sub.substitute_for_offer_id == "o:A"


def test_confirm_order_executes_via_transport():
    t = MCPTransport()
    server = _server()
    t.register(server)
    result = t.call(
        sender="agent:c", receiver="retailer:test",
        method="confirm_order",
        params={"sku": "A", "shared_fields": ["shipping_address"]},
    )
    assert result["status"] == "confirmed"
    assert result["sku"] == "A"
