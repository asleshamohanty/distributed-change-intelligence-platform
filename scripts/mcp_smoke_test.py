"""Ad hoc verification that all six MCP tools are actually callable over
Streamable HTTP — not just that the server process started. Not part of the
app; run manually: `python scripts/mcp_smoke_test.py`.
"""
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = "http://localhost:8100/mcp"


async def main() -> None:
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Registered tools:", [t.name for t in tools.tools])

            calls = [
                ("get_change_details", {"service": "order-service"}),
                ("get_dependency_graph", {"service": "order-service"}),
                ("get_blast_radius", {"service": "order-service"}),
                ("get_service_telemetry", {"service": "order-service"}),
                ("get_anomalies", {}),
                ("search_historical_incidents", {"query": "order service deploy latency spike", "limit": 2}),
            ]
            for name, args in calls:
                result = await session.call_tool(name, args)
                text = result.content[0].text if result.content else "<empty>"
                print(f"\n=== {name}({args}) ===")
                print(text[:500])


if __name__ == "__main__":
    asyncio.run(main())
