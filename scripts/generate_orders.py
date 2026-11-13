"""
Generate weekly batches of simulated Olist orders and append them to BigQuery.

Method: resample real orders and shift all their timestamps to a recent week.
- Status mix, delivery durations, items and payments follow the real data.
- customer_id, product_id and seller_id come from real rows, so dbt relationship tests pass.
- Written to separate tables (olist_raw.sim_*); the original Olist tables are never modified.
- Each batch covers one full Monday-to-Monday week. The latest batch is last week.
- Each order is stored with its full planned timeline, including events after today.
  The dbt staging model hides events that have not happened yet, so orders move from
  shipped to delivered on their own as time passes.
- Some batches get a known anomaly (late carriers, late sellers, cancellations), logged in
  olist_raw.sim_batches, so the monitoring can be tested against a ground truth.

Usage:
    python scripts/generate_orders.py                      # last week, random scenario
    python scripts/generate_orders.py --scenario normal    # last week, forced scenario
    python scripts/generate_orders.py --weeks 4            # backfill the last 4 weeks
"""

import argparse
import uuid
from datetime import timedelta

import numpy as np
import pandas as pd
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

PROJECT_ID = "olist-analytics-500414"
RAW = f"{PROJECT_ID}.olist_raw"
ORDERS_PER_BATCH = 100

# Probability of each scenario when none is forced
SCENARIOS = {
    "normal": 0.70,
    "carrier_delay": 0.10,
    "seller_delay": 0.10,
    "cancel_spike": 0.10,
}
SHARE_AFFECTED = 0.4  # share of shipped orders hit by a delay scenario

TIMESTAMP_COLS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def get_window(now: pd.Timestamp, weeks_ago: int = 0) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return a Monday-to-Monday week: last week, moved back by weeks_ago weeks."""
    today = now.normalize()
    this_monday = today - timedelta(days=today.weekday())
    window_start = this_monday - timedelta(weeks=1 + weeks_ago)
    window_end = window_start + timedelta(weeks=1)
    return window_start, window_end


def already_generated(client: bigquery.Client, window_start, window_end) -> bool:
    """True if a batch for this window already exists, which makes re-runs safe."""
    sql = f"""
        select count(*) as n
        from `{RAW}.sim_orders`
        where order_purchase_timestamp >= @start
          and order_purchase_timestamp < @end
    """
    params = [
        bigquery.ScalarQueryParameter("start", "TIMESTAMP", window_start),
        bigquery.ScalarQueryParameter("end", "TIMESTAMP", window_end),
    ]
    try:
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        rows = client.query(sql, job_config=job_config).result()
        return list(rows)[0].n > 0
    except NotFound:
        return False


def pick_scenario(forced: str | None, rng) -> str:
    """Use the forced scenario if given, otherwise draw one at random."""
    if forced:
        return forced
    return str(rng.choice(list(SCENARIOS), p=list(SCENARIOS.values())))


def read_real_sample(client: bigquery.Client, n: int):
    """Pick n random real orders, plus all their items and payments."""
    orders = client.query(
        f"select * from `{RAW}.orders` order by rand() limit {n}"
    ).to_dataframe()

    ids = [bigquery.ArrayQueryParameter("ids", "STRING", orders["order_id"].tolist())]
    job_config = bigquery.QueryJobConfig(query_parameters=ids)
    items = client.query(
        f"select * from `{RAW}.order_items` where order_id in unnest(@ids)",
        job_config=job_config,
    ).to_dataframe()
    payments = client.query(
        f"select * from `{RAW}.order_payments` where order_id in unnest(@ids)",
        job_config=job_config,
    ).to_dataframe()
    return orders, items, payments


def apply_scenario(orders: pd.DataFrame, scenario: str, rng) -> pd.DataFrame:
    """Inject a known anomaly into the batch, so the monitoring can be tested against it."""
    orders = orders.copy()
    if scenario == "normal":
        return orders

    shipped = orders["order_delivered_carrier_date"].notna()
    affected = shipped & (rng.random(len(orders)) < SHARE_AFFECTED)

    if scenario == "carrier_delay":
        # Parcels spend 7 more days on the road
        orders.loc[affected, "order_delivered_customer_date"] += pd.Timedelta(days=7)
    elif scenario == "seller_delay":
        # Sellers hand parcels to the carrier 5 days later; delivery moves with it
        for col in ["order_delivered_carrier_date", "order_delivered_customer_date"]:
            orders.loc[affected, col] += pd.Timedelta(days=5)
    elif scenario == "cancel_spike":
        # 15% of orders are cancelled before shipping
        cancelled = rng.random(len(orders)) < 0.15
        orders.loc[cancelled, "order_status"] = "canceled"
        orders.loc[cancelled, ["order_delivered_carrier_date", "order_delivered_customer_date"]] = pd.NaT
    return orders


def build_batch(orders, items, payments, window_start, rng, scenario):
    """Give each sampled order a new id and a new purchase time, shift all its dates,
    and inject the scenario. Dates after today are kept: dbt hides them until they pass."""
    orders = orders.copy()
    n = len(orders)

    # 1. New order ids
    orders["new_order_id"] = [uuid.uuid4().hex for _ in range(n)]

    # 2. New purchase time: a random whole second inside the 7-day window
    offsets = pd.to_timedelta(rng.integers(0, 7 * 24 * 3600, n), unit="s")
    new_purchase = pd.Series(window_start + offsets, index=orders.index)
    shift = new_purchase - orders["order_purchase_timestamp"]

    # 3. Shift every date of the order by the same amount (keeps real durations)
    for col in TIMESTAMP_COLS:
        orders[col] = orders[col] + shift

    # 4. Inject the scenario
    orders = apply_scenario(orders, scenario, rng)

    # 5. Round to whole seconds: pandas works in nanoseconds, BigQuery stores microseconds
    for col in TIMESTAMP_COLS:
        orders[col] = orders[col].dt.floor("s")

    # 6. Apply the new ids and the same shift to items and payments
    id_map = pd.Series(orders["new_order_id"].values, index=orders["order_id"])
    shift_map = pd.Series(shift.values, index=orders["order_id"])

    items = items.copy()
    items["shipping_limit_date"] = (
        items["shipping_limit_date"] + items["order_id"].map(shift_map)
    ).dt.floor("s")
    items["order_id"] = items["order_id"].map(id_map)

    payments = payments.copy()
    payments["order_id"] = payments["order_id"].map(id_map)

    orders["order_id"] = orders["new_order_id"]
    orders = orders.drop(columns="new_order_id")
    return orders, items, payments


def append(client: bigquery.Client, df: pd.DataFrame, source_table: str, target_table: str) -> None:
    """Append df to target_table, using the exact schema of the real source table."""
    schema = client.get_table(f"{RAW}.{source_table}").schema
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND", schema=schema)
    client.load_table_from_dataframe(df, f"{RAW}.{target_table}", job_config=job_config).result()


def log_batch(client: bigquery.Client, window_start, window_end, scenario: str, n_orders: int) -> None:
    """Record what was generated, including the injected scenario (ground truth for alerts)."""
    row = pd.DataFrame([{
        "window_start": window_start,
        "window_end": window_end,
        "scenario": scenario,
        "n_orders": n_orders,
        "generated_at": pd.Timestamp.now(tz="UTC").floor("s"),
    }])
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND",
        schema=[
            bigquery.SchemaField("window_start", "TIMESTAMP"),
            bigquery.SchemaField("window_end", "TIMESTAMP"),
            bigquery.SchemaField("scenario", "STRING"),
            bigquery.SchemaField("n_orders", "INT64"),
            bigquery.SchemaField("generated_at", "TIMESTAMP"),
        ],
    )
    client.load_table_from_dataframe(row, f"{RAW}.sim_batches", job_config=job_config).result()


def run_one_batch(client, rng, window_start, window_end, forced_scenario) -> None:
    """Generate, write and log one weekly batch, unless that week already exists."""
    print(f"\nBatch window: {window_start:%Y-%m-%d} -> {window_end:%Y-%m-%d}")

    if already_generated(client, window_start, window_end):
        print("Already exists, skipped.")
        return

    scenario = pick_scenario(forced_scenario, rng)
    print(f"Scenario: {scenario}")

    orders, items, payments = read_real_sample(client, ORDERS_PER_BATCH)
    orders, items, payments = build_batch(orders, items, payments, window_start, rng, scenario)

    append(client, orders, "orders", "sim_orders")
    append(client, items, "order_items", "sim_order_items")
    append(client, payments, "order_payments", "sim_order_payments")
    log_batch(client, window_start, window_end, scenario, len(orders))

    print(f"Generated {len(orders)} orders, {len(items)} items, {len(payments)} payments")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate weekly batches of simulated orders.")
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS),
        help="Force a scenario for every batch instead of drawing one at random.",
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=1,
        help="Number of weeks to generate, ending with last week (default: 1).",
    )
    args = parser.parse_args()

    client = bigquery.Client(project=PROJECT_ID)
    rng = np.random.default_rng()
    now = pd.Timestamp.now(tz="UTC").floor("s")

    # Oldest week first, so the batches are written in time order
    for weeks_ago in reversed(range(args.weeks)):
        window_start, window_end = get_window(now, weeks_ago)
        run_one_batch(client, rng, window_start, window_end, args.scenario)


if __name__ == "__main__":
    main()