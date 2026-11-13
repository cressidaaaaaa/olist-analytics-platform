-- Staging model for order items
-- Grain: one row per item within an order (order_id + order_item_id).
-- Stacks real and simulated items; price and freight_value are in BRL,
-- EUR conversion happens in intermediate.

with real_items as (
    select *, false as is_simulated
    from {{ source('olist_raw', 'order_items') }}
),

simulated_items as (
    select *, true as is_simulated
    from {{ source('olist_raw', 'sim_order_items') }}
),

unioned as (
    select * from real_items
    union all
    select * from simulated_items
)

select
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date,
    price,
    freight_value,
    is_simulated
from unioned