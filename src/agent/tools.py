"""Agent helper tools: date extraction, regex fallback, and PDF generation."""

import calendar
import json
import os
import re
from datetime import date

from fpdf import FPDF

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

# Design constants
HEADER_COLOR = (30, 60, 110)  # Dark blue
ACCENT_COLOR = (44, 62, 80)   # Dark gray
ROW_ALT_COLOR = (245, 247, 250)  # Light gray for alternating rows


def _fmt_currency(val):
    """Format a numeric value as a dollar string."""
    if isinstance(val, (int, float)):
        return f"${abs(val):,.2f}"
    return str(val)


def _add_header_bar(pdf, title, subtitle=None):
    """Add a colored header bar with title text."""
    pdf.set_fill_color(*HEADER_COLOR)
    pdf.rect(0, 0, 210, 40, "F")
    pdf.set_y(10)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT", align="C")
    if subtitle:
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, subtitle, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(15)


def _add_section_header(pdf, title):
    """Add a section header with a line separator."""
    pdf.set_draw_color(*ACCENT_COLOR)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*ACCENT_COLOR)
    pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)


def _add_narrative(pdf, text):
    """Add a narrative summary paragraph."""
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(0, 6, text)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)


def _add_footer(pdf):
    """Add a footer to the current page."""
    pdf.set_y(-20)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 10, f"Generated on {date.today().isoformat()}", align="L")
    pdf.cell(0, 10, f"Page {pdf.page_no()}", align="R")
    pdf.set_text_color(0, 0, 0)


def _add_dataframe_table(pdf, df):
    """Render a pandas DataFrame as a formatted table in the PDF."""
    if df is None or df.empty:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 8, "No data available for this section.", new_x="LMARGIN", new_y="NEXT")
        return

    col_count = len(df.columns)
    page_width = 190
    col_width = page_width / col_count

    # Headers
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*HEADER_COLOR)
    pdf.set_text_color(255, 255, 255)
    for col in df.columns:
        pdf.cell(col_width, 8, str(col)[:30], border=0, align="C", fill=True)
    pdf.ln()
    pdf.set_text_color(0, 0, 0)

    # Rows
    pdf.set_font("Helvetica", "", 8)
    for row_idx, (_, row) in enumerate(df.iterrows()):
        if row_idx % 2 == 1:
            pdf.set_fill_color(*ROW_ALT_COLOR)
            fill = True
        else:
            fill = False
        for val in row:
            if isinstance(val, float):
                text = _fmt_currency(val)
            elif isinstance(val, int) and not isinstance(val, bool):
                text = f"{val:,}"
            else:
                text = str(val)[:30]
            pdf.cell(col_width, 7, text, border=0, align="C", fill=fill)
        pdf.ln()


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
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=25)

    # --- Page 1: Title + Earnings & Expenses ---
    pdf.add_page()
    _add_header_bar(pdf, "Financial Report", f"Client {client_id}  |  {start_date} to {end_date}")

    _add_section_header(pdf, "1. Earnings and Expenses")
    _add_narrative(pdf, _generate_ee_narrative(ee_df, client_id, start_date, end_date))
    _add_dataframe_table(pdf, ee_df)
    pdf.ln(5)

    ee_img = "reports/figures/earnings_and_expenses.png"
    if os.path.exists(ee_img):
        pdf.image(ee_img, w=140, x=35)

    _add_footer(pdf)

    # --- Page 2: Expenses Summary ---
    pdf.add_page()
    _add_section_header(pdf, "2. Expenses by Category")
    _add_narrative(pdf, _generate_es_narrative(es_df))
    _add_dataframe_table(pdf, es_df)
    pdf.ln(5)

    es_img = "reports/figures/expenses_summary.png"
    if os.path.exists(es_img):
        pdf.image(es_img, w=160, x=25)

    _add_footer(pdf)

    # --- Page 3: Cash Flow Summary ---
    pdf.add_page()
    _add_section_header(pdf, "3. Cash Flow Summary")
    _add_narrative(pdf, _generate_cf_narrative(cf_df))
    _add_dataframe_table(pdf, cf_df)

    # Add totals row
    if cf_df is not None and not cf_df.empty:
        pdf.set_font("Helvetica", "B", 8)
        col_width = 190 / len(cf_df.columns)
        pdf.set_fill_color(*HEADER_COLOR)
        pdf.set_text_color(255, 255, 255)
        totals = ["TOTAL", _fmt_currency(cf_df["Inflows"].sum()), _fmt_currency(cf_df["Outflows"].sum()),
                  _fmt_currency(cf_df["Net Cash Flow"].sum()),
                  f"{cf_df['Net Cash Flow'].sum() / cf_df['Inflows'].sum() * 100:.1f}%" if cf_df["Inflows"].sum() > 0 else "0%"]
        for val in totals:
            pdf.cell(col_width, 8, val, border=0, align="C", fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)

    pdf.ln(5)

    cf_img = "reports/figures/cash_flow_summary.png"
    if os.path.exists(cf_img):
        pdf.image(cf_img, w=160, x=25)

    _add_footer(pdf)

    # Save
    os.makedirs(output_folder, exist_ok=True)
    filename = f"report_client_{client_id}_{start_date}_to_{end_date}.pdf"
    pdf.output(os.path.join(output_folder, filename))


if __name__ == "__main__":
    ...
