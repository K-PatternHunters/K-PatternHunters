"""
pipeline/embedder.py
텍스트 → 임베딩 벡터 변환

모델: BAAI/bge-base-en-v1.5 (768차원, 로컬 실행)
trust_remote_code 불필요, MTEB English 기준 OpenAI text-embedding-3-small 대비 동급 이상 성능
"""

import logging

from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
EMBEDDING_DIM   = 768
BATCH_SIZE      = 64


class Embedder:
    def __init__(self):
        log.info(f"임베딩 모델 로드 중: {EMBEDDING_MODEL}")
        self.model = SentenceTransformer(EMBEDDING_MODEL)
        self.dim   = EMBEDDING_DIM

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        텍스트 배열 → 임베딩 배열 (배치 처리)
        빈 문자열은 자동으로 공백으로 대체
        """
        safe_texts = [t.strip() or " " for t in texts]

        all_embeddings: list[list[float]] = []

        for i in range(0, len(safe_texts), BATCH_SIZE):
            batch = safe_texts[i : i + BATCH_SIZE]
            vecs = self.model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            all_embeddings.extend(vecs.tolist())

        return all_embeddings

    def embed_one(self, text: str) -> list[float]:
        """단일 텍스트 임베딩 (검색 쿼리용)"""
        return self.embed_batch([text])[0]
