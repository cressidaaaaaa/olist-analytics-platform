-- Intermediate model: order items enriched with purchase date and EUR amounts
-- Grain: one row per order item (order_id + order_item_id), same as stg_order_items.
-- Both joins are many-to-one (each item -> one order -> one FX rate per day),
-- so the row count must stay identical to stg_order_items (no fan-out).

with order_items as (
    select * from {{ ref('stg_order_items') }}
),

orders as (
    select
        order_id,
        order_status,
        order_purchase_timestamp
    from {{ ref('stg_orders') }}
),

fx_rates as (
    select
        rate_date,
        brl_to_eur
    from {{ ref('stg_fx_rates') }}
)

select
    oi.order_id,
    oi.order_item_id,
    oi.product_id,
    oi.seller_id,
    o.order_status,
    o.order_purchase_timestamp,
    date(o.order_purchase_timestamp) as purchase_date,

    -- Original amounts in BRL
    oi.price as price_brl,
    oi.freight_value as freight_brl,

    -- Exchange rate on the purchase date
    fx.brl_to_eur,

    -- Converted amounts in EUR, rounded to cents
    round(oi.price * fx.brl_to_eur, 2) as price_eur,
    round(oi.freight_value * fx.brl_to_eur, 2) as freight_eur,
    round((oi.price + oi.freight_value) * fx.brl_to_eur, 2) as item_total_eur

from order_items as oi
left join orders as o
    on oi.order_id = o.order_id
left join fx_rates as fx
    on date(o.order_purchase_timestamp) = fx.rate_date