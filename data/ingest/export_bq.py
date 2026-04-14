"""
BigQuery → 로컬 NDJSON.gz 파일 추출 스크립트 (1회만 실행)

BigQuery API를 1회만 사용해 로컬에 파일로 저장.
이후 ingest_local.py로 반복 적재 가능 (BQ 비용 없음).

출력 파일: {DATA_DIR}/events_{start}_{end}.ndjson.gz

실행:
  docker compose run --rm ingest python export_bq.py
  docker compose run --rm ingest python export_bq.py  # 재시도 시 이미 있는 청크는 스킵
"""

import gzip
import json
import logging
import os
import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, date, time

from google.cloud import bigquery
from google.oauth2 import service_account
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)
_print_lock = threading.Lock()


# ── 환경변수 ──────────────────────────────────────────────────────────────────
BQ_PROJECT_ID  = os.environ["BQ_PROJECT_ID"]
BQ_DATASET     = os.environ.get(
    "BQ_DATASET", "bigquery-public-data.ga4_obfuscated_sample_ecommerce"
)
BQ_DATE_START  = os.environ.get("BQ_DATE_START", "20201101")
BQ_DATE_END    = os.environ.get("BQ_DATE_END",   "20210131")
BQ_CHUNK_DAYS  = int(os.environ.get("BQ_CHUNK_DAYS")  or 7)
EXPORT_WORKERS = int(os.environ.get("INGEST_WORKERS") or 4)
PAGE_SIZE      = int(os.environ.get("BQ_BATCH_SIZE")  or 2000)
DATA_DIR       = os.environ.get("DATA_DIR", "/data")
SA_KEY_PATH    = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS", "/secrets/sa-key.json"
)


# ── JSON 직렬화 ───────────────────────────────────────────────────────────────
class _BQEncoder(json.JSONEncoder):
    """BQ Row에서 나오는 특수 타입 처리"""
    def default(self, obj):
        if isinstance(obj, (datetime, date, time)):
            return obj.isoformat()
        try:
            import decimal
            if isinstance(obj, decimal.Decimal):
                return float(obj)
        except ImportError:
            pass
        try:
            # BigQuery Row / struct → dict 변환
            return dict(obj)
        except (TypeError, ValueError):
            pass
        return super().default(obj)


def row_to_dict(row) -> dict:
    """BQ Row → JSON 직렬화 가능한 순수 dict"""
    def _convert(val):
        if val is None:
            return None
        if isinstance(val, (str, int, float, bool)):
            return val
        if isinstance(val, (datetime, date, time)):
            return val.isoformat()
        if isinstance(val, list):
            return [_convert(v) for v in val]
        try:
            # BigQuery Row, struct, RECORD → dict
            d = dict(val)
            return {k: _convert(v) for k, v in d.items()}
        except (TypeError, ValueError):
            return str(val)

    return {k: _convert(v) for k, v in dict(row).items()}


# ── BigQuery 클라이언트 ────────────────────────────────────────────────────────
def make_bq_client() -> bigquery.Client:
    creds = service_account.Credentials.from_service_account_file(
        SA_KEY_PATH,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return bigquery.Client(project=BQ_PROJECT_ID, credentials=creds)


# ── 날짜 청크 ─────────────────────────────────────────────────────────────────
def make_chunks(start: str, end: str, chunk_days: int) -> list[tuple[str, str]]:
    cur = datetime.strptime(start, "%Y%m%d")
    fin = datetime.strptime(end,   "%Y%m%d")
    chunks = []
    while cur <= fin:
        chunk_end = min(cur + timedelta(days=chunk_days - 1), fin)
        chunks.append((cur.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
        cur = chunk_end + timedelta(days=1)
    return chunks


def chunk_filepath(start: str, end: str) -> str:
    return os.path.join(DATA_DIR, f"events_{start}_{end}.ndjson.gz")


# ── 청크 export ───────────────────────────────────────────────────────────────
def export_chunk(chunk_start: str, chunk_end: str) -> tuple[str, int]:
    """
    BQ 쿼리 결과를 NDJSON.gz 파일로 저장.
    이미 파일이 존재하면 스킵 (재실행 안전).
    Returns: (filepath, row_count)
    """
    fpath = chunk_filepath(chunk_start, chunk_end)

    # 이미 존재하는 청크는 스킵 (재실행 시 BQ 비용 절약)
    if os.path.exists(fpath):
        log.info(f"[{chunk_start}~{chunk_end}] 이미 존재 — 스킵")
        return fpath, 0

    bq = make_bq_client()

    query = f"""
        SELECT
            event_date,
            event_timestamp,
            event_name,
            event_params,
            event_previous_timestamp,
            event_value_in_usd,
            event_bundle_sequence_id,
            event_server_timestamp_offset,
            user_id,
            user_pseudo_id,
            user_properties,
            user_first_touch_timestamp,
            user_ltv,
            device,
            geo,
            traffic_source,
            stream_id,
            platform,
            ecommerce,
            items
        FROM `{BQ_DATASET}.events_*`
        WHERE _TABLE_SUFFIX BETWEEN '{chunk_start}' AND '{chunk_end}'
    """

    try:
        with _print_lock:
            log.info(f"[{chunk_start}~{chunk_end}] ① BQ 쿼리 제출 중...")
        query_job = bq.query(query)

        with _print_lock:
            log.info(f"[{chunk_start}~{chunk_end}] ② BQ 실행 대기 중... (job_id: {query_job.job_id})")
        result = query_job.result(page_size=PAGE_SIZE)

        with _print_lock:
            log.info(f"[{chunk_start}~{chunk_end}] ③ 결과 수신 시작 → 파일 저장 중...")
    except Exception as e:
        log.error(f"[{chunk_start}~{chunk_end}] BQ 쿼리 실패: {e}")
        raise

    row_count = 0
    page_num  = 0
    tmp_path  = fpath + ".tmp"
    try:
        with gzip.open(tmp_path, "wt", encoding="utf-8") as f:
            for page in result.pages:
                page_num += 1
                for row in page:
                    f.write(json.dumps(row_to_dict(row), ensure_ascii=False))
                    f.write("\n")
                    row_count += 1
                # 페이지마다 진행 상황 출력
                with _print_lock:
                    log.info(
                        f"[{chunk_start}~{chunk_end}] "
                        f"page {page_num} — 누적 {row_count:,}행 저장 중..."
                    )
        os.rename(tmp_path, fpath)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return fpath, row_count


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

    chunks = make_chunks(BQ_DATE_START, BQ_DATE_END, BQ_CHUNK_DAYS)

    # 이미 완료된 청크 확인
    done    = [c for c in chunks if os.path.exists(chunk_filepath(*c))]
    pending = [c for c in chunks if not os.path.exists(chunk_filepath(*c))]

    log.info(
        f"BQ → 로컬 NDJSON.gz 추출 시작\n"
        f"  기간       : {BQ_DATE_START} ~ {BQ_DATE_END}\n"
        f"  전체 청크  : {len(chunks)}개\n"
        f"  완료(스킵) : {len(done)}개\n"
        f"  추출 예정  : {len(pending)}개\n"
        f"  병렬 수    : {EXPORT_WORKERS} workers\n"
        f"  저장 경로  : {DATA_DIR}"
    )

    if not pending:
        log.info("모든 청크가 이미 존재합니다. ingest_local.py를 실행하세요.")
        return

    total_rows = 0

    with ThreadPoolExecutor(max_workers=EXPORT_WORKERS) as executor:
        futures = {
            executor.submit(export_chunk, s, e): (s, e)
            for s, e in pending
        }
        with tqdm(total=len(pending), desc="청크 추출") as pbar:
            for future in as_completed(futures):
                s, e = futures[future]
                try:
                    fpath, count = future.result()
                    total_rows += count
                    sz_mb = os.path.getsize(fpath) / 1024 / 1024
                    log.info(f"[{s}~{e}] {count:,}행 → {sz_mb:.1f} MB")
                except Exception as err:
                    log.error(f"[{s}~{e}] 실패: {err}")
                finally:
                    pbar.update(1)

    # 최종 파일 목록 및 총 크기
    total_mb = sum(
        os.path.getsize(chunk_filepath(*c)) / 1024 / 1024
        for c in chunks
        if os.path.exists(chunk_filepath(*c))
    )
    log.info(
        f"추출 완료\n"
        f"  신규 추출 행 : {total_rows:,}건\n"
        f"  전체 파일 크기: {total_mb:.1f} MB (gzip 압축)\n"
        f"  저장 위치    : {DATA_DIR}\n\n"
        f"다음 단계:\n"
        f"  docker compose run --rm ingest python ingest_local.py"
    )


if __name__ == "__main__":
    main()