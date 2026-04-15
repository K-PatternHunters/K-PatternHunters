"""Web search tool — Tavily-backed live search for domain research enrichment."""

from __future__ import annotations

import asyncio
import logging

from tavily import TavilyClient

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: TavilyClient | None = None


def _get_client() -> TavilyClient:
    global _client
    settings = get_settings()
    if not settings.TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    if _client is None:
        _client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    return _client


def _search_sync(query: str, max_results: int) -> list[str]:
    response = _get_client().search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_answer=False,
        include_raw_content=False,
    )

    results: list[str] = []
    for item in response.get("results", []):
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        content = item.get("content", "").strip()

        block = f"[출처: {title} | {url}]\n{content}" if title or url else content
        if block:
            results.append(block)

    return results


async def web_search(query: str, max_results: int = 5) -> list[str]:
    """Search the web with Tavily and return compact snippets for prompt context."""
    try:
        return await asyncio.to_thread(_search_sync, query, max_results)
    except Exception as exc:  # noqa: BLE001
        logger.warning("web_search failed: %s", exc)
        return []
