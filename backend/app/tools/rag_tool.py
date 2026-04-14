"""Qdrant-backed RAG tool — embeds a query and retrieves the top-k relevant document chunks."""

import asyncio
import logging
import os

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from rag.pipeline.embedder import Embedder
from rag.pipeline.indexer import COLLECTION_NAME

log = logging.getLogger(__name__)

QDRANT_HOST     = os.environ.get("QDRANT_HOST", "qdrant")
QDRANT_PORT     = int(os.environ.get("QDRANT_PORT", "") or 6333)
TOP_K_DEFAULT   = 5
SCORE_THRESHOLD = 0.5

# 싱글턴 — 모델과 커넥션을 프로세스당 한 번만 로드
_embedder: Embedder | None = None
_qdrant: QdrantClient | None = None


def _get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _qdrant


def _search_sync(query: str, domain: str | None, top_k: int) -> list[str]:
    vector = _get_embedder().embed_one(query)

    query_filter = None
    if domain:
        query_filter = Filter(
            must=[FieldCondition(key="domain", match=MatchValue(value=domain))]
        )

    hits = _get_qdrant().search(
        collection_name = COLLECTION_NAME,
        query_vector    = vector,
        limit           = top_k,
        query_filter    = query_filter,
        with_payload    = True,
        score_threshold = SCORE_THRESHOLD,
    )

    results = []
    for hit in hits:
        payload = hit.payload or {}
        block = (
            f"[출처: {payload.get('source', '')} | "
            f"{payload.get('heading', '')} | "
            f"유사도: {hit.score:.2f}]\n"
            f"{payload.get('text', '')}"
        )
        results.append(block)

    return results


async def rag_search(
    query:  str,
    domain: str | None = None,
    top_k:  int = TOP_K_DEFAULT,
) -> list[str]:
    """
    쿼리와 유사한 문서 청크를 Qdrant에서 검색해 반환.

    Args:
        query:  검색 쿼리 (context_agent의 domain_description)
        domain: 도메인 필터 (None이면 전체 컬렉션 검색)
        top_k:  반환할 최대 결과 수

    Returns:
        포맷된 문자열 리스트 — context_agent 프롬프트에 그대로 삽입됨
    """
    return await asyncio.to_thread(_search_sync, query, domain, top_k)
