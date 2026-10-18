-- Dimension: products
-- Grain: one row per product_id.
-- Fills missing English category names so every product has a usable category.

select
    product_id,
    coalesce(product_category, product_category_name, 'unknown') as product_category,
    product_category_name as product_category_pt,
    product_photos_qty,
    product_weight_g,
    product_length_cm,
    product_height_cm,
    product_width_cm,
    product_length_cm * product_height_cm * product_width_cm as product_volume_cm3
from {{ ref('stg_products') }}