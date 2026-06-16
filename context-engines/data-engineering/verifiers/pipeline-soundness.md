---
domain: data-engineering
description: PASS/WARN/FAIL verifier for pipeline idempotency, schema contracts, and data freshness.
---

# Verifier: Pipeline Soundness

## FAIL (block — pipeline is unsafe to run/rerun)
- **F1 non-idempotent**: writes use blind `append`/`INSERT` so a rerun duplicates rows; or
  partitions on `now()`/wall-clock instead of the logical/event date.
- **F2 no unique key on upsert**: incremental/MERGE target without a `unique_key`/merge key.
- **F3 no schema contract**: downstream consumes columns with no enforced schema/types; an upstream
  rename silently breaks or nulls the field.
- **F4 unbounded reprocessing**: full-table scan each run where incremental partitioning is required
  (cost + runtime blowup), OR incremental with no late-arrival lookback (silent data loss).
- **F5 no failure handling**: tasks have no retries and a partial failure leaves the table in a
  half-written state with no transaction/atomic swap.
- **F6 freshness unchecked**: no source freshness or SLA check; stale upstream is consumed as if current.

## WARN (justify or fix)
- **W1**: `catchup=True` / backfill not bounded.
- **W2**: large payloads passed through XCom/driver instead of object storage.
- **W3**: no row-count / not-null / accepted-values tests on output grain.
- **W4**: no data-quality gate before publishing to marts/BI.
- **W5**: poke-mode sensors or polling where event-driven would do.
- **W6**: many tiny output files (downstream read amplification).
- **W7**: timezone-naive timestamps mixing UTC and local.

## PASS
- Reads/writes partitioned by logical/event date; reruns overwrite or MERGE -> idempotent.
- Incremental models have a `unique_key` and a late-arrival lookback window.
- Schema contract enforced (dbt tests / Great Expectations / explicit schema-on-read).
- Source freshness + row-count + null tests run; publish gated on them passing.
- Tasks retried; output written atomically (staging table -> atomic swap, or transaction).

## Quick checks
```sql
-- idempotency smoke: rerun a partition, count must not change
select count(*) from fct_orders where order_date = '2024-03-01';  -- before & after rerun
-- duplicate grain key (should be 0)
select order_id, count(*) c from fct_orders group by 1 having c > 1;
-- freshness
select max(loaded_at) >= dateadd(hour,-26, current_timestamp) as is_fresh from src;
```

## Verdict format
```
PIPELINE SOUNDNESS: FAIL
- F1: load task appends with INSERT, partitions on now() -> dup rows on retry
- F6: no freshness check on stripe source
Switch to MERGE on order_id partitioned by order_date; add dbt source freshness.
```
