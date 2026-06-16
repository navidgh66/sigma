---
domain: data-engineering
description: dbt model layering (staging/intermediate/marts), tests, and incremental materializations.
---

# dbt Models

## Layering convention
```
models/
  staging/      # 1:1 with source, light renames/casts, materialized=view
    stg_stripe__payments.sql
  intermediate/ # reusable joins/reshapes, not exposed to BI; int_ prefix
  marts/        # business-facing, materialized=table/incremental; fct_/dim_ prefix
    fct_orders.sql
    dim_customers.sql
```
Rules: only staging reads `source()`. Everything downstream uses `ref()`. Never `ref()` upward
(marts must not feed staging). One source table -> one staging model.

## Staging model
```sql
with source as (select * from {{ source('stripe', 'payments') }}),
renamed as (
    select
        id            as payment_id,
        order_id,
        amount / 100  as amount_usd,
        created::date as payment_date
    from source
)
select * from renamed
```

## Tests (schema.yml)
```yaml
models:
  - name: fct_orders
    columns:
      - name: order_id
        tests: [unique, not_null]
      - name: customer_id
        tests:
          - relationships:
              to: ref('dim_customers')
              field: customer_id
      - name: status
        tests:
          - accepted_values: {values: ['placed','shipped','returned']}
```
Add `dbt_utils`/`dbt_expectations` for freshness, row counts, accepted ranges. Put a
`unique` + `not_null` on every grain key — it's your contract.

## Incremental models
```sql
{{ config(materialized='incremental', unique_key='order_id',
          incremental_strategy='merge', on_schema_change='append_new_columns') }}
select * from {{ ref('stg_orders') }}
{% if is_incremental() %}
  -- only process new/changed rows; lookback window avoids late-arriving gaps
  where updated_at > (select dateadd(day,-3, max(updated_at)) from {{ this }})
{% endif %}
```
- `unique_key` + `merge` strategy makes reruns idempotent (no duplicates).
- Add a lookback window to capture late-arriving/updated rows.
- `--full-refresh` rebuilds from scratch when logic changes.

## Pitfalls
- Incremental without `unique_key` -> duplicate rows on rerun.
- No lookback -> late events silently dropped.
- Business logic in staging -> unmaintainable; keep staging thin.
- `source()` used outside staging -> breaks lineage discipline.
- Missing tests on grain keys -> silent fan-out from bad joins.
- Forgetting `on_schema_change` -> incremental breaks when columns added.

## Checklist
- [ ] staging->intermediate->marts layering respected
- [ ] grain keys have unique + not_null tests
- [ ] relationships tests on foreign keys
- [ ] incremental models have unique_key + lookback
- [ ] sources have freshness checks
