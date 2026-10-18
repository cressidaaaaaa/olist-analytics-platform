-- Dimension: customers
-- Grain: one row per customer_id (Olist creates one customer_id per order).
-- customer_unique_id identifies the real person; we use it to compute
-- how many orders each person placed and whether they are a repeat customer.

with customers as (
    select * from {{ ref('stg_customers') }}
),

orders as (
    select
        order_id,
        customer_id
    from {{ ref('stg_orders') }}
),

-- How many orders each real person (customer_unique_id) placed in total
orders_per_person as (
    select
        c.customer_unique_id,
        count(distinct o.order_id) as lifetime_orders
    from orders as o
    inner join customers as c
        on o.customer_id = c.customer_id
    group by c.customer_unique_id
)

select
    c.customer_id,
    c.customer_unique_id,
    c.customer_zip_code_prefix,
    c.customer_city,
    c.customer_state,
    p.lifetime_orders,
    p.lifetime_orders > 1 as is_repeat_customer
from customers as c
left join orders_per_person as p
    on c.customer_unique_id = p.customer_unique_id