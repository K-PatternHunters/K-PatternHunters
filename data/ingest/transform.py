"""
공통 변환 로직 — ingest.py / ingest_local.py 양쪽에서 import해서 사용.
BigQuery Row 또는 JSON dict 모두 처리 가능 (duck typing).
"""

import hashlib
from datetime import datetime, timezone

_PLACEHOLDERS = {"<Other>", "(other)", "(not set)", ""}

_ITEM_EVENTS = {
    "purchase", "add_to_cart", "remove_from_cart",
    "view_item", "view_item_list", "begin_checkout",
}


def flatten_params(params: list[dict]) -> dict:
    """
    event_params / user_properties REPEATED RECORD → flat dict
    int_value=0 같은 falsy 값도 누락되지 않도록 None 명시 체크 사용.
    """
    result = {}
    for p in (params or []):
        key = p.get("key")
        if not key:
            continue
        val = p.get("value") or {}
        extracted = next(
            (
                val[k]
                for k in ("string_value", "int_value", "float_value", "double_value")
                if val.get(k) is not None
            ),
            None,
        )
        result[key] = extracted
    return result


def clean_str(value) -> str | None:
    """obfuscated 플레이스홀더 → None 정규화"""
    if value is None:
        return None
    s = str(value).strip()
    return None if s in _PLACEHOLDERS else s


def ts_to_dt(ts) -> datetime | None:
    """마이크로초 timestamp → timezone-aware datetime (UTC)"""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts) / 1_000_000, tz=timezone.utc)
    except (ValueError, OSError):
        return None


def make_event_id(d: dict) -> str:
    raw = (
        f"{d.get('event_date')}_{d.get('event_timestamp')}"
        f"_{d.get('user_pseudo_id')}_{d.get('event_name')}"
        f"_{d.get('event_bundle_sequence_id')}"
    )
    return hashlib.md5(raw.encode()).hexdigest()


def to_event_doc(row: dict) -> dict:
    """
    BQ Row(dict) / JSON dict → events 컬렉션 문서.
    원본 dict를 수정하지 않고 새 dict를 반환.
    """
    d = dict(row)

    ep_flat = flatten_params(d.pop("event_params",    None) or [])
    up_flat = flatten_params(d.pop("user_properties", None) or [])
    d["event_params_flat"]    = ep_flat
    d["user_properties_flat"] = up_flat

    d.pop("items",    None)
    d.pop("app_info", None)

    d["user_id"] = clean_str(d.get("user_id"))
    if isinstance(d.get("traffic_source"), dict):
        d["traffic_source"] = {k: clean_str(v) for k, v in d["traffic_source"].items()}

    d["event_datetime"] = ts_to_dt(d.get("event_timestamp"))

    # 세션/페이지 필드 최상위 승격 (인덱스 활용)
    d["ga_session_id"]        = ep_flat.get("ga_session_id")
    d["ga_session_number"]    = ep_flat.get("ga_session_number")
    d["page_location"]        = ep_flat.get("page_location")
    d["page_title"]           = ep_flat.get("page_title")
    d["engagement_time_msec"] = ep_flat.get("engagement_time_msec")
    d["session_engaged"]      = ep_flat.get("session_engaged")

    d["_id"] = make_event_id(d)
    return d


def to_item_docs(row: dict) -> list[dict]:
    """구매 관련 이벤트의 items → event_items 컬렉션 문서 목록"""
    event_name = row.get("event_name", "")
    if event_name not in _ITEM_EVENTS:
        return []

    items = row.get("items") or []
    if not items:
        return []

    ts         = row.get("event_timestamp")
    uid        = row.get("user_pseudo_id")
    event_date = row.get("event_date")
    event_dt   = ts_to_dt(ts)

    docs = []
    for idx, item in enumerate(items):
        item_dict = dict(item) if item else {}
        item_dict.update({
            "event_name":      event_name,
            "event_timestamp": ts,
            "event_date":      event_date,
            "event_datetime":  event_dt,
            "user_pseudo_id":  uid,
        })
        raw = f"{ts}_{uid}_{event_name}_{idx}"
        item_dict["_id"] = hashlib.md5(raw.encode()).hexdigest()
        docs.append(item_dict)

    return docs