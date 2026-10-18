-- Intermediate model: payments rolled up to one row per order
-- Grain: one row per order (order_id).
-- stg_order_payments has one row per payment (an order can be split across
-- several payments), so we aggregate here BEFORE anything joins it to orders.
-- This prevents fan-out in fct_orders.

with payments as (
    select * from {{ ref('stg_order_payments') }}
),

orders as (
    select
        order_id,
        order_purchase_timestamp
    from {{ ref('stg_orders') }}
),

fx_rates as (
    select
        rate_date,
        brl_to_eur
    from {{ ref('stg_fx_rates') }}
),

-- Step 1: collapse multiple payments into one row per order
payments_per_order as (
    select
        order_id,
        count(*) as payment_count,
        string_agg(distinct payment_type, ', ') as payment_types,
        max(payment_installments) as max_installments,
        sum(payment_value) as total_paid_brl
    from payments
    group by order_id
)

-- Step 2: convert the order's total payment to EUR using the purchase-date rate
select
    p.order_id,
    p.payment_count,
    p.payment_types,
    p.max_installments,
    p.total_paid_brl,
    fx.brl_to_eur,
    round(p.total_paid_brl * fx.brl_to_eur, 2) as total_paid_eur
from payments_per_order as p
left join orders as o
    on p.order_id = o.order_id
left join fx_rates as fx
    on date(o.order_purchase_timestamp) = fx.rate_date