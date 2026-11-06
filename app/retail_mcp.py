"""Read-only fictional retail tools exposed over the installed MCP 2.x SDK.

This server has no business-system credentials, writes, or refund operations.
All responses carry the fixture timestamp and an explicit synthetic-data notice.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations


_FIXTURE = json.loads(
    (Path(__file__).resolve().parents[1] / "demo" / "retail-data.json").read_text()
)

retail_mcp = MCPServer(
    name="SkillsCentral fictional retail tools",
    version="1.0.0",
    instructions=(
        "All tools return fixed fictional demonstration data, not real retail records. "
        "Tools are read-only. Never claim to issue a refund, authorize a return, "
        "reserve stock, or modify an account. Preserve the synthetic label and "
        "as_of timestamp when explaining the result."
    ),
)

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _read_fixture(collection: str, key: str) -> dict[str, Any]:
    record = _FIXTURE[collection].get(key)
    return {
        "synthetic": True,
        "fictional": True,
        "as_of": _FIXTURE["as_of"],
        "notice": _FIXTURE["notice"],
        "read_only": True,
        "found": record is not None,
        "data": record,
        **({"message": "No matching record exists in the fixed fictional fixture."} if record is None else {}),
    }


@retail_mcp.tool(
    name="get_order",
    title="Read a fictional demo order",
    description=(
        "Read a fixed fictional order, including purchase age and item condition. "
        "Demo order IDs: SC-1001 (38-day-old unworn jacket), SC-1002 (delivery exception). "
        "This read-only tool cannot authorize returns, issue refunds, or access a real order system."
    ),
    annotations=_READ_ONLY,
)
def get_order(order_id: str) -> dict[str, Any]:
    """Return one fictional order by its demo order ID."""
    return _read_fixture("orders", order_id.strip().upper())


@retail_mcp.tool(
    name="find_store_inventory",
    title="Read fictional store inventory",
    description=(
        "Read a fixed fictional inventory snapshot for a demo product and store. "
        "Use product_id SKU-1001 or SKU-1002 with store_id SEA-01. "
        "Results are timestamped fixtures, not live availability or a reservation."
    ),
    annotations=_READ_ONLY,
)
def find_store_inventory(product_id: str, store_id: str) -> dict[str, Any]:
    """Return a fictional product/store availability snapshot."""
    key = f"{product_id.strip().upper()}:{store_id.strip().upper()}"
    return _read_fixture("inventory", key)


@retail_mcp.tool(
    name="get_loyalty_profile",
    title="Read a fictional loyalty profile",
    description=(
        "Read a fixed fictional customer loyalty tier and illustrative benefits. "
        "Demo customer IDs: C-1001 (demo premier), C-1002 (demo member). "
        "No real customer account is accessed or modified."
    ),
    annotations=_READ_ONLY,
)
def get_loyalty_profile(customer_id: str) -> dict[str, Any]:
    """Return a fictional loyalty profile by its demo customer ID."""
    return _read_fixture("loyalty_profiles", customer_id.strip().upper())


# Build this once before accessing session_manager. For embedding in FastAPI,
# extend the parent's routes with retail_mcp_app.routes and run
# `async with retail_mcp.session_manager.run()` in the parent's lifespan.
# This keeps the exact endpoint /mcp without a trailing-slash redirect.
public_host = os.getenv("DEMO_PUBLIC_HOST", "").strip()
if public_host and any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in public_host):
    raise ValueError("DEMO_PUBLIC_HOST must be a hostname or IPv4 address, without a scheme or port")

retail_mcp_app = retail_mcp.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    host="0.0.0.0",
    transport_security=TransportSecuritySettings(
        allowed_hosts=["127.0.0.1:*", "localhost:*", "testserver"] + ([f"{public_host}:*"] if public_host else []),
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*"] + ([f"http://{public_host}:*", f"https://{public_host}:*"] if public_host else []),
    ),
)
