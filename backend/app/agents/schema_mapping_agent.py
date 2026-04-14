"""Maps raw GA4 log fields to a normalised internal schema for downstream agent consumption."""

# TODO: query raw_logs collection from MongoDB
# TODO: use LLM to infer field meanings if schema differs from standard GA4 spec
# TODO: output normalised schema + mapped dataset reference to pipeline state


async def schema_mapping_agent(state: dict) -> dict:
    # Placeholder — implementation pending
    raise NotImplementedError
