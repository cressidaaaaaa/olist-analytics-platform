-- Dimension: sellers
-- Grain: one row per seller_id.

select
    seller_id,
    seller_zip_code_prefix,
    seller_city,
    seller_state
from {{ ref('stg_sellers') }}
