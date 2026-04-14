"""Schema Mapping Agent — maps raw GA4 log fields to a normalised internal schema.

Input  (PipelineState keys consumed):
    raw_logs       : list[dict]   — weekly raw log records
    domain_context : dict         — DomainContext.model_dump() (log_schema_hints used)

Output (PipelineState keys produced):
    field_mapping  : dict         — raw field path → normalised field name
"""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Standard GA4 BigQuery export field mapping (known spec)
# ---------------------------------------------------------------------------

_STANDARD_GA4_MAPPING: dict[str, str] = {
    # Top-level event fields
    "event_date": "event_date",
    "event_name": "event_name",
    "event_timestamp": "event_timestamp",
    "user_pseudo_id": "user_pseudo_id",
    # event_params array (extracted by key)
    "event_params[key=session_id].value.int_value": "session_id",
    "event_params[key=page_location].value.string_value": "page_location",
    "event_params[key=source].value.string_value": "traffic_source",
    "event_params[key=medium].value.string_value": "traffic_medium",
    "event_params[key=value].value.float_value": "event_value",
    "event_params[key=engagement_time_msec].value.int_value": "engagement_time_msec",
    "event_params[key=ga_session_id].value.int_value": "session_id",
    # ecommerce fields
    "ecommerce.transaction_id": "transaction_id",
    "ecommerce.purchase_revenue": "purchase_revenue",
    "ecommerce.tax": "tax",
    "ecommerce.shipping": "shipping",
    # items array
    "items[].item_id": "item_id",
    "items[].item_name": "item_name",
    "items[].item_category": "item_category",
    "items[].price": "item_price",
    "items[].quantity": "item_quantity",
    # device / geo
    "device.category": "device_category",
    "device.mobile_brand_name": "device_brand",
    "geo.country": "geo_country",
    "geo.city": "geo_city",
    # traffic source (top-level)
    "traffic_source.source": "traffic_source",
    "traffic_source.medium": "traffic_medium",
    "traffic_source.name": "traffic_campaign",
}

# Normalised names that must be present for downstream agents to work
_REQUIRED_NORMALISED_FIELDS: set[str] = {
    "event_date",
    "event_name",
    "event_timestamp",
    "user_pseudo_id",
    "session_id",
    "purchase_revenue",
    "transaction_id",
    "device_category",
    "traffic_source",
    "item_category",
}

_LLM_SYSTEM_PROMPT = """\
You are a data-engineering assistant specialising in GA4 event log schemas.

You will be given:
1. A list of top-level field names found in a raw log document.
2. A sample raw log document (JSON).
3. A standard GA4 field mapping that already covers most fields.

Your task: for any field present in the document that is NOT yet covered by the
standard mapping, infer its semantic meaning and propose an additional mapping entry.

Output ONLY a JSON object (no markdown, no explanation) of the form:
{
  "raw_field_path": "normalised_field_name",
  ...
}

If no additional mappings are needed, output an empty JSON object: {}
"""


def _extract_top_level_fields(sample: dict) -> list[str]:
    return list(sample.keys())


def _unmapped_fields(sample: dict, existing_mapping: dict[str, str]) -> list[str]:
    """Return top-level fields not yet covered (directly or as prefix) by the mapping."""
    covered_prefixes = {k.split(".")[0].split("[")[0] for k in existing_mapping}
    return [f for f in sample if f not in covered_prefixes]


async def _llm_infer_extra_mappings(
    sample: dict,
    existing_mapping: dict[str, str],
    schema_hints: dict[str, str],
) -> dict[str, str]:
    """Call LLM only when there are unmapped fields not covered by schema_hints."""
    unmapped = _unmapped_fields(sample, existing_mapping)
    # Remove fields already covered by schema_hints
    unmapped = [f for f in unmapped if f not in schema_hints]
    if not unmapped:
        return {}

    settings = get_settings()
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=settings.OPENAI_API_KEY)

    human = (
        f"Top-level fields in document: {unmapped}\n\n"
        f"Sample document (truncated):\n{json.dumps(sample, ensure_ascii=False, default=str)[:3000]}\n\n"
        f"Standard mapping already covers:\n{json.dumps(list(existing_mapping.keys()), ensure_ascii=False)}"
    )

    response = await llm.ainvoke(
        [SystemMessage(content=_LLM_SYSTEM_PROMPT), HumanMessage(content=human)]
    )
    try:
        extra: dict[str, str] = json.loads(response.content)
        return {k: v for k, v in extra.items() if isinstance(k, str) and isinstance(v, str)}
    except (json.JSONDecodeError, AttributeError):
        logger.warning("schema_mapping_agent: LLM returned non-JSON response — skipping extra mappings")
        return {}


async def schema_mapping_agent(state: dict) -> dict:
    """LangGraph node: build field_mapping from raw log schema.

    Reads up to 100 sample documents from state['raw_logs'] (no full load).
    Uses standard GA4 mapping as baseline; calls LLM only for unknown fields.
    """
    raw_logs: list[dict] = state.get("raw_logs", [])
    domain_context: dict = state.get("domain_context", {})
    schema_hints: dict[str, str] = domain_context.get("log_schema_hints", {})

    # Start from the known standard mapping
    field_mapping: dict[str, str] = dict(_STANDARD_GA4_MAPPING)

    # Merge schema hints from context_agent (highest priority)
    field_mapping.update(schema_hints)

    if not raw_logs:
        logger.warning("schema_mapping_agent: no raw_logs in state — returning standard mapping only")
        return {"field_mapping": field_mapping}

    # Sample at most 100 documents (volume safety)
    sample_docs = raw_logs[:100]
    representative_doc = sample_docs[0]

    # Check for fields not covered by standard mapping
    unmapped = _unmapped_fields(representative_doc, field_mapping)
    if unmapped:
        logger.info("schema_mapping_agent: unmapped fields detected %s — calling LLM", unmapped)
        extra = await _llm_infer_extra_mappings(representative_doc, field_mapping, schema_hints)
        if extra:
            logger.info("schema_mapping_agent: LLM added %d extra mappings", len(extra))
            field_mapping.update(extra)
    else:
        logger.info("schema_mapping_agent: all fields covered by standard mapping — no LLM call needed")

    # Warn about missing required normalised fields
    covered_normalised = set(field_mapping.values())
    missing = _REQUIRED_NORMALISED_FIELDS - covered_normalised
    if missing:
        logger.warning("schema_mapping_agent: required normalised fields not found: %s", missing)

    return {"field_mapping": field_mapping}
