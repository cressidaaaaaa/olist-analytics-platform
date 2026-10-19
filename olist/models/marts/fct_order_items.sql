-- Fact: order items
-- Grain: one row per order item (order_id + order_item_id).
-- Incremental: the first run builds the full table; later runs only process
-- recent orders and merge them in, matching rows on order_item_key.

{{
    config(
        materialized='incremental',
        unique_key='order_item_key'
    )
}}

select
    -- Keys
    concat(order_id, '-', cast(order_item_id as string)) as order_item_key,
    order_id,
    order_item_id,
    customer_id,
    product_id,
    seller_id,
    purchase_date,

    -- Context
    order_status,
    order_purchase_timestamp,

    -- Measures
    price_brl,
    freight_brl,
    brl_to_eur,
    price_eur,
    freight_eur,
    item_total_eur

from {{ ref('int_order_items_enriched') }}

{% if is_incremental() %}
-- Only on incremental runs: take orders from the last 3 days already in the table onward.
-- The 3-day overlap re-processes recent rows; unique_key makes them update, not duplicate.
where order_purchase_timestamp >= (
    select timestamp_sub(max(order_purchase_timestamp), interval 3 day)
    from {{ this }}
)
{% endif %}