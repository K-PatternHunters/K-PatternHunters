"""
ingest_docs.py
documents/ 폴더의 문서를 Qdrant에 적재하는 실행 스크립트

실행:
  docker compose run --rm rag python ingest_docs.py
  docker compose run --rm rag python ingest_docs.py --reset   # 기존 컬렉션 초기화 후 재적재
"""

import argparse
import logging
import os
import sys

from tqdm import tqdm

from rag.pipeline.embedder import Embedder
from rag.pipeline.indexer import Indexer
from rag.pipeline.loader import load_and_chunk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DOCS_ROOT    = os.environ.get("DOCS_ROOT",    "/app/rag/documents")
QDRANT_HOST  = os.environ.get("QDRANT_HOST",  "qdrant")
QDRANT_PORT  = int(os.environ.get("QDRANT_PORT", "") or 6333)
EMBED_BATCH  = int(os.environ.get("EMBED_BATCH_SIZE", "") or 50)
CHUNK_CHARS  = int(os.environ.get("CHUNK_MAX_CHARS",  "") or 1000)
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP",   "") or 100)


def main(reset: bool = False) -> None:
    log.info(
        f"RAG 문서 적재 시작\n"
        f"  문서 경로 : {DOCS_ROOT}\n"
        f"  Qdrant   : {QDRANT_HOST}:{QDRANT_PORT}\n"
        f"  청크 크기 : {CHUNK_CHARS}자 (overlap {CHUNK_OVERLAP}자)"
    )

    # ── 1. 문서 로드 및 청킹 ─────────────────────────────────────────────────
    log.info("① 문서 로드 및 청킹 중...")
    chunks = load_and_chunk(DOCS_ROOT, max_chars=CHUNK_CHARS, overlap=CHUNK_OVERLAP)

    if not chunks:
        log.error(f"{DOCS_ROOT} 에 처리 가능한 문서가 없습니다. (.md, .txt, .pdf 지원)")
        sys.exit(1)

    log.info(f"   총 {len(chunks)}개 청크 생성")

    # 도메인별 통계
    from collections import Counter
    domain_counts = Counter(c.domain for c in chunks)
    for domain, count in sorted(domain_counts.items()):
        log.info(f"   - {domain}: {count}개")

    # ── 2. Qdrant 연결 및 컬렉션 준비 ────────────────────────────────────────
    log.info("② Qdrant 연결 중...")
    indexer = Indexer(host=QDRANT_HOST, port=QDRANT_PORT)

    if reset:
        log.info("   컬렉션 초기화 (--reset 옵션)")
        try:
            indexer.client.delete_collection(collection_name="domain_docs")
        except Exception:
            pass
        indexer._ensure_collection()

    # ── 3. 임베딩 생성 ────────────────────────────────────────────────────────
    log.info("③ 임베딩 생성 중 (gte-large-en-v1.5)...")
    embedder   = Embedder()
    texts      = [c.text for c in chunks]
    embeddings = []

    for i in tqdm(range(0, len(texts), EMBED_BATCH), desc="임베딩 배치"):
        batch = texts[i : i + EMBED_BATCH]
        embeddings.extend(embedder.embed_batch(batch))

    # ── 4. Qdrant 저장 ────────────────────────────────────────────────────────
    log.info("④ Qdrant 저장 중...")
    upserted = indexer.upsert(chunks, embeddings)

    total = indexer.count()
    log.info(
        f"적재 완료\n"
        f"  upsert : {upserted}개\n"
        f"  전체   : {total}개 포인트 (domain_docs 컬렉션)"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reset",
        action="store_true",
        help="기존 컬렉션 초기화 후 재적재"
    )
    args = parser.parse_args()
    main(reset=args.reset)