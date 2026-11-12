"""
Load daily BRL -> EUR exchange rates from the Frankfurter API into BigQuery.

- First run (table missing): backfills from 2016-09-01 to today.
- Later runs: only fetches dates after the latest one already loaded, and appends them.
Safe to re-run: if there are no new business days, nothing is written.
"""

from datetime import date, timedelta

import pandas as pd
import requests
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

PROJECT_ID = "olist-analytics-500414"
TABLE_ID = f"{PROJECT_ID}.olist_raw.fx_rates"
BACKFILL_START = date(2016, 9, 1)
API_URL = "https://api.frankfurter.dev/v1"


def get_last_loaded_date(client: bigquery.Client):
    """Return the latest rate_date in the table, or None if the table does not exist."""
    try:
        rows = client.query(f"select max(rate_date) as last_date from `{TABLE_ID}`").result()
        return list(rows)[0].last_date
    except NotFound:
        return None


def fetch_rates(start: date, end: date) -> list[dict]:
    """Fetch daily BRL->EUR rates for one date range."""
    response = requests.get(
        f"{API_URL}/{start}..{end}",
        params={"base": "BRL", "symbols": "EUR"},
        timeout=30,
    )
    response.raise_for_status()
    rates = response.json()["rates"]
    return [{"rate_date": d, "brl_to_eur": v["EUR"]} for d, v in rates.items()]


def fetch_range(start: date, end: date) -> pd.DataFrame:
    """Fetch a long date range one calendar year at a time, keep only dates >= start."""
    rows = []
    for year in range(start.year, end.year + 1):
        chunk_start = max(start, date(year, 1, 1))
        chunk_end = min(end, date(year, 12, 31))
        rows += fetch_rates(chunk_start, chunk_end)

    df = pd.DataFrame(rows, columns=["rate_date", "brl_to_eur"])
    df["rate_date"] = pd.to_datetime(df["rate_date"]).dt.date
    return df[df["rate_date"] >= start].drop_duplicates("rate_date")


def append_to_bigquery(client: bigquery.Client, df: pd.DataFrame) -> None:
    """Append new rows to the raw table (created on first run)."""
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND",
        schema=[
            bigquery.SchemaField("rate_date", "DATE"),
            bigquery.SchemaField("brl_to_eur", "FLOAT64"),
        ],
    )
    client.load_table_from_dataframe(df, TABLE_ID, job_config=job_config).result()


def main() -> None:
    client = bigquery.Client(project=PROJECT_ID)

    last_date = get_last_loaded_date(client)
    start = BACKFILL_START if last_date is None else last_date + timedelta(days=1)
    end = date.today()
    print(f"Last loaded date: {last_date}")
    print(f"Fetching {start} -> {end}")

    if start > end:
        print("Already up to date.")
        return

    new_rows = fetch_range(start, end)
    if new_rows.empty:
        print("No new business days to load.")
    else:
        append_to_bigquery(client, new_rows)
        print(f"Loaded {len(new_rows)} new rows")

    print("Total rows in table:", client.get_table(TABLE_ID).num_rows)


if __name__ == "__main__":
    main()