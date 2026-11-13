-- Staging model for orders
-- Stacks the real Olist orders and the simulated weekly orders into one model.
-- Both sources have exactly the same columns; is_simulated tells them apart.
--
-- Simulated orders are stored with their full planned timeline, including dates
-- after today. Here, any event that has not happened yet is hidden, and the status
-- reflects how far the order has really got. Because this model is a view, it is
-- recalculated at every query, so orders move to "delivered" on their own over time.

with real_orders as (
    select *, false as is_simulated
    from {{ source('olist_raw', 'orders') }}
),

simulated_orders as (
    select *, true as is_simulated
    from {{ source('olist_raw', 'sim_orders') }}
),

unioned as (
    select * from real_orders
    union all
    select * from simulated_orders
)

select
    order_id,
    customer_id,

    -- Status as of now: the furthest step that has actually happened
    case
        when order_approved_at > current_timestamp() then 'created'
        when order_delivered_carrier_date > current_timestamp() then 'processing'
        when order_delivered_customer_date > current_timestamp() then 'shipped'
        else order_status
    end as order_status,

    order_purchase_timestamp,

    -- Hide events that are still in the future
    case when order_approved_at <= current_timestamp()
        then order_approved_at end as order_approved_at,
    case when order_delivered_carrier_date <= current_timestamp()
        then order_delivered_carrier_date end as order_delivered_carrier_date,
    case when order_delivered_customer_date <= current_timestamp()
        then order_delivered_customer_date end as order_delivered_customer_date,

    order_estimated_delivery_date,
    is_simulated
from unioned