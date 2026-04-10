"""Task 1: Data queries using DuckDB.

Each function takes file paths, creates an in-memory DuckDB connection,
and returns query results as DataFrames.
"""

import json

import duckdb


def question_1(cards_path: str) -> dict:
    """Q1: card_id with the latest expiry date and lowest credit limit."""
    con = duckdb.connect()
    con.execute("CREATE TABLE cards AS SELECT * FROM read_csv_auto($1)", [cards_path])
    result = con.execute("""
        WITH latest_expiry AS (
            SELECT *
            FROM cards
            QUALIFY RANK() OVER (ORDER BY expiry_date DESC) = 1
        )
        SELECT id AS card_id
        FROM latest_expiry
        QUALIFY RANK() OVER (ORDER BY credit_limit ASC) = 1
    """).df()
    con.close()
    return result


def question_2(users_path: str) -> dict:
    """Q2: client_id retiring within a year with lowest credit score and highest debt."""
    con = duckdb.connect()
    con.execute("CREATE TABLE users AS SELECT * FROM read_csv_auto($1)", [users_path])
    result = con.execute("""
        WITH to_retire AS (
            SELECT *, retirement_age - current_age AS years_to_retirement
            FROM users
            WHERE retirement_age - current_age = 1
        ),
        lowest_credit AS (
            SELECT id AS client_id, credit_score, total_debt
            FROM to_retire
            QUALIFY RANK() OVER (ORDER BY credit_score ASC) = 1
        )
        SELECT client_id
        FROM lowest_credit
        QUALIFY RANK() OVER (ORDER BY total_debt DESC) = 1
    """).df()
    con.close()
    return result


def question_3(transactions_path: str) -> dict:
    """Q3: transaction_id of an online purchase on Dec 31st with highest absolute amount."""
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE transactions AS SELECT * FROM read_csv_auto($1, quote='\"')",
        [transactions_path],
    )
    result = con.execute("""
        SELECT id AS transaction_id
        FROM transactions
        WHERE EXTRACT(MONTH FROM date) = 12
          AND EXTRACT(DAY FROM date) = 31
          AND LOWER(use_chip) LIKE '%online%'
        QUALIFY RANK() OVER (ORDER BY ABS(amount) DESC) = 1
    """).df()
    con.close()
    return result


def question_4(users_path: str, cards_path: str, transactions_path: str) -> dict:
    """Q4: client over 40 with most Visa transactions in Feb 2016."""
    con = duckdb.connect()
    con.execute("CREATE TABLE users AS SELECT * FROM read_csv_auto($1)", [users_path])
    con.execute("CREATE TABLE cards AS SELECT * FROM read_csv_auto($1)", [cards_path])
    con.execute(
        "CREATE TABLE transactions AS SELECT * FROM read_csv_auto($1, quote='\"')",
        [transactions_path],
    )
    result = con.execute("""
        WITH aggregates AS (
            SELECT
                users.id,
                transactions.card_id,
                COUNT(DISTINCT transactions.id) AS total_transactions
            FROM transactions
                LEFT JOIN cards ON transactions.card_id = cards.id
                    AND transactions.client_id = cards.client_id
                LEFT JOIN users ON transactions.client_id = users.id
            WHERE users.current_age > 40
              AND LOWER(cards.card_brand) LIKE '%visa%'
              AND EXTRACT(MONTH FROM date) = 2
              AND EXTRACT(YEAR FROM date) = 2016
            GROUP BY users.id, transactions.card_id
        )
        SELECT id AS client_id, card_id, total_transactions
        FROM aggregates
        QUALIFY RANK() OVER (ORDER BY total_transactions DESC) = 1
    """).df()
    con.close()
    return result


if __name__ == "__main__":
    processed = "./data/processed"
    results = {
        "target": {
            "query_1": question_1(f"{processed}/cards_data_processed.csv").to_dict(orient="records")[0],
            "query_2": question_2(f"{processed}/users_data_processed.csv").to_dict(orient="records")[0],
            "query_3": question_3(f"{processed}/transactions_data_processed.csv").to_dict(orient="records")[0],
            "query_4": question_4(
                f"{processed}/users_data_processed.csv",
                f"{processed}/cards_data_processed.csv",
                f"{processed}/transactions_data_processed.csv",
            ).to_dict(orient="records")[0],
        }
    }

    with open("./predictions/predictions_1.json", "w") as f:
        json.dump(results, f, indent=4)
