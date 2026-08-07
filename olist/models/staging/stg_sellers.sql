-- Staging model for sellers
-- Purpose: clean the raw sellers table, one-to-one with the source

select
    seller_id,                          -- seller id (primary key)
    seller_zip_code_prefix,             -- kept as string to preserve leading zeros
    lower(seller_city) as seller_city,  -- normalize city to lowercase
    seller_state                        -- state abbreviation (e.g. SP)
from {{ source('olist_raw', 'sellers') }}