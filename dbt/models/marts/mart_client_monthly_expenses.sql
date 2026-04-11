-- Monthly expense aggregation per client, used for Task 4 (expense forecasting)
SELECT
    client_id
    , DATE_TRUNC(transaction_date, MONTH) AS expense_month
    , SUM(IF(amount < 0, ABS(amount), 0)) AS total_expenses
    , COUNTIF(amount < 0) AS num_expense_transactions
    , AVG(IF(amount < 0, ABS(amount), NULL)) AS avg_expense_amount
    , MAX(IF(amount < 0, ABS(amount), NULL)) AS max_expense_amount
    , SUM(IF(amount > 0, amount, 0)) AS total_earnings
    , COUNTIF(amount > 0) AS num_earning_transactions
    , COUNT(*) AS total_transactions
FROM {{ ref('int_transactions_enriched') }}
GROUP BY ALL
