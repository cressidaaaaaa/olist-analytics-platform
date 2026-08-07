-- Staging model for products
-- Purpose: clean the raw products table and attach the ENGLISH category name.
-- Design note: we LEFT JOIN the category translation lookup here (in staging)
--   as a pragmatic choice. It's a 1:1 lookup (no fan-out risk) that makes the
--   Portuguese category readable. LEFT JOIN keeps all products even if a
--   translation is missing.

select
    p.product_id,                                   -- product id (primary key)
    p.product_category_name,                        -- original category name (Portuguese)
    t.product_category_name_english as product_category,  -- translated category (English)
    p.product_name_lenght as product_name_length,   -- fix source typo: lenght -> length
    p.product_description_lenght as product_description_length,  -- fix source typo
    p.product_photos_qty,                           -- number of photos
    p.product_weight_g,                             -- weight in grams
    p.product_length_cm,                            -- dimensions in cm
    p.product_height_cm,
    p.product_width_cm
from {{ source('olist_raw', 'products') }} as p
left join {{ source('olist_raw', 'category_translation') }} as t
    on p.product_category_name = t.product_category_name