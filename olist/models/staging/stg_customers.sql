-- Staging model for customers
-- Purpose: clean the raw customers table, one-to-one with the source
-- Note: customer_id is order-level (one per order).
--       customer_unique_id is the true person-level identifier.

select
    customer_id,                          -- order-level customer id (FK from orders)
    customer_unique_id,                   -- true person-level id (same person across orders)
    customer_zip_code_prefix,             -- kept as string to preserve leading zeros
    lower(customer_city) as customer_city, -- normalize city to lowercase
    customer_state                        -- state abbreviation (e.g. SP)
from {{ source('olist_raw', 'customers') }}