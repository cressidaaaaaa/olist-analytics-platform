"""
Generate one weekly batch of simulated Olist orders and append them to BigQuery.

Method: resample real orders and shift all their timestamps to a recent week.
- Status mix, delivery durations, items and payments follow the real data.
- customer_id, product_id and seller_id come from real rows, so dbt relationship tests pass.
- Written to separate tables (olist_raw.sim_*); the original Olist tables are never modified.
- Each run covers the week that ended 21 days ago, so most orders already have their
  final status. Re-running for the same week does nothing.
- Some batches get a known anomaly (late carriers, late sellers, cancellations), logged in
  olist_raw.sim_batches, so the monitoring can be tested against a ground truth.
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
LAG_DAYS = 21  # the batch covers the 7 days that ended this many days ago

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


def get_window(now: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the start and end of the week this batch covers."""
    window_end = now - timedelta(days=LAG_DAYS)
    window_start = window_end - timedelta(days=7)
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


def build_batch(orders, items, payments, window_start, now, rng, scenario):
    """Give each sampled order a new id and a new purchase time, shift all its dates,
    and inject the scenario."""
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

    # 4. Inject the scenario (before the future check, so delays can push dates past today)
    orders = apply_scenario(orders, scenario, rng)

    # 5. Dates that land after today have not happened yet
    future_delivery = orders["order_delivered_customer_date"] > now
    orders.loc[future_delivery, "order_delivered_customer_date"] = pd.NaT
    orders.loc[future_delivery, "order_status"] = "shipped"

    future_carrier = orders["order_delivered_carrier_date"] > now
    orders.loc[future_carrier, "order_delivered_carrier_date"] = pd.NaT
    orders.loc[future_carrier, "order_status"] = "processing"

    # 6. Round to whole seconds: pandas works in nanoseconds, BigQuery stores microseconds
    for col in TIMESTAMP_COLS:
        orders[col] = orders[col].dt.floor("s")

    # 7. Apply the new ids and the same shift to items and payments
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one weekly batch of simulated orders.")
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS),
        help="Force a scenario instead of drawing one at random.",
    )
    args = parser.parse_args()

    client = bigquery.Client(project=PROJECT_ID)
    rng = np.random.default_rng()
    now = pd.Timestamp.now(tz="UTC").floor("s")

    window_start, window_end = get_window(now)
    print(f"Batch window: {window_start:%Y-%m-%d} -> {window_end:%Y-%m-%d}")

    if already_generated(client, window_start, window_end):
        print("A batch for this window already exists. Nothing to do.")
        return

    scenario = pick_scenario(args.scenario, rng)
    print(f"Scenario: {scenario}")

    orders, items, payments = read_real_sample(client, ORDERS_PER_BATCH)
    orders, items, payments = build_batch(orders, items, payments, window_start, now, rng, scenario)

    append(client, orders, "orders", "sim_orders")
    append(client, items, "order_items", "sim_order_items")
    append(client, payments, "order_payments", "sim_order_payments")
    log_batch(client, window_start, window_end, scenario, len(orders))

    print(f"Generated {len(orders)} orders, {len(items)} items, {len(payments)} payments")
    print(orders["order_status"].value_counts().to_string())


if __name__ == "__main__":
    main()