-- Staging model for order payments
-- Grain: one row per payment within an order (order_id + payment_sequential).
-- Stacks real and simulated payments.

with real_payments as (
    select *, false as is_simulated
    from {{ source('olist_raw', 'order_payments') }}
),

simulated_payments as (
    select *, true as is_simulated
    from {{ source('olist_raw', 'sim_order_payments') }}
),

unioned as (
    select * from real_payments
    union all
    select * from simulated_payments
)

select
    order_id,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value,
    is_simulated
from unioned