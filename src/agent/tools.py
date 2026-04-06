"""Agent helper tools: date extraction, regex fallback, and PDF generation."""

import os
import re
import json
import calendar

import pandas as pd
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
    "first": 1, "second": 2, "third": 3, "fourth": 4,
    "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
}

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
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

def _add_dataframe_table(pdf, df):
    """Render a pandas DataFrame as a simple table in the PDF."""
    if df is None or df.empty:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 8, "No data available for this section.", new_x="LMARGIN", new_y="NEXT")
        return

    pdf.set_font("Helvetica", "", 8)
    col_count = len(df.columns)
    col_width = min(180 / col_count, 40)

    # Headers
    pdf.set_font("Helvetica", "B", 8)
    for col in df.columns:
        pdf.cell(col_width, 7, str(col)[:20], border=1, align="C")
    pdf.ln()

    # Rows
    pdf.set_font("Helvetica", "", 7)
    for _, row in df.iterrows():
        for val in row:
            text = f"{val:.2f}" if isinstance(val, float) else str(val)
            pdf.cell(col_width, 6, text[:20], border=1, align="C")
        pdf.ln()


def generate_pdf(client_id, start_date, end_date, ee_df, es_df, cf_df, output_folder="reports"):
    """Generate a PDF financial report with tables and charts.

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
    pdf.set_auto_page_break(auto=True, margin=15)

    # --- Page 1: Title + Earnings & Expenses ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, f"Financial Report - Client {client_id}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Period: {start_date} to {end_date}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, "1. Earnings and Expenses", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    _add_dataframe_table(pdf, ee_df)
    pdf.ln(5)

    ee_img = "reports/figures/earnings_and_expenses.png"
    if os.path.exists(ee_img):
        pdf.image(ee_img, w=150, x=30)

    # --- Page 2: Expenses Summary ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, "2. Expenses Summary by Category", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    _add_dataframe_table(pdf, es_df)
    pdf.ln(5)

    es_img = "reports/figures/expenses_summary.png"
    if os.path.exists(es_img):
        pdf.image(es_img, w=170, x=20)

    # --- Page 3: Cash Flow Summary ---
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, "3. Cash Flow Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    _add_dataframe_table(pdf, cf_df)

    # Save
    os.makedirs(output_folder, exist_ok=True)
    filename = f"report_client_{client_id}_{start_date}_to_{end_date}.pdf"
    pdf.output(os.path.join(output_folder, filename))


if __name__ == "__main__":
    ...
