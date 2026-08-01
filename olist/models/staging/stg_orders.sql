-- Staging model for orders
-- Purpose: clean the raw orders table, one-to-one with the source
-- Layer: staging (1:1 cleaning, no joins, no aggregation)

select
    order_id,
    customer_id,
    order_status,
    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date
from {{ source('olist_raw', 'orders') }}