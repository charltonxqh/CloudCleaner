"""Synchronous CloudCleaner client for the read-only MCP server."""

import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor

from mcp import Client


def enabled() -> bool:
    return bool(os.getenv("CLOUDCLEANER_MCP_URL"))


async def _call_tool_async(name: str, arguments: dict) -> dict:
    url = os.environ["CLOUDCLEANER_MCP_URL"]

    async with Client(url) as client:
        result = await client.call_tool(name, arguments)

    if result.is_error:
        messages = [
            getattr(block, "text", "")
            for block in result.content
            if getattr(block, "text", "")
        ]
        detail = "; ".join(messages) or f"MCP tool {name} failed"
        raise RuntimeError(detail)

    if result.structured_content is not None:
        return result.structured_content

    for block in result.content:
        text = getattr(block, "text", None)
        if not text:
            continue

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue

        if isinstance(payload, dict):
            return payload

    raise RuntimeError(f"MCP tool {name} returned no structured content")


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def call_tool(name: str, arguments: dict | None = None) -> dict:
    return _run(_call_tool_async(name, arguments or {}))