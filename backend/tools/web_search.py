"""DuckDuckGo web search tool."""

from __future__ import annotations

import asyncio

from duckduckgo_search import DDGS
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class WebSearchInput(BaseModel):
    """Inputs for web search."""

    query: str = Field(description="Search query string")


class WebSearchTool(BaseTool):
    """Search the public web via DuckDuckGo."""

    name: str = "web_search"
    description: str = (
        "Search the web for current information. "
        "Use when asked about recent events, current data, or anything that might "
        "have changed recently. Input: search query string."
    )
    args_schema: type[BaseModel] = WebSearchInput

    def _run(self, query: str) -> str:
        try:
            results = DDGS().text(query, max_results=5)
            if not results:
                return "No results found."
            lines: list[str] = []
            for i, item in enumerate(results, start=1):
                title = item.get("title", "")
                url = item.get("href", item.get("url", ""))
                body = item.get("body", "")
                lines.append(f"{i}. {title}\n   URL: {url}\n   {body}\n")
            return "\n".join(lines)
        except Exception as exc:
            return f"Search failed: {exc!s}"

    async def _arun(self, query: str) -> str:
        return await asyncio.to_thread(self._run, query)
