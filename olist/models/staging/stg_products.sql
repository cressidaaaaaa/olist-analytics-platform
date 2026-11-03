-- Staging model for products
-- Purpose: clean the raw products table, one-to-one with the source.
-- The English category name is attached later in dim_product.

select
    product_id,                                                  -- product id (primary key)
    product_category_name,                                       -- category name (Portuguese)
    product_name_lenght as product_name_length,                  -- fix source typo: lenght -> length
    product_description_lenght as product_description_length,   -- fix source typo
    product_photos_qty,                                          -- number of photos
    product_weight_g,                                            -- weight in grams
    product_length_cm,                                           -- dimensions in cm
    product_height_cm,
    product_width_cm
from {{ source('olist_raw', 'products') }}