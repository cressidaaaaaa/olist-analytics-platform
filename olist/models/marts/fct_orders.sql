-- Fact: orders
-- Grain: one row per order (order_id).
-- Every source is first reduced to one row per order, then joined on order_id,
-- so all joins are one-to-one and the row count equals stg_orders (no fan-out).

with orders as (
    select * from {{ ref('stg_orders') }}
),

-- Items: many rows per order -> roll up to one row per order
items_per_order as (
    select
        order_id,
        count(*) as item_count,
        sum(price_brl) as items_price_brl,
        sum(freight_brl) as items_freight_brl,
        sum(item_total_eur) as items_total_eur
    from {{ ref('int_order_items_enriched') }}
    group by order_id
),

-- Payments: already one row per order
payments as (
    select * from {{ ref('int_payments_by_order') }}
),

-- Reviews: an order can occasionally have more than one review -> average them
reviews_per_order as (
    select
        order_id,
        count(*) as review_count,
        avg(review_score) as review_score
    from {{ ref('stg_order_reviews') }}
    group by order_id
)

select
    -- Keys
    o.order_id,
    o.customer_id,
    date(o.order_purchase_timestamp) as purchase_date,

    -- Status and timestamps
    o.order_status,
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,

    -- Items
    coalesce(i.item_count, 0) as item_count,
    i.items_price_brl,
    i.items_freight_brl,
    i.items_total_eur,

    -- Payments
    p.payment_count,
    p.payment_types,
    p.max_installments,
    p.total_paid_brl,
    p.total_paid_eur,

    -- Delivery performance (null when the order was never delivered)
    date_diff(
        date(o.order_delivered_customer_date),
        date(o.order_purchase_timestamp),
        day
    ) as delivery_days,
    date(o.order_delivered_customer_date) > date(o.order_estimated_delivery_date) as is_late,

    -- Customer satisfaction
    r.review_count,
    r.review_score

from orders as o
left join items_per_order as i
    on o.order_id = i.order_id
left join payments as p
    on o.order_id = p.order_id
left join reviews_per_order as r
    on o.order_id = r.order_id