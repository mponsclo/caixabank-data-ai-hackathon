"""Task 5: AI Agent for generating PDF financial reports.

Uses LangChain + Ollama (llama3.2:1b) to parse natural language date requests,
then calls Task 2 data functions and generates a PDF report with fpdf2.

Architecture:
- LLM extracts dates from natural language (with regex fallback for reliability)
- Client validation is deterministic (check DataFrame)
- Task 2 functions generate data + charts
- fpdf2 assembles the PDF report
"""

import pandas as pd
from langchain_ollama import ChatOllama

from agent.tools import extract_dates, generate_pdf
from data.data_functions import cash_flow_summary, earnings_and_expenses, expenses_summary


def run_agent(df: pd.DataFrame, client_id: int, input: str) -> dict:
    """Create a PDF report using an AI agent that extracts dates from natural language.

    The agent parses the input prompt to determine the date range, validates the
    client exists in the data, calls the three Task 2 analysis functions, and
    generates a PDF report.

    Parameters
    ----------
    df : pd.DataFrame
        Transaction data with columns: client_id, date, amount, mcc, etc.
    client_id : int
        ID of the client requesting the report.
    input : str
        Natural language prompt describing the desired report period.

    Returns
    -------
    dict
        {
            "start_date": "YYYY-MM-DD",
            "end_date": "YYYY-MM-DD",
            "client_id": int,
            "create_report": bool
        }
    """
    model = ChatOllama(model="llama3.2:1b", temperature=0)
    pdf_output_folder = "reports/"

    # 1. Extract dates from natural language input
    start_date, end_date = extract_dates(model, input)

    # 2. Validate client exists in data
    client_exists = int(client_id) in df["client_id"].values

    # 3. Build result
    variables_dict = {
        "start_date": start_date,
        "end_date": end_date,
        "client_id": int(client_id),
        "create_report": client_exists,
    }

    # 4. Generate report if client is valid
    if client_exists:
        ee_df = earnings_and_expenses(df, client_id, start_date, end_date)
        es_df = expenses_summary(df, client_id, start_date, end_date)
        cf_df = cash_flow_summary(df, client_id, start_date, end_date)
        generate_pdf(client_id, start_date, end_date, ee_df, es_df, cf_df, pdf_output_folder)

    return variables_dict


if __name__ == "__main__":
    ...
