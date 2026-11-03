-- Dimension: products
-- Grain: one row per product_id.
-- Attaches the English category name from the translation lookup and fills
-- missing values so every product has a usable category.

with products as (
    select * from {{ ref('stg_products') }}
),

translations as (
    select
        product_category_name,
        product_category
    from {{ ref('stg_category_translation') }}
)

select
    p.product_id,
    coalesce(t.product_category, p.product_category_name, 'unknown') as product_category,
    p.product_category_name as product_category_pt,
    p.product_photos_qty,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm,
    p.product_length_cm * p.product_height_cm * p.product_width_cm as product_volume_cm3
from products as p
left join translations as t
    on p.product_category_name = t.product_category_name