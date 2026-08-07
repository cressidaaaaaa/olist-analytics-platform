-- Staging model for the product category translation lookup
-- Purpose: map Portuguese category names to English

select
    product_category_name,                          -- category name in Portuguese
    product_category_name_english as product_category  -- category name in English (renamed)
from {{ source('olist_raw', 'category_translation') }}