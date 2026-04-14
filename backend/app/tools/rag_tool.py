"""Qdrant-backed RAG tool — embeds a query and retrieves the top-k relevant document chunks."""

# TODO: accept query string + optional collection_name override
# TODO: embed query with OpenAIEmbeddings (langchain_openai — v1.0+ import path)
# TODO: search Qdrant collection and return top-k results as LangChain Documents
# TODO: wrap as a @tool decorated function for LangGraph agent tool use

# from langchain_openai import OpenAIEmbeddings  # langchain v1.0+ import path
# from langchain_core.tools import tool            # langchain v1.0+ import path


async def rag_search(query: str, collection_name: str = "reports", top_k: int = 5):
    # Placeholder — implementation pending
    raise NotImplementedError
