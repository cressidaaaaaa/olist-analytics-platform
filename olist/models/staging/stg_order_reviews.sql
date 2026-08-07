-- Staging model for order reviews
-- Grain: one row per review (review_id)
-- Note: comment text (Portuguese) is preserved for potential AI/sentiment analysis later.

select
    review_id,                          -- review id (primary key)
    order_id,                           -- FK to orders
    review_score,                       -- rating from 1 to 5 (key measure)
    review_comment_title,               -- review title (Portuguese, often empty)
    review_comment_message,             -- review body (Portuguese, kept for future analysis)
    review_creation_date,               -- when the review was created
    review_answer_timestamp             -- when the review was answered
from {{ source('olist_raw', 'order_reviews') }}