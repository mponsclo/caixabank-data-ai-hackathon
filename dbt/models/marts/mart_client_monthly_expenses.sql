-- Monthly expense aggregation per client, used for Task 4 (expense forecasting)
select
    client_id,
    date_trunc('month', transaction_date)::date as expense_month,
    sum(case when amount < 0 then abs(amount) else 0 end) as total_expenses,
    count(case when amount < 0 then 1 end) as num_expense_transactions,
    avg(case when amount < 0 then abs(amount) end) as avg_expense_amount,
    max(case when amount < 0 then abs(amount) end) as max_expense_amount,
    sum(case when amount > 0 then amount else 0 end) as total_earnings,
    count(case when amount > 0 then 1 end) as num_earning_transactions,
    count(*) as total_transactions
from {{ ref('int_transactions_enriched') }}
group by client_id, date_trunc('month', transaction_date)::date
order by client_id, expense_month
