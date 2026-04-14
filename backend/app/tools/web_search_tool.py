"""Web search tool — wraps an external search API (e.g. Tavily or SerpAPI) for live domain research."""

# TODO: choose search provider (Tavily recommended for LangChain v1.0+)
# TODO: wrap as a @tool decorated function returning a list of result snippets
# TODO: used exclusively by context_agent for live domain context enrichment

# from langchain_community.tools.tavily_search import TavilySearchResults  # langchain v1.0+


async def web_search(query: str, max_results: int = 5):
    # Placeholder — implementation pending
    raise NotImplementedError
