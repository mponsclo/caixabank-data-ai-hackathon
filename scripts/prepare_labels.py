"""
Convert train_fraud_labels.json (nested dict) to CSV for BigQuery loading.

Input format:  {"target": {"txn_id_1": "Yes", "txn_id_2": "No", ...}}
Output format: transaction_id,is_fraud (CSV with header)
"""

import csv
import json
import os

INPUT_PATH = "data/raw/train_fraud_labels.json"
OUTPUT_PATH = "data/processed/train_fraud_labels.csv"


def main():
    with open(INPUT_PATH) as f:
        data = json.load(f)

    # The JSON has a "target" key wrapping the dict
    labels = data.get("target", data)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["transaction_id", "is_fraud"])
        for txn_id, label in labels.items():
            writer.writerow([txn_id, label])

    print(f"Wrote {len(labels):,} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
