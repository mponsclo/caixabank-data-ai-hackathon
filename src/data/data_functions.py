import os
import json

import pandas as pd
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


MCC_CODES_PATH = os.path.join(os.path.dirname(__file__), "../../data/raw/mcc_codes.json")
FIGURES_DIR = "reports/figures"

PERIOD_THRESHOLD_DAYS = 60


def _parse_amount_col(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the amount column is numeric (handles '$' prefixed strings)."""
    if df["amount"].dtype == object:
        df = df.copy()
        df["amount"] = pd.to_numeric(
            df["amount"].str.replace("$", "", regex=False).str.replace(",", "", regex=False)
        )
    return df


def earnings_and_expenses(
    df: pd.DataFrame, client_id: int, start_date: str, end_date: str
) -> pd.DataFrame:
    """Calculate total earnings and expenses for a client within a date range.

    Parameters
    ----------
    df : pd.DataFrame
        Transaction data with columns: client_id, date, amount.
    client_id : int
        Client identifier.
    start_date : str
        Start date (inclusive), format "YYYY-MM-DD".
    end_date : str
        End date (inclusive), format "YYYY-MM-DD".

    Returns
    -------
    pd.DataFrame
        Single-row DataFrame with columns ['Earnings', 'Expenses'], rounded to 2 decimals.
        Also saves a bar plot to reports/figures/earnings_and_expenses.png.
    """
    df = _parse_amount_col(df)

    con = duckdb.connect()
    con.register("txn", df)
    result = con.execute("""
        SELECT
            ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2) AS "Earnings",
            ROUND(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 2) AS "Expenses"
        FROM txn
        WHERE client_id = $1
          AND date >= $2::TIMESTAMP
          AND date <= $3::TIMESTAMP
    """, [client_id, start_date, end_date]).df()
    con.close()

    os.makedirs(FIGURES_DIR, exist_ok=True)
    fig, ax = plt.subplots()
    ax.bar(
        ["Earnings", "Expenses"],
        [abs(result["Earnings"].iloc[0]), abs(result["Expenses"].iloc[0])],
    )
    ax.set_ylabel("Amount")
    ax.set_title("Earnings and Expenses")
    fig.savefig(os.path.join(FIGURES_DIR, "earnings_and_expenses.png"))
    plt.close(fig)

    return result


def expenses_summary(
    df: pd.DataFrame, client_id: int, start_date: str, end_date: str
) -> pd.DataFrame:
    """Summarize expenses by merchant category for a client within a date range.

    Parameters
    ----------
    df : pd.DataFrame
        Transaction data with columns: client_id, date, amount, mcc.
    client_id : int
        Client identifier.
    start_date : str
        Start date (inclusive), format "YYYY-MM-DD".
    end_date : str
        End date (inclusive), format "YYYY-MM-DD".

    Returns
    -------
    pd.DataFrame
        Columns: ['Expenses Type', 'Total Amount', 'Average', 'Max', 'Min', 'Num. Transactions'].
        Sorted alphabetically by Expenses Type, rounded to 2 decimals.
        Also saves a bar plot to reports/figures/expenses_summary.png.
    """
    df = _parse_amount_col(df)

    with open(MCC_CODES_PATH) as f:
        mcc_codes = json.load(f)

    mcc_df = pd.DataFrame(
        [(int(k), v) for k, v in mcc_codes.items()],
        columns=["mcc", "category_name"],
    )

    con = duckdb.connect()
    con.register("txn", df)
    con.register("mcc_lookup", mcc_df)
    result = con.execute("""
        SELECT
            m.category_name AS "Expenses Type",
            ROUND(SUM(ABS(d.amount)), 2) AS "Total Amount",
            ROUND(AVG(ABS(d.amount)), 2) AS "Average",
            ROUND(ABS(MAX(d.amount)), 2) AS "Max",
            ROUND(ABS(MIN(d.amount)), 2) AS "Min",
            CAST(COUNT(*) AS BIGINT) AS "Num. Transactions"
        FROM txn d
        JOIN mcc_lookup m ON CAST(d.mcc AS INTEGER) = m.mcc
        WHERE d.client_id = $1
          AND d.date >= $2::TIMESTAMP
          AND d.date <= $3::TIMESTAMP
          AND d.amount < 0
        GROUP BY m.category_name
        ORDER BY m.category_name
    """, [client_id, start_date, end_date]).df()
    con.close()

    os.makedirs(FIGURES_DIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.bar(result["Expenses Type"], result["Total Amount"])
    ax.set_ylabel("Total Amount")
    ax.set_title("Expenses Summary by Category")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "expenses_summary.png"))
    plt.close(fig)

    return result


def cash_flow_summary(
    df: pd.DataFrame, client_id: int, start_date: str, end_date: str
) -> pd.DataFrame:
    """Calculate cash flow summary grouped by week or month.

    Groups by week (Sunday-ending) if period <= 60 days, by month otherwise.

    Parameters
    ----------
    df : pd.DataFrame
        Transaction data with columns: client_id, date, amount.
    client_id : int
        Client identifier.
    start_date : str
        Start date (inclusive), format "YYYY-MM-DD".
    end_date : str
        End date (inclusive), format "YYYY-MM-DD".

    Returns
    -------
    pd.DataFrame
        Columns: ['Date', 'Inflows', 'Outflows', 'Net Cash Flow', '% Savings'].
        Sorted by ascending date, rounded to 2 decimals.
    """
    df = _parse_amount_col(df)

    filtered = df[
        (df["client_id"] == client_id)
        & (df["date"] >= start_date)
        & (df["date"] <= end_date)
    ].copy()

    period_days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days

    if period_days > PERIOD_THRESHOLD_DAYS:
        grouped = filtered.groupby(pd.Grouper(key="date", freq="ME")).agg(
            Inflows=("amount", lambda x: round(x[x > 0].sum(), 2)),
            Outflows=("amount", lambda x: round(abs(x[x < 0].sum()), 2)),
        ).reset_index()
        grouped["Date"] = grouped["date"].dt.strftime("%Y-%m")
    else:
        grouped = filtered.groupby(pd.Grouper(key="date", freq="W")).agg(
            Inflows=("amount", lambda x: round(x[x > 0].sum(), 2)),
            Outflows=("amount", lambda x: round(abs(x[x < 0].sum()), 2)),
        ).reset_index()
        grouped["Date"] = grouped["date"].dt.strftime("%Y-%m-%d")

    grouped["Net Cash Flow"] = round(grouped["Inflows"] - grouped["Outflows"], 2)
    grouped["% Savings"] = round(grouped["Net Cash Flow"] / grouped["Inflows"] * 100, 2)

    return grouped[["Date", "Inflows", "Outflows", "Net Cash Flow", "% Savings"]].reset_index(drop=True)


if __name__ == "__main__":
    ...
