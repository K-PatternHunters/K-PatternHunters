"""
로컬 NDJSON.gz → MongoDB 적재 스크립트

export_bq.py로 저장한 파일을 읽어 MongoDB에 적재.
BQ API를 전혀 사용하지 않으므로 반복 실행해도 비용 없음.

실행:
  docker compose run --rm ingest python ingest_local.py
  docker compose run --rm ingest python ingest_local.py  # 재실행 safe (upsert)
"""

import gzip
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne
from tqdm import tqdm

from transform import to_event_doc, to_item_docs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

_print_lock = threading.Lock()


# ── 환경변수 ──────────────────────────────────────────────────────────────────
MONGO_URI              = os.environ["MONGO_URI"]
MONGO_DB               = os.environ.get("MONGO_DB", "ga4_ecommerce")
MONGO_COLLECTION       = os.environ.get("MONGO_COLLECTION", "events")
MONGO_ITEMS_COLLECTION = "event_items"
DATA_DIR               = os.environ.get("DATA_DIR", "/data")
BATCH_SIZE             = int(os.environ.get("BQ_BATCH_SIZE")  or 2000)
WORKERS                = int(os.environ.get("INGEST_WORKERS") or 4)


# ── MongoDB 인덱스 ─────────────────────────────────────────────────────────────
def ensure_indexes(events_col, items_col) -> None:
    events_col.create_index([("event_date",     ASCENDING)])
    events_col.create_index([("event_date",     DESCENDING)])
    events_col.create_index([("event_datetime", ASCENDING)])
    events_col.create_index([("event_name",     ASCENDING), ("event_date", ASCENDING)])
    events_col.create_index([("event_date",     ASCENDING), ("event_name", ASCENDING)])
    events_col.create_index([
        ("user_pseudo_id",             ASCENDING),
        ("user_first_touch_timestamp", ASCENDING),
    ])
    events_col.create_index([
        ("user_pseudo_id",  ASCENDING),
        ("ga_session_id",   ASCENDING),
        ("event_timestamp", ASCENDING),
    ])
    events_col.create_index([("page_location",          ASCENDING)])
    events_col.create_index([("traffic_source.source",  ASCENDING)])
    events_col.create_index([("traffic_source.medium",  ASCENDING)])
    events_col.create_index([("device.category",        ASCENDING)])
    events_col.create_index([("geo.country",            ASCENDING)])
    events_col.create_index([("ecommerce.transaction_id", ASCENDING)])

    items_col.create_index([("event_date",     ASCENDING)])
    items_col.create_index([("event_name",     ASCENDING)])
    items_col.create_index([("user_pseudo_id", ASCENDING)])
    items_col.create_index([("item_id",        ASCENDING)])
    items_col.create_index([("item_name",      ASCENDING)])

    log.info("인덱스 확인/생성 완료")


# ── 파일 탐색 ─────────────────────────────────────────────────────────────────
def find_data_files() -> list[str]:
    """DATA_DIR에서 .ndjson.gz 파일 목록 반환 (날짜순 정렬)"""
    if not os.path.isdir(DATA_DIR):
        raise FileNotFoundError(
            f"데이터 디렉터리 없음: {DATA_DIR}\n"
            f"먼저 export_bq.py를 실행하세요."
        )
    files = sorted(
        os.path.join(DATA_DIR, f)
        for f in os.listdir(DATA_DIR)
        if f.endswith(".ndjson.gz")
    )
    if not files:
        raise FileNotFoundError(
            f"{DATA_DIR} 에 .ndjson.gz 파일이 없습니다.\n"
            f"먼저 export_bq.py를 실행하세요."
        )
    return files


# ── 파일 단위 적재 ────────────────────────────────────────────────────────────
def ingest_file(filepath: str, events_col, items_col) -> tuple[int, int]:
    """
    .ndjson.gz 파일 1개를 읽어 MongoDB에 upsert.
    라인 단위 스트리밍 → 메모리 사용 최소화.
    """
    total_events = 0
    total_items  = 0

    event_ops: list[UpdateOne] = []
    item_ops:  list[UpdateOne] = []

    def flush():
        nonlocal total_events, total_items
        if event_ops:
            events_col.bulk_write(event_ops, ordered=False)
            total_events += len(event_ops)
            event_ops.clear()
        if item_ops:
            items_col.bulk_write(item_ops, ordered=False)
            total_items += len(item_ops)
            item_ops.clear()

    with gzip.open(filepath, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                log.warning(f"JSON 파싱 오류 ({filepath}): {e}")
                continue

            doc = to_event_doc(row)
            event_ops.append(
                UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
            )

            for item_doc in to_item_docs(row):
                item_ops.append(
                    UpdateOne({"_id": item_doc["_id"]}, {"$set": item_doc}, upsert=True)
                )

            # 배치가 찼으면 flush
            if len(event_ops) >= BATCH_SIZE:
                flush()

    # 남은 배치 flush
    flush()

    return total_events, total_items


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main() -> None:
    files = find_data_files()

    total_size_mb = sum(os.path.getsize(f) for f in files) / 1024 / 1024

    log.info(
        f"로컬 NDJSON.gz → MongoDB 적재 시작\n"
        f"  파일 수    : {len(files)}개\n"
        f"  전체 크기  : {total_size_mb:.1f} MB (gzip 압축)\n"
        f"  병렬 수    : {WORKERS} workers\n"
        f"  배치 크기  : {BATCH_SIZE:,}건"
    )

    mongo      = MongoClient(MONGO_URI)
    events_col = mongo[MONGO_DB][MONGO_COLLECTION]
    items_col  = mongo[MONGO_DB][MONGO_ITEMS_COLLECTION]

    ensure_indexes(events_col, items_col)

    total_events = 0
    total_items  = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {
            executor.submit(ingest_file, f, events_col, items_col): f
            for f in files
        }
        with tqdm(total=len(files), desc="파일 적재") as pbar:
            for future in as_completed(futures):
                fpath = futures[future]
                fname = os.path.basename(fpath)
                try:
                    ev_cnt, item_cnt = future.result()
                    total_events += ev_cnt
                    total_items  += item_cnt
                    with _print_lock:
                        log.info(f"[{fname}] events {ev_cnt:,}건  items {item_cnt:,}건")
                except Exception as e:
                    with _print_lock:
                        log.error(f"[{fname}] 실패: {e}")
                finally:
                    pbar.update(1)

    log.info(
        f"적재 완료\n"
        f"  events     : {total_events:,}건 → {MONGO_DB}.{MONGO_COLLECTION}\n"
        f"  event_items: {total_items:,}건  → {MONGO_DB}.{MONGO_ITEMS_COLLECTION}"
    )
    mongo.close()


if __name__ == "__main__":
    main()