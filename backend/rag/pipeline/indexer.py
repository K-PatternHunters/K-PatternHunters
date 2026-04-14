"""
pipeline/indexer.py
Chunk + 임베딩 → Qdrant 저장

컬렉션: domain_docs
중복 방지: chunk_id 기준 upsert
"""

import logging

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from rag.pipeline.embedder import EMBEDDING_DIM
from rag.pipeline.loader import Chunk

log = logging.getLogger(__name__)

COLLECTION_NAME = "domain_docs"


class Indexer:
    def __init__(self, host: str = "localhost", port: int = 6333):
        self.client = QdrantClient(host=host, port=port)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """컬렉션이 없으면 생성, 있으면 그대로 사용"""
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME not in existing:
            self.client.create_collection(
                collection_name = COLLECTION_NAME,
                vectors_config  = VectorParams(
                    size     = EMBEDDING_DIM,
                    distance = Distance.COSINE,
                ),
            )
            log.info(f"Qdrant 컬렉션 생성: {COLLECTION_NAME}")
        else:
            log.info(f"Qdrant 컬렉션 사용: {COLLECTION_NAME}")

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> int:
        """
        청크 + 임베딩을 Qdrant에 upsert.
        chunk_id를 point id로 사용 (중복 적재 방지).
        Returns: upsert된 포인트 수
        """
        if len(chunks) != len(embeddings):
            raise ValueError(f"chunks({len(chunks)})와 embeddings({len(embeddings)}) 수가 다름")

        points = []
        for chunk, embedding in zip(chunks, embeddings):
            # Qdrant point id는 UUID 또는 unsigned int
            # chunk_id(MD5 hex)를 int로 변환 (상위 16자리 사용)
            point_id = int(chunk.chunk_id[:16], 16)

            points.append(PointStruct(
                id      = point_id,
                vector  = embedding,
                payload = {
                    "chunk_id": chunk.chunk_id,
                    "text":     chunk.text,
                    "source":   chunk.source,
                    "domain":   chunk.domain,
                    "heading":  chunk.heading,
                    **chunk.metadata,
                },
            ))

        self.client.upsert(
            collection_name = COLLECTION_NAME,
            points          = points,
        )
        return len(points)

    def count(self, domain: str | None = None) -> int:
        """저장된 포인트 수 반환 (도메인 필터 가능)"""
        if domain:
            result = self.client.count(
                collection_name = COLLECTION_NAME,
                count_filter    = Filter(
                    must=[FieldCondition(key="domain", match=MatchValue(value=domain))]
                ),
            )
        else:
            result = self.client.count(collection_name=COLLECTION_NAME)
        return result.count

    def delete_by_source(self, source: str) -> None:
        """특정 소스 파일의 청크 전체 삭제 (문서 업데이트 시 활용)"""
        self.client.delete(
            collection_name = COLLECTION_NAME,
            points_selector = Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=source))]
            ),
        )
        log.info(f"삭제 완료: {source}")