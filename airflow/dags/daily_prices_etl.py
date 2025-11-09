from __future__ import annotations

import csv
import datetime as dt
import os
import random

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from airflow import DAG
from airflow.operators.python import PythonOperator

DATA_DIR = "/opt/airflow/dags/data"
os.makedirs(DATA_DIR, exist_ok=True)
RAW_CSV = os.path.join(DATA_DIR, "prices_raw.csv")

# --- Config ---
PG_HOST = os.getenv("PG_HOST", "db")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_DB = os.getenv("PG_DB", "tcsdb")
PG_USER = os.getenv("PG_USER", "tcs")
PG_PASS = os.getenv("PG_PASS", "tcs")
# PG_HOST = "db" PG_DB = "tcsdb" PG_USER = "tcs" PG_PASS = "tcs" PG_PORT = 5432

# Días de retención (por defecto 30). Podés cambiarlo por Variable de Airflow si querés.
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "30"))
# Si querés “ensayo”: no borra, solo cuenta y loguea.
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in {"1", "true", "yes"}

default_args = {
    "owner": "airflow",
    "retries": 0,
}


def cleanup_item_prices(**_):
    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASS
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Índices recomendados (por si aún no existen)
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_item_prices_run_ts
        ON item_prices(run_ts);
        """
    )

    # Contar cuántos se borrarían
    cur.execute(
        """
        SELECT COUNT(*)
        FROM item_prices
        WHERE run_ts < NOW() - make_interval(days => %s)
        """,
        (RETENTION_DAYS,),
    )
    (to_delete,) = cur.fetchone()
    print(
        f"[cleanup_item_prices] retention_days={RETENTION_DAYS} "
        f"candidates={to_delete} dry_run={DRY_RUN}"
    )

    if not DRY_RUN and to_delete:
        cur.execute(
            """
            DELETE FROM item_prices
            WHERE run_ts < NOW() - make_interval(days => %s)
            """,
            (RETENTION_DAYS,),
        )
        print(f"[cleanup_item_prices] deleted={to_delete}")

    cur.close()
    conn.close()


with DAG(
    dag_id="cleanup_item_prices",
    description="Borra históricos antiguos de item_prices",
    start_date=dt.datetime(2025, 11, 8),
    schedule="0 3 * * *",  # todos los días 03:00
    catchup=False,
    default_args=default_args,
    tags=["housekeeping", "retention"],
) as dag:
    t_cleanup = PythonOperator(
        task_id="cleanup_item_prices_task",
        python_callable=cleanup_item_prices,
    )

    t_cleanup


def generate_dummy_csv(**_):
    rows = []
    for i in range(5):
        rows.append(
            {
                "name": f"product_{i}",
                "price": round(random.uniform(10, 5000), 2),
            }
        )
    with open(RAW_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "price"])
        writer.writeheader()
        writer.writerows(rows)


def transform_with_pandas(**_):
    df = pd.read_csv(RAW_CSV)
    df["name"] = df["name"].str.lower().str.strip()
    df["price"] = df["price"].round(2)
    # Reglas simples:
    df = df.dropna(subset=["name", "price"])
    df = df[df["price"].between(0.01, 1_000_000)]
    df.to_csv(RAW_CSV, index=False)


def load_to_postgres(**_):
    import csv

    conn = psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=PG_USER,
        password=PG_PASS,
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Leer todo el CSV una sola vez
    with open(RAW_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # -------- UPSERT batch en items --------
    upsert_sql = """
        INSERT INTO items (name, price)
        VALUES %s
        ON CONFLICT (name) DO UPDATE
            SET price = EXCLUDED.price
    """
    upsert_values = [(r["name"], r["price"]) for r in rows]
    execute_values(cur, upsert_sql, upsert_values)

    # -------- Historial (append-only) --------
    # Usamos template para incluir NOW() sin armar tuplas de timestamps en Python
    hist_sql = "INSERT INTO item_prices (item_name, price, run_ts) VALUES %s"
    hist_values = [(r["name"], r["price"]) for r in rows]
    execute_values(cur, hist_sql, hist_values, template="(%s, %s, NOW())")

    cur.close()
    conn.close()


default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": dt.timedelta(seconds=30),
}

with DAG(
    dag_id="daily_prices_etl",
    description="Demo ETL: genera CSV, transforma con pandas y carga en Postgres",
    start_date=dt.datetime(2025, 11, 7),
    schedule="@daily",
    catchup=False,
    default_args=default_args,
    tags=["demo", "etl"],
) as dag:
    t_generate = PythonOperator(
        task_id="generate_dummy_csv",
        python_callable=generate_dummy_csv,
    )
    t_transform = PythonOperator(
        task_id="transform_with_pandas",
        python_callable=transform_with_pandas,
    )
    t_load = PythonOperator(
        task_id="load_to_postgres",
        python_callable=load_to_postgres,
    )

    t_generate >> t_transform >> t_load
