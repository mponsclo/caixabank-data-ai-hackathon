"""Producer Cloud Function — publishes transaction chunks to Pub/Sub.

Triggered on schedule by Cloud Scheduler. Reads the next time-based chunk
of transactions from the CSV in GCS, serializes each row as a Protobuf
message, and publishes to a Pub/Sub topic. Tracks progress via a cursor
file in GCS.

Environment variables:
    GCP_PROJECT_ID  — GCP project ID
    PUBSUB_TOPIC_ID — Pub/Sub topic name
    SOURCE_BUCKET   — GCS bucket containing the CSV
    SOURCE_FILE     — CSV object path (default: transactions_data.csv)
    CURSOR_BUCKET   — GCS bucket for cursor state (default: same as SOURCE_BUCKET)
    CURSOR_PATH     — Cursor object path (default: pipeline/cursor.json)
    CHUNK_DAYS      — Number of days per chunk (default: 30)
"""

import csv
import json
import logging
import os
from datetime import datetime, timedelta

import functions_framework
import transaction_pb2
from google.cloud import pubsub_v1, storage

logger = logging.getLogger(__name__)

# Configuration
PROJECT_ID = os.environ["GCP_PROJECT_ID"]
TOPIC_ID = os.environ["PUBSUB_TOPIC_ID"]
SOURCE_BUCKET = os.environ["SOURCE_BUCKET"]
SOURCE_FILE = os.environ.get("SOURCE_FILE", "transactions_data.csv")
CURSOR_BUCKET = os.environ.get("CURSOR_BUCKET", SOURCE_BUCKET)
CURSOR_PATH = os.environ.get("CURSOR_PATH", "pipeline/cursor.json")
CHUNK_DAYS = int(os.environ.get("CHUNK_DAYS", "30"))

storage_client = storage.Client()
publisher = pubsub_v1.PublisherClient()


def _read_cursor() -> str:
    """Read the last processed timestamp from GCS cursor file."""
    bucket = storage_client.bucket(CURSOR_BUCKET)
    blob = bucket.blob(CURSOR_PATH)
    if not blob.exists():
        return "1970-01-01 00:00:00"
    data = json.loads(blob.download_as_text())
    return data["last_timestamp"]


def _write_cursor(last_timestamp: str) -> None:
    """Write the last processed timestamp to GCS cursor file."""
    bucket = storage_client.bucket(CURSOR_BUCKET)
    blob = bucket.blob(CURSOR_PATH)
    blob.upload_from_string(json.dumps({"last_timestamp": last_timestamp}), content_type="application/json")


def _parse_row(row: dict) -> transaction_pb2.Transaction:
    """Convert a CSV row dict to a Protobuf Transaction message."""
    txn = transaction_pb2.Transaction()
    txn.id = int(row["id"])
    txn.date = row["date"]
    txn.client_id = int(row["client_id"])
    txn.card_id = int(row["card_id"])
    txn.amount = row["amount"]
    txn.use_chip = row["use_chip"]
    txn.merchant_id = int(row["merchant_id"])
    txn.merchant_city = row.get("merchant_city", "")
    txn.merchant_state = row.get("merchant_state", "")
    txn.zip = row.get("zip", "")
    txn.mcc = int(row["mcc"])
    txn.errors = row.get("errors", "")
    return txn


@functions_framework.http
def produce(request):
    """HTTP entry point — reads next chunk from CSV and publishes to Pub/Sub."""
    cursor_ts = _read_cursor()
    cursor_dt = datetime.strptime(cursor_ts, "%Y-%m-%d %H:%M:%S")
    chunk_end_dt = cursor_dt + timedelta(days=CHUNK_DAYS)
    chunk_end_ts = chunk_end_dt.strftime("%Y-%m-%d %H:%M:%S")

    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

    # Stream the CSV from GCS line-by-line (avoids loading 1.2GB into memory)
    bucket = storage_client.bucket(SOURCE_BUCKET)
    blob = bucket.blob(SOURCE_FILE)

    count = 0
    skipped = 0
    last_ts = cursor_ts
    futures = []

    with blob.open("r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_ts = row["date"]

            # Skip rows at or before cursor (CSV is ordered by timestamp)
            if row_ts <= cursor_ts:
                continue

            # Stop at chunk boundary
            if row_ts > chunk_end_ts:
                break

            try:
                txn = _parse_row(row)
            except (ValueError, KeyError) as e:
                logger.warning("Skipping malformed row %s: %s", row.get("id", "?"), e)
                skipped += 1
                continue

            data = txn.SerializeToString()
            future = publisher.publish(topic_path, data)
            futures.append(future)
            last_ts = row_ts
            count += 1

    # Wait for all publishes to complete
    for future in futures:
        future.result()

    # Always advance cursor to chunk_end, even if no rows were found.
    # This prevents re-scanning the same empty window on the next run.
    _write_cursor(chunk_end_ts if count == 0 else last_ts)

    result = {
        "status": "ok",
        "chunk_start": cursor_ts,
        "chunk_end": last_ts if count > 0 else chunk_end_ts,
        "messages_published": count,
        "rows_skipped": skipped,
    }
    return (json.dumps(result), 200, {"Content-Type": "application/json"})
