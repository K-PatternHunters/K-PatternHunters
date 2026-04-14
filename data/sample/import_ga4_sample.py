"""Imports the GA4 obfuscated sample e-commerce dataset into the MongoDB raw_logs collection."""

# Dataset: BigQuery public dataset — bigquery-public-data.ga4_obfuscated_sample_ecommerce
# Reference: https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset
#
# TODO: Step 1 — download / export GA4 sample data from BigQuery as NDJSON or CSV
#   Option A: bq extract --destination_format NEWLINE_DELIMITED_JSON ...
#   Option B: use google-cloud-bigquery Python client to stream rows directly
#
# TODO: Step 2 — transform each row to match RawLog schema (app.core.models.RawLog)
#   Key fields: event_date, event_timestamp, event_name, user_pseudo_id,
#               ecommerce (nested), items (array), traffic_source, device, geo
#
# TODO: Step 3 — bulk insert into MongoDB raw_logs collection
#   Use insert_many() with ordered=False for best throughput
#   Add indexes: { event_date: 1 }, { user_pseudo_id: 1 }, { event_name: 1 }
#
# TODO: Step 4 — print summary: total docs inserted, date range, unique users
#
# Usage (inside Docker):
#   docker compose exec backend python data/sample/import_ga4_sample.py


def main():
    # Placeholder — implementation pending
    raise NotImplementedError("Implement GA4 import logic before running.")


if __name__ == "__main__":
    main()
