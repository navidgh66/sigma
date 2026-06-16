---
domain: data-engineering
description: Airflow DAG design — dependencies, sensors, idempotent tasks, and running dbt via Cosmos.
---

# Airflow DAGs

## DAG skeleton (TaskFlow API)
```python
from airflow.decorators import dag, task
from pendulum import datetime

@dag(
    schedule="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,                 # almost always False unless backfilling intentionally
    max_active_runs=1,             # prevent overlapping runs on the same data
    default_args={"retries": 2, "retry_delay": 300, "owner": "data-eng"},
    tags=["sales", "daily"],
)
def sales_pipeline():
    @task
    def extract(**ctx):
        ds = ctx["ds"]             # logical date — partition on THIS, not datetime.now()
        return load_partition(ds)

    @task
    def transform(raw): ...

    transform(extract())

sales_pipeline()
```

## Idempotency (the core principle)
- Partition all reads/writes by the **logical date** (`{{ ds }}`/`data_interval_start`),
  never `datetime.now()`. A rerun of 2024-03-01 must reprocess exactly that partition.
- Writes should be overwrite/MERGE on the partition, not blind append.
- A task rerun must produce the same result — no side effects that accumulate.

## Dependencies
```python
extract_t >> [transform_a, transform_b] >> load_t   # fan-out / fan-in
```
- Keep tasks atomic and retryable. One logical step per task.
- Use XCom for small metadata only — never pass large datasets through XCom; write to storage.

## Sensors (wait for upstream)
```python
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor
wait = S3KeySensor(
    task_id="wait_for_file", bucket_key="raw/{{ ds }}/data.parquet",
    mode="reschedule",          # frees the worker slot while waiting (vs poke)
    timeout=6*3600, poke_interval=300,
)
```
Always `mode="reschedule"` for long waits, or sensors hog worker slots (sensor deadlock).
Prefer event-driven (Datasets / deferrable sensors) over polling where possible.

## dbt via Cosmos
```python
from cosmos import DbtTaskGroup, ProjectConfig, ProfileConfig
dbt_tg = DbtTaskGroup(
    project_config=ProjectConfig("/opt/dbt/my_project"),
    profile_config=ProfileConfig(...),
)
extract_t >> dbt_tg            # Cosmos renders each dbt model as its own Airflow task
```
Cosmos gives per-model retries, granular lineage, and selective reruns — better than a single
`BashOperator` running `dbt run`.

## Pitfalls
- `catchup=True` by accident -> floods scheduler with historical runs.
- Using `datetime.now()` -> non-idempotent, unbackfillable.
- `mode="poke"` sensors -> worker starvation.
- Heavy compute inside the scheduler/parsing path -> slow DAG parsing; keep top-level light.
- Append writes -> duplicates on retry.

## Checklist
- [ ] catchup set intentionally; max_active_runs guards overlap
- [ ] tasks partition on logical date, idempotent
- [ ] retries configured; XCom carries only metadata
- [ ] long sensors use reschedule/deferrable
- [ ] dbt run via Cosmos for granular tasks
