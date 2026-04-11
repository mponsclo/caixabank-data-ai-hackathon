"""Consumer Cloud Function — writes Pub/Sub transactions to BigQuery.

Triggered by Pub/Sub messages via EventArc. Receives a CloudEvent containing
a Pub/Sub message with a Protobuf-serialized Transaction, deserializes it,
and performs a streaming insert to BigQuery.

Environment variables:
    GCP_PROJECT_ID — GCP project ID
    BQ_DATASET     — BigQuery dataset (default: landing)
    BQ_TABLE       — BigQuery table (default: transactions_data_stream)
"""

import base64
import os

import functions_framework
import transaction_pb2
from cloudevents.http import CloudEvent
from google.cloud import bigquery

PROJECT_ID = os.environ["GCP_PROJECT_ID"]


def _safe_float(value: str):
    """Convert string to float, returning None for empty or invalid values."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


DATASET_ID = os.environ.get("BQ_DATASET", "landing")
TABLE_ID = os.environ.get("BQ_TABLE", "transactions_data_stream")

bq_client = bigquery.Client(project=PROJECT_ID)


def _proto_to_bq_row(txn: transaction_pb2.Transaction) -> dict:
    """Convert a Protobuf Transaction to a BigQuery row dict."""
    return {
        "id": str(txn.id),
        "date": txn.date,
        "client_id": txn.client_id,
        "card_id": txn.card_id,
        "amount": txn.amount,
        "use_chip": txn.use_chip,
        "merchant_id": txn.merchant_id,
        "merchant_city": txn.merchant_city,
        "merchant_state": txn.merchant_state,
        "zip": _safe_float(txn.zip),
        "mcc": txn.mcc,
        "errors": txn.errors,
    }


@functions_framework.cloud_event
def consume(cloud_event: CloudEvent):
    """CloudEvent entry point — triggered by Pub/Sub via EventArc."""
    data = base64.b64decode(cloud_event.data["message"]["data"])

    txn = transaction_pb2.Transaction()
    txn.ParseFromString(data)

    row = _proto_to_bq_row(txn)
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    errors = bq_client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"BigQuery streaming insert failed: {errors}")
