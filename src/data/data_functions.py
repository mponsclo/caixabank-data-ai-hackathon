import json
import os

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mtick  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

MCC_CODES_PATH = os.path.join(os.path.dirname(__file__), "../../data/raw/mcc_codes.json")
FIGURES_DIR = "reports/figures"

PERIOD_THRESHOLD_DAYS = 60

# Chart style constants — matches report CSS palette
COLOR_EARNINGS = "#1B8C5A"
COLOR_EXPENSES = "#D64045"
COLOR_INFLOW = "#1B8C5A"
COLOR_OUTFLOW = "#D64045"
COLOR_NET = "#003547"
COLOR_CATEGORY = "#007A8C"

# Professional chart styling
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter", "Helvetica Neue", "Arial", "sans-serif"],
    "axes.facecolor": "#FAFBFC",
    "figure.facecolor": "#FFFFFF",
    "axes.edgecolor": "#E5E7EB",
    "axes.labelcolor": "#1A1A2E",
    "text.color": "#1A1A2E",
    "xtick.color": "#6B7280",
    "ytick.color": "#6B7280",
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.color": "#E5E7EB",
    "grid.linestyle": "--",
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def _clean_axes(ax):
    """Remove top and right spines for cleaner charts."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#E5E7EB")
    ax.spines["bottom"].set_color("#E5E7EB")


def _dollar_label(value):
    """Format a number as a dollar string."""
    return f"${value:,.2f}"


def _parse_amount_col(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the amount column is numeric (handles '$' prefixed strings)."""
    if df["amount"].dtype == object:
        df = df.copy()
        df["amount"] = pd.to_numeric(df["amount"].str.replace("$", "", regex=False).str.replace(",", "", regex=False))
    return df


def earnings_and_expenses(df: pd.DataFrame, client_id: int, start_date: str, end_date: str) -> pd.DataFrame:
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
    result = con.execute(
        """
        SELECT
            ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2) AS "Earnings",
            ROUND(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 2) AS "Expenses"
        FROM txn
        WHERE client_id = $1
          AND date >= $2::TIMESTAMP
          AND date <= $3::TIMESTAMP
    """,
        [client_id, start_date, end_date],
    ).df()
    con.close()

    earnings_val = abs(result["Earnings"].iloc[0])
    expenses_val = abs(result["Expenses"].iloc[0])

    os.makedirs(FIGURES_DIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(
        ["Earnings", "Expenses"],
        [earnings_val, expenses_val],
        color=[COLOR_EARNINGS, COLOR_EXPENSES],
        width=0.45,
        edgecolor="white",
        linewidth=1.5,
        zorder=3,
    )
    for bar, val in zip(bars, [earnings_val, expenses_val]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(earnings_val, expenses_val) * 0.02,
            _dollar_label(val),
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
            color="#1A1A2E",
        )
    ax.set_ylabel("Amount ($)", fontsize=10, fontweight="500")
    _clean_axes(ax)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.set_axisbelow(True)
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "earnings_and_expenses.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)

    return result


def expenses_summary(df: pd.DataFrame, client_id: int, start_date: str, end_date: str) -> pd.DataFrame:
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
    result = con.execute(
        """
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
    """,
        [client_id, start_date, end_date],
    ).df()
    con.close()

    # Sort by amount for the chart (largest first)
    plot_df = result.sort_values("Total Amount", ascending=True)

    os.makedirs(FIGURES_DIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, max(4, len(plot_df) * 0.55)))
    bars = ax.barh(
        plot_df["Expenses Type"], plot_df["Total Amount"],
        color=COLOR_CATEGORY, edgecolor="white", linewidth=1.2, zorder=3,
    )
    for bar, val in zip(bars, plot_df["Total Amount"]):
        ax.text(
            bar.get_width() + max(plot_df["Total Amount"]) * 0.02,
            bar.get_y() + bar.get_height() / 2,
            _dollar_label(val),
            ha="left",
            va="center",
            fontsize=9,
            color="#1A1A2E",
        )
    ax.set_xlabel("Total Amount ($)", fontsize=10, fontweight="500")
    _clean_axes(ax)
    ax.xaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.set_axisbelow(True)
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "expenses_summary.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)

    return result


def cash_flow_summary(df: pd.DataFrame, client_id: int, start_date: str, end_date: str) -> pd.DataFrame:
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
        Also saves a chart to reports/figures/cash_flow_summary.png.
    """
    df = _parse_amount_col(df)

    filtered = df[(df["client_id"] == client_id) & (df["date"] >= start_date) & (df["date"] <= end_date)].copy()

    period_days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days

    if period_days > PERIOD_THRESHOLD_DAYS:
        grouped = (
            filtered.groupby(pd.Grouper(key="date", freq="ME"))
            .agg(
                Inflows=("amount", lambda x: round(x[x > 0].sum(), 2)),
                Outflows=("amount", lambda x: round(abs(x[x < 0].sum()), 2)),
            )
            .reset_index()
        )
        grouped["Date"] = grouped["date"].dt.strftime("%Y-%m")
    else:
        grouped = (
            filtered.groupby(pd.Grouper(key="date", freq="W"))
            .agg(
                Inflows=("amount", lambda x: round(x[x > 0].sum(), 2)),
                Outflows=("amount", lambda x: round(abs(x[x < 0].sum()), 2)),
            )
            .reset_index()
        )
        grouped["Date"] = grouped["date"].dt.strftime("%Y-%m-%d")

    grouped["Net Cash Flow"] = round(grouped["Inflows"] - grouped["Outflows"], 2)
    grouped["% Savings"] = round(grouped["Net Cash Flow"] / grouped["Inflows"].replace(0, np.nan) * 100, 2).fillna(0)

    result = grouped[["Date", "Inflows", "Outflows", "Net Cash Flow", "% Savings"]].reset_index(drop=True)

    # Generate cash flow chart
    os.makedirs(FIGURES_DIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    x = np.arange(len(result))
    width = 0.33
    ax.bar(x - width / 2, result["Inflows"], width, label="Inflows", color=COLOR_INFLOW, edgecolor="white", linewidth=1.2, zorder=3)
    ax.bar(x + width / 2, result["Outflows"], width, label="Outflows", color=COLOR_OUTFLOW, edgecolor="white", linewidth=1.2, zorder=3)
    ax.plot(x, result["Net Cash Flow"], color=COLOR_NET, marker="o", linewidth=2.5, markersize=6, label="Net Cash Flow", zorder=5)
    ax.set_xticks(x)
    ax.set_xticklabels(result["Date"], rotation=45 if len(result) > 6 else 0, ha="right" if len(result) > 6 else "center")
    ax.set_ylabel("Amount ($)", fontsize=10, fontweight="500")
    ax.legend(frameon=True, fancybox=True, shadow=False, framealpha=0.9, edgecolor="#E5E7EB", fontsize=9)
    _clean_axes(ax)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    ax.set_axisbelow(True)
    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "cash_flow_summary.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)

    return result


if __name__ == "__main__":
    ...
