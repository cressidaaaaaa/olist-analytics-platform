-- Staging model for order items (order line items)
-- Grain: one row per item within an order (order_id + order_item_id)
-- Note: price and freight_value are in BRL (Brazilian Real).
--       Currency conversion to EUR happens later in the intermediate layer.

select
    order_id,               -- FK to orders (repeats: one order can have many items)
    order_item_id,          -- item sequence number within the order (1, 2, 3...)
    product_id,             -- FK to products
    seller_id,              -- FK to sellers
    shipping_limit_date,    -- deadline for the seller to ship
    price,                  -- item price in BRL (key measure)
    freight_value           -- shipping cost in BRL (key measure)
from {{ source('olist_raw', 'order_items') }}