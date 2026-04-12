"""Agent helper tools: date extraction, regex fallback, and PDF generation."""

import base64
import calendar
import ctypes.util
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# WeasyPrint needs gobject/pango/cairo shared libraries.
# On macOS with Homebrew, these live in /opt/homebrew/lib but aren't on the
# default dyld search path. Patch DYLD_FALLBACK_LIBRARY_PATH before import.
if sys.platform == "darwin" and not ctypes.util.find_library("gobject-2.0"):
    _brew_lib = "/opt/homebrew/lib"
    if os.path.isdir(_brew_lib):
        os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", _brew_lib)

from jinja2 import Environment, FileSystemLoader  # noqa: E402
from weasyprint import HTML  # noqa: E402

# ---------- Date Extraction ----------

EXTRACTION_PROMPT = """Extract the start date and end date from the user's request.
Return ONLY a JSON object with start_date and end_date in YYYY-MM-DD format.

Examples:
User: Create a pdf report for the fourth month of 2017
Answer: {{"start_date": "2017-04-01", "end_date": "2017-04-30"}}

User: Create a pdf report from 2018-01-01 to 2018-05-31
Answer: {{"start_date": "2018-01-01", "end_date": "2018-05-31"}}

User: Create a report for january 2020
Answer: {{"start_date": "2020-01-01", "end_date": "2020-01-31"}}

User: Create a report for the third quarter of 2019
Answer: {{"start_date": "2019-07-01", "end_date": "2019-09-30"}}

User: {input}
Answer: """


ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
}

MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _last_day(year, month):
    """Return the last day of the given month."""
    return calendar.monthrange(year, month)[1]


def _month_range(year, month):
    """Return (start_date, end_date) strings for a given year/month."""
    return (
        f"{year:04d}-{month:02d}-01",
        f"{year:04d}-{month:02d}-{_last_day(year, month):02d}",
    )


def _quarter_range(year, quarter):
    """Return (start_date, end_date) strings for a given year/quarter."""
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    return (
        f"{year:04d}-{start_month:02d}-01",
        f"{year:04d}-{end_month:02d}-{_last_day(year, end_month):02d}",
    )


def regex_extract_dates(input_text):
    """Extract start_date and end_date from text using regex patterns.

    Returns (start_date, end_date) tuple of strings, or None if no pattern matches.
    """
    text = input_text.lower().strip()

    # Pattern 1: explicit ISO dates "from YYYY-MM-DD to YYYY-MM-DD"
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1), m.group(2)

    # Pattern 2: two ISO dates anywhere in text
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    if len(dates) >= 2:
        return dates[0], dates[1]

    # Extract year (needed for patterns below)
    year_match = re.search(r"\b(20\d{2}|19\d{2})\b", text)
    if not year_match:
        return None
    year = int(year_match.group(1))

    # Pattern 3: ordinal month "the {ordinal} month of {year}"
    for word, num in ORDINALS.items():
        if re.search(rf"\b{word}\s+month\b", text):
            return _month_range(year, num)

    # Pattern 4: ordinal quarter "the {ordinal} quarter of {year}"
    for word, num in ORDINALS.items():
        if num <= 4 and re.search(rf"\b{word}\s+quarter\b", text):
            return _quarter_range(year, num)

    # Pattern 5: "Q{n} {year}"
    m = re.search(r"\bq([1-4])\b", text)
    if m:
        return _quarter_range(year, int(m.group(1)))

    # Pattern 6: month name "{month} {year}"
    for name, num in MONTH_NAMES.items():
        if name in text:
            return _month_range(year, num)

    # Pattern 7: full year "annual report {year}" or just a year
    if "annual" in text or "full year" in text:
        return f"{year}-01-01", f"{year}-12-31"

    return None


def extract_dates(model, input_text):
    """Extract dates using LLM with regex fallback.

    Parameters
    ----------
    model : ChatOllama or compatible LLM
        The language model to use for extraction.
    input_text : str
        Natural language prompt containing date information.

    Returns
    -------
    tuple of (start_date, end_date) as YYYY-MM-DD strings.
    """
    # Try LLM first
    try:
        prompt = EXTRACTION_PROMPT.format(input=input_text)
        response = model.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)

        # Try to parse JSON from response
        json_match = re.search(r"\{[^}]+\}", text)
        if json_match:
            parsed = json.loads(json_match.group())
            start = parsed.get("start_date", "")
            end = parsed.get("end_date", "")
            if re.match(r"\d{4}-\d{2}-\d{2}", start) and re.match(r"\d{4}-\d{2}-\d{2}", end):
                return start, end

        # Try line-based format
        start_m = re.search(r"start[_\s]*date[\"':\s]+(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
        end_m = re.search(r"end[_\s]*date[\"':\s]+(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
        if start_m and end_m:
            return start_m.group(1), end_m.group(1)
    except Exception:
        pass

    # Regex fallback
    result = regex_extract_dates(input_text)
    if result:
        return result

    raise ValueError(f"Could not extract dates from: {input_text}")


# ---------- PDF Generation ----------

# Template directory (resolved relative to this file)
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _fmt_currency(val):
    """Format a numeric value as a dollar string."""
    if isinstance(val, (int, float)):
        return f"${abs(val):,.2f}"
    return str(val)


def _read_chart_b64(path):
    """Read a PNG chart file and return its base64-encoded string, or None."""
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    return None


def _generate_ee_narrative(ee_df, client_id, start_date, end_date):
    """Generate narrative text for earnings and expenses section."""
    if ee_df is None or ee_df.empty:
        return "No transaction data available for this period."
    earnings = abs(ee_df["Earnings"].iloc[0])
    expenses = abs(ee_df["Expenses"].iloc[0])
    net = earnings - expenses
    savings_pct = (net / earnings * 100) if earnings > 0 else 0
    return (
        f"Client {client_id} earned {_fmt_currency(earnings)} and spent {_fmt_currency(expenses)} "
        f"during this period, resulting in net savings of {_fmt_currency(net)} ({savings_pct:.1f}% savings rate)."
    )


def _generate_es_narrative(es_df):
    """Generate narrative text for expenses summary section."""
    if es_df is None or es_df.empty:
        return "No expense transactions found for this period."
    top = es_df.sort_values("Total Amount", ascending=False).iloc[0]
    total = es_df["Total Amount"].sum()
    n_categories = len(es_df)
    return (
        f"Spending was distributed across {n_categories} {'category' if n_categories == 1 else 'categories'}, "
        f"totaling {_fmt_currency(total)}. The largest category was {top['Expenses Type']} "
        f"({_fmt_currency(top['Total Amount'])}, {int(top['Num. Transactions'])} transactions, "
        f"avg {_fmt_currency(top['Average'])} per transaction)."
    )


def _generate_cf_narrative(cf_df):
    """Generate narrative text for cash flow section."""
    if cf_df is None or cf_df.empty:
        return "No cash flow data available for this period."
    total_inflows = cf_df["Inflows"].sum()
    total_outflows = cf_df["Outflows"].sum()
    total_net = total_inflows - total_outflows
    n_positive = (cf_df["Net Cash Flow"] > 0).sum()
    n_periods = len(cf_df)
    best_idx = cf_df["Inflows"].idxmax()
    best_period = cf_df.loc[best_idx, "Date"]
    best_inflow = cf_df.loc[best_idx, "Inflows"]
    return (
        f"Net cash flow was positive in {n_positive} of {n_periods} periods. "
        f"Total inflows: {_fmt_currency(total_inflows)}, total outflows: {_fmt_currency(total_outflows)}, "
        f"net: {_fmt_currency(total_net)}. "
        f"The highest inflow period was {best_period} ({_fmt_currency(best_inflow)})."
    )


def generate_pdf(client_id, start_date, end_date, ee_df, es_df, cf_df, output_folder="reports"):
    """Generate a PDF financial report with tables, charts, and narrative summaries.

    Parameters
    ----------
    client_id : int
        Client identifier.
    start_date, end_date : str
        Date range for the report.
    ee_df : pd.DataFrame
        Earnings and expenses data.
    es_df : pd.DataFrame
        Expenses summary by category.
    cf_df : pd.DataFrame
        Cash flow summary.
    output_folder : str
        Directory to save the PDF.
    """
    # --- Compute KPI values from dataframes ---
    if ee_df is not None and not ee_df.empty:
        earnings = abs(ee_df["Earnings"].iloc[0])
        expenses = abs(ee_df["Expenses"].iloc[0])
        net = earnings - expenses
        savings_pct = (net / earnings * 100) if earnings > 0 else 0
        ee_data = {
            "earnings": _fmt_currency(earnings),
            "expenses": _fmt_currency(expenses),
            "net": _fmt_currency(net),
        }
    else:
        earnings = expenses = net = savings_pct = 0
        ee_data = None

    # --- Build expenses-by-category row list ---
    es_rows = []
    n_categories = 0
    if es_df is not None and not es_df.empty:
        n_categories = len(es_df)
        for _, row in es_df.iterrows():
            es_rows.append(
                {
                    "category": str(row["Expenses Type"]),
                    "total": _fmt_currency(row["Total Amount"]),
                    "average": _fmt_currency(row["Average"]),
                    "max": _fmt_currency(row["Max"]),
                    "min": _fmt_currency(row["Min"]),
                    "count": f"{int(row['Num. Transactions']):,}",
                }
            )

    # --- Build cash-flow row list and totals ---
    cf_rows = []
    cf_totals = None
    if cf_df is not None and not cf_df.empty:
        for _, row in cf_df.iterrows():
            cf_rows.append(
                {
                    "date": str(row["Date"]),
                    "inflows": _fmt_currency(row["Inflows"]),
                    "outflows": _fmt_currency(row["Outflows"]),
                    "net": _fmt_currency(row["Net Cash Flow"]),
                    "savings_pct": f"{row['% Savings']:.1f}%",
                }
            )
        total_inflows = cf_df["Inflows"].sum()
        total_outflows = cf_df["Outflows"].sum()
        total_net = cf_df["Net Cash Flow"].sum()
        overall_savings = (total_net / total_inflows * 100) if total_inflows > 0 else 0
        cf_totals = {
            "inflows": _fmt_currency(total_inflows),
            "outflows": _fmt_currency(total_outflows),
            "net": _fmt_currency(total_net),
            "savings_pct": f"{overall_savings:.1f}%",
        }

    # --- Read chart images as base64 ---
    ee_chart_b64 = _read_chart_b64("reports/figures/earnings_and_expenses.png")
    es_chart_b64 = _read_chart_b64("reports/figures/expenses_summary.png")
    cf_chart_b64 = _read_chart_b64("reports/figures/cash_flow_summary.png")

    # --- Render template ---
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    template = env.get_template("report_template.html")

    html_str = template.render(
        client_id=client_id,
        start_date=start_date,
        end_date=end_date,
        generated_date=date.today().isoformat(),
        # KPI values
        kpi_earnings=_fmt_currency(earnings),
        kpi_expenses=_fmt_currency(expenses),
        kpi_net=_fmt_currency(net),
        kpi_savings_rate=f"{savings_pct:.1f}%",
        # Narratives
        ee_narrative=_generate_ee_narrative(ee_df, client_id, start_date, end_date),
        es_narrative=_generate_es_narrative(es_df),
        cf_narrative=_generate_cf_narrative(cf_df),
        # Table data
        ee_data=ee_data,
        es_rows=es_rows,
        n_categories=n_categories,
        cf_rows=cf_rows,
        cf_totals=cf_totals,
        # Charts (base64)
        ee_chart_b64=ee_chart_b64,
        es_chart_b64=es_chart_b64,
        cf_chart_b64=cf_chart_b64,
    )

    # --- Generate PDF ---
    os.makedirs(output_folder, exist_ok=True)
    filename = f"report_client_{client_id}_{start_date}_to_{end_date}.pdf"
    output_path = os.path.join(output_folder, filename)

    HTML(string=html_str, base_url=str(_TEMPLATE_DIR)).write_pdf(output_path)


if __name__ == "__main__":
    ...
