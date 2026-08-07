-- Staging model for order payments
-- Grain: one row per payment within an order (order_id + payment_sequential)
-- Note: one order can be split across multiple payments.

select
    order_id,               -- FK to orders (repeats: one order can have many payments)
    payment_sequential,     -- payment sequence number within the order
    payment_type,           -- payment method: credit_card / boleto / voucher / debit_card
    payment_installments,   -- number of installments (e.g. 3 = paid in 3 parts)
    payment_value           -- payment amount in BRL (key measure)
from {{ source('olist_raw', 'order_payments') }}